from .base import Region, Source
from .biz_trade import BizTrade
from .dub import Dub
from .firma_verkauf import FirmaVerkauf
from .kleinanzeigen import Kleinanzeigen
from .nexxt_change import NexxtChange

# config-Schlüssel -> Klasse. Neue Börse: Klasse schreiben und hier eintragen.
SOURCES: dict[str, type[Source]] = {
    "nexxt_change": NexxtChange,
    "dub": Dub,
    "firma_verkauf": FirmaVerkauf,
    "biz_trade": BizTrade,
    "kleinanzeigen": Kleinanzeigen,
}

__all__ = ["SOURCES", "Region", "Source"]
