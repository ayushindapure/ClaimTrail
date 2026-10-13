#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export npm_config_cache="${npm_config_cache:-/workspace/.cache/npm}"
export UV_CACHE_DIR="${UV_CACHE_DIR:-/workspace/.cache/uv}"
export NEXT_TELEMETRY_DISABLED=1
export OMP_THREAD_LIMIT=2
for tool in node npm python3 uv tesseract; do
  command -v "$tool" >/dev/null || { echo "Missing prerequisite: $tool" >&2; exit 1; }
done
tesseract --list-langs 2>/dev/null | rg '^eng$' >/dev/null
if [[ ! -x .venv/bin/python ]]; then uv venv --python python3 .venv; fi
uv pip sync --python .venv/bin/python --require-hashes backend/requirements.lock
npm ci --no-audit --no-fund
.venv/bin/python -c 'from backend.store import initialise; initialise()'
