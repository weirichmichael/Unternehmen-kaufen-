"""Parser-Tests für die privaten Börsen (Kleinanzeigen, firma-verkauf, biz-trade)."""

from dealscout.models import Listing
from dealscout.sources import biz_trade, firma_verkauf, kleinanzeigen
from dealscout.sources.nexxt_change import parse_detail_page as nexxt_detail

KA_LIST = """
<article class="flex" data-adid="111" data-href="/s-anzeige/hausmeisterservice-abzugeben/111-298-1">
 <script type="application/ld+json">{"title":"Hausmeisterservice abzugeben","description":"Kleiner Betrieb, fester Kundenstamm"}</script>
 <div><span>72764 Reutlingen</span><span class="ml-xsmall">(12 km)</span></div>
 <div><span>03.11.2026</span></div>
 <p class="text-title3">15.000 € VB</p>
</article>
<article class="flex" data-adid="222" data-href="/s-anzeige/rollator/222-1-1">
 <script type="application/ld+json">{"title":"Rollator abzugeben (Firma X)","description":"kaum benutzt"}</script>
 <div><span>13435 Berlin</span><span>(534 km)</span></div>
</article>
"""

FV_LIST = """
<article class="box bg-primary layout-common"><a href="/adv/808574">
 <header class="f-row"><span>Gebot</span><span><img/> PLZ: Baden-Württemberg </span></header>
 <h2 class="box-title">Hausmeisterservice Verkauf</h2><p class="box-desc">Kleiner Kundenstamm</p>
 <footer><p>ID: #123 Einzelunternehmen</p><p>Unternehmensverkauf</p></footer></a></article>
<article class="box bg-primary layout-common"><a href="/adv/999">
 <header class="f-row"><span>Gesuch</span><span>PLZ: Bayern</span></header>
 <h2 class="box-title">Suche Hausmeisterservice</h2><p class="box-desc">x</p>
 <footer><p>ID: #9</p><p>Unternehmensverkauf</p></footer></a></article>
"""

FV_DETAIL = """
<div class="vf-details-main"><section><dl>
 <dt>Branche</dt><dd>Dienstleistung</dd>
 <dt>Region</dt><dd><img/> DE <i></i> Baden-Württemberg</dd>
 <dt>Jahresumsatz</dt><dd>Bis 249.999,00
     <span>EURO</span></dd>
 <dt>Preisvorstellung</dt><dd><span>50000 EURO</span></dd>
</dl></section><article><p class="vf-detailed-description">Ich verkaufe meinen Betrieb.</p></article></div>
"""

BT_LIST = """
<div class="adsxs"><p><i><i>Biete</i></i><br></p>
 <span style='display:block; font-weight:bold;'>Unternehmensverkauf</span>
 <div><div id="descr"><span><a title="Gebäudereinigung / Hausmeisterservice" href="ma-22387.htm">Gebäudereinigung</a></span></div>
 <div class="descr-caption">Sehr guter Kundenstamm<br>-----<br>Baden-Württemberg</div></div>
 <span style='position: relative; z-index: 2; font-size: 0.9rem;'>Dienstleistung&nbsp;</span><br>
 <span><i class="fas fa-users"></i> <i>10 bis 20 Mitarbeiter&nbsp;</i><br>
 <img src="flags/de.png"/> Landkreis Esslingen&nbsp;<br></span></div>
<div class="adsxs"><p><i><i>Suche</i></i></p>
 <span style='font-weight:bold;'>Unternehmenskauf</span>
 <a title="Personaldienstleister" href="ma-1.htm">x</a><img src="flags/de.png"/> Gelsenkirchen</div>
"""

BT_DETAIL = """
<div itemprop='description'>Verkaufe aus gesundheitlichen Gründen.</div>
<div class='sectiondetail2'><div class='sectionlabel'>Umsatzklasse</div><div>250 Tsd. bis 1 Mio. Euro</div></div>
<div class='sectiondetail2'><div class='sectionlabel'>Preisvorstellung €(EUR)</div><div itemprop='price'>900.000</div></div>
<div class='sectiondetail1'><div class='sectionlabel'>Region</div><div>73 / <img/> Deutschland</div></div>
<div class='sectiondetail1'><div class='sectionlabel'>Bundesland > Kreis</div><div><a>Baden-Württemberg</a> > Landkreis Esslingen</div></div>
"""

NEXXT_PARTNER = """
<section class="margin-details-zusatz-box info-box inserate-info-box">
 <h3 class="box-headline">Regionalpartner</h3>
 <div class="box-wrapper"><figure></figure><p>IHK Nordschwarzwald</p><p>Pforzheim</p></div>
</section>
"""


def test_kleinanzeigen_list():
    ls = kleinanzeigen.parse_search_page(KA_LIST)
    assert [l.source_id for l in ls] == ["111", "222"]
    l = ls[0]
    assert l.title == "Hausmeisterservice abzugeben"
    assert l.location == "72764 Reutlingen"
    assert l.extra["entfernung"] == "12 km"
    assert l.date == "2026-11-03"
    assert l.price_min == 15_000
    assert kleinanzeigen.distance_km(ls[1]) == 534


def test_kleinanzeigen_sale_intent():
    yes = ["Hausmeisterservice abzugeben", "Nachfolger gesucht oder komplette Ablöse!", "Friseursalon zu verkaufen"]
    no = ["Hotel in Stuttgart gesucht – Pacht/Kauf", "Suche Hausmeisterservice zum Kauf",
          "Hausmeister (m/w/d) in Teilzeit", "Hausverwaltung mit freien Kapazitäten"]
    assert all(kleinanzeigen.has_sale_intent(t, t) for t in yes)
    assert not any(kleinanzeigen.has_sale_intent(t, t) for t in no)


def test_firma_verkauf():
    offer, wanted = firma_verkauf.parse_search_page(FV_LIST)
    assert offer.source_id == "808574" and offer.location == "Baden-Württemberg"
    assert firma_verkauf.is_offer(offer) and not firma_verkauf.is_offer(wanted)
    d = firma_verkauf.parse_detail_page(FV_DETAIL, offer)
    assert d.revenue_max == 249_999 and d.revenue_min is None
    assert d.price_min == 50_000
    assert d.description == "Ich verkaufe meinen Betrieb."


def test_biz_trade():
    offer, wanted = biz_trade.parse_search_page(BT_LIST)
    assert offer.source_id == "22387"
    assert offer.title == "Gebäudereinigung / Hausmeisterservice"
    assert offer.location == "Baden-Württemberg / Landkreis Esslingen"
    assert offer.employees == "10 bis 20 Mitarbeiter"
    assert biz_trade.is_offer(offer) and not biz_trade.is_offer(wanted)
    d = biz_trade.parse_detail_page(BT_DETAIL, offer)
    assert d.price == "900.000 €" and d.price_min == 900_000
    assert (d.revenue_min, d.revenue_max) == (250_000, 1_000_000)
    assert d.extra["plz_bereich"] == "73"


def test_nexxt_regionalpartner():
    l = nexxt_detail(NEXXT_PARTNER, Listing(source="nexxt-change", source_id="1", url="u", title="t"))
    assert l.extra["regionalpartner"] == "IHK Nordschwarzwald"


def test_kleinanzeigen_service_offer_is_not_a_sale():
    assert not kleinanzeigen.has_sale_intent("Winterdienst? Wir übernehmen das!", "Winterdienst? Wir übernehmen das!")
    assert kleinanzeigen.has_sale_intent("Schlüsseldienst zu übernehmen", "Schlüsseldienst zu übernehmen")
