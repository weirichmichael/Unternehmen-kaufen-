#!/bin/zsh
# iPhone-Adresse der Weboberfläche über Tailscale – nutzt dasselbe Tailnet wie der ZVG-Agent.
# Der ZVG-Agent belegt https://<mac>.ts.net (Port 443 -> 8000); diese Oberfläche läuft auf Port 8443 -> 8001.
# Aufruf im Terminal:  ~/Projects/unternehmen_kaufen/tailscale_einrichten.sh
cd "$(dirname "$0")" || exit 1
TS=$(command -v tailscale || echo /Applications/Tailscale.app/Contents/MacOS/Tailscale)
[ -x "$TS" ] || { echo "Tailscale nicht gefunden – bitte zuerst aus dem Mac App Store installieren und anmelden."; exit 1; }
"$TS" status >/dev/null 2>&1 || { echo "Tailscale ist nicht verbunden – App öffnen und anmelden."; exit 1; }
NAME=$("$TS" status --json | ./venv/bin/python -c 'import json,sys; print((json.load(sys.stdin).get("Self") or {}).get("DNSName","").rstrip("."))')
[ -n "$NAME" ] || { echo "Kein Tailscale-Name – in der Admin-Konsole MagicDNS einschalten, dann erneut starten."; exit 1; }
# nur im eigenen Tailnet sichtbar (serve, nicht funnel); die ZVG-Freigabe auf Port 443 bleibt unberührt
"$TS" serve --bg --https=8443 8001 || { echo "tailscale serve fehlgeschlagen – HTTPS Certificates in der Admin-Konsole eingeschaltet?"; exit 1; }
BASIS="https://$NAME:8443"
touch .env
if grep -q '^DEALSCOUT_WEB_BASIS=' .env; then sed -i '' "s#^DEALSCOUT_WEB_BASIS=.*#DEALSCOUT_WEB_BASIS=$BASIS#" .env; else echo "DEALSCOUT_WEB_BASIS=$BASIS" >> .env; fi
./betrieb_einrichten.sh
echo ""
echo "Weboberfläche:  $BASIS/"
curl -s -o /dev/null -w "Test über Tailscale vom Mac: HTTP %{http_code}\n" "$BASIS/status" || true
