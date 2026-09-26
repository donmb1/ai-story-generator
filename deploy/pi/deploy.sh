#!/bin/sh
# Überträgt das Backend per rsync auf den Server (z. B. Raspberry Pi) und baut/startet den Container.
#
#   PI=user@host ./deploy/pi/deploy.sh
#
# Oder PI (und optional DEST) in deploy/pi/deploy.conf eintragen (wird nicht eingecheckt):
#   PI=user@raspberrypi.local
#   DEST=ai-story
set -e
cd "$(dirname "$0")/../.."
[ -f deploy/pi/deploy.conf ] && . deploy/pi/deploy.conf
[ -n "$PI" ] || { echo "PI=user@host setzen (oder deploy/pi/deploy.conf anlegen)"; exit 1; }
DEST=${DEST:-ai-story}
ssh "$PI" "mkdir -p $DEST/deploy/pi"
rsync -az --delete \
  --exclude .venv --exclude data --exclude .env --exclude preview --exclude __pycache__ --exclude tests \
  backend/ "$PI:$DEST/backend/"
rsync -az deploy/pi/docker-compose.yml deploy/pi/env.example "$PI:$DEST/deploy/pi/"
ssh "$PI" "cd $DEST/deploy/pi && [ -f .env ] || { echo '.env fehlt auf dem Server (Vorlage: env.example)'; exit 1; }; \
  . ./.env && mkdir -p data && docker compose up -d --build && sleep 3 && docker compose ps && \
  curl -fsS http://\$LAN_IP:8787/health; echo"
