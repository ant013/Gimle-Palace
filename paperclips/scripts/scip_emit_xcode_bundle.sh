#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
DEFAULT_MANIFEST="$REPO_ROOT/services/palace-mcp/scripts/uw-ios-bundle-manifest.json"
DEFAULT_EMIT_SCRIPT="$REPO_ROOT/paperclips/scripts/scip_emit_swift_kit.sh"
DEFAULT_LOCAL_REPO_BASE="${HS_REPO_ROOT:-/Users/Shared/Ios/HorizontalSystems}"
DEFAULT_REMOTE_HOST="${IMAC_HOST:-imac-ssh.ant013.work}"
DEFAULT_REMOTE_BASE="${IMAC_HS_PATH:-/Users/Shared/Ios/HorizontalSystems}"
DEFAULT_SCOPE="full"
FULL_SCOPE_MIN_SUCCESS_COUNT=35
SMOKE_SCOPE_MIN_SUCCESS_COUNT=4
SMOKE_MEMBERS=(
    "evm-kit:EvmKit.Swift"
    "bitcoin-core:BitcoinCore.Swift"
    "bitcoin-kit:BitcoinKit.Swift"
    "dash-kit:DashKit.Swift"
)

usage() {
    cat <<'EOF'
Usage: scip_emit_uw_ios_bundle.sh [options]

Emit SCIP for every uw-ios bundle member by reusing scip_emit_swift_kit.sh.
The script keeps going across member failures and prints a final JSON summary.

Options:
  --scope <full|smoke>     Member scope to process (default: full)
  --repo-root <path>      Local base dir for HorizontalSystems repos
                          (default: /Users/Shared/Ios/HorizontalSystems)
  --manifest <path>       Bundle manifest to iterate
  --emit-script <path>    Per-member helper script to invoke
  --remote-host <host>    SSH host for the iMac
  --remote-base <path>    Remote base dir that contains bundle repos
  --emitter-dir <path>    Forwarded to scip_emit_swift_kit.sh
  --emitter-bin <path>    Forwarded to scip_emit_swift_kit.sh
  --dry-run               Print planned work without changing state
  --help, -h              Show this message

Notes:
  - Membership comes from uw-ios-bundle-manifest.json.
  - `--scope=smoke` runs only the 4 Board-approved SwiftPM kits:
    evm-kit, bitcoin-core, bitcoin-kit, dash-kit.
  - Local path resolution is tolerant of the current dev-Mac layout:
    it tries <repo-root>/<relative_path>, <repo-root>/<relative_path>.Swift,
    then the parent directory of <repo-root> with the same two variants.
  - Exit code is 0 when dry-run is used or the scope threshold succeeds.
EOF
}

log() {
    printf '[%s] %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$*" >&2
}

die() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

require_command() {
    command -v "$1" >/dev/null 2>&1 || die "missing required command: $1"
}

validate_scope() {
    local scope="$1"
    case "$scope" in
        full|smoke) ;;
        *)
            die "invalid scope '$scope' (expected full or smoke)"
            ;;
    esac
}

manifest_members() {
    local manifest="$1"
    python3 - "$manifest" <<'PY'
import json
import sys
from pathlib import Path

manifest = json.loads(Path(sys.argv[1]).read_text())
for member in manifest.get("members", []):
    print(f"{member['slug']}\t{member['relative_path']}\ttrue")
PY
}

scope_members() {
    local manifest="$1"
    local scope="$2"
    shift 2
    if [[ "$scope" == "full" ]]; then
        manifest_members "$manifest"
        return 0
    fi

    python3 - "$manifest" "$@" <<'PY'
import json
import sys
from pathlib import Path

manifest = json.loads(Path(sys.argv[1]).read_text())
members_by_slug = {
    member["slug"]: member["relative_path"]
    for member in manifest.get("members", [])
}
for item in sys.argv[2:]:
    slug, fallback_relative_path = item.split(":", 1)
    relative_path = members_by_slug.get(slug, fallback_relative_path)
    manifest_match = "true" if slug in members_by_slug else "false"
    print(f"{slug}\t{relative_path}\t{manifest_match}")
PY
}

