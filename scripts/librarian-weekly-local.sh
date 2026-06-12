#!/bin/sh
set -eu

cd /Users/spencer/librarian
export PYTHONPATH=src

.venv/bin/python -m librarian weekly --apply --notify-mac --open --message-self
