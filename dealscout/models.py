"""Gemeinsames Datenmodell für Inserate aus allen Börsen."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class Listing:
    source: str                       # z.B. "nexxt-change", "dub"
    source_id: str                    # eindeutige ID innerhalb der Quelle
    url: str
    title: str
    date: str | None = None           # Inseratsdatum (ISO, falls bekannt)
    industry: str | None = None       # Branche laut Börse
    location: str | None = None       # z.B. "Bayern / Schwaben" oder "Bayern"
    teaser: str | None = None         # Kurzbeschreibung
    description: str | None = None    # Langtext (nur nach Detailabruf)
    employees: str | None = None      # Rohtext, z.B. "6 - 10 Beschäftigte"
    revenue: str | None = None        # Rohtext, z.B. "über 250 - 500 Tsd. Euro"
    earnings: str | None = None       # Ergebnis/EBIT, falls angegeben
    price: str | None = None          # Preisvorstellung (Rohtext)
    revenue_min: float | None = None  # geparst in EUR
    revenue_max: float | None = None
    price_min: float | None = None
    price_max: float | None = None
    earnings_value: float | None = None
    extra: dict = field(default_factory=dict)

    # wird von der Bewertung gesetzt, nicht gespeichert
    score: float = 0.0
    matched: list[str] = field(default_factory=list)

    @property
    def key(self) -> str:
        return f"{self.source}:{self.source_id}"

    def text(self) -> str:
        """Gesamter durchsuchbarer Text (für Keyword-Matching)."""
        parts = [self.title, self.industry, self.teaser, self.description]
        return "\n".join(p for p in parts if p)

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("score")
        d.pop("matched")
        return d
