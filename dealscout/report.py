"""Ausgabe: Terminal-Tabelle, CSV und eine eigenständige HTML-Seite."""

from __future__ import annotations

import csv
import html
from datetime import datetime
from pathlib import Path

from .pipeline import Row


def _eur(v: float | None) -> str:
    if v is None:
        return ""
    if v >= 1_000_000:
        return f"{v / 1_000_000:.1f} Mio".replace(".", ",")
    return f"{v / 1_000:.0f} Tsd"


def _range(lo: float | None, hi: float | None, raw: str | None) -> str:
    if lo is None and hi is None:
        return raw or ""
    if lo == hi:
        return _eur(lo)
    if hi is None:
        return f"> {_eur(lo)}"
    if lo is None:
        return f"< {_eur(hi)}"
    return f"{_eur(lo)}–{_eur(hi)}"


def _distance(l) -> str:
    km = l.extra.get("entfernung_km")
    if km is not None:
        exact = (l.extra.get("ort_genauigkeit") or "").startswith(("plz", "ort"))
        return f"{'' if exact else '~'}{km} km"
    return "Ort unklar"


def print_table(rows: list[Row], new_keys: set[str] | None = None, limit: int = 30) -> None:
    shown = [r for r in rows if not r.reject and r.status != "verworfen"]
    shown = sorted(shown, key=lambda r: r.listing.extra.get("entfernung_km") is None)[:limit]
    if not shown:
        print("Keine passenden Inserate.")
        return
    for r in shown:
        l = r.listing
        flag = "NEU " if new_keys and l.key in new_keys else "    "
        print(
            f"{flag}[{l.score:5.1f}] {l.title[:70]}\n"
            f"       {l.source} | {l.location or '?'} ({_distance(l)}) | Umsatz {_range(l.revenue_min, l.revenue_max, l.revenue) or '?'}"
            f" | Preis {_range(l.price_min, l.price_max, l.price) or '?'} | MA {l.employees or '?'}"
            f" | {r.status}\n"
            f"       {', '.join(l.matched) or '-'}  ->  {l.url}\n"
        )


CSV_FIELDS = [
    "score", "status", "title", "source", "location", "industry", "employees",
    "revenue", "earnings", "price", "price_min", "price_max", "revenue_min", "revenue_max",
    "date", "first_seen", "matched", "entfernung_km", "ort_genauigkeit", "regionalpartner", "url", "auch_auf", "expose_pdf", "note", "reject",
]


def write_csv(rows: list[Row], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as f:  # BOM -> Excel erkennt UTF-8
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS, delimiter=";")
        w.writeheader()
        for r in rows:
            l = r.listing
            w.writerow(
                {
                    "score": f"{l.score:.1f}".replace(".", ","),
                    "status": r.status,
                    "title": l.title,
                    "source": l.source,
                    "location": l.location,
                    "industry": l.industry,
                    "employees": l.employees,
                    "revenue": l.revenue,
                    "earnings": l.earnings,
                    "price": l.extra.get("kaufpreis_text") or l.price,
                    "price_min": l.price_min,
                    "price_max": l.price_max,
                    "revenue_min": l.revenue_min,
                    "revenue_max": l.revenue_max,
                    "date": l.date,
                    "first_seen": r.first_seen,
                    "matched": ", ".join(l.matched),
                    "regionalpartner": l.extra.get("regionalpartner"),
                    "entfernung_km": l.extra.get("entfernung_km"),
                    "ort_genauigkeit": l.extra.get("ort_genauigkeit"),
                    "url": l.url,
                    "auch_auf": l.extra.get("auch_auf"),
                    "expose_pdf": l.extra.get("expose_pdf"),
                    "note": r.note,
                    "reject": r.reject,
                }
            )


_CSS = """
:root{--bg:#f7f7f5;--card:#fff;--fg:#1d1d1b;--muted:#6b6b66;--line:#e4e3de;--accent:#1f6f5c;--new:#c2410c;--chip:#eef4f1}
@media (prefers-color-scheme:dark){:root{--bg:#161615;--card:#1f1f1d;--fg:#ecebe6;--muted:#9a9993;--line:#2f2f2c;--accent:#5cc0a4;--new:#fb923c;--chip:#23302b}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.45 system-ui,-apple-system,Segoe UI,sans-serif}
main{max-width:1100px;margin:0 auto;padding:24px 16px}h1{font-size:22px;margin:0 0 4px}.sub{color:var(--muted);margin-bottom:16px}
.bar{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:16px}.bar #q{flex:1;min-width:200px;padding:8px 10px;border:1px solid var(--line);border-radius:8px;background:var(--card);color:var(--fg)}
.bar label{display:flex;align-items:center;gap:6px;color:var(--muted);font-size:14px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px;margin-bottom:10px}
.card h2{font-size:16px;margin:0 0 6px}.card h2 a{color:var(--fg);text-decoration:none}.card h2 a:hover{color:var(--accent)}
.meta{display:flex;flex-wrap:wrap;gap:6px 16px;color:var(--muted);font-size:13px;margin-bottom:6px}.meta b{color:var(--fg);font-weight:600}
.teaser{font-size:14px;margin:6px 0}.chips{display:flex;flex-wrap:wrap;gap:4px}.chip{background:var(--chip);color:var(--accent);border-radius:99px;padding:1px 8px;font-size:12px}
.score{float:right;font-weight:700;color:var(--accent);font-variant-numeric:tabular-nums}.new{color:var(--new);font-weight:700;font-size:12px;margin-right:6px}
.section{font-size:15px;color:var(--muted);text-transform:uppercase;letter-spacing:.04em;margin:22px 0 10px}.rej{opacity:.55}.why{color:var(--new);font-size:12px}details{margin-top:6px;font-size:13px;color:var(--muted)}details pre{white-space:pre-wrap;font:inherit;color:var(--fg)}
"""

