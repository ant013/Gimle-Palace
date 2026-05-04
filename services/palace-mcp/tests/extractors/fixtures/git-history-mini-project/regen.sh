#!/usr/bin/env bash
set -euo pipefail
DIR="$(dirname "$0")"
RUNNER="$DIR/repo"
rm -rf "$RUNNER"
cd "$(git -C "$DIR" rev-parse --show-toplevel)/services/palace-mcp"
uv run python "$DIR/_build_synth_repo.py" "$RUNNER"
echo "Repo generated at $RUNNER"
