#!/usr/bin/env python3
"""
Weboberfläche: Übersicht der Inserate, Markieren (interessant / kontaktiert / verworfen), Notizen, Status.

    ./venv/bin/uvicorn web.app:app --port 8001

Läuft im Betrieb dauerhaft auf 127.0.0.1:8001 (launchd com.weirich.dealscout-web) und ist vom iPhone
nur über das private Tailscale-Netz erreichbar – genau wie die Weboberfläche des ZVG-Agenten.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fastapi import FastAPI, Form, Request  # noqa: E402
from fastapi.responses import HTMLResponse, RedirectResponse  # noqa: E402
from fastapi.templating import Jinja2Templates  # noqa: E402

from dealscout.config import load_config  # noqa: E402
from dealscout.pipeline import evaluate  # noqa: E402
from dealscout.report import _distance, _range  # noqa: E402
from dealscout.storage import STATUSES, Store  # noqa: E402

app = FastAPI(title="Unternehmen kaufen")
vorlagen = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

TABS = [
    ("offen", "Offen"),
    ("interessant", "Interessant"),
    ("kontaktiert", "Kontaktiert"),
    ("verworfen", "Verworfen"),
    ("ausgeblendet", "Vom Tool ausgeblendet"),
]


def _cfg():
    cfg = load_config(ROOT / "config.yaml")
    cfg.database = str(ROOT / cfg.database)
    cfg.geo_cache = str(ROOT / cfg.geo_cache)
    return cfg


def _tab_of(row) -> str:
    if row.status and row.status != "neu":
        return row.status
    return "ausgeblendet" if row.reject else "offen"


def _view(row, generated: datetime) -> dict:
    l = row.listing
    first = datetime.fromisoformat(row.first_seen)
    return {
        "key": l.key, "url": l.url, "title": l.title, "source": l.source,
        "location": l.location, "km": l.extra.get("entfernung_km"), "distance": _distance(l),
        "price": l.extra.get("kaufpreis_text") or _range(l.price_min, l.price_max, l.price),
        "price_min": l.price_min,
        "revenue": _range(l.revenue_min, l.revenue_max, l.revenue), "earnings": l.earnings,
        "employees": l.employees, "teaser": l.teaser, "description": l.description,
        "matched": l.matched, "score": round(l.score), "partner": l.extra.get("regionalpartner"),
        "einstieg": l.extra.get("einstieg"),
        "teil": l.extra.get("teilscores") or {}, "signale": l.extra.get("signale") or {},
        "einarbeitung": l.extra.get("einarbeitung"), "hebel_ideen": l.extra.get("hebel_ideen"),
        "expose": l.extra.get("expose_pdf"), "also": l.extra.get("auch_auf"),
        "reject": row.reject, "status": row.status, "note": row.note or "",
        "new": generated - first < timedelta(days=3), "first_seen": row.first_seen,
        "tab": _tab_of(row),
    }


@app.get("/", response_class=HTMLResponse)
def uebersicht(request: Request, tab: str = "offen", q: str = "", quelle: str = "",
               km: int = 0, preis: int = 0, sort: str = "score", unklar: str = "1"):
    cfg = _cfg()
    store = Store(cfg.database)
    rows = evaluate(cfg, store)
    now = datetime.now()
    items = [_view(r, now) for r in rows]

    counts = {t: 0 for t, _ in TABS}
    for it in items:
        counts[it["tab"]] += 1
    radius = cfg.region.radius_km
    km = km or radius

    def keep(it):
        if it["tab"] != tab:
            return False
        if quelle and it["source"] != quelle:
            return False
        if it["km"] is not None and it["km"] > km + 10:
            return False
        if it["km"] is None and unklar != "1" and tab == "offen":
            return False
        if preis and it["price_min"] is not None and it["price_min"] > preis:
            return False
        if q:
            hay = " ".join(str(it[k] or "") for k in ("title", "location", "teaser", "description", "partner", "note")).lower()
            if q.lower() not in hay:
                return False
        return True

    shown = [it for it in items if keep(it)]
    if sort == "km":
        shown.sort(key=lambda it: (it["km"] is None, it["km"] or 0, -it["score"]))
    elif sort in ("hebel", "einstieg"):
        shown.sort(key=lambda it: (-(it["teil"].get(sort) or 0), -it["score"]))
    elif sort == "neu":
        shown.sort(key=lambda it: (it["first_seen"], it["score"]), reverse=True)
    else:
        shown.sort(key=lambda it: (it["km"] is None, -it["score"]))

    runs = store.runs(1)
    return vorlagen.TemplateResponse(request, "uebersicht.html", {
        "items": shown, "tabs": TABS, "tab": tab, "counts": counts,
        "q": q, "quelle": quelle, "km": km, "radius": radius, "preis": preis, "sort": sort, "unklar": unklar,
        "quellen": sorted({it["source"] for it in items}), "plz": cfg.region.plz,
        "neu": sum(1 for it in items if it["new"] and it["tab"] == "offen"),
        "letzter_lauf": runs[0] if runs else None,
        "zurueck": str(request.url.path) + ("?" + request.url.query if request.url.query else ""),
    })


@app.post("/markieren")
def markieren(key: str = Form(...), status: str = Form(...), zurueck: str = Form("/")):
    store = Store(_cfg().database)
    row = store.get(key)
    if row is not None and status in STATUSES:
        # nochmal auf denselben Knopf = zurücksetzen
        store.set_status(key, "neu" if row["status"] == status else status)
    return RedirectResponse(_safe(zurueck) + f"#k-{key}", status_code=303)


@app.post("/notiz")
def notiz(key: str = Form(...), note: str = Form(""), zurueck: str = Form("/")):
    store = Store(_cfg().database)
    row = store.get(key)
    if row is not None:
        store.db.execute("UPDATE listings SET note = ? WHERE key = ?", (note.strip() or None, key))
        store.db.commit()
    return RedirectResponse(_safe(zurueck) + f"#k-{key}", status_code=303)


@app.get("/status", response_class=HTMLResponse)
def status_seite(request: Request):
    cfg = _cfg()
    store = Store(cfg.database)
    total = store.db.execute("SELECT COUNT(*) FROM listings").fetchone()[0]
    by_source = store.db.execute("SELECT source, COUNT(*) n FROM listings GROUP BY source ORDER BY n DESC").fetchall()
    return vorlagen.TemplateResponse(request, "status.html", {
        "runs": store.runs(30), "total": total, "by_source": by_source,
        "plz": cfg.region.plz, "radius": cfg.region.radius_km,
    })


def _safe(url: str) -> str:
    """Nur relative Rücksprungziele zulassen."""
    return url if url.startswith("/") and not url.startswith("//") else "/"
