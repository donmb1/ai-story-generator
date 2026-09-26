#!/bin/sh
# Simuliert den Kindle-Client in BusyBox (nur wget, kein curl) gegen ein lokales Backend.
#   ./run-sim.sh happy|offline      Ergebnis: sim/out/<name>/shown/*.png + Logs
set -e
cd "$(dirname "$0")"
name=${1:-happy}
rm -rf "out/$name"; mkdir -p "out/$name/tmp/shown" "out/$name/us/aistory/stories"
url="http://host.docker.internal:${PORT:-8787}"
[ "$name" = offline ] && url="http://host.docker.internal:1"
cat > "out/$name/config.sh" <<CFG
BACKEND_URLS="http://host.docker.internal:1 $url"
DEVICE_TOKEN="${DEVICE_TOKEN:-$(sed -n "s/^DEVICE_TOKEN=//p" ../../backend/.env 2>/dev/null)}"
SCREEN_W=1072
SCREEN_H=1448
TOUCH_FLAGS=""
IDLE_EXIT_S=5
FULL_REFRESH_EVERY=6
WIFI_ON=1
STOP_FRAMEWORK=0
STORY_DIR="/us/aistory/stories"
CFG
docker run --rm -v "$PWD/..":/k -v "$PWD/out/$name/us":/us -v "$PWD/out/$name/tmp":/t \
  -e AISTORY_CONFIG=/k/sim/out/$name/config.sh -e AISTORY_TMP=/t \
  -e EIPS=/k/sim/eips -e LIPC_SET=/k/sim/lipc -e LIPC_GET=/k/sim/lipc \
  -e KTAP_BIN=/k/sim/ktap -e TAPS=/k/sim/taps-$name.txt \
  busybox:1.36 sh /k/device/app/bin/aistory.sh
echo "--- log"; cat "out/$name/tmp/aistory.log"
echo "--- display"; cat "out/$name/tmp/eips.log"
