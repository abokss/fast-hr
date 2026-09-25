#!/bin/zsh
cd "$(dirname "$0")" || exit 1
if [ ! -x backend/venv/bin/python ]; then
  echo 'First install dependencies as described in README.md.'
  read '?Press Enter to close.'
  exit 1
fi
backend/venv/bin/python scripts/run_local.py
read '?Press Enter to close.'
