"""Kleinanzeigen.de – private Verkäufe ("Hausmeisterservice abzugeben", "Nachfolger gesucht").

Sehr verrauscht: die meisten Treffer sind Dienstleistungsangebote oder Stellenanzeigen.
Darum werden nur Anzeigen mit erkennbarer Verkaufs-/Übergabeabsicht übernommen.
Umkreissuche nativ über PLZ -> interne Orts-ID.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterator
from urllib.parse import quote

from bs4 import BeautifulSoup

from ..models import Listing
from ..parsing import clean_ws, parse_amount_range, parse_german_date
from .base import Region, Source

log = logging.getLogger(__name__)

BASE = "https://www.kleinanzeigen.de"
RADII = (5, 10, 20, 30, 50, 100, 150, 200)
# Rubriken: 277 = Immobilien > Gewerbeimmobilien, 298 = Dienstleistungen > Weitere Dienstleistungen
DEFAULT_CATEGORIES = (277, 298)

# Formulierungen, die auf Verkauf/Übergabe eines Betriebs hindeuten
SALE_INTENT = re.compile(
    r"abzugeben|abgabe|zu verkaufen|verkaufe|zu übergeben|übergabe|nachfolge|nachfolger|"
    r"übernahme|übernehmen|firmenverkauf|unternehmensverkauf|geschäftsaufgabe|geschäftsauflösung|"
    r"kundenstamm|ablöse|ruhestand|aus altersgründen|gesellschaftsanteile|geschäftsanteile",
    re.I,
)
# ... aber keine Gesuche / Stellenanzeigen / reine Dienstleistungsangebote
NOT_A_SALE = re.compile(
    r"\b(suche|suchen|gesucht wird ein|kaufe|ankauf)\b.{0,40}\b(firma|unternehmen|betrieb|gmbh)\b|"
    r"\(m/w/d\)|\bm/w/d\b|minijob|teilzeit|vollzeit|aushilfe|ausbildung",
    re.I,
)


# Titel wie "Hotel gesucht", "Suche Firma", "Kaufe Betrieb" sind Gesuche – außer es geht um Nachfolge
WANTED_TITLE = re.compile(r"\b(suche|sucht|suchen|gesucht|kaufe|ankauf)\b", re.I)


def has_sale_intent(text: str, title: str = "") -> bool:
    if WANTED_TITLE.search(title) and not re.search(r"nachfolge|abzugeben|zu verkaufen", title, re.I):
        return False
    return bool(SALE_INTENT.search(text)) and not NOT_A_SALE.search(text)


def distance_km(listing: Listing) -> int | None:
    m = re.match(r"(\d+)", listing.extra.get("entfernung", ""))
    return int(m.group(1)) if m else None


def _slug(query: str) -> str:
    s = re.sub(r"[^\wäöüß]+", "-", query.lower()).strip("-")
    return quote(s)


def parse_search_page(html: str) -> list[Listing]:
    soup = BeautifulSoup(html, "html.parser")
    out: list[Listing] = []
    for art in soup.select("article[data-adid]"):
        ad_id = art["data-adid"]
        href = art.get("data-href") or ""
        meta: dict = {}
        ld = art.find("script", type="application/ld+json")
        if ld and ld.string:
            try:
                meta = json.loads(ld.string)
            except ValueError:
                meta = {}
        for tag in art.find_all(["script", "svg"]):
            tag.decompose()
        strings = list(art.stripped_strings)
        title = meta.get("title") or ""
        if not title:
            h = art.find(["h2", "h3"])
            title = h.get_text(" ", strip=True) if h else ""
        location = next((s for s in strings if re.match(r"^\d{5}\s", s)), None)
        dist = next((s for s in strings if re.match(r"^\(\d+\s*km\)$", s)), None)
        date = next((parse_german_date(s) for s in strings if re.match(r"^\d{2}\.\d{2}\.\d{4}$", s)), None)
        price_el = art.select_one("p.text-title3, .aditem-main--middle--price-shipping--price")
        price = clean_ws(price_el.get_text(" ")) if price_el else None
        lst = Listing(
            source="kleinanzeigen",
            source_id=ad_id,
            url=BASE + href if href.startswith("/") else href,
            title=clean_ws(title) or "",
            date=date,
            location=location,
            teaser=clean_ws(meta.get("description")),
            price=price,
        )
        if dist:
            lst.extra["entfernung"] = dist.strip("()")
        lst.price_min, lst.price_max = parse_amount_range(price)
        out.append(lst)
    return out


def parse_detail_page(html: str, listing: Listing) -> Listing:
    soup = BeautifulSoup(html, "html.parser")
    desc = soup.select_one("#viewad-description-text")
    if desc:
        listing.description = clean_ws(desc.get_text("\n"))
    loc = soup.select_one("#viewad-locality")
    if loc and clean_ws(loc.get_text(" ")):
        listing.location = clean_ws(loc.get_text(" "))
    price = soup.select_one("#viewad-price")
    if price and clean_ws(price.get_text(" ")):
        listing.price = clean_ws(price.get_text(" "))
        listing.price_min, listing.price_max = parse_amount_range(listing.price)
    crumbs = [clean_ws(a.get_text(" ")) for a in soup.select("#vap-brdcrmb a, .breadcrump-link")]
    crumbs = [c for c in crumbs if c and c.lower() != "kleinanzeigen"]
    if crumbs:
        listing.industry = " > ".join(dict.fromkeys(crumbs))
    return listing


class Kleinanzeigen(Source):
    name = "kleinanzeigen"

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._loc_cache: dict[str, str | None] = {}

    def supports_radius(self) -> bool:
        return True

    def _location_id(self, plz: str) -> str | None:
        if plz not in self._loc_cache:
            raw = self.http.get(BASE + "/s-ort-empfehlungen.json", params={"query": plz})
            data = json.loads(raw)
            ids = [k.lstrip("_") for k, v in data.items() if k != "_0" and str(v).startswith(plz)]
            self._loc_cache[plz] = ids[0] if ids else None
        return self._loc_cache[plz]

    def search(self, query: str | None, region: Region) -> Iterator[Listing]:
        if not query:
            return
        if not region.plz:
            log.warning("kleinanzeigen: ohne PLZ keine Umkreissuche – übersprungen")
            return
        loc_id = self._location_id(region.plz)
        if not loc_id:
            log.warning("kleinanzeigen: Orts-ID für PLZ %s nicht gefunden", region.plz)
            return
        # Kleinanzeigen kennt nur feste Radien -> nächstgrößeren nehmen, genau filtern wir danach selbst
        radius = next((r for r in RADII if r >= region.radius_km), RADII[-1])
        slug = _slug(query)
        # Nur in Rubriken suchen, in denen Betriebe verkauft werden (sonst: "Nachfolger"-Spielzeug, Bücher …)
        categories = self.options.get("categories", DEFAULT_CATEGORIES) or [None]
        for cat in categories:
            cat_part = f"c{cat}" if cat else ""
            for page in range(1, self.max_pages + 1):
                page_part = f"seite:{page}/" if page > 1 else ""
                url = f"{BASE}/s-{region.plz}/{page_part}{slug}/k0{cat_part}l{loc_id}r{radius}"
                listings = parse_search_page(self.http.get(url))
                # Kleinanzeigen hängt bei wenigen Treffern bundesweite Ergebnisse an -> nach Entfernung filtern
                kept = [
                    l for l in listings
                    if has_sale_intent(f"{l.title}\n{l.teaser or ''}", l.title)
                    and (distance_km(l) is None or distance_km(l) <= region.radius_km)
                ]
                log.info("kleinanzeigen %r c%s Seite %d: %d Anzeigen, %d mit Verkaufsabsicht",
                         query, cat, page, len(listings), len(kept))
                yield from kept
                if len(listings) < 25:  # letzte Seite
                    break

    def fetch_details(self, listing: Listing) -> Listing:
        return parse_detail_page(self.http.get(listing.url), listing)
