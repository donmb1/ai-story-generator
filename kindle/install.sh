#!/bin/sh
# Kopiert die App auf den per USB angeschlossenen Kindle (Jailbreak mit Scriptlets, z. B. WinterBreak)
# und trägt Backend-Adressen und Geräte-Token aus backend/.env ein.
#   ./kindle/install.sh ["url1 url2"]    Standard: KINDLE_BACKEND_URLS aus backend/.env
#
# Auf dem Kindle:
#   /mnt/us/aistory/app/     App (aistory.sh, ktap, config.sh)
#   /mnt/us/aistory/hello/   Hello World + Systeminfo
#   /mnt/us/documents/*.sh   Scriptlets – erscheinen als "Bücher" in der Bibliothek
set -e
cd "$(dirname "$0")"
# macOS: /Volumes/Kindle, Linux meist /media/$USER/Kindle
KINDLE=${KINDLE:-/Volumes/Kindle}
[ -d "$KINDLE/documents" ] || { echo "Kindle nicht unter $KINDLE gemountet"; exit 1; }
[ -f ../backend/.env ] || { echo "backend/.env fehlt (Vorlage: backend/.env.example)"; exit 1; }
TOKEN=$(sed -n 's/^DEVICE_TOKEN=//p' ../backend/.env | tr -d '"')
[ -n "$TOKEN" ] || { echo "DEVICE_TOKEN fehlt in backend/.env"; exit 1; }
URLS=${1:-$(sed -n 's/^KINDLE_BACKEND_URLS=//p' ../backend/.env | tr -d '"')}
[ -n "$URLS" ] || { echo 'Backend-Adresse fehlt: KINDLE_BACKEND_URLS="http://<server-ip>:8787" in backend/.env oder als Argument'; exit 1; }

mkdir -p "$KINDLE/aistory/stories"
# Kalibrierung vom Gerät behalten, falls schon gesetzt
OLD_FLAGS=$(sed -n 's/^TOUCH_FLAGS=//p' "$KINDLE/aistory/app/config.sh" 2>/dev/null || true)
for part in app hello; do
  rm -rf "$KINDLE/aistory/$part"
  cp -R "device/$part" "$KINDLE/aistory/$part"
done
CFG="$KINDLE/aistory/app/config.sh"
# sed ohne -i, damit es mit BSD- (macOS) und GNU-sed (Linux) gleich funktioniert
sed -e "s|^BACKEND_URLS=.*|BACKEND_URLS=\"$URLS\"|" -e "s|^DEVICE_TOKEN=.*|DEVICE_TOKEN=\"$TOKEN\"|" "$CFG" > "$CFG.tmp"
if [ -n "$OLD_FLAGS" ] && [ "$OLD_FLAGS" != '""' ]; then
  sed "s|^TOUCH_FLAGS=.*|TOUCH_FLAGS=$OLD_FLAGS|" "$CFG.tmp" > "$CFG.tmp2" && mv "$CFG.tmp2" "$CFG.tmp"
fi
mv "$CFG.tmp" "$CFG"
cp scriptlets/*.sh "$KINDLE/documents/"
# macOS-Metadaten nicht auf den Kindle schleppen
find "$KINDLE/aistory" "$KINDLE/documents" -name '._*' -delete 2>/dev/null || true
echo "Installiert."
grep -E '^(BACKEND_URLS|TOUCH_FLAGS)' "$KINDLE/aistory/app/config.sh"
ls "$KINDLE/documents"/*.sh
