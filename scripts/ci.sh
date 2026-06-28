#!/usr/bin/env bash
# ci.sh — Full CI pipeline (init -> lint -> test -> build).
# Run this locally to simulate what CI does.
set -euo pipefail

echo "========== 1. Init environment =========="
uv venv
uv sync

echo ""
echo "========== 2. Type check (Pyright) =========="
uv run pyright

echo ""
echo "========== 3. Lint (Ruff) =========="
uv run ruff check .

echo ""
echo "========== 4. Unit tests with coverage =========="
uv run pytest tests/ \
    --cov=src/amrita_sense \
    --cov-report=term-missing \
    --cov-report=xml \
    -v

echo ""
echo "========== 5. Build package =========="
uv build

echo ""
echo "========== 6. Build docs =========="
npm run docs:build

echo ""
echo "=== CI pipeline complete ==="
