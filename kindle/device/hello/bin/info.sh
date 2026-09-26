#!/bin/sh
# Sammelt Infos fuer Phase 5 (curl/TLS/Python/FBInk vorhanden?) nach /mnt/us/hello.log
L=/mnt/us/hello.log
{
  echo "== date";    date
  echo "== uname";   uname -a
  echo "== version"; cat /etc/prettyversion.txt 2>/dev/null
  echo "== mem";     free 2>/dev/null
  echo "== tools"
  echo "== libkh fbink"; ls -la /mnt/us/libkh/bin/fbink 2>&1
  for t in curl wget openssl python python3 fbink eips lipc-get-prop; do
    printf '%s: ' "$t"; command -v "$t" || echo "-"
  done
  echo "== curl";    curl --version 2>&1 | head -3
  echo "== openssl"; openssl version 2>&1
  echo "== fb";      eips -i 2>&1 | head -20
} > "$L" 2>&1
eips -c
eips 3 5 "Info geschrieben: hello.log"
