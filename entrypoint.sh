#!/bin/sh
set -e

DATA_DIR="${DATA_DIR:-/data}"

# Seed matches.csv into the volume on first run
if [ ! -f "$DATA_DIR/matches.csv" ]; then
    cp /app/data/matches.csv "$DATA_DIR/matches.csv"
fi

exec python main.py
