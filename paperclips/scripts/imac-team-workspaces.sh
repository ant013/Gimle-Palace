#!/usr/bin/env bash
# Prepare isolated stable checkouts for Claude and CX/Codex Paperclip teams.
set -euo pipefail

MODE="dry-run"
SOURCE_REPO="${PAPERCLIP_SOURCE_REPO:-/Users/Shared/Ios/Gimle-Palace}"
CLAUDE_WORKSPACE="${PAPERCLIP_CLAUDE_WORKSPACE:-/Users/Shared/Ios/worktrees/claude/Gimle-Palace}"
CODEX_WORKSPACE="${PAPERCLIP_CODEX_WORKSPACE:-/Users/Shared/Ios/worktrees/cx/Gimle-Palace}"
INTEGRATION_BRANCH="${PAPERCLIP_INTEGRATION_BRANCH:-develop}"

usage() {
  cat <<'USAGE'
Usage:
  ./paperclips/scripts/imac-team-workspaces.sh --dry-run
  ./paperclips/scripts/imac-team-workspaces.sh --apply

Environment:
  PAPERCLIP_SOURCE_REPO       defaults to /Users/Shared/Ios/Gimle-Palace
  PAPERCLIP_CLAUDE_WORKSPACE  defaults to /Users/Shared/Ios/worktrees/claude/Gimle-Palace
  PAPERCLIP_CODEX_WORKSPACE   defaults to /Users/Shared/Ios/worktrees/cx/Gimle-Palace
  PAPERCLIP_INTEGRATION_BRANCH defaults to develop

The target directories are stable team checkouts. Paperclip may create
per-issue worktrees from those roots; the roots themselves stay isolated by
team so Claude and CX/Codex do not share a mutable checkout.
USAGE
}

for arg in "$@"; do
  case "$arg" in
    --dry-run) MODE="dry-run" ;;
    --apply) MODE="apply" ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $arg" >&2; usage; exit 1 ;;
  esac
done

if [ ! -d "$SOURCE_REPO/.git" ]; then
  echo "ERROR: source repo not found: $SOURCE_REPO" >&2
  exit 1
fi

REMOTE_URL="$(git -C "$SOURCE_REPO" remote get-url origin)"

run() {
  if [ "$MODE" = "dry-run" ]; then
    printf '+'
    printf ' %q' "$@"
    printf '\n'
  else
    "$@"
  fi
}

prepare_workspace() {
  local target="$1"

  echo ""
  echo "Workspace: $target"

  if [ -d "$target/.git" ] || [ -f "$target/.git" ]; then
    echo "  existing checkout"
  else
    run mkdir -p "$(dirname "$target")"
    run git clone "$REMOTE_URL" "$target"
  fi

  run git -C "$target" fetch origin --prune
  run git -C "$target" switch "$INTEGRATION_BRANCH"
  run git -C "$target" pull --ff-only
  run git -C "$target" submodule update --init paperclips/fragments/shared
  run git -C "$target" status --short --branch
}

echo "Mode: $MODE"
echo "Source repo: $SOURCE_REPO"
echo "Remote: $REMOTE_URL"
echo "Integration branch: $INTEGRATION_BRANCH"

prepare_workspace "$CLAUDE_WORKSPACE"
prepare_workspace "$CODEX_WORKSPACE"
