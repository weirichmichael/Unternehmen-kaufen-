"""Sammelmail: Inhalt und Versand (SMTP wird durch eine Attrappe ersetzt)."""

from dealscout import mail
from dealscout.models import Listing
from dealscout.pipeline import Row


def _row(key, title, reject=None, km=12):
    l = Listing(source="nexxt-change", source_id=key, url=f"https://x/{key}", title=title,
                location="Hessen / Bergstraße", price="über 50 - 250 Tsd. Euro", price_min=50_000, price_max=250_000)
    l.extra.update({"entfernung_km": km, "ort_genauigkeit": "landkreis: Bergstraße", "regionalpartner": "IHK Darmstadt"})
    l.score = 30
    return Row(l, "neu", None, "2026-11-05T17:30:00", reject)


class FakeSMTP:
    sent = []

    def __init__(self, host, port, timeout=None):
        self.host = host

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def login(self, user, pw):
        self.user = user

    def send_message(self, m):
        FakeSMTP.sent.append(m)


def test_notify_sends_only_new_matching(monkeypatch):
    monkeypatch.setenv("GMAIL_ADDRESS", "ich@example.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "geheim")
    monkeypatch.setenv("DEALSCOUT_WEB_BASIS", "https://mac.ts.net:8443")
    monkeypatch.setattr(mail.smtplib, "SMTP_SSL", FakeSMTP)
    FakeSMTP.sent = []
    rows = [_row("1", "Hausmeisterservice Riedstadt"), _row("2", "Alt", km=5),
            _row("3", "Reinigung", reject="Gebäudereinigung (ausgeschlossen)")]
    n = mail.notify(rows, new_keys={"nexxt-change:1", "nexxt-change:3"})
    assert n == 1
    (m,) = FakeSMTP.sent
    assert m["To"] == "ich@example.com" and "1 neues Angebot" in m["Subject"]
    text = m.get_body(("plain",)).get_content()
    assert "Hausmeisterservice Riedstadt" in text and "Reinigung" not in text and "Alt" not in text
    html = m.get_body(("html",)).get_content()
    assert "https://mac.ts.net:8443/" in html and "IHK Darmstadt" in html


def test_no_mail_without_news(monkeypatch):
    monkeypatch.setattr(mail.smtplib, "SMTP_SSL", FakeSMTP)
    FakeSMTP.sent = []
    assert mail.notify([_row("1", "x")], new_keys=set()) == 0
    assert FakeSMTP.sent == []


def test_load_env(tmp_path, monkeypatch):
    monkeypatch.delenv("GMAIL_ADDRESS", raising=False)
    (tmp_path / ".env").write_text('GMAIL_ADDRESS="a@b.de"\n# Kommentar\nLEER=\n')
    mail.load_env(tmp_path / ".env")
    import os
    assert os.environ["GMAIL_ADDRESS"] == "a@b.de"
