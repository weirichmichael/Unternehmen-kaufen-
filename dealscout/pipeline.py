"""Ablauf eines Suchlaufs: Börsen abfragen -> Region filtern -> Details laden -> speichern."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from .config import Config
from .geo import Geo, annotate_distance, within
from .http import PoliteSession
from .models import Listing
from .parsing import parse_amount, parse_amount_range
from .scoring import in_region, norm, rejection_reason, score
from .sources import SOURCES, Source
from .storage import Store

log = logging.getLogger(__name__)


@dataclass
class RunResult:
    seen: int = 0
    in_region: int = 0
    new_keys: set[str] = field(default_factory=set)
    errors: list[str] = field(default_factory=list)


def build_sources(cfg: Config, http: PoliteSession, only: list[str] | None = None) -> list[Source]:
    out = []
    for key, cls in SOURCES.items():
        opts = cfg.sources.get(key) or {}
        if not opts.get("enabled", True):
            continue
        if only and key not in only and cls.name not in only:
            continue
        out.append(cls(http, max_pages=int(opts.get("max_pages", 5)), options=opts))
    return out


class RegionCheck:
    """Region prüfen: erst über die berechnete Entfernung, sonst über Bundesland/Umkreis der Börse."""

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.geo: Geo | None = None
        self.home = None
        if cfg.region.plz:
            try:
                self.geo = Geo.load(cfg.geo_cache)
                self.home = self.geo.plz_coord(cfg.region.plz)
                if not self.home:
                    log.warning("PLZ %s nicht in den GeoNames-Daten – keine Entfernungsberechnung", cfg.region.plz)
            except Exception as e:  # ohne Geodaten geht es auch, nur ungenauer
                log.warning("Geodaten nicht verfügbar (%s) – filtere nur nach Bundesland/Umkreis", e)
                self.geo = None

    def reason(self, lst: Listing, radius_filtered: bool) -> str | None:
        """None = in der Region, sonst Grund für den Ausschluss."""
        if self.geo and self.home:
            annotate_distance(lst, self.geo, self.home)
            ok = within(lst, self.cfg.region.radius_km)
            if ok is True:
                return None
            if ok is False:
                return f"{lst.extra['entfernung_km']} km entfernt"
            # Entfernung unbekannt -> nur Bundesland bekannt
            if not radius_filtered and self.cfg.region.unknown_distance == "drop":
                return "Ort unklar (nur Bundesland)"
        return None if in_region(lst, self.cfg.region, radius_filtered) else "außerhalb Region"


def run(cfg: Config, store: Store, only: list[str] | None = None, refresh: bool = False) -> RunResult:
    http = PoliteSession(delay=cfg.delay_seconds)
    res = RunResult()
    region = RegionCheck(cfg)

    for src in build_sources(cfg, http, only):
        queries: list[str | None] = list(src.queries(cfg.queries))
        if cfg.browse_all_in_radius and src.supports_browse_all() and cfg.region.plz:
            queries.insert(0, None)

        found: dict[str, Listing] = {}
        for q in queries:
            try:
                for lst in src.search(q, cfg.region):
                    found.setdefault(lst.key, lst)
            except Exception as e:  # eine kaputte Börse soll den Lauf nicht abbrechen
                msg = f"{src.name} Suche {q!r}: {e}"
                log.warning(msg)
                res.errors.append(msg)
        res.seen += len(found)

        radius = src.supports_radius()
        for lst in found.values():
            if radius and cfg.region.plz:
                lst.extra["umkreis"] = _radius_tag(cfg)
            # Vorab-Check mit den Listendaten; ist die Entfernung schon sicher zu groß, sparen wir den Detailabruf
            if region.reason(lst, radius):
                continue
            res.in_region += 1
            details = False
            if cfg.fetch_details and (refresh or not store.has_details(lst.key)):
                try:
                    lst = src.fetch_details(lst)
                    details = True
                except Exception as e:
                    msg = f"{src.name} Details {lst.url}: {e}"
                    log.warning(msg)
                    res.errors.append(msg)
                # Detailseite kann genaueren Standort liefern -> nochmal prüfen
                if details and region.reason(lst, radius):
                    res.in_region -= 1
                    continue
            if store.upsert(lst, details=details):
                res.new_keys.add(lst.key)
    return res


def _radius_tag(cfg: Config) -> str:
    return f"{cfg.region.plz}/{cfg.region.radius_km}km"


def _title_key(title: str) -> str:
    return re.sub(r"[^a-z0-9äöü]+", " ", norm(title)).strip()


def mark_duplicates(listings: list[Listing]) -> None:
    """Markiert Inserate, die auf mehreren Börsen stehen (DUB spiegelt z.B. nexxt-change)."""
    keys = [(_title_key(l.title), l) for l in listings]
    for i, (ti, li) in enumerate(keys):
        for tj, lj in keys[:i]:
            if li.source == lj.source:
                continue
            n = min(len(ti), len(tj), 70)
            if n >= 20 and (ti[:n] == tj[:n] or SequenceMatcher(None, ti, tj).ratio() > 0.9):
                li.extra["auch_auf"] = lj.url
                lj.extra.setdefault("auch_auf", li.url)
                break


def reparse_amounts(lst: Listing) -> Listing:
    """Beträge aus den Rohtexten neu berechnen – so wirken Parser-Fixes auch rückwirkend."""
    lst.revenue_min, lst.revenue_max = parse_amount_range(lst.revenue)
    lst.price_min, lst.price_max = parse_amount_range(lst.extra.get("kaufpreis_text") or lst.price)
    lst.earnings_value = parse_amount(lst.earnings)
    return lst


@dataclass
class Row:
    listing: Listing
    status: str
    note: str | None
    first_seen: str
    reject: str | None


def evaluate(cfg: Config, store: Store) -> list[Row]:
    """Lädt alles aus der DB und bewertet mit der *aktuellen* Konfiguration neu."""
    rows: list[Row] = []
    region = RegionCheck(cfg)
    for r in store.all():
        lst = reparse_amounts(store.load(r))
        radius = lst.extra.get("umkreis") == _radius_tag(cfg)  # Börse hat bereits Umkreis gefiltert
        score(lst, cfg.criteria)
        reason = region.reason(lst, radius)
        reason = reason or rejection_reason(lst, cfg.criteria)
        rows.append(Row(lst, r["status"], r["note"], r["first_seen"], reason))
    mark_duplicates([r.listing for r in rows if not r.reject])
    rows.sort(key=lambda r: (r.reject is not None, r.status == "verworfen", -r.listing.score, r.first_seen))
    return rows
