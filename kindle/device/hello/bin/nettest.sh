#!/bin/sh
# Prüft, ob der Kindle modernes HTTPS kann (TLS 1.2 + Let's-Encrypt-Zertifikat)
# und ob die konfigurierten Backends erreichbar sind. Ergebnis: /mnt/us/aistory/nettest.log
. /mnt/us/aistory/app/config.sh 2>/dev/null
OUT=/mnt/us/aistory/nettest.log
{
  echo "== date";    date
  echo "== uname";   uname -a
  echo "== version"; cat /etc/prettyversion.txt 2>/dev/null
  echo "== tools"
  for t in curl wget openssl; do printf '%s: ' "$t"; command -v "$t" || echo "-"; done
  echo "== curl -V"; curl -V 2>&1 | head -3
  echo "== openssl"; openssl version 2>&1
  for url in https://valid-isrgrootx1.letsencrypt.org/ https://www.google.com/; do
    echo "== curl $url"
    curl -sS -o /dev/null -m 15 -w "http=%{http_code} ssl_verify=%{ssl_verify_result}\n" "$url" 2>&1
  done
  for url in $BACKEND_URLS; do
    echo "== backend $url/health"
    curl -sS -m 10 "$url/health" 2>&1; echo
  done
} > "$OUT" 2>&1
eips -c
eips 2 3 "Netztest fertig: aistory/nettest.log"
