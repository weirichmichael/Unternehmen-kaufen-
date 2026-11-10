from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .scoring import Criteria
from .sources.base import Region


@dataclass
class Config:
    criteria: Criteria
    queries: list[str]
    browse_all_in_radius: bool
    sources: dict[str, dict] = field(default_factory=dict)
    fetch_details: bool = True
    delay_seconds: float = 1.5
    database: str = "data/dealscout.sqlite"
    report_dir: str = "reports"
    geo_cache: str = "data/geo"

    @property
    def region(self) -> Region:
        return self.criteria.region


def load_config(path: str | Path) -> Config:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    r = raw.get("region") or {}
    region = Region(
        plz=str(r["plz"]).strip() if r.get("plz") else None,
        radius_km=int(r.get("radius_km", 50)),
        bundeslaender=list(r.get("bundeslaender") or []),
        include_unknown_location=bool(r.get("include_unknown_location", False)),
        unknown_distance=str(r.get("unknown_distance", "keep")),
    )
    sc = raw.get("scoring") or {}
    flt = raw.get("filters") or {}
    criteria = Criteria(
        keywords={str(k): float(v) for k, v in (sc.get("keywords") or {}).items()},
        exclude=list(sc.get("exclude") or []),
        exclude_title=list(sc.get("exclude_title") or []),
        targets={str(k): float(v) for k, v in (sc.get("targets") or {}).items()},
        require_target=bool(sc.get("require_target", False)),
        branch_notes=list(sc.get("branch_notes") or []),
        min_score=float(sc.get("min_score", 0)),
        price_max=flt.get("price_max"),
        revenue_min=flt.get("revenue_min"),
        revenue_max=flt.get("revenue_max"),
        region=region,
    )
    s = raw.get("search") or {}
    return Config(
        criteria=criteria,
        queries=list(s.get("queries") or []),
        browse_all_in_radius=bool(s.get("browse_all_in_radius", True)),
        sources=raw.get("sources") or {},
        fetch_details=bool(raw.get("fetch_details", True)),
        delay_seconds=float(raw.get("delay_seconds", 1.5)),
        database=raw.get("database", "data/dealscout.sqlite"),
        report_dir=raw.get("report_dir", "reports"),
    )
