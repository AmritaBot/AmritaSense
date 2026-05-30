#!/usr/bin/env bash
# docs-build.sh — Build the VitePress documentation.
set -euo pipefail

echo "=== Building docs ==="
npm run docs:build
