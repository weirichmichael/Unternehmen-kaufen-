"""Hilfsfunktionen zum Parsen deutscher Geld- und Bereichsangaben."""

from __future__ import annotations

import re

_UNITS = {
    "tsd": 1_000,
    "tausend": 1_000,
    "t": 1_000,
    "k": 1_000,
    "mio": 1_000_000,
    "million": 1_000_000,
    "millionen": 1_000_000,
    "mrd": 1_000_000_000,
}

_NUM = r"\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:,\d+)?"


def _to_float(num: str) -> float:
    return float(num.replace(".", "").replace(",", "."))


def parse_amount_range(text: str | None) -> tuple[float | None, float | None]:
    """Wandelt Angaben wie

    - "500.000 €"                    -> (500000, 500000)
    - "über 250 - 500 Tsd. Euro"     -> (250000, 500000)
    - "über 2,5 Mio. Euro"           -> (2500000, None)
    - "bis 50 Tsd. Euro"             -> (None, 50000)
    - "Nicht veröffentlicht"         -> (None, None)

    in einen (min, max)-Bereich in EUR um.
    """
    if not text:
        return None, None
    t = text.lower().replace("\xa0", " ")
    # "245.000.00" (Punkt statt Komma vor den Cents) -> "245.000"
    t = re.sub(r"(\d{1,3}(?:\.\d{3})+)[.,]\d{2}(?!\d)", r"\1", t)
    # Jede Zahl mit ihrer (optionalen) Einheit: "500 tsd. - 2,5 mio." / "250 - 500 tsd."
    tokens = re.findall(rf"({_NUM})\s*(tsd|tausend|mio|millionen|million|mrd)?\b", t)
    if not tokens:
        return None, None
    tokens = tokens[:2]
    values = []
    for i, (num, unit) in enumerate(tokens):
        if not unit:
            # "250 - 500 Tsd." -> Einheit der folgenden Zahl übernehmen
            unit = next((u for _, u in tokens[i + 1:] if u), "")
        values.append(_to_float(num) * (_UNITS[unit] if unit else 1))

    if len(values) == 2:
        return min(values), max(values)
    v = values[0]
    if re.search(r"\b(über|ueber|ab|mehr als|>)\s", t):
        return v, None
    if re.search(r"\b(bis|unter|weniger als|<)\s", t):
        return None, v
    return v, v


def parse_amount(text: str | None) -> float | None:
    lo, hi = parse_amount_range(text)
    return lo if lo is not None else hi


def clean_ws(text: str | None) -> str | None:
    if text is None:
        return None
    t = re.sub(r"[ \t\r\f\v\xa0]+", " ", text)
    t = re.sub(r"\n\s*\n+", "\n\n", t)
    return t.strip() or None


def parse_german_date(text: str | None) -> str | None:
    """"04.11.2026" -> "2026-11-04"."""
    if not text:
        return None
    m = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", text)
    if not m:
        return None
    d, mth, y = m.groups()
    return f"{y}-{int(mth):02d}-{int(d):02d}"
