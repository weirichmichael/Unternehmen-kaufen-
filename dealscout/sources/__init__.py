from .base import Region, Source
from .dub import Dub
from .nexxt_change import NexxtChange

# config-Schlüssel -> Klasse. Neue Börse: Klasse schreiben und hier eintragen.
SOURCES: dict[str, type[Source]] = {
    "nexxt_change": NexxtChange,
    "dub": Dub,
}

__all__ = ["SOURCES", "Region", "Source"]
