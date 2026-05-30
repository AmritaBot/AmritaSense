#!/usr/bin/env bash
# init-env.sh — Initialize the Python virtual environment and install dependencies.
set -euo pipefail

echo "=== Creating virtual environment ==="
uv venv

echo "=== Installing dependencies ==="
uv sync

echo "=== Done ==="
echo "Activate with: source .venv/bin/activate"
