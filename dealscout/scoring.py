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
    # Branchen ausblenden, wenn der Begriff im Titel steht – außer einer der "unless"-Begriffe auch
    # (z.B. Reinigung raus, aber "Hausmeisterservice / Gebäudereinigung" bleibt)
    exclude_title: list[dict] = field(default_factory=list)
    # Zielbranchen (Begriff -> Gewicht). Mit require_target muss mindestens eine davon vorkommen.
    targets: dict[str, float] = field(default_factory=dict)
    require_target: bool = False
    # Hinweise zum Einstieg je Branche: [{terms: [...], note: "zulassungsfrei"}, ...] – erster Treffer zählt
    branch_notes: list[dict] = field(default_factory=list)
    # Teilbewertungen aus dem Inseratstext: {"hebel": {muster: gewicht}, "einstieg": {...}, "huerden": {...}}
    # Muster sind reguläre Ausdrücke (Kleinschreibung). Hürden zählen nicht, wenn kurz davor
    # "nicht", "kein" oder "ohne" steht ("Branchenerfahrung nicht zwingend erforderlich").
    signals: dict[str, dict[str, float]] = field(default_factory=dict)
    # Mitarbeiterzahl -> Punkte, z.B. [{"min": 2, "max": 20, "points": 4}, ...]
    size_points: list[dict] = field(default_factory=list)
    price_max: float | None = None
    revenue_min: float | None = None
    revenue_max: float | None = None
    min_score: float = 0.0
    region: Region = field(default_factory=Region)


_NEGATION = re.compile(r"\b(nicht|kein\w*|ohne)\b[^.!?\n]{0,30}$")


def _signal_hits(text: str, patterns: dict[str, float], negatable: bool) -> tuple[float, list[str]]:
    total, hits = 0.0, []
    for pat, weight in patterns.items():
        for m in re.finditer(norm(pat), text):  # gleiche Normalisierung wie der Text (ß -> ss)
            if negatable and (_NEGATION.search(text[max(0, m.start() - 40):m.start()])
                              or re.search(r"\b(nicht|kein\w*|ohne)\b", m.group(0))):
                continue  # "nicht erforderlich", "keine Vorkenntnisse … Voraussetzung"
            total += weight
            hits.append(m.group(0))
            break
    return total, hits


def employee_count(text: str | None) -> tuple[int | None, int | None]:
    """'6 - 10 Beschäftigte' -> (6, 10); 'bis 5' -> (1, 5); 'Einzelunternehmen' -> (1, 1); '12' -> (12, 12)."""
    if not text:
        return None, None
    t = text.lower()
    if "einzel" in t:
        return 1, 1
    nums = [int(n) for n in re.findall(r"\d+", t)]
    if not nums:
        return None, None
    if t.strip().startswith(("bis", "unter")):
        return 1, nums[0]
    if len(nums) >= 2:
        return nums[0], nums[1]
    return nums[0], (None if re.search(r"über|mehr als|ab", t) else nums[0])


def score(listing: Listing, c: Criteria) -> Listing:
    text = norm(listing.text())
    title = norm(listing.title)
    branche = 0.0
    matched: list[str] = []
    targets: list[str] = []
    # Zielbranche zählt nur, wenn sie die Branche des Inserats beschreibt: Titel, Branche, Kurzbeschreibung –
    # nicht der Langtext ("Kunden sind Hausverwaltungen" macht noch keine Hausverwaltung)
    head = norm(" ".join(p for p in (listing.title, listing.industry, listing.teaser) if p))
    for kw, weight in list(c.targets.items()) + list(c.keywords.items()):
        k = norm(kw)
        if k in text and kw not in matched:
            # Treffer im Titel zählen doppelt
            branche += weight * (2 if k in title else 1)
            matched.append(kw)
            if kw in c.targets and k in head:
                targets.append(kw)

    parts = {"branche": branche}
    signals: dict[str, list[str]] = {}
    for group, patterns in c.signals.items():
        pts, hits = _signal_hits(text, patterns, negatable=(group == "huerden"))
        parts[group] = pts
        if hits:
            signals[group] = hits

    lo, hi = employee_count(listing.employees)
    size = 0.0
    if lo is not None:
        mid = lo if hi is None else (lo + hi) / 2
        for rule in c.size_points:
            if rule.get("min", 0) <= mid <= rule.get("max", 10**9):
                size = float(rule.get("points", 0))
                break
    parts["groesse"] = size

    listing.score = sum(parts.values())
    listing.matched = matched
    listing.extra["zielbranchen"] = targets
    listing.extra["teilscores"] = {k: round(v, 1) for k, v in parts.items()}
    listing.extra["signale"] = signals
    # Branchenhinweise: zuerst im Titel suchen, dann im ganzen Text
    for key in ("einstieg", "einarbeitung", "hebel_ideen"):
        listing.extra.pop(key, None)
    for where in (title, text):
        rule = next((r for r in c.branch_notes if any(norm(t) in where for t in r.get("terms", []))), None)
        if rule:
            listing.extra["einstieg"] = rule.get("note")
            if rule.get("einarbeitung"):
                listing.extra["einarbeitung"] = rule["einarbeitung"]
            if rule.get("hebel"):
                listing.extra["hebel_ideen"] = rule["hebel"]
            break
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
    title = norm(listing.title)
    for rule in c.exclude_title:
        terms = [norm(t) for t in rule.get("terms", [])]
        unless = [norm(t) for t in rule.get("unless", [])]
        # Standard: nur der Titel; mit "in: [title, industry]" auch die Branchenangabe der Börse
        fields = rule.get("in", ["title"])
        hay = " | ".join(norm(getattr(listing, f) or "") for f in fields)
        hit = next((t for t in terms if t in hay), None)
        if hit and not any(u in title for u in unless):
            return (rule.get("reason") or "Branche ausgeschlossen") + f" („{hit}“)"
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
    if c.require_target and c.targets and not listing.extra.get("zielbranchen"):
        return "keine Zielbranche"
    if listing.score < c.min_score:
        return "Score zu niedrig"
    return None
