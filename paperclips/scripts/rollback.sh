#!/usr/bin/env bash
# UAA Phase C: replay inverse mutations from a journal entry per spec §8.5.
#
# Snapshots (recorded by bootstrap-project.sh + update-versions.sh) carry the
# OLD state of each mutation. rollback.sh replays them in reverse order (LIFO)
# to restore the system to its pre-bootstrap state.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# shellcheck source=lib/_common.sh
source "${SCRIPT_DIR}/lib/_common.sh"
# shellcheck source=lib/_paperclip_api.sh
source "${SCRIPT_DIR}/lib/_paperclip_api.sh"

JOURNAL_DIR="${HOME}/.paperclip/journal"

usage() {
  cat <<EOF
Usage:
  $(basename "$0") --list                              # list recent journal entries
  $(basename "$0") <journal-id-or-path>                # replay inverse mutations
  $(basename "$0") <journal-id> --dry-run              # show what would happen

A journal-id is the filename basename, e.g. "20260516T120000Z-bootstrap-trading"
(with or without the trailing ".json").
EOF
}

case "${1:-}" in
  -h|--help) usage; exit 0 ;;
  "") usage; exit 2 ;;
esac

if [ "$1" = "--list" ]; then
  if [ ! -d "$JOURNAL_DIR" ]; then
    log warn "no journal dir at $JOURNAL_DIR — nothing recorded yet"
    exit 0
  fi
  log info "recent journal entries (newest first):"
  found=0
  while IFS= read -r f; do
    [ -z "$f" ] && continue
    found=1
    op=$(jq -r '.op // "?"' "$f" 2>/dev/null || echo "?")
    ts=$(jq -r '.timestamp // "?"' "$f" 2>/dev/null || echo "?")
    outcome=$(jq -r '.outcome // "in-progress"' "$f" 2>/dev/null || echo "?")
    entries=$(jq '.entries | length' "$f" 2>/dev/null || echo 0)
    name=$(basename "$f" .json)
    printf "  %s  %-50s op=%-25s entries=%d  outcome=%s\n" "$ts" "$name" "$op" "$entries" "$outcome"
  done < <(ls -1t "$JOURNAL_DIR"/*.json 2>/dev/null | head -20)
  [ "$found" -eq 0 ] && log warn "no journal files found"
  exit 0
fi

DRY_RUN=0
journal_id=""
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) journal_id="$1"; shift ;;
  esac
done

[ -n "$journal_id" ] || { usage; die "journal-id required"; }
validate_journal_id "$journal_id"

# Resolve to absolute journal path
journal_path=""
if [ -f "$journal_id" ]; then
  journal_path="$journal_id"
elif [ -f "${JOURNAL_DIR}/${journal_id}.json" ]; then
  journal_path="${JOURNAL_DIR}/${journal_id}.json"
elif [ -f "${JOURNAL_DIR}/${journal_id}" ]; then
  journal_path="${JOURNAL_DIR}/${journal_id}"
else
  die "journal not found: $journal_id (looked in $JOURNAL_DIR)"
fi

require_command jq
log info "replaying journal: $journal_path"

entries=$(jq '.entries | length' "$journal_path")
log info "found $entries snapshots to replay (reverse order)"

if [ "$entries" -eq 0 ]; then
  log warn "no snapshots in this journal — nothing to roll back"
  exit 0
fi

# Replay each entry in REVERSE order (LIFO)
for i in $(seq $((entries - 1)) -1 0); do
  entry=$(jq -c ".entries[$i]" "$journal_path")
  kind=$(printf '%s' "$entry" | jq -r '.kind')
  case "$kind" in
    agent_instructions_snapshot)
      agent_id=$(printf '%s' "$entry" | jq -r '.agent_id')
      old_content=$(printf '%s' "$entry" | jq -r '.old_content')
      log info "rolling back AGENTS.md for agent $agent_id"
      if [ "$DRY_RUN" -eq 1 ]; then
        bytes=$(printf '%s' "$old_content" | wc -c | tr -d ' ')
        log info "DRY RUN — would PUT old AGENTS.md (${bytes} bytes)"
      else
        paperclip_deploy_agents_md "$agent_id" "$old_content" >/dev/null
        log ok "restored agent $agent_id"
      fi
      ;;
    plugin_config_snapshot)
      plugin_id=$(printf '%s' "$entry" | jq -r '.plugin_id')
      old_config=$(printf '%s' "$entry" | jq -c '.old_config')
      log info "rolling back plugin config $plugin_id"
      if [ "$DRY_RUN" -eq 1 ]; then
        log info "DRY RUN — would POST old config"
      else
        paperclip_plugin_set_config "$plugin_id" "$old_config" >/dev/null
        log ok "restored plugin $plugin_id"
      fi
      ;;
    version_bump_snapshot)
      log warn "version-bump snapshot found — manual rollback required. Entry contents:"
      printf '%s' "$entry" | jq .
      ;;
    agent_hire)
      agent_id=$(printf '%s' "$entry" | jq -r '.id')
      agent_name=$(printf '%s' "$entry" | jq -r '.name')
      log info "rolling back hire of $agent_name ($agent_id)"
      if [ "$DRY_RUN" -eq 1 ]; then
        log info "DRY RUN — would delete agent $agent_name ($agent_id)"
      else
        paperclip_delete_agent "$agent_id" >/dev/null
        log ok "deleted agent $agent_name"
      fi
      ;;
    *)
      log warn "unknown snapshot kind: $kind — skipping"
      ;;
  esac
done

log ok "rollback complete"
