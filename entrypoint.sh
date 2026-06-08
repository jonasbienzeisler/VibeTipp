#!/bin/sh
set -e

DATA_DIR="${DATA_DIR:-/data}"

# Ensure /data is owned by vibetipp (needed for rootless Podman where new volumes start root-owned)
chown -R vibetipp:vibetipp "$DATA_DIR"

# Seed matches.csv into the volume if missing or empty (header-only)
MATCHES_TARGET="$DATA_DIR/matches.csv"
MATCHES_SRC="/app/data/matches.csv"
LINE_COUNT=$(wc -l < "$MATCHES_TARGET" 2>/dev/null || echo 0)
if [ "$LINE_COUNT" -le 1 ]; then
    cp "$MATCHES_SRC" "$MATCHES_TARGET"
fi

exec gosu vibetipp python main.py
