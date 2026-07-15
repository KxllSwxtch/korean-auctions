#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

exec venv/bin/python -m pytest \
  tests/test_glovis_models.py \
  tests/test_glovis_transport.py \
  tests/test_glovis_service.py \
  tests/test_glovis_routes.py \
  "$@"
