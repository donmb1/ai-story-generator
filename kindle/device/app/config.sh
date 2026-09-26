# AI Story Reader – Kindle-Konfiguration (wird von bin/aistory.sh eingelesen)

# Backend-Adressen, in dieser Reihenfolge probiert (install.sh setzt die Werte beim Kopieren):
# z. B. zuerst direkt im Heim-WLAN, dann eine öffentliche HTTPS-Adresse (Tailscale Funnel o. ä.)
BACKEND_URLS="http://192.168.1.50:8787"

# Muss DEVICE_TOKEN im Backend entsprechen. Kein API-Key – der bleibt auf dem Server.
DEVICE_TOKEN="CHANGE-ME"

# Display Kindle Paperwhite 3
SCREEN_W=1072
SCREEN_H=1448

# Touch-Kalibrierung (mit dem Scriptlet "AI Story - Touch-Test" prüfen):
#   -s = x/y tauschen, -x = x spiegeln, -y = y spiegeln, -d /dev/input/eventN = Gerät fest
TOUCH_FLAGS=""

# Nach so vielen Sekunden ohne Tap beendet sich die App (Akku sparen)
IDLE_EXIT_S=1800

# Voller Refresh (gegen Ghosting) alle N Seiten/Bildschirme
FULL_REFRESH_EVERY=6

# 1 = WLAN beim Start einschalten, falls aus (Flugmodus bleibt sonst unberührt)
WIFI_ON=1

# 1 = Kindle-Oberfläche während der App anhalten (robuster gegen Überzeichnen, Start/Ende dauern länger)
STOP_FRAMEWORK=0

# Hier werden Geschichten für das Offline-Lesen abgelegt
STORY_DIR="/mnt/us/aistory/stories"
