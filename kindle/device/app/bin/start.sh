#!/bin/sh
# Startet die App losgelöst vom aufrufenden Scriptlet, höchstens einmal gleichzeitig.
PIDFILE=/tmp/aistory.pid
if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then exit 0; fi
DIR=$(cd "$(dirname "$0")" && pwd)
( sleep 1; exec /bin/sh "$DIR/aistory.sh" ) >/dev/null 2>&1 &
echo $! > "$PIDFILE"
