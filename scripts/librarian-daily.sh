#!/bin/sh
set -eu

cd /Users/spencer/librarian
export PYTHONPATH=src
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

.venv/bin/python -m librarian daily --apply --lookup --enrich
