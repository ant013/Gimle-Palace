#!/usr/bin/env bash
# Build Paperclip agent bundles through the project manifest compatibility renderer.
# Outputs are committed — visible in PR diffs.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT="gimle"
TARGET="claude"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --project)
      if [ "$#" -lt 2 ]; then
        echo "ERROR: --project requires a project key" >&2
        exit 1
      fi
      PROJECT="$2"
      shift 2
      ;;
    --project=*)
      PROJECT="${1#--project=}"
      shift
      ;;
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
  ./paperclips/build.sh --project gimle --target codex

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

python3 "$SCRIPT_DIR/scripts/build_project_compat.py" \
  --project "$PROJECT" \
  --target "$TARGET" \
  --inventory skip
