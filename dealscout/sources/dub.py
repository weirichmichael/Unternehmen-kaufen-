"""DUB.de – Deutsche Unternehmerbörse.

Standort nur auf Bundesland-Ebene -> Regionsfilter über `bundeslaender`.
Hinweis: robots.txt sperrt /app/ und /api/ – wir nutzen ausschließlich die
öffentliche Suchseite /de/unternehmen-kaufen/ und die Exposé-Seiten.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from ..models import Listing
from ..parsing import clean_ws, parse_amount, parse_amount_range
from .base import Region, Source

log = logging.getLogger(__name__)

BASE = "https://www.dub.de"
SEARCH_URL = BASE + "/de/unternehmen-kaufen/"

_NA = {"keine angabe", "k.a.", "-", ""}


def _val(text: str | None) -> str | None:
    t = clean_ws(text)
    return None if t is None or t.lower() in _NA else t


def _slug(url: str) -> str:
    path = urlparse(url).path.rstrip("/")
    return path.rsplit("/", 1)[-1]


def parse_search_page(html: str) -> list[Listing]:
    soup = BeautifulSoup(html, "html.parser")
    out: list[Listing] = []
    for row in soup.select("tr[data-listing-card]"):
        cells = row.find_all("td")
        if len(cells) < 5:
            continue
        a = cells[0].find("a", href=True)
        if not a:
            continue
        url = urljoin(BASE, a["href"].split("?")[0])
        revenue = _val(cells[1].get_text(" "))
        earnings = _val(cells[2].get_text(" "))
        lst = Listing(
            source="dub",
            source_id=row.get("data-listing-id") or _slug(url),
            url=url,
            title=clean_ws(a.get("title") or a.get_text(" ")) or "",
            revenue=revenue,
            earnings=earnings,
            employees=_val(cells[3].get_text(" ")),
            location=_val(cells[4].get_text(" ")),
        )
        lst.revenue_min, lst.revenue_max = parse_amount_range(revenue)
        lst.earnings_value = parse_amount(earnings)
        out.append(lst)
    return out


def parse_detail_page(html: str, listing: Listing) -> Listing:
    soup = BeautifulSoup(html, "html.parser")
    kpis: dict[str, str] = {}
    for cell in soup.select("[data-testid='metric-cell']"):
        label = cell.select_one(".dub-kpi-label")
        value = cell.select_one(".dub-kpi-value")
        if label and value:
            kpis.setdefault(clean_ws(label.get_text()).lower(), _val(value.get_text(" ")) or "")

    desc_el = soup.select_one("[data-testid='company-description'] .ld-card__body")
    if desc_el:
        listing.description = clean_ws(desc_el.get_text("\n"))

    badges = soup.select(".dub-hero__pill--ref")
    if badges:
        listing.industry = clean_ws(badges[0].get_text())

    if kpis.get("standort"):
        listing.location = kpis["standort"]
    for key, attr in (("umsatz", "revenue"), ("ergebnis", "earnings"), ("mitarbeiter", "employees")):
        if kpis.get(key):
            setattr(listing, attr, kpis[key])
    for key in ("kaufpreis", "preis", "preisvorstellung"):
        if kpis.get(key):
            listing.price = kpis[key]
            break
    listing.revenue_min, listing.revenue_max = parse_amount_range(listing.revenue)
    listing.earnings_value = parse_amount(listing.earnings)
    listing.price_min, listing.price_max = parse_amount_range(listing.price)
    for key in ("transaktionshintergrund", "anteile zum verkauf"):
        if kpis.get(key):
            listing.extra[key] = kpis[key]
    return listing


class Dub(Source):
    name = "dub"

    def search(self, query: str | None, region: Region) -> Iterator[Listing]:
        if not query:
            # Ohne Suchbegriff wären das >2000 Inserate bundesweit – zu viel Last.
            return
        seen: set[str] = set()
        for page in range(1, self.max_pages + 1):
            params = {"q": query, "view": "list"}
            if page > 1:
                params["page"] = str(page)
            listings = parse_search_page(self.http.get(SEARCH_URL, params=params))
            new = [l for l in listings if l.source_id not in seen]
            log.info("dub %r Seite %d: %d Treffer", query, page, len(new))
            if not new:
                break
            seen.update(l.source_id for l in new)
            yield from new

    def fetch_details(self, listing: Listing) -> Listing:
        return parse_detail_page(self.http.get(listing.url), listing)
