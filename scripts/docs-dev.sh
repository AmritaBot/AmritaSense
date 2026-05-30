#!/usr/bin/env bash
# docs-dev.sh — Start the VitePress dev server with hot reload.
set -euo pipefail

echo "=== Starting VitePress dev server ==="
npm run docs:dev
