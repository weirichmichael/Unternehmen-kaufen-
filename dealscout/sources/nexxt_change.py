"""nexxt-change.org – die bundesweite Nachfolgebörse von KfW/BMWK/IHK/HWK.

Größte und kostenlose Börse; viele kleine Betriebe (Handwerk, Dienstleistung).
Unterstützt Suche nach PLZ + Umkreis (max. 100 km).
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterator
from urllib.parse import parse_qs, urljoin, urlparse

from bs4 import BeautifulSoup

from ..models import Listing
from ..parsing import clean_ws, parse_amount_range, parse_german_date
from .base import Region, Source

log = logging.getLogger(__name__)

BASE = "https://www.nexxt-change.org"
SEARCH_URL = BASE + "/SiteGlobals/Forms/Verkaufsangebot_Suche/Verkaufsangebotssuche_Formular"


def parse_search_page(html: str) -> tuple[list[Listing], str | None]:
    """Parst eine Trefferseite. Gibt (Inserate, URL der nächsten Seite) zurück."""
    soup = BeautifulSoup(html, "html.parser")
    listings: list[Listing] = []
    for item in soup.select("li.inserat-list-item"):
        a = item.select_one("h3.card-title a[href]")
        if not a:
            continue
        url = urljoin(BASE, a["href"])
        ad_id = parse_qs(urlparse(url).query).get("adId", [""])[0]
        if not ad_id:
            continue
        date_el = item.select_one("span.date")
        secondary = [clean_ws(p.get_text(" ")) for p in item.select("p.card-topline--secondary")]
        industry = secondary[0] if len(secondary) > 0 else None
        location = secondary[1] if len(secondary) > 1 else None
        if location:
            location = re.sub(r"\s*/\s*", " / ", location)
        teaser_el = item.select_one("p.inserat-teaser")
        listings.append(
            Listing(
                source="nexxt-change",
                source_id=ad_id,
                url=url,
                title=clean_ws(a.get_text(" ")) or "",
                date=parse_german_date(date_el.get_text()) if date_el else None,
                industry=industry,
                location=location,
                teaser=clean_ws(teaser_el.get_text(" ")) if teaser_el else None,
            )
        )

    next_url = _find_next_page(soup)
    return listings, next_url


def _find_next_page(soup: BeautifulSoup) -> str | None:
    # Paginierungslinks enthalten "..._list%253D<seitennummer>"
    current = 1
    cur_el = soup.select_one(".pagination .active, .pagination [aria-current]")
    if cur_el:
        m = re.search(r"\d+", cur_el.get_text())
        if m:
            current = int(m.group())
    candidates: dict[int, str] = {}
    for a in soup.select("a[href*='_list%253D']"):
        m = re.search(r"_list%253D(\d+)(?:&|$)", a["href"])
        if m:
            candidates[int(m.group(1))] = urljoin(BASE, a["href"])
    return candidates.get(current + 1)


def parse_detail_page(html: str, listing: Listing) -> Listing:
    soup = BeautifulSoup(html, "html.parser")

    facts: dict[str, str] = {}
    for dl in soup.select("dl"):
        for dt in dl.find_all("dt"):
            dd = dt.find_next_sibling("dd")
            if not dd:
                continue
            label = clean_ws(dt.get_text(" ")).rstrip(":").strip().lower()
            items = [clean_ws(li.get_text(" ")) for li in dd.find_all("li")]
            value = "; ".join(i for i in items if i) if items else clean_ws(dd.get_text(" "))
            if label and value:
                facts.setdefault(label, value)

    # Beschreibung: Absatz(e) nach der Überschrift "Beschreibung"
    desc = None
    for h in soup.find_all(["h2", "h3"]):
        if clean_ws(h.get_text()) == "Beschreibung":
            parts = []
            for sib in h.find_next_siblings():
                if sib.name in ("h2", "h3") or "details-unternehmen" in (sib.get("class") or []):
                    break
                parts.append(sib.get_text("\n"))
            desc = clean_ws("\n".join(parts))
            break

    if desc:
        listing.description = desc
    if facts.get("standort"):
        listing.location = facts["standort"].replace(" > ", " / ")
    if facts.get("branche"):
        listing.industry = facts["branche"]
    listing.employees = facts.get("anzahl mitarbeiter") or listing.employees
    listing.revenue = facts.get("letzter jahresumsatz") or listing.revenue
    listing.price = facts.get("preisvorstellung") or listing.price
    listing.revenue_min, listing.revenue_max = parse_amount_range(listing.revenue)
    listing.price_min, listing.price_max = parse_amount_range(listing.price)

    # Expliziter Kaufpreis im Fließtext ("Kaufpreis: 2.800.000 € VHB") ist genauer als die Spanne
    if desc:
        m = re.search(r"Kaufpreis[^:\n]{0,20}:\s*([^\n]{1,40})", desc)
        if m:
            lo, hi = parse_amount_range(m.group(1))
            if lo and (lo == hi):
                listing.extra["kaufpreis_text"] = m.group(1).strip()
                listing.price_min = listing.price_max = lo

    if facts.get("chiffre"):
        listing.extra["chiffre"] = facts["chiffre"]
    if facts.get("inseratstyp"):
        listing.extra["inseratstyp"] = facts["inseratstyp"]
    # Betreuender Regionalpartner (IHK, Handwerkskammer, Sparkasse …)
    for box in soup.select("section.inserate-info-box"):
        head = box.select_one(".box-headline")
        if head and "Regionalpartner" in head.get_text():
            p = box.select_one(".box-wrapper > p")
            if p and clean_ws(p.get_text(" ")):
                listing.extra["regionalpartner"] = clean_ws(p.get_text(" "))
            break
    expose = soup.select_one("a[href*='expose.pdf']")
    if expose:
        listing.extra["expose_pdf"] = urljoin(BASE, expose["href"])
    return listing


class NexxtChange(Source):
    name = "nexxt-change"

    def supports_radius(self) -> bool:
        return True

    def supports_browse_all(self) -> bool:
        return True

    def search(self, query: str | None, region: Region) -> Iterator[Listing]:
        params = {"suchbegriff": query or ""}
        if region.plz:
            params["ad_zip"] = region.plz
            params["ad_radius"] = str(min(max(region.radius_km, 0), 100))
        url: str | None = SEARCH_URL
        page = 0
        while url and page < self.max_pages:
            html = self.http.get(url, params=params if page == 0 else None)
            listings, url = parse_search_page(html)
            page += 1
            log.info("nexxt-change %r Seite %d: %d Treffer", query, page, len(listings))
            yield from listings
            if not listings:
                break

    def fetch_details(self, listing: Listing) -> Listing:
        return parse_detail_page(self.http.get(listing.url), listing)
