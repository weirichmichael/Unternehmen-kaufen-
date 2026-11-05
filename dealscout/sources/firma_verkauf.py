"""firma-verkauf.de – private Unternehmensbörse (viele Kleinbetriebe aus Handel & Dienstleistung).

Standort nur Bundesland. Die Suche liefert zuerst die Treffer, danach "Füllmaterial" –
wir hören auf zu blättern, sobald eine Seite keinen Treffer mehr enthält.
Gesuche ("Suche Hausverwaltung") werden verworfen.
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

BASE = "https://www.firma-verkauf.de"
SEARCH_URL = BASE + "/adv/searching"

# Kategorien, die einen Kauf ermöglichen (nicht: Kooperation, Finanzierung, Vermietung …)
SALE_CATEGORIES = {"unternehmensverkauf", "unternehmensnachfolge", "unternehmensbeteiligung"}


def parse_search_page(html: str) -> list[Listing]:
    soup = BeautifulSoup(html, "html.parser")
    out: list[Listing] = []
    for box in soup.select("article.box"):
        a = box.find("a", href=re.compile(r"^/adv/\d+"))
        if not a:
            continue
        spans = [clean_ws(s.get_text(" ")) for s in box.select("header > span")]
        ad_type = spans[0] if spans else None
        region = None
        if len(spans) > 1 and spans[1]:
            region = re.sub(r"^PLZ:\s*", "", spans[1]).strip() or None
        foot = [clean_ws(p.get_text(" ")) for p in box.select("footer p")]
        category = foot[1] if len(foot) > 1 else None
        employees = None
        if foot:
            m = re.search(r"#\d+\s*(.*)$", foot[0] or "")
            employees = (m.group(1).strip() or None) if m else None
        title = box.select_one(".box-title")
        desc = box.select_one(".box-desc")
        lst = Listing(
            source="firma-verkauf",
            source_id=re.search(r"/adv/(\d+)", a["href"]).group(1),
            url=urljoin(BASE, a["href"]),
            title=clean_ws(title.get_text(" ")) if title else "",
            teaser=clean_ws(desc.get_text(" ")) if desc else None,
            location=None if region in (None, "online") else region,
            employees=employees,
            industry=category,
        )
        lst.extra["typ"] = ad_type
        lst.extra["kategorie"] = category
        out.append(lst)
    return out


def is_offer(listing: Listing) -> bool:
    typ = (listing.extra.get("typ") or "").lower()
    cat = (listing.extra.get("kategorie") or "").lower()
    return typ == "gebot" and (not cat or cat in SALE_CATEGORIES)


def parse_detail_page(html: str, listing: Listing) -> Listing:
    soup = BeautifulSoup(html, "html.parser")
    facts: dict[str, str] = {}
    for dt in soup.select(".vf-details-main dl dt"):
        dd = dt.find_next_sibling("dd")
        if dd:
            facts[clean_ws(dt.get_text()).lower()] = " ".join(dd.get_text(" ").split())
    if facts.get("branche"):
        listing.industry = facts["branche"]
    if facts.get("region"):
        region = re.sub(r"^(DE|AT|CH)\s*", "", facts["region"]).strip()
        listing.location = region or listing.location
    listing.employees = facts.get("mitarbeiter") or listing.employees
    if facts.get("jahresumsatz"):
        listing.revenue = facts["jahresumsatz"].replace("EURO", "€")
        listing.revenue_min, listing.revenue_max = parse_amount_range(listing.revenue)
    if facts.get("preisvorstellung"):
        listing.price = facts["preisvorstellung"].replace("EURO", "€")
        listing.price_min, listing.price_max = parse_amount_range(listing.price)
    if facts.get("preisgestaltung"):
        listing.extra["preisgestaltung"] = facts["preisgestaltung"]
    desc = soup.select_one(".vf-detailed-description")
    if desc:
        listing.description = clean_ws(desc.get_text("\n"))
    return listing


class FirmaVerkauf(Source):
    name = "firma-verkauf"

    def search(self, query: str | None, region: Region) -> Iterator[Listing]:
        if not query:
            return
        words = [w.lower() for w in re.findall(r"\w{4,}", query)]
        for page in range(1, self.max_pages + 1):
            params = {
                "title": query, "companyCategory": "", "industryCategory": "",
                "country": "DE", "zipCode": "", "pageNumber": str(page),
            }
            listings = parse_search_page(self.http.get(SEARCH_URL, params=params))
            hits = [l for l in listings if any(w in l.text().lower() for w in words)]
            offers = [l for l in hits if is_offer(l)]
            log.info("firma-verkauf %r Seite %d: %d Treffer, %d Verkaufsangebote", query, page, len(hits), len(offers))
            yield from offers
            if len(hits) < len(listings) or not listings:
                break  # ab hier nur noch Füllmaterial

    def fetch_details(self, listing: Listing) -> Listing:
        return parse_detail_page(self.http.get(listing.url), listing)
