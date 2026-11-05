"""biz-trade.de – Marktplatz für Unternehmen (DE/AT/CH), Standort bis auf Landkreis genau.

Suche per POST (Formular auf marktplatz.htm), max. ~40 Treffer je Suchbegriff.
"Suche ..."-Inserate (Kaufgesuche) werden verworfen.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterator
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..models import Listing
from ..parsing import clean_ws, parse_amount_range
from .base import Region, Source

log = logging.getLogger(__name__)

BASE = "https://www.biz-trade.de/"
SEARCH_URL = BASE + "marktplatz.htm"


def parse_search_page(html: str) -> list[Listing]:
    soup = BeautifulSoup(html, "html.parser")
    out: list[Listing] = []
    for card in soup.select("div.adsxs"):
        a = card.find("a", href=re.compile(r"^ma-\d+\.htm$"))
        if not a:
            continue
        ad_id = re.search(r"ma-(\d+)", a["href"]).group(1)
        first = card.find("p")
        kind = clean_ws(first.get_text(" ")) if first else None  # "Biete" / "Suche"
        cat_el = card.find("span", style=re.compile("font-weight:bold"))
        category = clean_ws(cat_el.get_text(" ")) if cat_el else None
        caption = card.select_one(".descr-caption")
        teaser, state = None, None
        if caption:
            parts = caption.get_text("\n").split("-----")
            teaser = clean_ws(parts[0])
            state = clean_ws(parts[1]) if len(parts) > 1 else None
        industry_el = card.find("span", style=re.compile("font-size: 0.9rem"))
        emp_el = card.select_one("i.fa-users")
        employees = clean_ws(emp_el.find_next("i").get_text(" ")) if emp_el and emp_el.find_next("i") else None
        flag = card.find("img", src=re.compile(r"^flags/"))
        county = clean_ws(flag.next_sibling) if flag and isinstance(flag.next_sibling, str) else None
        country = re.search(r"flags/(\w+)\.png", flag["src"]).group(1) if flag else None
        location = " / ".join(x for x in (state, county) if x) or None
        lst = Listing(
            source="biz-trade",
            source_id=ad_id,
            url=urljoin(BASE, a["href"]),
            title=clean_ws(a.get("title") or a.get_text(" ")) or "",
            teaser=teaser,
            industry=clean_ws(industry_el.get_text(" ")) if industry_el else None,
            location=location,
            employees=employees,
        )
        lst.extra.update({"typ": kind, "kategorie": category, "land": country})
        out.append(lst)
    return out


def is_offer(listing: Listing) -> bool:
    return (listing.extra.get("typ") or "").lower().startswith("biete") and listing.extra.get("land") in (None, "de")


def parse_detail_page(html: str, listing: Listing) -> Listing:
    soup = BeautifulSoup(html, "html.parser")
    facts: dict[str, str] = {}
    for row in soup.select("div.sectiondetail1, div.sectiondetail2"):
        label = row.select_one(".sectionlabel")
        value = label.find_next_sibling("div") if label else None
        if label and value:
            facts[clean_ws(label.get_text(" ")).lower()] = clean_ws(value.get_text(" ")) or ""
    desc = soup.find(itemprop="description")
    if desc:
        listing.description = clean_ws(desc.get_text("\n"))
    for key, val in facts.items():
        if key.startswith("preisvorstellung"):
            listing.price = f"{val} €" if val and re.search(r"\d", val) and "€" not in val else val
        elif key == "umsatzklasse":
            listing.revenue = val
        elif key == "personal":
            listing.employees = val
        elif key == "branche":
            listing.industry = val
        elif key.startswith("bundesland"):
            listing.location = val.replace(" > ", " / ")
        elif key == "region":
            m = re.match(r"(\d{1,2})\s*/", val)
            if m:
                listing.extra["plz_bereich"] = m.group(1)
        elif key == "umgebung":
            listing.extra["umgebung"] = val
    listing.revenue_min, listing.revenue_max = parse_amount_range(listing.revenue)
    listing.price_min, listing.price_max = parse_amount_range(listing.price)
    return listing


class BizTrade(Source):
    name = "biz-trade"

    def search(self, query: str | None, region: Region) -> Iterator[Listing]:
        if not query:
            return
        html = self.http.post(SEARCH_URL, data={"skey": query, "func": "searchres", "option": "marketplace"})
        listings = parse_search_page(html)
        offers = [l for l in listings if is_offer(l)]
        log.info("biz-trade %r: %d Treffer, %d Verkaufsangebote", query, len(listings), len(offers))
        yield from offers

    def fetch_details(self, listing: Listing) -> Listing:
        return parse_detail_page(self.http.get(listing.url), listing)
