#!/usr/bin/env bash
# Mutation journal per UAA spec §8.5 — snapshot before risky operations.
# Source-only.
#
# IMP-C fix: journal files contain AGENTS.md content (medium sensitivity)
# and plugin configs. Force 600/700 modes.

JOURNAL_DIR="${HOME}/.paperclip/journal"
umask 0077

journal_init() {
  mkdir -p "$JOURNAL_DIR"
  chmod 700 "$JOURNAL_DIR"
}

# Start a new journal entry; returns its path on stdout.
journal_open() {
  local op="$1"   # short name, e.g. "bootstrap-trading"
  journal_init
  local ts
  ts=$(date -u +%Y%m%dT%H%M%SZ)
  local path="$JOURNAL_DIR/${ts}-${op}.json"
  printf '{"op":"%s","timestamp":"%s","entries":[]}' "$op" "$ts" > "$path"
  chmod 600 "$path"
  echo "$path"
}

# Append a snapshot/entry to journal. entry_json must be a valid JSON object.
journal_record() {
  local journal_path="$1"
  local entry_json="$2"
  local tmp="${journal_path}.tmp"
  jq --argjson e "$entry_json" '.entries += [$e]' "$journal_path" > "$tmp" && mv "$tmp" "$journal_path"
}

journal_finalize() {
  local journal_path="$1"
  local outcome="$2"  # "success" or "failure"
  local tmp="${journal_path}.tmp"
  jq --arg o "$outcome" '. + {outcome: $o}' "$journal_path" > "$tmp" && mv "$tmp" "$journal_path"
}
