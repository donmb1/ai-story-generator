#!/bin/sh
# Touch-Kalibrierung: zeigt Gerät, Wertebereich und 3 Taps an.
# Bitte nacheinander tippen: 1) oben links  2) oben rechts  3) unten links
EXT_DIR=$(cd "$(dirname "$0")/.." && pwd)
. "$EXT_DIR/config.sh"
OUT=/mnt/us/aistory/touchtest.log
mkdir -p /mnt/us/aistory
cp "$EXT_DIR/bin/ktap" /tmp/ktap && chmod +x /tmp/ktap
sleep 1
eips -c
eips 2 2 "Touch-Test"
/tmp/ktap -W "$SCREEN_W" -H "$SCREEN_H" $TOUCH_FLAGS info > "$OUT" 2>&1
row=4
while read -r line; do eips 2 $row "$line"; row=$((row + 1)); done < "$OUT"
row=$((row + 1))
for corner in "oben links" "oben rechts" "unten links"; do
    eips 2 $row "Tippe $corner ..."
    res=$(/tmp/ktap -W "$SCREEN_W" -H "$SCREEN_H" $TOUCH_FLAGS once 20)
    echo "$corner: $res" >> "$OUT"
    eips 2 $((row + 1)) "-> x y rawx rawy = $res"
    row=$((row + 3))
done
eips 2 $((row + 1)) "Erwartet: oben links ~ 0 0, oben rechts ~ $SCREEN_W 0"
eips 2 $((row + 2)) "Ergebnis steht in aistory/touchtest.log"
