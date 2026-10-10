#!/usr/bin/env bash
# One-time setup. Safe to re-run.
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 not found. Install Python 3.11 or newer." >&2
  exit 1
fi

if [ ! -d .venv ]; then
  echo "==> creating virtualenv"
  python3 -m venv .venv
fi

echo "==> installing dependencies"
./.venv/bin/python -m pip install --quiet --upgrade pip
./.venv/bin/python -m pip install --quiet -r requirements-dev.txt

echo
echo "Done. Next:"
echo "  ./run doctor"
echo "  ./run synthetic"
