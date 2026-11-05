#!/bin/zsh
# Richtet den Betrieb ein oder frischt ihn auf (idempotent) – wie beim ZVG-Agenten:
#   Tageslauf 17:30 Uhr (com.weirich.dealscout) und Weboberfläche dauerhaft (com.weirich.dealscout-web).
# Nach Codeänderungen: ./betrieb_einrichten.sh  (startet den Webserver mit dem neuen Code neu)
cd "$(dirname "$0")" || exit 1
[ -x venv/bin/python ] || { python3 -m venv venv && ./venv/bin/pip install -q -r requirements.txt; }
[ -f config.yaml ] || cp config.example.yaml config.yaml
mkdir -p logs ~/Library/LaunchAgents
domain="gui/$(id -u)"
for label in com.weirich.dealscout com.weirich.dealscout-web; do
  cp "$label.plist" ~/Library/LaunchAgents/
  launchctl bootout "$domain/$label" 2>/dev/null
  # launchd gibt einen entladenen Dienst nicht sofort frei - warten und erneut versuchen
  for versuch in 1 2 3 4 5; do
    sleep 2
    if launchctl bootstrap "$domain" ~/Library/LaunchAgents/"$label.plist" 2>/dev/null; then
      echo "geladen: $label"; break
    fi
    launchctl print "$domain/$label" >/dev/null 2>&1 && { echo "bereits geladen: $label"; break; }
    [ $versuch = 5 ] && echo "FEHLER: $label konnte nicht geladen werden"
  done
done
sleep 3
curl -s -o /dev/null -w "Weboberfläche: HTTP %{http_code}\n" http://127.0.0.1:8001/status
