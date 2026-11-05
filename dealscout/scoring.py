"""Bewertung & Filterung der Inserate nach den eigenen Kriterien."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from .models import Listing
from .sources.base import Region


def norm(text: str) -> str:
    t = unicodedata.normalize("NFKC", text).lower()
    return t.replace("ß", "ss")


@dataclass
class Criteria:
    keywords: dict[str, float] = field(default_factory=dict)  # Begriff -> Gewicht
    exclude: list[str] = field(default_factory=list)           # Ausschlussbegriffe
    price_max: float | None = None
    revenue_min: float | None = None
    revenue_max: float | None = None
    min_score: float = 0.0
    region: Region = field(default_factory=Region)


def score(listing: Listing, c: Criteria) -> Listing:
    text = norm(listing.text())
    title = norm(listing.title)
    s = 0.0
    matched: list[str] = []
    for kw, weight in c.keywords.items():
        k = norm(kw)
        if k in text:
            # Treffer im Titel zählen doppelt
            s += weight * (2 if k in title else 1)
            matched.append(kw)
    listing.score = s
    listing.matched = matched
    return listing


def in_region(listing: Listing, region: Region, source_filtered_by_radius: bool) -> bool:
    """Prüft die Region. Inserate, die die Börse selbst per Umkreis gefiltert hat, sind ok."""
    if source_filtered_by_radius and region.plz:
        return True
    if not region.bundeslaender:
        return True
    loc = norm(listing.location or "")
    if not loc or loc in ("deutschland", "bundesweit"):
        return region.include_unknown_location
    return any(norm(bl) in loc for bl in region.bundeslaender)


# Kaufgesuche erkennen: jemand sucht einen *Betrieb* (nicht: einen *Nachfolger* / Käufer).
_BUSINESS = (
    r"(?:handwerks)?betrieb|unternehmen|firma|gmbh|ug\b|hausverwaltung|immobilienverwaltung|"
    r"hausmeister\w*|gebäudereinigung|reinigungsfirma|verwaltung|kanzlei|praxis|geschäft|beteiligung"
)
_WANTED_PATTERNS = [
    # "Wir suchen (im Raum X) einen bestehenden Handwerksbetrieb"
    rf"\b(?:wir suchen|suchen wir|ich suche|suche ich|suchen|suche|sucht)\b[^.!?\n]{{0,80}}?"
    rf"\b(?:einen|eine|ein|nach)\b\s+(?:\w+\s+){{0,3}}?(?:{_BUSINESS})",
    # "Hausverwaltung zur Übernahme / Beteiligung gesucht", "zum Kauf gesucht"
    r"\b(?:zur übernahme|zum kauf|zur beteiligung|übernahme|kauf|beteiligung)\b[^.!?\n]{0,25}\bgesucht\b",
    r"\bkaufgesuch\b|\bkaufe (?:ihr|ihre|ihren|dein|deine|deinen)\b",
]
_WANTED = re.compile("|".join(_WANTED_PATTERNS), re.I)
_SELLER = re.compile(r"\bnachfolger(?:in|/-?in)?\b[^.!?\n]{0,15}\bgesucht|\b(?:suche|suchen|sucht)\b[^.!?\n]{0,40}\b(?:nachfolger|käufer|übernehmer)", re.I)


def is_wanted_ad(listing: Listing) -> bool:
    """True, wenn das Inserat ein Kaufgesuch ist (Titel + Anfang der Beschreibung)."""
    head = "\n".join(p for p in (listing.title, listing.teaser, (listing.description or "")[:400]) if p)
    m = _WANTED.search(head)
    if not m:
        return False
    # "Wir suchen einen Nachfolger für unser Unternehmen" ist ein Angebot
    return not _SELLER.search(head[: m.end() + 40])


def rejection_reason(listing: Listing, c: Criteria) -> str | None:
    """Gibt einen Grund zurück, wenn das Inserat nicht passt, sonst None."""
    if is_wanted_ad(listing):
        return "Kaufgesuch, kein Angebot"
    text = norm(listing.text())
    for ex in c.exclude:
        if re.search(r"\b" + re.escape(norm(ex)), text):
            return f"Ausschlussbegriff '{ex}'"
    # Preis: nur ausschließen, wenn der *Mindest*preis sicher über dem Limit liegt
    if c.price_max is not None and listing.price_min is not None and listing.price_min > c.price_max:
        return f"Preis ab {listing.price_min:,.0f} € > {c.price_max:,.0f} €"
    if c.revenue_max is not None and listing.revenue_min is not None and listing.revenue_min > c.revenue_max:
        return "Umsatz zu hoch"
    if c.revenue_min is not None and listing.revenue_max is not None and listing.revenue_max < c.revenue_min:
        return "Umsatz zu niedrig"
    if listing.score < c.min_score:
        return "Score zu niedrig"
    return None
