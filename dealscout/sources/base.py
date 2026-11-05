from __future__ import annotations

import abc
from collections.abc import Iterator
from dataclasses import dataclass, field

from ..http import PoliteSession
from ..models import Listing


@dataclass
class Region:
    plz: str | None = None
    radius_km: int = 50
    bundeslaender: list[str] = field(default_factory=list)
    include_unknown_location: bool = False
    # Inserate, bei denen nur das Bundesland bekannt ist: "keep" (anzeigen, markiert) oder "drop"
    unknown_distance: str = "keep"


class Source(abc.ABC):
    """Eine Unternehmensbörse. Neue Börsen = neue Unterklasse + Eintrag in SOURCES."""

    name: str = "?"

    def __init__(self, http: PoliteSession, max_pages: int = 5, options: dict | None = None):
        self.http = http
        self.max_pages = max_pages
        self.options = options or {}

    def queries(self, general: list[str]) -> list[str]:
        """Suchbegriffe für diese Börse: eigene aus der Config (`queries`) oder die allgemeinen."""
        own = self.options.get("queries")
        return list(own) if own else list(general)

    @abc.abstractmethod
    def search(self, query: str | None, region: Region) -> Iterator[Listing]:
        """Liefert Inserate aus der Trefferliste (ohne Detailabruf).

        `query=None` bedeutet: alles in der Region (sofern die Börse das kann).
        """

    @abc.abstractmethod
    def fetch_details(self, listing: Listing) -> Listing:
        """Ergänzt ein Inserat um Daten der Detailseite."""

    def supports_radius(self) -> bool:
        """True, wenn die Börse selbst nach PLZ + Umkreis filtert."""
        return False

    def supports_browse_all(self) -> bool:
        """True, wenn eine Suche ohne Suchbegriff sinnvoll ist."""
        return False
