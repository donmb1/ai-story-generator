#!/bin/sh
# Startet das Backend im Heimnetz. Liest backend/.env, falls vorhanden.
cd "$(dirname "$0")"
[ -f .env ] && { set -a; . ./.env; set +a; }
[ -x .venv/bin/uvicorn ] || { python3 -m venv .venv && .venv/bin/pip install -r requirements.txt; }
exec .venv/bin/uvicorn app.main:app --host "${HOST:-0.0.0.0}" --port "${PORT:-8787}" --no-access-log
