"""Parser-Tests gegen minimale, nachgebaute HTML-Ausschnitte der Börsen.

Wenn eine Börse ihr Layout ändert, schlagen zuerst die Live-Läufe fehl –
dann hier das neue Markup nachbauen und den Parser anpassen.
"""

from dealscout.models import Listing
from dealscout.scoring import Criteria, in_region, rejection_reason, score
from dealscout.sources import dub, nexxt_change
from dealscout.sources.base import Region

NEXXT_LIST = """
<ol class="inserate-liste">
 <li class="inserat-list-item"><div class="card"><div class="card-block">
  <p class="card-topline"><span class="date">04.11.2026</span></p>
  <h3 class="card-title"><a href="https://www.nexxt-change.org/DE/Verkaufsangebot/Detailseite/detailseite_jsp?adId=123">Hausmeisterservice abzugeben</a></h3>
  <p class="card-topline card-topline--secondary"> Gebäudebetreuung </p>
  <p class="card-short-text inserat-teaser">Kleiner Betrieb mit Stammkunden.</p>
  <p class="card-topline card-topline--secondary"> Baden-W&uuml;rttemberg
      / T&uuml;bingen
      / Reutlingen </p>
 </div></div></li>
</ol>
<ul class="pagination">
 <li><span class="pagination-link active">1</span></li>
 <li><a class="pagination-link" href="https://www.nexxt-change.org/x?gtp=%2526abc_list%253D2&amp;ad_radius=50">2</a></li>
</ul>
"""

NEXXT_DETAIL = """
<main>
 <dl class="print-only"><dt>Chiffre:</dt><dd>EX-A-1-2026</dd></dl>
 <h3>Beschreibung</h3>
 <p>Toller Betrieb.<br>Kaufpreis: 120.000 € VHB</p>
 <div class="detail-item details-unternehmen rich-text">
  <dl class="lined">
   <dt> Standort : </dt><dd><ul><li>Baden-Württemberg > Tübingen > Reutlingen</li></ul></dd>
   <dt>Anzahl Mitarbeiter:</dt><dd> bis 5 Beschäftigte </dd>
   <dt>Letzter Jahresumsatz:</dt><dd> &uuml;ber 250 - 500 Tsd. Euro </dd>
   <dt>Preisvorstellung:</dt><dd> &uuml;ber 50 - 250 Tsd. Euro </dd>
   <dt>Exposé:</dt><dd><a href="/cae/servlet/pdfs/1/expose.pdf">PDF</a></dd>
  </dl>
 </div>
</main>
"""

DUB_LIST = """
<table><tbody>
<tr data-listing-card data-listing-id="abc-1">
 <td><a href="/de/unternehmen-kaufen/expose/hausmeister-xy/?src=search" title="Hausmeister XY"><span>Hausmeister XY</span></a></td>
 <td><a title="500.000 €">500.000&nbsp;€</a></td>
 <td><a title="115.000 €">115.000&nbsp;€</a></td>
 <td><a title="Keine Angabe">Keine Angabe</a></td>
 <td><a title="Bayern">Bayern</a></td>
</tr>
</tbody></table>
"""

DUB_DETAIL = """
<span class="dub-hero__pill dub-hero__pill--ref">Dienstleistungen</span>
<div data-testid="metric-cell"><span class="dub-kpi-label">Umsatz</span><span class="dub-kpi-value">500.000 €</span></div>
<div data-testid="metric-cell"><span class="dub-kpi-label">Mitarbeiter</span><span class="dub-kpi-value">10</span></div>
<div data-testid="metric-cell"><span class="dub-kpi-label">Standort</span><span class="dub-kpi-value">Bayern</span></div>
<section data-testid="company-description"><div class="ld-card__body"><p>Winterdienst und Grünpflege.</p></div></section>
"""


