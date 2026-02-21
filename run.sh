#!/usr/bin/env bash
# Launch Sentinel Solo using the project venv.

set -e
cd "$(dirname "$0")"

if [[ ! -x venv/bin/python ]]; then
    echo "Virtual environment not found. Run: python3 -m venv venv && ./venv/bin/pip install -r requirements.txt"
    exit 1
fi

# Optional: avoid Gdk cursor theme warning on some Linux setups
export XCURSOR_THEME="${XCURSOR_THEME:-Adwaita}"
export XCURSOR_SIZE="${XCURSOR_SIZE:-24}"

exec ./venv/bin/python main.py "$@"
