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
python3 "$SCRIPT_DIR/scripts/validate_codex_target_runtime.py" \
  --codex-dist "$CODEX_DIST" \
  --runtime-map "$SCRIPT_DIR/fragments/shared/targets/codex/runtime-map.json"

if command -v rg >/dev/null 2>&1; then
  marker_found=$(rg -n "AGENTS\\.md|codex_local|codebase-memory|serena" "$CODEX_DIST" >/dev/null && echo yes || echo no)
else
  marker_found=$(grep -R -n -E "AGENTS\\.md|codex_local|codebase-memory|serena" "$CODEX_DIST" >/dev/null && echo yes || echo no)
fi

if [ "$marker_found" != "yes" ]; then
  echo "ERROR: Codex output is missing expected Codex runtime guidance" >&2
  exit 1
fi

echo "Codex target validation OK: $CODEX_DIST"
