#!/usr/bin/env bash
# Expands `<!-- @include fragments/X.md -->` markers in roles/*.md into dist/*.md
# Outputs are committed — visible in PR diffs.
# Note: named `dist/` (not `build/`) because the project root .gitignore excludes `build/`.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROLES_DIR="$SCRIPT_DIR/roles"
FRAG_DIR="$SCRIPT_DIR/fragments"
OUT_DIR="$SCRIPT_DIR/dist"

mkdir -p "$OUT_DIR"

for role_file in "$ROLES_DIR"/*.md; do
  role_name=$(basename "$role_file")
  out_file="$OUT_DIR/$role_name"
  awk -v frag_dir="$FRAG_DIR" '
    /<!-- @include fragments\/.*\.md -->/ {
      match($0, /fragments\/[^ ]+\.md/)
      frag = substr($0, RSTART + 10, RLENGTH - 10)
      path = frag_dir "/" frag
      while ((getline line < path) > 0) print line
      close(path)
      next
    }
    { print }
  ' "$role_file" > "$out_file"
  echo "built $out_file"
done
