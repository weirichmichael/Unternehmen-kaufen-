"""Tests für die Verortung mit einem Mini-Datensatz (keine Netzwerkzugriffe)."""

from dealscout.geo import Geo, annotate_distance, within
from dealscout.models import Listing

ROWS = [
    # plz, ort, kreis, lat, lon
    ("69250", "Schönau", "Rhein-Neckar-Kreis", 49.4366, 8.8088),
    ("69117", "Heidelberg", "Stadtkreis Heidelberg", 49.41, 8.69),
    ("69118", "Heidelberg", "Stadtkreis Heidelberg", 49.42, 8.73),
    ("69120", "Heidelberg", "Stadtkreis Heidelberg", 49.42, 8.67),
    ("64521", "Groß-Gerau", "Landkreis Groß-Gerau", 49.92, 8.48),
    ("68159", "Mannheim", "Stadtkreis Mannheim", 49.49, 8.46),
    ("68161", "Mannheim", "Stadtkreis Mannheim", 49.49, 8.47),
    ("68163", "Mannheim", "Stadtkreis Mannheim", 49.47, 8.48),
    ("88045", "Friedrichshafen", "Bodenseekreis", 47.65, 9.48),
    ("88046", "Friedrichshafen", "Bodenseekreis", 47.66, 9.47),
    ("88048", "Friedrichshafen", "Bodenseekreis", 47.67, 9.50),
    ("06333", "Hessen", "Landkreis Harz", 51.98, 10.78),  # Dorf "Hessen" – darf nicht greifen
]


def geo():
    return Geo(ROWS)


def _l(**kw):
    base = dict(source="dub", source_id="1", url="u", title="Betrieb")
    base.update(kw)
    return Listing(**base)


def locate(**kw):
    g = geo()
    l = _l(**kw)
    km = annotate_distance(l, g, g.plz_coord("69250"))
    return l, km


def test_plz_in_location():
    l, km = locate(source="kleinanzeigen", location="69117 Baden-Württemberg - Heidelberg")
    assert l.extra["ort_genauigkeit"].startswith("plz") and km < 15
    assert within(l, 50) is True


def test_landkreis():
    l, km = locate(source="biz-trade", location="Hessen / Landkreis Groß-Gerau")
    assert l.extra["ort_genauigkeit"].startswith("landkreis") and 50 < km < 70
    assert within(l, 50) is True  # Toleranz für Kreis-Mittelpunkt


def test_nexxt_skips_regierungsbezirk():
    l, _ = locate(source="nexxt-change", location="Baden-Württemberg / Karlsruhe")
    assert l.extra["ort_genauigkeit"] == "unbekannt"
    l, _ = locate(source="nexxt-change", location="Baden-Württemberg / Karlsruhe / Heidelberg")
    assert l.extra["ort_genauigkeit"].startswith(("landkreis", "ort"))


def test_bundesland_is_not_a_place():
    l, km = locate(location="Hessen")
    assert km is None and within(l, 50) is None


def test_region_alias_and_city_in_text():
    l, km = locate(location="Baden-Württemberg", title="Gebäudeservice am Bodensee")
    assert l.extra["ort_genauigkeit"].startswith("text") and km > 150
    assert within(l, 50) is False
    l, km = locate(location="Baden-Württemberg", title="Reinigungsfirma im Raum Mannheim")
    assert km < 40 and within(l, 50) is True
