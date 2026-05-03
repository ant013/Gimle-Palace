#!/usr/bin/env bash
# Expands `<!-- @include fragments/X.md -->` markers in roles/*.md into dist/*.md
# Outputs are committed — visible in PR diffs.
# Note: named `dist/` (not `build/`) because the project root .gitignore excludes `build/`.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRAG_DIR="$SCRIPT_DIR/fragments"

TARGET="claude"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --target)
      if [ "$#" -lt 2 ]; then
        echo "ERROR: --target requires claude or codex" >&2
        exit 1
      fi
      TARGET="$2"
      shift 2
      ;;
    --target=*)
      TARGET="${1#--target=}"
      shift
      ;;
    -h|--help)
      cat <<'USAGE'
Usage:
  ./paperclips/build.sh
  ./paperclips/build.sh --target claude
  ./paperclips/build.sh --target codex

Targets:
  claude  Builds paperclips/roles/*.md into paperclips/dist/*.md.
  codex   Builds paperclips/roles-codex/*.md into paperclips/dist/codex/*.md.
USAGE
      exit 0
      ;;
    *)
      echo "ERROR: unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

case "$TARGET" in
  claude)
    ROLES_DIR="$SCRIPT_DIR/roles"
    OUT_DIR="$SCRIPT_DIR/dist"
    ;;
  codex)
    ROLES_DIR="$SCRIPT_DIR/roles-codex"
    OUT_DIR="$SCRIPT_DIR/dist/codex"
    ;;
  *)
    echo "ERROR: unknown target: $TARGET" >&2
    exit 1
    ;;
esac

if [ ! -d "$ROLES_DIR" ]; then
  echo "ERROR: roles directory not found for target '$TARGET': $ROLES_DIR" >&2
  exit 1
fi

mkdir -p "$OUT_DIR"
if [ "$TARGET" = "codex" ]; then
  rm -f "$OUT_DIR"/*.md
fi

found=0
for role_file in "$ROLES_DIR"/*.md; do
  [ -e "$role_file" ] || continue
  found=1
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

  if [ "$TARGET" = "codex" ]; then
    perl -0pi -e '
      s/CLAUDE\.md/AGENTS.md/g;
      s/claude CLI cache/session cache/g;
      s/Claude CLI cache/session cache/g;
      s/claude CLI/session cache/g;
      s/Claude CLI/session cache/g;
      s/OpusArchitectReviewer/CodexArchitectReviewer/g;
      s/Opus adversarial/Codex adversarial/g;
      s/superpowers:/codex-discipline:/g;
      s/pr-review-toolkit:/codex-review:/g;
    ' "$out_file"
  fi

  echo "built $out_file"
done

if [ "$found" -eq 0 ]; then
  echo "ERROR: no role files found for target '$TARGET' in $ROLES_DIR" >&2
  exit 1
fi
