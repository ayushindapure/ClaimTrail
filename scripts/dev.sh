#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export npm_config_cache="${npm_config_cache:-/workspace/.cache/npm}"
export NEXT_TELEMETRY_DISABLED=1
export OMP_THREAD_LIMIT=2
command -v setsid >/dev/null || { echo "This Linux launcher requires setsid." >&2; exit 1; }
if [[ ! -x .venv/bin/python || ! -d node_modules ]]; then
  echo "Run bash scripts/setup.sh first." >&2
  exit 1
fi
.venv/bin/python - <<'PY'
import socket
for port in (8000, 3000):
    with socket.socket() as sock:
        if sock.connect_ex(('127.0.0.1', port)) == 0:
            raise SystemExit(f'Port {port} is already occupied. Stop that service or run the API/frontend separately on chosen ports.')
PY
setsid .venv/bin/python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000 &
api_pid=$!
cleanup() {
  trap - EXIT INT TERM
  kill -TERM -- "-$api_pid" 2>/dev/null || true
  if [[ -n "${web_pid:-}" ]]; then kill -TERM -- "-$web_pid" 2>/dev/null || true; fi
  wait "$api_pid" 2>/dev/null || true
  if [[ -n "${web_pid:-}" ]]; then wait "$web_pid" 2>/dev/null || true; fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
for attempt in $(seq 1 45); do
  if curl --fail --silent http://127.0.0.1:8000/api/health >/dev/null; then break; fi
  if ! kill -0 "$api_pid" 2>/dev/null; then wait "$api_pid"; exit 1; fi
  sleep 1
done
curl --fail --silent http://127.0.0.1:8000/api/health >/dev/null
setsid node node_modules/next/dist/bin/next dev --hostname 0.0.0.0 --port 3000 &
web_pid=$!
wait -n "$api_pid" "$web_pid"
