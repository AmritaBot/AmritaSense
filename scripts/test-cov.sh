#!/usr/bin/env bash
# test-cov.sh — Run unit tests with coverage report.
set -euo pipefail

echo "=== Running tests with coverage ==="
uv run pytest tests/ \
    --cov=src/amrita_sense \
    --cov-report=term-missing \
    --cov-report=xml \
    -v