resolve_local_repo_path() {
    local repo_root="$1"
    local relative_path="$2"
    local sibling_root
    local candidate
    local previous=""

    sibling_root="$(dirname "$repo_root")"
    for candidate in \
        "$repo_root/$relative_path" \
        "$repo_root/${relative_path}.Swift" \
        "$sibling_root/$relative_path" \
        "$sibling_root/${relative_path}.Swift"
    do
        [[ "$candidate" == "$previous" ]] && continue
        if [[ -d "$candidate" ]]; then
            printf '%s\n' "$candidate"
            return 0
        fi
        previous="$candidate"
    done

    return 1
}

extract_key_value() {
    local key="$1"
    local file="$2"
    python3 - "$key" "$file" <<'PY'
import sys
from pathlib import Path

key = sys.argv[1]
path = Path(sys.argv[2])
for line in path.read_text().splitlines():
    if line.startswith(f"{key}="):
        print(line.split("=", 1)[1])
PY
}

append_result() {
    local results_file="$1"
    local slug="$2"
    local relative_path="$3"
    local manifest_match="$4"
    local local_repo_path="$5"
    local status="$6"
    local exit_code="$7"
    local duration_seconds="$8"
    local source_path="$9"
    local destination_path="${10}"
    local size_bytes="${11}"
    local error_message="${12}"

    python3 - "$results_file" "$slug" "$relative_path" "$manifest_match" "$local_repo_path" \
        "$status" "$exit_code" "$duration_seconds" "$source_path" "$destination_path" \
        "$size_bytes" "$error_message" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])

def maybe_int(value: str):
    return int(value) if value else None

payload = {
    "slug": sys.argv[2],
    "relative_path": sys.argv[3],
    "manifest_match": sys.argv[4] == "true",
    "local_repo_path": sys.argv[5] or None,
    "status": sys.argv[6],
    "exit_code": int(sys.argv[7]),
    "duration_seconds": int(sys.argv[8]),
    "source_path": sys.argv[9] or None,
    "destination_path": sys.argv[10] or None,
    "size_bytes": maybe_int(sys.argv[11]),
    "error": sys.argv[12] or None,
}

with path.open("a", encoding="utf-8") as fh:
    fh.write(json.dumps(payload, sort_keys=True))
    fh.write("\n")
PY
}

LOCAL_REPO_BASE="$DEFAULT_LOCAL_REPO_BASE"
MANIFEST_PATH="$DEFAULT_MANIFEST"
EMIT_SCRIPT="$DEFAULT_EMIT_SCRIPT"
REMOTE_HOST="$DEFAULT_REMOTE_HOST"
REMOTE_BASE="$DEFAULT_REMOTE_BASE"
SCOPE="$DEFAULT_SCOPE"
EMITTER_DIR=""
EMITTER_BIN=""
DRY_RUN="false"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --scope=*)
            SCOPE="${1#*=}"
            shift
            ;;
        --scope)
            [[ $# -ge 2 ]] || die "--scope requires a value"
            SCOPE="$2"
            shift 2
            ;;
        --repo-root=*)
            LOCAL_REPO_BASE="${1#*=}"
            shift
            ;;
        --repo-root)
            [[ $# -ge 2 ]] || die "--repo-root requires a value"
            LOCAL_REPO_BASE="$2"
            shift 2
            ;;
        --manifest=*)
            MANIFEST_PATH="${1#*=}"
            shift
            ;;
        --manifest)
            [[ $# -ge 2 ]] || die "--manifest requires a value"
            MANIFEST_PATH="$2"
            shift 2
            ;;
        --emit-script=*)
            EMIT_SCRIPT="${1#*=}"
            shift
            ;;
        --emit-script)
            [[ $# -ge 2 ]] || die "--emit-script requires a value"
            EMIT_SCRIPT="$2"
            shift 2
            ;;
        --remote-host=*)
            REMOTE_HOST="${1#*=}"
            shift
            ;;
        --remote-host)
            [[ $# -ge 2 ]] || die "--remote-host requires a value"
            REMOTE_HOST="$2"
            shift 2
            ;;
        --remote-base=*)
            REMOTE_BASE="${1#*=}"
            shift
            ;;
        --remote-base)
            [[ $# -ge 2 ]] || die "--remote-base requires a value"
            REMOTE_BASE="$2"
            shift 2
            ;;
        --emitter-dir=*)
            EMITTER_DIR="${1#*=}"
            shift
            ;;
        --emitter-dir)
            [[ $# -ge 2 ]] || die "--emitter-dir requires a value"
            EMITTER_DIR="$2"
            shift 2
            ;;
        --emitter-bin=*)
            EMITTER_BIN="${1#*=}"
            shift
            ;;
        --emitter-bin)
            [[ $# -ge 2 ]] || die "--emitter-bin requires a value"
            EMITTER_BIN="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN="true"
            shift
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        --*)
            die "unknown option: $1"
            ;;
        *)
            die "unexpected positional argument: $1"
            ;;
    esac
