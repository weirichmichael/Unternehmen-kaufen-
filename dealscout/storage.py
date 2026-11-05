"""SQLite-Ablage: merkt sich, welche Inserate wir schon kennen, plus eigene Notizen/Status."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from .models import Listing

STATUSES = ("neu", "interessant", "kontaktiert", "verworfen")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS listings (
    key            TEXT PRIMARY KEY,
    source         TEXT NOT NULL,
    data           TEXT NOT NULL,
    first_seen     TEXT NOT NULL,
    last_seen      TEXT NOT NULL,
    details_at     TEXT,
    status         TEXT NOT NULL DEFAULT 'neu',
    note           TEXT
);
"""


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class Store:
    def __init__(self, path: str | Path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path))
        self.db.row_factory = sqlite3.Row
        self.db.executescript(_SCHEMA)

    def get(self, key: str) -> sqlite3.Row | None:
        return self.db.execute("SELECT * FROM listings WHERE key = ?", (key,)).fetchone()

    def load(self, row: sqlite3.Row) -> Listing:
        return Listing(**json.loads(row["data"]))

    def has_details(self, key: str) -> bool:
        row = self.get(key)
        return bool(row and row["details_at"])

    def upsert(self, listing: Listing, details: bool = False) -> bool:
        """Speichert ein Inserat. Gibt True zurück, wenn es neu war."""
        now = _now()
        row = self.get(listing.key)
        data = json.dumps(listing.to_dict(), ensure_ascii=False)
        if row is None:
            self.db.execute(
                "INSERT INTO listings (key, source, data, first_seen, last_seen, details_at) VALUES (?,?,?,?,?,?)",
                (listing.key, listing.source, data, now, now, now if details else None),
            )
            self.db.commit()
            return True
        if not details and row["details_at"]:
            # Detaildaten nicht mit der dünneren Listenansicht überschreiben
            self.db.execute("UPDATE listings SET last_seen = ? WHERE key = ?", (now, listing.key))
        else:
            self.db.execute(
                "UPDATE listings SET data = ?, last_seen = ?, details_at = COALESCE(?, details_at) WHERE key = ?",
                (data, now, now if details else None, listing.key),
            )
        self.db.commit()
        return False

    def set_status(self, key: str, status: str, note: str | None = None) -> bool:
        if status not in STATUSES:
            raise ValueError(f"Status muss einer von {STATUSES} sein")
        cur = self.db.execute(
            "UPDATE listings SET status = ?, note = COALESCE(?, note) WHERE key = ?", (status, note, key)
        )
        self.db.commit()
        return cur.rowcount > 0

    def all(self) -> list[sqlite3.Row]:
        return self.db.execute("SELECT * FROM listings ORDER BY first_seen DESC").fetchall()
