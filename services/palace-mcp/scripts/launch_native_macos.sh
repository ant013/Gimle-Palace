#!/usr/bin/env bash
# Launch palace-mcp natively on macOS (no Docker) with MPS GPU support.
# Used by ~/Library/LaunchAgents/work.ant013.palace-mcp-native.plist or
# can be run manually for ad-hoc development.
#
# Required:
#   - Native venv at /Users/ant013/Android/Gimle-Palace-native/.venv with
#     palace-mcp installed editable (`pip install -e services/palace-mcp`)
#   - .env file at /Users/ant013/Android/Gimle-Palace-native/.env with at
#     minimum: NEO4J_URI, NEO4J_PASSWORD, OPENAI_API_KEY (dummy ok for qodo),
#     PALACE_REPOS_ROOT, PALACE_HF_CACHE_DIR
#   - Symlink /Users/$USER/Ios-hs -> /Users/$USER/Ios/HorizontalSystems
#   - Local Neo4j (brew services start neo4j) listening on bolt://localhost:7687
#   - Apple Silicon Mac with PyTorch MPS support
#
# Usage:
#   ./launch_native_macos.sh             # foreground (Ctrl-C to stop)
#   ./launch_native_macos.sh --daemon    # background, writes pidfile
#
# See docs/runbooks/native-macos-palace-mcp.md for full setup.

set -euo pipefail

NATIVE_ROOT="${PALACE_NATIVE_ROOT:-/Users/ant013/Android/Gimle-Palace-native}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_ROOT="${PALACE_SERVICE_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"
PORT="${PALACE_NATIVE_PORT:-8765}"
HOST="${PALACE_NATIVE_HOST:-0.0.0.0}"
LOG_DIR="${PALACE_NATIVE_LOG_DIR:-$HOME/Library/Logs/palace-mcp-native}"
PID_FILE="${PALACE_NATIVE_PID_FILE:-$LOG_DIR/palace-mcp.pid}"

ENV_FILE="$NATIVE_ROOT/.env"
PYBIN="$NATIVE_ROOT/.venv/bin"

[ -f "$ENV_FILE" ] || { echo "ERR: missing $ENV_FILE" >&2; exit 1; }
[ -x "$PYBIN/uvicorn" ] || { echo "ERR: missing $PYBIN/uvicorn — run pip install -e first" >&2; exit 1; }
mkdir -p "$LOG_DIR"

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

cd "$SERVICE_ROOT"

if [ "${1:-}" = "--daemon" ]; then
  LOG="$LOG_DIR/palace-mcp.log"
  echo "starting palace-mcp daemon — pid -> $PID_FILE, log -> $LOG"
  nohup "$PYBIN/uvicorn" palace_mcp.main:app --host "$HOST" --port "$PORT" --app-dir src \
    >> "$LOG" 2>&1 &
  echo $! > "$PID_FILE"
  disown
  sleep 3
  if curl -sf -o /dev/null --max-time 5 "http://localhost:$PORT/healthz"; then
    echo "OK — healthz=200, pid=$(cat "$PID_FILE")"
  else
    echo "WARN — healthz did not respond yet; check $LOG"
    exit 1
  fi
else
  exec "$PYBIN/uvicorn" palace_mcp.main:app --host "$HOST" --port "$PORT" --app-dir src
fi
