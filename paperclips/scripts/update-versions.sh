#!/usr/bin/env bash
# UAA Phase C: bump pinned versions in versions.env then re-run install-paperclip.sh.
#
# Workflow:
#   1. Edit paperclips/scripts/versions.env (bump PAPERCLIPAI_VERSION, etc.).
#   2. Run this script.
#   3. It journals current versions (pre-state) then re-runs install-paperclip.sh.
#   4. If anything breaks, use rollback.sh <journal-id> to see what changed.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# shellcheck source=lib/_common.sh
source "${SCRIPT_DIR}/lib/_common.sh"
# shellcheck source=lib/_journal.sh
source "${SCRIPT_DIR}/lib/_journal.sh"

usage() {
  cat <<EOF
Usage:
  $(basename "$0")                # journal current versions then re-run install-paperclip.sh
  $(basename "$0") --show-current # print current versions.env (no install)
  $(basename "$0") --help         # this message

Edit paperclips/scripts/versions.env FIRST to bump versions; this script then
applies them. Pre-bump state is recorded in ~/.paperclip/journal/<ts>-version-bump.json.
EOF
}

case "${1:-}" in
  -h|--help) usage; exit 0 ;;
  --show-current)
    log info "current versions.env:"
    grep -E '^[A-Z_]+="' "${SCRIPT_DIR}/versions.env"
    exit 0
    ;;
esac

require_command jq

# Snapshot pre-state into journal
journal=$(journal_open "version-bump")
log info "journal: $journal"

current_paperclipai=$(paperclip --version 2>/dev/null || echo "missing")
current_pnpm=$(pnpm --version 2>/dev/null || echo "missing")
current_telegram_sha=""
src="${HOME}/.paperclip/plugins-src/paperclip-plugin-telegram"
if [ -d "$src/.git" ]; then
  current_telegram_sha=$(git -C "$src" rev-parse HEAD 2>/dev/null || echo "missing")
fi

snapshot=$(jq -n \
  --arg pc "$current_paperclipai" \
  --arg pnpm "$current_pnpm" \
  --arg tg "$current_telegram_sha" \
  '{kind:"version_bump_snapshot",paperclipai:$pc,pnpm:$pnpm,telegram_sha:$tg}')
journal_record "$journal" "$snapshot"

log info "pre-bump state recorded — re-running install-paperclip.sh"
"${SCRIPT_DIR}/install-paperclip.sh"

journal_finalize "$journal" "success"
log ok "update complete — see $journal"
