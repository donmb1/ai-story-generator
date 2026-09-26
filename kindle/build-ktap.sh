#!/bin/sh
# Baut ktap statisch für ARMv7 (Kindle PW2+ / 5.x) in einem Alpine-Container unter QEMU.
# Voraussetzung: Docker Desktop. Ergebnis: device/app/bin/ktap
set -e
cd "$(dirname "$0")"
docker run --rm --platform linux/arm/v7 -v "$PWD":/w -w /w alpine:3.20 sh -c '
  apk add -q gcc musl-dev linux-headers >/dev/null
  gcc -Os -static -Wall -Wextra -march=armv7-a -mfpu=vfpv3-d16 -mthumb \
      -o device/app/bin/ktap src/ktap.c
  strip device/app/bin/ktap'
file device/app/bin/ktap