_JS = """
const q=document.getElementById('q'),rej=document.getElementById('rej');
function f(){const t=q.value.toLowerCase();document.querySelectorAll('.card').forEach(c=>{
 const ok=c.dataset.text.includes(t)&&(rej.checked||!c.classList.contains('rej'));c.style.display=ok?'':'none'})}
q.addEventListener('input',f);rej.addEventListener('change',f);f();
"""


def write_html(rows: list[Row], path: Path, new_keys: set[str] | None = None, title: str = "Unternehmensbörsen") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    e = html.escape
    good = sum(1 for r in rows if not r.reject and r.status != "verworfen")
    cards = []
    # Erst die verorteten Treffer, dann die mit unbekanntem Ort (nur Bundesland), dann ausgeblendete
    def group(r) -> int:
        if r.reject or r.status == "verworfen":
            return 2
        return 1 if r.listing.extra.get("entfernung_km") is None and r.listing.extra.get("ort_genauigkeit") else 0
    rows = sorted(rows, key=group)  # stabil: Score-Reihenfolge bleibt innerhalb der Gruppen
    headings = {0: "In der Nähe", 1: "Ort unklar – Börse nennt nur das Bundesland", 2: ""}
    current = None
    for r in rows:
        g = group(r)
        if g != current:
            current = g
            if headings[g]:
                cards.append(f"<h2 class='section' data-group='{g}'>{headings[g]}</h2>")
        l = r.listing
        rej = bool(r.reject) or r.status == "verworfen"
        meta = [
            f"<span>{e(l.source)}</span>",
            f"<span>📍 <b>{e(l.location or '?')}</b></span>",
            f"<span>Umsatz <b>{e(_range(l.revenue_min, l.revenue_max, l.revenue) or '?')}</b></span>",
        ]
        if l.earnings:
            meta.append(f"<span>Ergebnis <b>{e(l.earnings)}</b></span>")
        meta.append(f"<span>Preis <b>{e(l.extra.get('kaufpreis_text') or _range(l.price_min, l.price_max, l.price) or '?')}</b></span>")
        meta.append(f"<span>MA <b>{e(l.employees or '?')}</b></span>")
        if l.extra.get("regionalpartner"):
            meta.append(f"<span>betreut von <b>{e(l.extra['regionalpartner'])}</b></span>")
        meta.append(f"<span title='{e(l.extra.get('ort_genauigkeit') or '')}'>{e(_distance(l))}</span>")
        if l.date:
            meta.append(f"<span>vom {e(l.date)}</span>")
        meta.append(f"<span>Status: {e(r.status)}</span>")
        links = []
        if l.extra.get("expose_pdf"):
            links.append(f"<a href='{e(l.extra['expose_pdf'])}'>Exposé (PDF)</a>")
        if l.extra.get("auch_auf"):
            links.append(f"<a href='{e(l.extra['auch_auf'])}'>auch auf anderer Börse</a>")
        chips = "".join(f"<span class='chip'>{e(m)}</span>" for m in l.matched)
        desc = l.description or ""
        text = " ".join([l.title, l.location or "", l.industry or "", l.teaser or "", desc, r.status]).lower()
        cards.append(
            f"<article class='card{' rej' if rej else ''}' data-text='{e(text)}'>"
            f"<span class='score'>{l.score:.0f}</span>"
            f"<h2>{'<span class=new>NEU</span>' if new_keys and l.key in new_keys else ''}"
            f"<a href='{e(l.url)}' target='_blank' rel='noopener'>{e(l.title)}</a></h2>"
            f"<div class='meta'>{''.join(meta)}</div>"
            + (f"<div class='why'>ausgeblendet: {e(r.reject or 'verworfen')}</div>" if rej else "")
            + (f"<p class='teaser'>{e(l.teaser)}</p>" if l.teaser else "")
            + f"<div class='chips'>{chips}</div>"
            + (f"<div class='meta'>{' · '.join(links)}</div>" if links else "")
            + (f"<details><summary>Beschreibung</summary><pre>{e(desc)}</pre></details>" if desc else "")
            + (f"<div class='meta'>Notiz: {e(r.note)}</div>" if r.note else "")
            + f"<div class='meta'><code>{e(l.key)}</code></div>"
            + "</article>"
        )
    doc = f"""<!doctype html><html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{e(title)}</title><style>{_CSS}</style></head>
<body><main><h1>{e(title)}</h1>
<div class="sub">{good} passende Inserate · Stand {datetime.now():%d.%m.%Y %H:%M}</div>
<div class="bar"><input id="q" placeholder="Filtern (Titel, Ort, Branche …)"><label><input type="checkbox" id="rej"> ausgeblendete zeigen</label></div>
{''.join(cards)}
</main><script>{_JS}</script></body></html>"""
    path.write_text(doc, encoding="utf-8")