def test_nexxt_list_and_detail():
    listings, nxt = nexxt_change.parse_search_page(NEXXT_LIST)
    assert len(listings) == 1
    l = listings[0]
    assert l.source_id == "123"
    assert l.date == "2026-11-04"
    assert l.location == "Baden-Württemberg / Tübingen / Reutlingen"
    assert l.industry == "Gebäudebetreuung"
    assert nxt and "_list%253D2" in nxt

    l = nexxt_change.parse_detail_page(NEXXT_DETAIL, l)
    assert l.revenue_min == 250_000 and l.revenue_max == 500_000
    assert l.price_min == l.price_max == 120_000  # expliziter Kaufpreis schlägt Spanne
    assert l.employees == "bis 5 Beschäftigte"
    assert l.extra["chiffre"] == "EX-A-1-2026"
    assert l.extra["expose_pdf"].endswith("/expose.pdf")
    assert "Toller Betrieb" in l.description


def test_dub_list_and_detail():
    (l,) = dub.parse_search_page(DUB_LIST)
    assert l.source_id == "abc-1"
    assert l.url == "https://www.dub.de/de/unternehmen-kaufen/expose/hausmeister-xy/"
    assert l.revenue_min == 500_000
    assert l.earnings_value == 115_000
    assert l.employees is None
    l = dub.parse_detail_page(DUB_DETAIL, l)
    assert l.employees == "10"
    assert l.industry == "Dienstleistungen"
    assert "Winterdienst" in l.description


def _l(**kw):
    base = dict(source="dub", source_id="1", url="u", title="t")
    base.update(kw)
    return Listing(**base)


def test_region_filter():
    region = Region(plz="72555", bundeslaender=["Baden-Württemberg"])
    assert in_region(_l(location="Baden-Württemberg"), region, False)
    assert not in_region(_l(location="Bayern"), region, False)
    assert not in_region(_l(location="Deutschland"), region, False)
    assert in_region(_l(location="Bayern"), region, True)  # Börse hat Umkreis schon gefiltert


def test_scoring_and_rejection():
    c = Criteria(keywords={"hausmeister": 10, "winterdienst": 4}, exclude=["insolvenz"], price_max=300_000)
    l = score(_l(title="Hausmeisterservice", teaser="mit Winterdienst"), c)
    assert l.score == 24 and l.matched == ["hausmeister", "winterdienst"]
    assert rejection_reason(l, c) is None
    assert rejection_reason(_l(title="x", price_min=400_000), c)
    assert rejection_reason(_l(title="x", teaser="aus Insolvenz"), c)


def test_wanted_ads_are_rejected():
    from dealscout.scoring import is_wanted_ad

    wanted = [
        _l(title="Handwerksbetrieb oder Hausverwaltung zur Übernahme / Beteiligung",
           description="Handwerksbetrieb oder Hausverwaltung zur Übernahme / Beteiligung gesucht\n"
                       "Wir suchen im Raum Mannheim einen bestehenden Handwerksbetrieb."),
        _l(title="Hausverwaltung", description="Wir suchen eine Hausverwaltung zum Kauf."),
        _l(title="Gebäudereinigung zum Kauf gesucht"),
    ]
    offers = [
        _l(title="Hausmeisterservice Raum Riedstadt sucht Nachfolger"),
        _l(title="Reparaturwerkstatt", description="Wir suchen einen Nachfolger für unser Einzelunternehmen."),
        _l(title="Nachfolger für Buchhandlung gesucht"),
        _l(title="Gebäudereinigung", description="Käufer zur Übernahme unseres Dienstleistungsservices gesucht"),
        _l(title="Maler und Lackierbetrieb", description="Für meinen Betrieb suche ich einen Nachfolger."),
    ]
    assert all(is_wanted_ad(l) for l in wanted)
    assert not any(is_wanted_ad(l) for l in offers)


