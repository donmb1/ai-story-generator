#!/bin/sh
# Phase 4: kleinstmoegliches E-Ink-Experiment mit Bordmitteln (eips, kein Extra-Paket)
eips -c
eips 3 5 "Hello World"
eips 3 7 "AI Story Reader - Phase 4"
eips 3 9 "$(date '+%Y-%m-%d %H:%M')"
