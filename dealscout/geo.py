"""Entfernung Inserat <-> eigene PLZ.

Grundlage: GeoNames-Postleitzahlen (DE), einmalig geladen und in data/geo/ gecacht.
Ein Inserat wird so genau wie möglich verortet:

    PLZ (5-stellig)  >  Landkreis  >  Ort im Standortfeld  >  PLZ-Bereich (2-stellig)
    >  Ort/Region im Titel oder Text ("Raum Mannheim", "Rhein-Main", "am Bodensee")

Bleibt nur das Bundesland übrig, ist die Entfernung unbekannt.
"""

from __future__ import annotations

import io
import logging
import math
import re
import unicodedata
import zipfile
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import requests

from .models import Listing

log = logging.getLogger(__name__)

GEONAMES_URL = "https://download.geonames.org/export/zip/DE.zip"

# Toleranz je Genauigkeit: ein Landkreis-Mittelpunkt kann ~20 km vom Betrieb entfernt liegen
TOLERANCE_KM = {"plz": 5, "ort": 5, "landkreis": 15, "text": 15, "plz-bereich": 40}

# Landschafts-/Regionsnamen, die häufig statt eines Ortes genannt werden -> repräsentativer Ort
REGION_ALIASES = {
    "rhein-main": "Frankfurt am Main", "rhein main": "Frankfurt am Main",
    "rhein-neckar": "Mannheim", "kurpfalz": "Heidelberg", "metropolregion rhein-neckar": "Mannheim",
    "bergstraße": "Bensheim", "odenwald": "Michelstadt", "kraichgau": "Sinsheim",
    "bodensee": "Friedrichshafen", "allgäu": "Kempten (Allgäu)", "ruhrgebiet": "Essen",
    "rheinhessen": "Mainz", "südpfalz": "Landau in der Pfalz", "vorderpfalz": "Neustadt an der Weinstraße",
    "westpfalz": "Kaiserslautern", "hohenlohe": "Künzelsau", "breisgau": "Freiburg im Breisgau",
    "ortenau": "Offenburg", "schwäbische alb": "Reutlingen", "taunus": "Bad Homburg vor der Höhe",
    "wetterau": "Friedberg (Hessen)", "spessart": "Aschaffenburg", "hunsrück": "Simmern/Hunsrück",
    "eifel": "Daun", "westerwald": "Montabaur", "sauerland": "Meschede", "münsterland": "Münster",
    "oberschwaben": "Ravensburg", "schwarzwald": "Freudenstadt", "nordschwarzwald": "Pforzheim",
}

BUNDESLAENDER = {
    "baden-württemberg", "bayern", "berlin", "brandenburg", "bremen", "hamburg", "hessen",
    "mecklenburg-vorpommern", "niedersachsen", "nordrhein-westfalen", "rheinland-pfalz", "saarland",
    "sachsen", "sachsen-anhalt", "schleswig-holstein", "schleswig holstein", "thüringen",
    "deutschland", "bundesweit", "online",
}

_REGIERUNGSBEZIRKE_RAW = (
    "Stuttgart", "Karlsruhe", "Freiburg", "Tübingen", "Darmstadt", "Gießen", "Kassel",
    "Rheinhessen-Pfalz", "Koblenz", "Trier", "Oberbayern", "Niederbayern", "Oberpfalz", "Oberfranken",
    "Mittelfranken", "Unterfranken", "Schwaben", "Düsseldorf", "Köln", "Münster", "Detmold", "Arnsberg",
    "Braunschweig", "Hannover", "Lüneburg", "Weser-Ems", "Chemnitz", "Dresden", "Leipzig",
)

_KREIS_PREFIX = re.compile(r"^(landkreis|kreisfreie stadt|stadtkreis|kreis|region|lk)\s+")
_KREIS_SUFFIX = re.compile(r",\s*(stadtkreis|landkreis|kreisfreie stadt)$")


def _norm(text: str) -> str:
    t = unicodedata.normalize("NFKC", text).lower().strip()
    t = t.replace("ß", "ss")
    return re.sub(r"\s+", " ", t)


REGIERUNGSBEZIRKE = {_norm(x) for x in _REGIERUNGSBEZIRKE_RAW}


def norm_kreis(name: str) -> str:
    t = _norm(name)
    t = _KREIS_SUFFIX.sub("", t)
    t = _KREIS_PREFIX.sub("", t)
    return t.strip(" ,")