def test_exclude_title_with_exception():
    rule = {"terms": ["gebäudereinigung"], "unless": ["hausmeister"], "reason": "Gebäudereinigung (ausgeschlossen)"}
    c = Criteria(exclude_title=[rule])
    assert rejection_reason(_l(title="Gebäudereinigung zu verkaufen"), c).startswith("Gebäudereinigung (ausgeschlossen)")
    assert rejection_reason(_l(title="Hausmeisterservice / Gebäudereinigung"), c) is None
    assert rejection_reason(_l(title="Hausverwaltung", teaser="inkl. Treppenhausreinigung"), c) is None


def test_focus_targets_meisterpflicht_and_notes():
    from dealscout.config import load_config

    c = load_config("config.example.yaml").criteria

    def judge(**kw):
        l = score(_l(**kw), c)
        return rejection_reason(l, c), l.extra.get("einstieg")

    # Zielbranchen bleiben, mit Einstiegshinweis
    assert judge(title="Rohr- und Kanalreinigungsbetrieb abzugeben") == (None, "zulassungsfrei (handwerksähnlich)")
    assert judge(title="Hausmeisterservice sucht Nachfolger") == (None, "zulassungsfrei")
    reason, note = judge(title="Kleine Hausverwaltung zu verkaufen")
    assert reason is None and "34c" in note
    # Meisterpflicht raus – auch über die Branchenangabe der Börse
    assert judge(title="Fachbetrieb für Heizung und Sanitär", teaser="Kunden sind Hausverwaltungen")[0].startswith("Meisterpflicht")
    assert judge(title="Etablierter Betrieb sucht Nachfolger", industry="Elektroinstallation",
                 teaser="Wartung für Hausverwaltung")[0].startswith("Meisterpflicht")
    # ... außer der Hausmeister-Teil steht im Titel
    assert judge(title="Hausmeisterservice & Malerarbeiten")[0] is None
    # Zielbranche nur im Langtext zählt nicht
    assert judge(title="Bau- und Sanierungsunternehmen", description="Unsere Kunden sind Hausverwaltungen.")[0] == "keine Zielbranche"
    # fremde Branche ohne Zielbezug
    assert judge(title="Imbiss abzugeben")[0] == "keine Zielbranche"
    assert judge(title="Hausverwaltung für Arztpraxen")[0] is None  # Ausnahme: Hausverwaltung im Titel
    assert judge(title="Physiotherapiepraxis mit Hausmeisterdienst")[0] is None  # unless: hausmeister


def test_subscores_leverage_entry_hurdles_size():
    from dealscout.config import load_config
    from dealscout.scoring import employee_count

    c = load_config("config.example.yaml").criteria
    l = score(_l(title="Rohrreinigung abzugeben", employees="6 - 10 Beschäftigte",
                 description="Aufträge kommen über Mundpropaganda, Rechnungen noch auf Papier. "
                             "Wartungsverträge mit Hausverwaltungen. Einarbeitung durch den Inhaber, "
                             "eingespieltes Team. Branchenerfahrung nicht zwingend erforderlich."), c)
    t = l.extra["teilscores"]
    assert t["hebel"] >= 10 and t["einstieg"] >= 10 and t["groesse"] == 4
    assert t["huerden"] == 0  # "nicht zwingend erforderlich" ist keine Hürde
    assert "papier" in l.extra["signale"]["hebel"]
    assert "Online-Terminbuchung" in l.extra["hebel_ideen"] and "Monate" in l.extra["einarbeitung"]

    l = score(_l(title="Hausmeisterservice", description="Meisterbrief erforderlich. Regelmäßig Aufträge."), c)
    assert l.extra["teilscores"]["huerden"] < 0
    assert "regelmässig" in " ".join(l.extra["signale"]["hebel"])  # ß-Normalisierung greift

    assert employee_count("6 - 10 Beschäftigte") == (6, 10)
    assert employee_count("bis 5 Beschäftigte") == (1, 5)
    assert employee_count("Einzelunternehmen") == (1, 1)
    assert employee_count("Nicht veröffentlicht") == (None, None)
