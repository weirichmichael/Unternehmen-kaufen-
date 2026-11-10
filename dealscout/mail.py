"""Sammelmail über neue passende Inserate – Versand über Gmail wie beim ZVG-Agenten.

Zugang aus der .env im Projektordner (gleiche Namen wie beim ZVG-Agenten, Zeilen einfach kopieren):

    GMAIL_ADDRESS=...@gmail.com
    GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx     (Google-Konto -> Sicherheit -> App-Passwörter)
    DEALSCOUT_WEB_BASIS=https://macbook-air-von-michael.<tailnet>.ts.net:8443   (optional, für Links)

Gibt es nichts Neues, wird keine Mail verschickt.
"""

from __future__ import annotations

import html
import logging
import os
import smtplib
from email.message import EmailMessage
from email.utils import formataddr
from pathlib import Path

from .pipeline import Row
from .report import _distance, _range

log = logging.getLogger(__name__)

SMTP_SERVER, SMTP_PORT = "smtp.gmail.com", 465


def load_env(path: str | Path = ".env") -> None:
    """Minimaler .env-Leser (KEY=VALUE), überschreibt keine bereits gesetzten Variablen."""
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


def access() -> tuple[str, str]:
    addr, pw = os.environ.get("GMAIL_ADDRESS"), os.environ.get("GMAIL_APP_PASSWORD")
    if not (addr and pw):
        raise RuntimeError("GMAIL_ADDRESS und GMAIL_APP_PASSWORD fehlen in der .env")
    return addr, pw


def web_base() -> str | None:
    b = os.environ.get("DEALSCOUT_WEB_BASIS")
    return b.rstrip("/") if b else None


def _facts(l) -> list[str]:
    f = [_distance(l), l.location or "?"]
    price = l.extra.get("kaufpreis_text") or _range(l.price_min, l.price_max, l.price)
    if price:
        f.append(f"Preis {price}")
    rev = _range(l.revenue_min, l.revenue_max, l.revenue)
    if rev:
        f.append(f"Umsatz {rev}")
    if l.employees:
        f.append(f"MA {l.employees}")
    if l.extra.get("einstieg"):
        f.append(l.extra["einstieg"])
    return f


def new_matches(rows: list[Row], new_keys: set[str]) -> list[Row]:
    new = [r for r in rows if r.listing.key in new_keys and not r.reject]
    new.sort(key=lambda r: (r.listing.extra.get("entfernung_km") is None, -r.listing.score))
    return new


def build(rows: list[Row]) -> tuple[str, str, str]:
    """(Betreff, Text, HTML) der Sammelmail."""
    n = len(rows)
    subject = f"Unternehmen kaufen: {n} {'neues Angebot' if n == 1 else 'neue Angebote'}"
    base = web_base()

    text_lines = [f"{n} neue passende Inserate im Umkreis.", ""]
    for r in rows:
        l = r.listing
        text_lines += [f"- {l.title} ({l.source})", f"  {' | '.join(_facts(l))}", f"  {l.url}", ""]
    if base:
        text_lines.append(f"Übersicht: {base}/")
    text = "\n".join(text_lines)

    e = html.escape
    items = []
    for r in rows:
        l = r.listing
        partner = f"<br><span style='color:#6c6c66'>betreut von {e(l.extra['regionalpartner'])}</span>" if l.extra.get("regionalpartner") else ""
        teaser = f"<br><span style='color:#444'>{e((l.teaser or '')[:220])}</span>" if l.teaser else ""
        sig = l.extra.get("signale") or {}
        bits = [f"Hebel: {', '.join(sig['hebel'])}"] if sig.get("hebel") else []
        bits += [f"Einstieg: {', '.join(sig['einstieg'])}"] if sig.get("einstieg") else []
        bits += [f"Hürde: {', '.join(sig['huerden'])}"] if sig.get("huerden") else []
        signals = f"<br><span style='color:#2a4d8f;font-size:13px'>{e(' · '.join(bits))}</span>" if bits else ""
        items.append(
            "<tr><td style='padding:10px 0;border-bottom:1px solid #eeeeea'>"
            f"<a href='{e(l.url)}' style='color:#2a4d8f;font-weight:600;text-decoration:none'>{e(l.title)}</a>"
            f"<br><span style='color:#1c1c1a'>{e(' · '.join(_facts(l)))}</span>"
            f"<br><span style='color:#6c6c66'>{e(l.source)}</span>{partner}{signals}{teaser}</td></tr>"
        )
    button = (f"<p><a href='{e(base)}/' style='display:inline-block;padding:10px 16px;border-radius:8px;"
              f"background:#2a4d8f;color:#fff;text-decoration:none;font-weight:600'>Übersicht öffnen</a></p>") if base else ""
    body = (
        "<div style='font:14px/1.5 -apple-system,Segoe UI,sans-serif;color:#1c1c1a;max-width:640px'>"
        f"<p><b>{n} neue passende Inserate</b> im Umkreis.</p>{button}"
        f"<table style='width:100%;border-collapse:collapse'>{''.join(items)}</table>{button}</div>"
    )
    return subject, text, body


def send(subject: str, text: str, body_html: str | None = None, to: str | None = None) -> None:
    addr, pw = access()
    m = EmailMessage()
    m["Subject"] = subject
    m["From"] = formataddr(("Unternehmen kaufen", addr))
    m["To"] = to or addr
    m.set_content(text)
    if body_html:
        m.add_alternative(body_html, subtype="html")
    with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, timeout=60) as s:
        s.login(addr, pw)
        s.send_message(m)
    log.info("Mail versendet: %s", subject)


def notify(rows: list[Row], new_keys: set[str]) -> int:
    """Schickt die Sammelmail, falls es neue passende Inserate gibt. Gibt die Anzahl zurück."""
    new = new_matches(rows, new_keys)
    if new:
        send(*build(new))
    return len(new)
