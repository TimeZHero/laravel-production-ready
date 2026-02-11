#!/bin/sh
set -eu

cd "$(dirname "$0")"

# Create a virtual environment if it doesn't exist
if [ ! -d .venv ]; then
    echo "==> Creating virtual environment..."
    python3 -m venv .venv
fi

echo "==> Installing dependencies..."
.venv/bin/pip install -q -r requirements.txt

echo "==> Running tests..."
.venv/bin/pytest -v --tb=short "$@"
