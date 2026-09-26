#!/bin/sh
# AI Story Reader – Kindle-Client (BusyBox ash).
#
# Thin Client: Das Backend rendert jeden Bildschirm als PNG und wertet Taps aus.
# Dieses Skript zeigt nur Bilder an, liest Taps (ktap) und blättert Geschichten lokal.

EXT_DIR=$(cd "$(dirname "$0")/.." && pwd)
. "${AISTORY_CONFIG:-$EXT_DIR/config.sh}"

EIPS=${EIPS:-eips}
LIPC_SET=${LIPC_SET:-lipc-set-prop}
LIPC_GET=${LIPC_GET:-lipc-get-prop}
TMP=${AISTORY_TMP:-/tmp/aistory}
LOG="$TMP/aistory.log"
CACHE_DIR=$(dirname "$STORY_DIR")
REFRESH_COUNT=0

mkdir -p "$TMP" "$STORY_DIR"
: > "$LOG"

log() { echo "$(date '+%H:%M:%S') $*" >> "$LOG"; }

# ------------------------------------------------------------------ Anzeige

show() {
    # $1 = PNG. Alle FULL_REFRESH_EVERY Bilder ein voller Refresh gegen Ghosting.
    REFRESH_COUNT=$((REFRESH_COUNT + 1))
    if [ "$REFRESH_COUNT" -ge "${FULL_REFRESH_EVERY:-6}" ] || [ "$2" = full ]; then
        REFRESH_COUNT=0
        $EIPS -f -g "$1" >/dev/null 2>&1
    else
        $EIPS -g "$1" >/dev/null 2>&1
    fi
}

message() {
    # Notfall-Text ohne Server (eips-Rasterschrift, nur ASCII)
    $EIPS -c >/dev/null 2>&1
    row=3
    for line in "$@"; do
        $EIPS 2 $row "$line" >/dev/null 2>&1
        row=$((row + 2))
    done
}

# ------------------------------------------------------------------ HTTP

if command -v curl >/dev/null 2>&1; then HTTP=curl; else HTTP=wget; fi

fetch() {
    # $1 = Pfad inkl. Query, $2 = Zieldatei, $3 = Timeout in s
    url="$BACKEND_URL$1"
    rm -f "$2.part"
    if [ "$HTTP" = curl ]; then
        curl -fsS -m "$3" -H "Authorization: Bearer $DEVICE_TOKEN" -o "$2.part" "$url" 2>>"$LOG"
    else
        case "$1" in *\?*) sep='&' ;; *) sep='?' ;; esac
        wget -q -T "$3" -O "$2.part" "$url${sep}t=$DEVICE_TOKEN" 2>>"$LOG"
    fi
    rc=$?
    if [ $rc -eq 0 ] && [ -s "$2.part" ]; then
        mv "$2.part" "$2"
        return 0
    fi
    rm -f "$2.part"
    log "fetch failed rc=$rc path=${1%%\?*}"
    return 1
}

request() {
    # Holt einen Befehl vom Backend nach CMD A1 A2 A3. Bei Fehler: CMD=offline
    if fetch "$1" "$TMP/cmd" "$2"; then
        read -r CMD A1 A2 A3 < "$TMP/cmd"
        return 0
    fi
    CMD=offline
    return 1
}

# ------------------------------------------------------------------ Touch

start_touch() {
    # ktap aus /tmp starten (/mnt/us ist FAT, Ausführungsrechte dort unzuverlässig)
    cp "${KTAP_BIN:-$EXT_DIR/bin/ktap}" "$TMP/ktap" && chmod +x "$TMP/ktap"
    rm -f "$TMP/tcmd" "$TMP/tout"
    mkfifo "$TMP/tcmd" "$TMP/tout"
    # shellcheck disable=SC2086
    "$TMP/ktap" -W "$SCREEN_W" -H "$SCREEN_H" $TOUCH_FLAGS serve < "$TMP/tcmd" > "$TMP/tout" 2>>"$LOG" &
    KTAP_PID=$!
    exec 3>"$TMP/tcmd"
    exec 4<"$TMP/tout"
}

wait_tap() {
    # $1 = Timeout in s. Setzt TX TY. 1 = Timeout/Fehler
    echo "w $1" >&3
    read -r TX TY <&4 || return 1
    case "$TX" in timeout|error|'') return 1 ;; esac
    log "tap $TX $TY"
    return 0
}

# ------------------------------------------------------------------ Start/Ende

pick_backend() {
    # Erste erreichbare Adresse aus BACKEND_URLS nehmen (Heim-WLAN vor Funnel)
    for cand in ${BACKEND_URLS:-$BACKEND_URL}; do
        BACKEND_URL=$cand
        if fetch "/health" "$TMP/health" 4; then
            log "backend $cand"
            return 0
        fi
    done
    return 1
}

wifi_up() {
    [ "${WIFI_ON:-1}" = 1 ] || { pick_backend; return; }
    state=$($LIPC_GET com.lab126.cmd wirelessEnable 2>/dev/null)
    if [ "$state" = 0 ]; then
        log "enabling wifi"
        $LIPC_SET com.lab126.cmd wirelessEnable 1 2>/dev/null
    fi
    i=0
    while [ $i -lt 15 ]; do
        pick_backend && return 0
        [ $i -eq 1 ] && message "AI Story Reader" "Verbinde mit dem Server ..."
        sleep 2
        i=$((i + 1))
    done
    return 1
}