def haversine(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


def _mean(points: list[tuple[float, float]]) -> tuple[float, float]:
    return (sum(p[0] for p in points) / len(points), sum(p[1] for p in points) / len(points))


@dataclass
class Position:
    coord: tuple[float, float]
    precision: str  # plz | ort | landkreis | plz-bereich | text
    label: str


class Geo:
    def __init__(self, rows: list[tuple[str, str, str, float, float]]):
        """rows: (plz, ort, kreis, lat, lon)"""
        plz: dict[str, list] = defaultdict(list)
        kreis: dict[str, list] = defaultdict(list)
        ort: dict[str, list] = defaultdict(list)
        prefix: dict[str, list] = defaultdict(list)
        ort_plz_count: dict[str, set] = defaultdict(set)
        for p, o, k, lat, lon in rows:
            c = (lat, lon)
            plz[p].append(c)
            prefix[p[:2]].append(c)
            if k:
                kreis[norm_kreis(k)].append(c)
            ort[_norm(o)].append(c)
            ort_plz_count[_norm(o)].add(p)
        self.plz = {k: _mean(v) for k, v in plz.items()}
        self.kreis = {k: _mean(v) for k, v in kreis.items()}
        self.prefix = {k: _mean(v) for k, v in prefix.items()}
        # Orte nur, wenn eindeutig (alle Einträge nah beieinander) – "Neustadt" gibt es dutzendfach
        self.ort: dict[str, tuple[float, float]] = {}
        self.big_ort: set[str] = set()
        for name, pts in ort.items():
            center = _mean(pts)
            if name in BUNDESLAENDER:
                continue  # es gibt z.B. ein Dorf "Hessen" in Sachsen-Anhalt
            if all(haversine(center, p) < 25 for p in pts):
                self.ort[name] = center
                if len(ort_plz_count[name]) >= 3 and len(name) >= 5:
                    self.big_ort.add(name)  # Städte mit mehreren PLZ -> auch im Fließtext suchen
        names = sorted(self.big_ort, key=len, reverse=True)
        self._text_re = re.compile(r"(?<![\w-])(" + "|".join(re.escape(n) for n in names) + r")(?![\w-])", re.I)
        self._alias_re = re.compile(
            r"(?<![\w-])(" + "|".join(re.escape(a) for a in sorted(REGION_ALIASES, key=len, reverse=True)) + r")(?![\w])",
            re.I,
        )

    # ------------------------------------------------------------------ laden
    @classmethod
    def load(cls, cache_dir: str | Path = "data/geo") -> "Geo":
        path = Path(cache_dir) / "DE.txt"
        if not path.exists():
            log.info("Lade PLZ-Daten von GeoNames …")
            path.parent.mkdir(parents=True, exist_ok=True)
            resp = requests.get(GEONAMES_URL, timeout=60)
            resp.raise_for_status()
            with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
                path.write_bytes(z.read("DE.txt"))
        rows = []
        for line in path.read_text(encoding="utf-8").splitlines():
            f = line.split("\t")
            if len(f) > 10 and f[9] and f[10]:
                rows.append((f[1], f[2], f[7], float(f[9]), float(f[10])))
        return cls(rows)

    # --------------------------------------------------------------- verorten
    def plz_coord(self, plz: str) -> tuple[float, float] | None:
        return self.plz.get(plz)

    def _segment(self, seg: str) -> Position | None:
        s = seg.strip()
        if not s or s.lower() in BUNDESLAENDER:
            return None
        k = norm_kreis(s)
        if k in self.kreis:
            return Position(self.kreis[k], "landkreis", s)
        o = _norm(re.sub(r"\s*\([A-ZÄÖÜ]{1,3}\)$", "", s))  # "Esslingen am Neckar (ES)"
        if o in self.ort:
            return Position(self.ort[o], "ort", s)
        return None

    def locate(self, listing: Listing) -> Position | None:
        loc = listing.location or ""
        # 1) PLZ
        m = re.search(r"\b(\d{5})\b", loc)
        if m and m.group(1) in self.plz:
            return Position(self.plz[m.group(1)], "plz", m.group(1))
        # 2) Standortfeld von hinten nach vorne (genaueste Angabe steht meist hinten)
        segments = [s for s in re.split(r"\s*(?:/|>|;|,| - )\s*", loc) if s]
        if listing.source == "nexxt-change":
            # "Bundesland / Regierungsbezirk / Kreis" – der Regierungsbezirk ist kein Ort
            if len(segments) >= 3:
                segments = segments[2:]
            elif len(segments) == 2 and _norm(segments[1]) not in REGIERUNGSBEZIRKE:
                segments = segments[1:]
            else:
                segments = []
        for seg in reversed(segments):
            pos = self._segment(seg)
            if pos:
                return pos
        for seg in re.split(r",\s*", listing.extra.get("umgebung") or ""):
            pos = self._segment(seg)
            if pos:
                return Position(pos.coord, "ort", pos.label)
        # 3) PLZ-Bereich ("Region 63xxx", biz-trade "73 / Deutschland")
        pre = listing.extra.get("plz_bereich")
        m = re.search(r"\b(\d{2})x{3}\b", loc, re.I)
        pre = pre or (m.group(1) if m else None)
        if pre and pre.zfill(2) in self.prefix:
            return Position(self.prefix[pre.zfill(2)], "plz-bereich", f"{pre}xxx")
        # 4) Ort / Region im Titel oder Text
        text = "\n".join(p for p in (listing.title, listing.teaser, (listing.description or "")[:600]) if p)
        hits = []
        m = self._text_re.search(text)
        if m:
            hits.append((m.start(), Position(self.ort[_norm(m.group(1))], "text", m.group(1))))
        m = self._alias_re.search(text)
        if m:
            target = _norm(REGION_ALIASES[m.group(1).lower()])
            if target in self.ort:
                hits.append((m.start(), Position(self.ort[target], "text", m.group(1))))
        if hits:
            return min(hits, key=lambda h: h[0])[1]
        return None


def annotate_distance(listing: Listing, geo: Geo, home: tuple[float, float]) -> float | None:
    """Setzt extra['entfernung_km'] und extra['ort_genauigkeit']; gibt die Entfernung zurück."""
    pos = geo.locate(listing)
    if not pos:
        listing.extra.pop("entfernung_km", None)
        listing.extra["ort_genauigkeit"] = "unbekannt"
        return None
    km = round(haversine(home, pos.coord))
    listing.extra["entfernung_km"] = km
    listing.extra["ort_genauigkeit"] = f"{pos.precision}: {pos.label}"
    return km


def within(listing: Listing, radius_km: int) -> bool | None:
    """True/False, wenn die Entfernung bekannt ist, sonst None."""
    km = listing.extra.get("entfernung_km")
    if km is None:
        return None
    precision = (listing.extra.get("ort_genauigkeit") or "").split(":")[0]
    return km <= radius_km + TOLERANCE_KM.get(precision, 15)
