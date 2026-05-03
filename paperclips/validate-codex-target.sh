#!/usr/bin/env bash
# Validate generated Codex Paperclip bundles do not depend on runtime-specific
# assumptions from the existing production target.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CODEX_DIST="$SCRIPT_DIR/dist/codex"

if [ ! -d "$CODEX_DIST" ]; then
  echo "ERROR: Codex dist not found: $CODEX_DIST" >&2
  echo "Run: $SCRIPT_DIR/build.sh --target codex" >&2
  exit 1
fi

python3 "$SCRIPT_DIR/scripts/validate_instructions.py"

if rg -n "superpowers:|Claude Code|Claude CLI|claude CLI|claude-api|CLAUDE\\.md|pr-review-toolkit:|OpusArchitectReviewer" "$CODEX_DIST"; then
  echo "ERROR: Codex output contains forbidden runtime references" >&2
  exit 1
fi

if ! rg -n "AGENTS\\.md|codex_local|codebase-memory|serena" "$CODEX_DIST" >/dev/null; then
  echo "ERROR: Codex output is missing expected Codex runtime guidance" >&2
  exit 1
fi

echo "Codex target validation OK: $CODEX_DIST"