done

require_command bash
require_command python3
validate_scope "$SCOPE"
[[ -f "$MANIFEST_PATH" ]] || die "manifest not found: $MANIFEST_PATH"
[[ -f "$EMIT_SCRIPT" ]] || die "emit helper not found: $EMIT_SCRIPT"

if [[ "$SCOPE" == "smoke" ]]; then
    MEMBERS_TSV="$(scope_members "$MANIFEST_PATH" "$SCOPE" "${SMOKE_MEMBERS[@]}")"
    MIN_SUCCESS_COUNT="$SMOKE_SCOPE_MIN_SUCCESS_COUNT"
else
    MEMBERS_TSV="$(scope_members "$MANIFEST_PATH" "$SCOPE")"
    MIN_SUCCESS_COUNT="$FULL_SCOPE_MIN_SUCCESS_COUNT"
fi
MEMBERS_TOTAL="$(printf '%s\n' "$MEMBERS_TSV" | sed '/^$/d' | wc -l | tr -d ' ')"
[[ "$MEMBERS_TOTAL" -gt 0 ]] || die "manifest has no members: $MANIFEST_PATH"

RESULTS_FILE="$(mktemp "${TMPDIR:-/tmp}/uw-ios-scip-emit-results.XXXXXX")"
RUN_LOG_DIR="$(mktemp -d "${TMPDIR:-/tmp}/uw-ios-scip-emit-logs.XXXXXX")"
START_EPOCH="$(date +%s)"

index=0
ok_count=0
failed_count=0