cleanup() {
    log "exit"
    [ -n "$PREFETCH_PID" ] && kill "$PREFETCH_PID" 2>/dev/null
    echo q >&3 2>/dev/null
    [ -n "$KTAP_PID" ] && kill "$KTAP_PID" 2>/dev/null
    rm -f "$TMP/tcmd" "$TMP/tout"
    $LIPC_SET com.lab126.powerd preventScreenSaver 0 2>/dev/null
    if [ "${STOP_FRAMEWORK:-0}" = 1 ]; then
        start lab126_gui 2>/dev/null || start framework 2>/dev/null
    else
        $EIPS -c >/dev/null 2>&1
        $LIPC_SET com.lab126.appmgrd start app://com.lab126.booklet.home 2>/dev/null
    fi
}

# ------------------------------------------------------------------ Bildschirme

ui_screen() {
    # STATE ist gesetzt. Bild holen, anzeigen, auf einen Treffer warten.
    fetch "/k/screen.png?s=$STATE" "$TMP/screen.png" 30 || { CMD=offline; return; }
    show "$TMP/screen.png"
    while :; do
        wait_tap "$IDLE_EXIT_S" || { CMD=exit; return; }
        request "/k/tap?s=$STATE&x=$TX&y=$TY" 30 || return
        [ "$CMD" = none ] || return
    done
}

generate() {
    # Lade-Bildschirm zeigen, dann blockierend erzeugen lassen
    fetch "/k/screen.png?s=$STATE" "$TMP/screen.png" 30 && show "$TMP/screen.png" full
    request "/k/generate?s=$STATE" 240
}

prefetch() {
    # $1 = id, $2 = Seitenzahl. Lädt fehlende Seiten im Hintergrund.
    dir="$STORY_DIR/$1"
    n=1
    while [ $n -le "$2" ]; do
        [ -s "$dir/$n.png" ] || fetch "/k/story/$1/$n.png" "$dir/$n.png" 30 || return 1
        n=$((n + 1))
    done
}

reader() {
    # $1 = id, $2 = Seiten, $3 = Startseite
    id=$1 pages=$2 page=${3:-1}
    dir="$STORY_DIR/$id"
    mkdir -p "$dir"
    [ -s "$dir/pages" ] || echo "$pages" > "$dir/pages"
    echo "$id" > "$CACHE_DIR/last"
    prefetch "$id" "$pages" &
    PREFETCH_PID=$!

    while :; do
        # auf die Seite warten (kommt vom Prefetch oder direkt)
        i=0
        while [ ! -s "$dir/$page.png" ] && [ $i -lt 30 ]; do
            [ $i -eq 5 ] && fetch "/k/story/$id/$page.png" "$dir/$page.png" 30
            sleep 1
            i=$((i + 1))
        done
        if [ ! -s "$dir/$page.png" ]; then CMD=offline; return; fi
        show "$dir/$page.png"
        echo "$page" > "$TMP/last_page"

        wait_tap "$IDLE_EXIT_S" || { CMD=exit; return; }
        if [ "$TY" -lt $((SCREEN_H * 12 / 100)) ]; then
            request "/k/menu?id=$id&pg=$page" 15
            return
        elif [ "$TX" -lt $((SCREEN_W * 35 / 100)) ]; then
            [ "$page" -gt 1 ] && page=$((page - 1))
        else
            if [ "$page" -ge "$pages" ]; then
                request "/k/menu?id=$id&pg=$page" 15
                return
            fi
            page=$((page + 1))
        fi
    done
}

offline() {
    # Server nicht erreichbar: nochmal / letzte Geschichte offline / beenden
    log "offline"
    if [ -s "$CACHE_DIR/offline.png" ]; then
        show "$CACHE_DIR/offline.png" full
    else
        message "Keine Verbindung zum Server." "" "Oben tippen:   nochmal versuchen" \
                "Mitte tippen:  letzte Geschichte lesen" "Unten tippen:  beenden"
    fi
    wait_tap "$IDLE_EXIT_S" || { CMD=exit; return; }
    if [ "$TY" -lt $((SCREEN_H / 3)) ]; then
        wifi_up
        request "/k/start" 20
    elif [ "$TY" -lt $((SCREEN_H * 2 / 3)) ] && [ -s "$CACHE_DIR/last" ]; then
        id=$(cat "$CACHE_DIR/last")
        CMD=read A1=$id A2=$(ls "$STORY_DIR/$id" 2>/dev/null | grep -c '\.png$') A3=1
        [ "$A2" -gt 0 ] || CMD=offline
    elif [ "$TY" -ge $((SCREEN_H * 2 / 3)) ]; then
        CMD=exit
    fi
}

# ------------------------------------------------------------------ Hauptschleife

main() {
    log "start backends=${BACKEND_URLS:-$BACKEND_URL} http=$HTTP"
    trap cleanup EXIT
    trap 'exit 0' INT TERM HUP

    if [ "${STOP_FRAMEWORK:-0}" = 1 ]; then
        stop lab126_gui 2>/dev/null || stop framework 2>/dev/null
        sleep 2
    fi
    $LIPC_SET com.lab126.powerd preventScreenSaver 1 2>/dev/null
    start_touch

    if wifi_up && request "/k/start" 20; then
        fetch "/k/offline.png" "$CACHE_DIR/offline.png" 20
    else
        CMD=offline
    fi

    while :; do
        case "$CMD" in
            ui)   STATE=$A1; ui_screen ;;
            gen)  STATE=$A1; generate ;;
            read) reader "$A1" "$A2" "$A3" ;;
            exit) break ;;
            *)    offline ;;
        esac
    done
}

main "$@"
