#!/bin/sh
set -eu

cd /Users/spencer/librarian
export PYTHONPATH=src
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

echo "Weekly preflight: daily ingest/repair"
.venv/bin/python -m librarian daily --apply --lookup --enrich

echo "Weekly delivery: local digest"
.venv/bin/python -m librarian weekly --apply --notify-mac --open --message-self