while IFS=$'\t' read -r slug relative_path manifest_match; do
    [[ -n "${slug:-}" ]] || continue
    index=$((index + 1))
    member_start_epoch="$(date +%s)"
    source_path=""
    destination_path=""
    size_bytes=""
    error_message=""
    local_repo_path=""
    member_status="missing_repo"
    member_exit_code=1
    member_log_file="$RUN_LOG_DIR/${slug}.log"

    if local_repo_path="$(resolve_local_repo_path "$LOCAL_REPO_BASE" "$relative_path")"; then
        cmd=(
            bash "$EMIT_SCRIPT" "$slug"
            --repo-path "$local_repo_path"
            --remote-relative-path "$relative_path"
            --manifest "$MANIFEST_PATH"
            --remote-host "$REMOTE_HOST"
            --remote-base "$REMOTE_BASE"
        )
        if [[ -n "$EMITTER_DIR" ]]; then
            cmd+=(--emitter-dir "$EMITTER_DIR")
        fi
        if [[ -n "$EMITTER_BIN" ]]; then
            cmd+=(--emitter-bin "$EMITTER_BIN")
        fi
        if [[ "$DRY_RUN" == "true" ]]; then
            cmd+=(--dry-run)
        fi

        log "[$index/$MEMBERS_TOTAL] emitting $slug from $local_repo_path"
        set +e
        "${cmd[@]}" >"$member_log_file" 2>&1
        member_exit_code=$?
        set -e

        source_path="$(extract_key_value source "$member_log_file" || true)"
        destination_path="$(extract_key_value destination "$member_log_file" || true)"
        size_bytes="$(extract_key_value size_bytes "$member_log_file" || true)"
        if [[ "$member_exit_code" -eq 0 ]]; then
            member_status="ok"
            ok_count=$((ok_count + 1))
        else
            member_status="helper_failed"
            error_message="$(tail -n 5 "$member_log_file" | tr '\n' ' ' | sed 's/[[:space:]]\+/ /g; s/^ //; s/ $//')"
            failed_count=$((failed_count + 1))
        fi
    else
        error_message="local repo path not found under $LOCAL_REPO_BASE for relative_path=$relative_path"
        printf '%s\n' "$error_message" >"$member_log_file"
        failed_count=$((failed_count + 1))
        log "[$index/$MEMBERS_TOTAL] missing local repo for $slug ($relative_path)"
    fi

    member_duration_seconds="$(( $(date +%s) - member_start_epoch ))"
    append_result \
        "$RESULTS_FILE" \
        "$slug" \
        "$relative_path" \
        "${manifest_match:-true}" \
        "$local_repo_path" \
        "$member_status" \
        "$member_exit_code" \
        "$member_duration_seconds" \
        "$source_path" \
        "$destination_path" \
        "$size_bytes" \
        "$error_message"
done <<< "$MEMBERS_TSV"

END_EPOCH="$(date +%s)"

python3 - "$RESULTS_FILE" "$MANIFEST_PATH" "$SCOPE" "$LOCAL_REPO_BASE" "$REMOTE_HOST" "$REMOTE_BASE" \
    "$DRY_RUN" "$START_EPOCH" "$END_EPOCH" "$MIN_SUCCESS_COUNT" "$RUN_LOG_DIR" <<'PY'
import json
import sys
from pathlib import Path

results_path = Path(sys.argv[1])
manifest_path = Path(sys.argv[2])
scope = sys.argv[3]
local_repo_base = sys.argv[4]
remote_host = sys.argv[5]
remote_base = sys.argv[6]
dry_run = sys.argv[7] == "true"
started_at_epoch = int(sys.argv[8])
finished_at_epoch = int(sys.argv[9])
min_success_count = int(sys.argv[10])
run_log_dir = sys.argv[11]

manifest = json.loads(manifest_path.read_text())
members = [json.loads(line) for line in results_path.read_text().splitlines() if line.strip()]
ok_count = sum(1 for member in members if member["status"] == "ok")
failed_count = len(members) - ok_count

summary = {
    "bundle_name": manifest.get("bundle_name", "uw-ios"),
    "scope": scope,
    "members_total": len(members),
    "members_ok": ok_count,
    "members_failed": failed_count,
    "min_success_count": min_success_count,
    "meets_success_threshold": ok_count >= min_success_count,
    "dry_run": dry_run,
    "local_repo_base": local_repo_base,
    "remote_host": remote_host,
    "remote_base": remote_base,
    "started_at_epoch": started_at_epoch,
    "finished_at_epoch": finished_at_epoch,
    "duration_seconds": finished_at_epoch - started_at_epoch,
    "run_log_dir": run_log_dir,
    "members": members,
}
print(json.dumps(summary, indent=2, sort_keys=True))
PY

if [[ "$DRY_RUN" == "true" || "$ok_count" -ge "$MIN_SUCCESS_COUNT" ]]; then
    exit 0
fi

exit 1
