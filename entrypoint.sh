#!/bin/sh
set -e

DATA_DIR="${DATA_DIR:-/data}"

# Fix volume ownership so vibetipp can write — handles volumes created by old root containers
chown -R vibetipp:vibetipp "$DATA_DIR"

# Seed matches.csv into the volume if missing or empty (header-only)
MATCHES_TARGET="$DATA_DIR/matches.csv"
MATCHES_SRC="/app/data/matches.csv"
LINE_COUNT=$(wc -l < "$MATCHES_TARGET" 2>/dev/null || echo 0)
if [ "$LINE_COUNT" -le 1 ]; then
    cp "$MATCHES_SRC" "$MATCHES_TARGET"
fi

exec gosu vibetipp python main.py
