#!/usr/bin/env bash
# regen-uw-ios-scip.sh — regenerate SCIP indexes for uw-ios bundle and rsync to iMac (GIM-182 §7.3).
#
# Run on dev Mac (not inside container). For each Kit in the manifest:
#   1. mtime-guard: skip if scip/index.scip is newer than Sources/**
#   2. Run palace-swift-scip-emit --project <slug> --output scip/index.scip
#   3. sha256 verification: compute scip/index.scip.sha256
#   4. rsync to iMac: imac-ssh.ant013.work:/Users/Shared/Ios/HorizontalSystems/<kit>/
#
# Usage:
#   cd /path/to/HorizontalSystems
#   bash ~/Gimle-Palace/services/palace-mcp/scripts/regen-uw-ios-scip.sh
#
# Environment variables:
#   HS_BASE_DIR   — parent dir containing all Kit dirs (default: $PWD)
#   IMAC_HOST     — rsync destination host (default: imac-ssh.ant013.work)
#   IMAC_HS_PATH  — remote path (default: /Users/Shared/Ios/HorizontalSystems)
#   MANIFEST      — path to uw-ios-bundle-manifest.json

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MANIFEST="${MANIFEST:-${SCRIPT_DIR}/uw-ios-bundle-manifest.json}"
HS_BASE_DIR="${HS_BASE_DIR:-$PWD}"
IMAC_HOST="${IMAC_HOST:-imac-ssh.ant013.work}"
IMAC_HS_PATH="${IMAC_HS_PATH:-/Users/Shared/Ios/HorizontalSystems}"
LOG_FILE="${HOME}/Library/Logs/palace-uw-ios-regen.log"
MAX_LOG_SIZE_BYTES=$((10 * 1024 * 1024))  # 10 MB

# Simple log rotation (keep 3 files)
_rotate_log() {
  if [ -f "$LOG_FILE" ] && [ "$(wc -c < "$LOG_FILE")" -ge "$MAX_LOG_SIZE_BYTES" ]; then
    mv -f "${LOG_FILE}.2" "${LOG_FILE}.3" 2>/dev/null || true
    mv -f "${LOG_FILE}.1" "${LOG_FILE}.2" 2>/dev/null || true
    mv -f "${LOG_FILE}" "${LOG_FILE}.1"
  fi
}

_log() {
  local ts; ts=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
  echo "[$ts] $*" | tee -a "$LOG_FILE"
}

_rotate_log
mkdir -p "$(dirname "$LOG_FILE")"
_log "regen-uw-ios-scip START hs_base=$HS_BASE_DIR"

# Read manifest members
MEMBERS=$(python3 - <<PYEOF
import json, sys
manifest = json.load(open("$MANIFEST"))
for m in manifest["members"]:
    print(f"{m['slug']}|{m['relative_path']}")
PYEOF
)

fail_count=0
skip_count=0
ok_count=0

while IFS='|' read -r slug rel_path; do
  kit_dir="${HS_BASE_DIR}/${rel_path}"
  scip_out="${kit_dir}/scip/index.scip"
  sha_out="${scip_out}.sha256"

  if [ ! -d "$kit_dir" ]; then
    _log "WARN: $slug — dir not found: $kit_dir (skip)"
    skip_count=$((skip_count + 1))
    continue
  fi

  # mtime-guard: skip if SCIP is newer than all Sources files
  if [ -f "$scip_out" ]; then
    newest_src=$(find "${kit_dir}" -name '*.swift' -newer "$scip_out" 2>/dev/null | head -1)
    if [ -z "$newest_src" ]; then
      _log "skip (up-to-date): $slug"
      skip_count=$((skip_count + 1))
      continue
    fi
  fi

  _log "regen: $slug ($rel_path)"
  mkdir -p "$(dirname "$scip_out")"

  if ! palace-swift-scip-emit \
    --project "$slug" \
    --source-root "$kit_dir" \
    --output "$scip_out" >> "$LOG_FILE" 2>&1; then
    _log "FAIL: $slug — palace-swift-scip-emit exited non-zero"
    fail_count=$((fail_count + 1))
    continue
  fi

  # sha256 verification
  sha256sum "$scip_out" > "$sha_out"
  _log "sha256 ok: $slug → $(cat "$sha_out")"

  # rsync to iMac (SSH key auth only)
  remote_kit_dir="${IMAC_HS_PATH}/${rel_path}/scip/"
  if ! rsync \
    --partial --append-verify --checksum \
    -e "ssh -o ControlMaster=auto -o ControlPath=/tmp/hs-regen-%r@%h:%p -o ControlPersist=60" \
    "$scip_out" "$sha_out" \
    "${IMAC_HOST}:${remote_kit_dir}"; then
    _log "FAIL: $slug — rsync failed"
    fail_count=$((fail_count + 1))
    continue
  fi

  _log "done: $slug"
  ok_count=$((ok_count + 1))
done <<< "$MEMBERS"

_log "regen-uw-ios-scip DONE: ok=$ok_count skip=$skip_count fail=$fail_count"

if [ "$fail_count" -gt 0 ]; then
  echo "ERROR: $fail_count kit(s) failed — inspect $LOG_FILE" >&2
  exit 1
fi
