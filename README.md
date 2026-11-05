# dealscout – Unternehmen in der Region finden

Durchsucht Unternehmensbörsen automatisch nach kleinen Unternehmen zum Kauf
(Fokus: Hausverwaltung, Hausmeisterservice, Gebäudedienste – aber auch alles
andere in der Umgebung), bewertet die Treffer nach eigenen Kriterien und merkt
sich, was schon bekannt ist. So sieht man bei jedem Lauf nur das **Neue**.

## Unterstützte Börsen

**Offizielle / Kammern**

| Börse | Regionsfilter | Hinweise |
|---|---|---|
| [nexxt-change.org](https://www.nexxt-change.org) | PLZ + Umkreis (max. 100 km) | Offizielle Nachfolgebörse von KfW/BMWK. **Hier stellen die IHKs, Handwerkskammern, Sparkassen und Volksbanken ihre Inserate ein** – der betreuende Partner („betreut von IHK Reutlingen“) steht im Report. Zusätzlich wird *alles* im Umkreis geholt, nicht nur Suchbegriffe. |

**Private Börsen**

| Börse | Regionsfilter | Hinweise |
|---|---|---|
| [dub.de](https://www.dub.de) | Bundesland | Suche ist unscharf → lokale Bewertung sortiert. Kaufpreis meist nicht angezeigt, dafür Umsatz + Ergebnis. |
| [firma-verkauf.de](https://www.firma-verkauf.de) | Bundesland | Viele Kleinbetriebe mit Preisangabe. Gesuche werden verworfen. |
| [biz-trade.de](https://www.biz-trade.de) | Bundesland + Landkreis | Max. ~40 Treffer je Suchbegriff. Gesuche werden verworfen. |
| [kleinanzeigen.de](https://www.kleinanzeigen.de) | PLZ + Umkreis | Privatverkäufe (Imbiss, Friseur, Kiosk, Hausmeisterservice …). Gesucht wird nur in den Rubriken *Gewerbeimmobilien* und *Weitere Dienstleistungen*, und nur Anzeigen mit Verkaufsabsicht („abzugeben“, „Nachfolger“, „Übernahme“ …) werden übernommen. |

**Bewusst nicht dabei**

- *Unternehmensbörse Handwerk BW* (nachfolge-im-handwerk.de): Inserate nur nach (kostenloser) Registrierung sichtbar; viele erscheinen zusätzlich auf nexxt-change.
- *IHK-eigene Listen* (z. B. IHK München, Oldenburg): vertrauliche Vermittlung per Fragebogen/Chiffre-Liste, keine öffentliche Inseratsseite.
- *viaductus.de*: Aggregator-Suche nur mit Login. *con|cess* ist zu matchbridge.de umgezogen, *firmenzukaufen.de* lädt Inserate nur per JavaScript – Kandidaten für später.

## Schnellstart

```bash
pip install -e .            # oder: pip install requests beautifulsoup4 PyYAML
cp config.example.yaml config.yaml
# config.yaml öffnen: PLZ, Radius, Bundesländer, Suchbegriffe, Preisgrenze anpassen

python -m dealscout run     # Börsen abfragen -> Tabelle + reports/report.html + reports/report.csv
```

Der erste Lauf dauert ein paar Minuten, weil für jedes Inserat die Detailseite
(Preis, Umsatz, Beschreibung) geladen wird – mit Pause zwischen den Anfragen.
Folgeläufe laden nur noch Details für neue Inserate.

## Befehle

```bash
python -m dealscout run                     # alle Börsen
python -m dealscout run --source nexxt_change
python -m dealscout run --source kleinanzeigen --source biz_trade
python -m dealscout list                    # gespeicherte Treffer, mit aktueller Config neu bewertet
python -m dealscout report                  # nur HTML/CSV neu erzeugen (z.B. nach Config-Änderung)
python -m dealscout mark nexxt-change:751046 interessant --note "Exposé angefordert"
python -m dealscout mark dub:abc... verworfen
```

Status: `neu`, `interessant`, `kontaktiert`, `verworfen` (verworfene werden im Report ausgeblendet).

## Bewertung

- **Region**: nexxt-change filtert selbst per PLZ/Umkreis; bei DUB zählt das Bundesland.
- **Score**: Summe der Gewichte aus `scoring.keywords`, die im Titel/Branche/Text vorkommen (Titel zählt doppelt).
- **Filter**: `filters.price_max` usw. schließen nur aus, wenn der Wert *sicher* drüber liegt
  (Inserate ohne Preisangabe bleiben drin).
- `scoring.exclude`: Begriffe, die ein Inserat ausblenden (z.B. „insolvenz").

Bewertung und Filter werden bei `list`/`report` immer mit der aktuellen
`config.yaml` neu berechnet – Config ändern, `report` laufen lassen, fertig.

## Neue Börse hinzufügen

1. `dealscout/sources/<name>.py` mit einer Klasse, die von `Source` erbt
   (`search()` liefert `Listing`s aus der Trefferliste, `fetch_details()` ergänzt die Detailseite).
2. In `dealscout/sources/__init__.py` in `SOURCES` eintragen.
3. In `config.yaml` unter `sources:` aktivieren.
4. Parser-Test mit einem kleinen HTML-Ausschnitt in `tests/test_sources.py`.

## Fair bleiben

- Anfragen sind gedrosselt (`delay_seconds`, Standard 1,5 s) – bitte nicht runterdrehen.
- `robots.txt` wird respektiert (bei DUB z.B. nur öffentliche Such- und Exposé-Seiten, nicht `/app/` oder `/api/`).
- Nur für die private Suche gedacht; Inseratsinhalte nicht weiterveröffentlichen.
  Nutzungsbedingungen der jeweiligen Börse beachten.

## Tests

```bash
pip install pytest && python -m pytest -q
```
