#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname "$0")" && pwd)"

exec python3 "$SCRIPT_DIR/spike.py" hostile-fixtures "$@"
