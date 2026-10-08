#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")"
if [ ! -f state/chronology.sqlite ]; then
    python3 -m cronologia init
fi
exec python3 -m cronologia update
