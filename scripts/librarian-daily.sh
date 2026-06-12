#!/bin/sh
set -eu

cd /Users/spencer/Desktop/Project/librarian
export PYTHONPATH=src

.venv/bin/python -m librarian daily --apply
