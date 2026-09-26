#!/bin/sh
# Notausgang: App und Touch-Leser beenden, Bildschirmschoner wieder erlauben.
[ -f /tmp/aistory.pid ] && kill "$(cat /tmp/aistory.pid)" 2>/dev/null
killall ktap 2>/dev/null
rm -f /tmp/aistory.pid
lipc-set-prop com.lab126.powerd preventScreenSaver 0 2>/dev/null
