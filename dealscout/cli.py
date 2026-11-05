"""Kommandozeile.

    python -m dealscout run                 # Börsen abfragen, neue Treffer zeigen, Report schreiben
    python -m dealscout list                # gespeicherte Treffer (mit aktueller Config neu bewertet)
    python -m dealscout report              # nur Report (HTML + CSV) neu erzeugen
    python -m dealscout mark KEY interessant --note "Anrufen"
    python -m dealscout run --mail          # Tageslauf: wie run, plus Sammelmail bei neuen Treffern
    python -m dealscout testmail            # Probemail mit den 3 besten aktuellen Treffern
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .config import load_config
from .pipeline import evaluate, run
from .report import print_table, write_csv, write_html
from .storage import STATUSES, Store


def _write_reports(cfg, rows, new_keys=None) -> tuple[Path, Path]:
    out = Path(cfg.report_dir)
    html_path, csv_path = out / "report.html", out / "report.csv"
    write_html(rows, html_path, new_keys)
    write_csv(rows, csv_path)
    return html_path, csv_path


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="dealscout", description="Unternehmensbörsen nach passenden Übernahmezielen durchsuchen")
    p.add_argument("-c", "--config", default="config.yaml", help="Pfad zur Konfiguration (Standard: config.yaml)")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)

    pr = sub.add_parser("run", help="Börsen abfragen")
    pr.add_argument("--source", action="append", help="nur diese Börse (mehrfach möglich): nexxt_change, dub")
    pr.add_argument("--refresh", action="store_true", help="Detailseiten auch für bekannte Inserate neu laden")
    pr.add_argument("--limit", type=int, default=30)
    pr.add_argument("--mail", action="store_true", help="Sammelmail bei neuen passenden Inseraten (Gmail, .env)")

    sub.add_parser("testmail", help="Probemail mit den 3 besten aktuellen Treffern an dich selbst")

    pl = sub.add_parser("list", help="gespeicherte Treffer anzeigen")
    pl.add_argument("--limit", type=int, default=30)

    sub.add_parser("report", help="HTML/CSV-Report neu erzeugen")

    pm = sub.add_parser("mark", help="Status eines Inserats setzen")
    pm.add_argument("key", help="z.B. nexxt-change:660031")
    pm.add_argument("status", choices=STATUSES)
    pm.add_argument("--note")

    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(levelname)s %(message)s")

    cfg_path = Path(args.config)
    if not cfg_path.exists():
        print(f"Konfiguration {cfg_path} fehlt. Anlegen mit:  cp config.example.yaml config.yaml", file=sys.stderr)
        return 2
    cfg = load_config(cfg_path)
    store = Store(cfg.database)
    from . import mail
    mail.load_env(cfg_path.parent / ".env")

    if args.cmd == "run":
        run_id = store.run_started()
        try:
            res = run(cfg, store, only=args.source, refresh=args.refresh)
        except Exception as e:
            store.run_finished(run_id, error=str(e))
            raise
        rows = evaluate(cfg, store)
        new_good = [r for r in rows if r.listing.key in res.new_keys and not r.reject]
        print(
            f"\n{res.seen} Inserate gesehen, {res.in_region} in der Region, "
            f"{len(res.new_keys)} neu ({len(new_good)} davon passend).\n"
        )
        print_table(rows, res.new_keys, limit=args.limit)
        h, c = _write_reports(cfg, rows, res.new_keys)
        print(f"Report: {h}  |  {c}")
        mailed, mail_error = 0, None
        if args.mail:
            try:
                mailed = mail.notify(rows, res.new_keys)
                print(f"Mail: {mailed} neue Angebote gemeldet" if mailed else "Mail: nichts Neues, keine Mail")
            except Exception as e:
                mail_error = f"Mail fehlgeschlagen: {e}"
                print(mail_error, file=sys.stderr)
        for err in res.errors:
            print(f"WARNUNG: {err}", file=sys.stderr)
        store.run_finished(run_id, seen=res.seen, new=len(new_good), mailed=mailed,
                           error="; ".join(filter(None, [mail_error] + res.errors[:5])) or None)
        return 1 if mail_error else 0

    if args.cmd == "testmail":
        rows = [r for r in evaluate(cfg, store) if not r.reject][:3]
        if not rows:
            print("Keine Treffer in der Datenbank – erst 'run' ausführen.", file=sys.stderr)
            return 1
        subject, text, body = mail.build(rows)
        mail.send("TEST – " + subject, text, body)
        print(f"Testmail an {mail.access()[0]} verschickt ({len(rows)} Inserate).")
        return 0

    if args.cmd == "list":
        print_table(evaluate(cfg, store), limit=args.limit)
        return 0

    if args.cmd == "report":
        h, c = _write_reports(cfg, evaluate(cfg, store))
        print(f"Report: {h}  |  {c}")
        return 0

    if args.cmd == "mark":
        if not store.set_status(args.key, args.status, args.note):
            print(f"Unbekannter Schlüssel: {args.key}", file=sys.stderr)
            return 1
        print(f"{args.key} -> {args.status}")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
