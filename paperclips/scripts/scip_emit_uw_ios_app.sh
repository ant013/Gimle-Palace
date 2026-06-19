#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
DEFAULT_EMITTER_DIR="$REPO_ROOT/services/palace-mcp/scip_emit_swift"
DEFAULT_REMOTE_HOST="${IMAC_HOST:-imac-ssh.ant013.work}"
DEFAULT_REMOTE_BASE="${IMAC_HS_PATH:-/Users/Shared/Ios/HorizontalSystems}"
EMITTER_NAME="palace-swift-scip-emit-cli"
EMITTER_VERSION="2026-05-15"
DEFAULT_SLUG="uw-ios-app"
DEFAULT_RELATIVE_PATH="unstoppable-wallet-ios"
DEFAULT_SCHEME="Development"
DEFAULT_DESTINATION="generic/platform=iOS Simulator"

usage() {
    cat <<'EOF'
Usage: scip_emit_uw_ios_app.sh --repo-path <unstoppable-wallet-ios> [options]

Emit the unstoppable-wallet-ios app SCIP index from an Xcode workspace build
on a dev Mac with full Xcode, then copy it to the iMac repo mirror.

Required:
  --repo-path <path>          Local path to unstoppable-wallet-ios checkout
                              (must contain the .xcworkspace / .xcodeproj)

Options:
  --workspace <relpath>       Workspace path relative to --repo-path
                              (default: Wallet.xcworkspace)
  --project <relpath>         Use -project instead of -workspace
                              (mutually exclusive with --workspace)
  --scheme <name>             xcodebuild scheme (default: Development)
  --destination <spec>        xcodebuild destination
                              (default: 'generic/platform=iOS Simulator')
  --derived-data <path>       Explicit DerivedData root
                              (default: <repo>/.palace-scip-derived-data-app)
  --output <path>             SCIP output path
                              (default: <repo>/scip/index.scip)
  --slug <name>               Palace project slug
                              (default: uw-ios-app)
  --relative-path <name>      Remote-side relative path under remote-base
                              (default: unstoppable-wallet-ios)
  --container-scip-path <p>   Container-visible SCIP path for extractor env
                              (default: /repos-hs/<relative-path>/scip/index.scip)
  --container-indexstore-path <p>
                              Container-visible IndexStore path for call_hierarchy
                              (default: /repos-hs/<relative-path>/.palace-scip-derived-data-app/Index.noindex/DataStore)
  --env-file <path>           Optional local env file to merge
                              PALACE_SCIP_INDEX_PATHS[slug] and
                              PALACE_INDEXSTORE_PATHS[slug]
  --remote-host <host>        SSH host for the iMac mirror
  --remote-base <path>        Remote base dir for repo mirrors
  --emitter-dir <path>        palace-swift-scip-emit package dir
  --emitter-bin <path>        Explicit emitter binary path
  --no-remote-copy            Skip scp + remote metadata write
  --dry-run                   Print intended actions without changing state
  --help, -h                  Show this message

Notes:
  - xcodebuild requires full Xcode (Command Line Tools alone are insufficient).
  - Workspace build pulls SwiftPM dependencies (HS Kits) into DerivedData.
    Additional per-kit SCIP can be emitted from the same DerivedData by
    re-invoking palace-swift-scip-emit-cli with a different --project-root.
EOF
}

log() {
    printf '[%s] %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$*"
}

die() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

require_command() {
    command -v "$1" >/dev/null 2>&1 || die "missing required command: $1"
}

require_full_xcode() {
    local dev_dir
    dev_dir="$(xcode-select -p 2>/dev/null || true)"
    if [[ -z "$dev_dir" || "$dev_dir" == *"CommandLineTools"* ]]; then
        die "xcodebuild requires full Xcode; current developer dir: ${dev_dir:-<none>}. Install Xcode and 'sudo xcode-select -s /Applications/Xcode.app/Contents/Developer'."
    fi
    xcrun -f xcodebuild >/dev/null 2>&1 || \
        die "xcrun cannot locate xcodebuild even though DEVELOPER_DIR=$dev_dir"
}

run_cmd() {
    if [[ "$DRY_RUN" == "true" ]]; then
        printf 'DRY-RUN:'
        printf ' %q' "$@"
        printf '\n'
        return 0
    fi
    "$@"
}

xcodebuild_emitted_index() {
    [[ -d "$DERIVED_DATA/Index.noindex" ]] || return 1
    find "$DERIVED_DATA/Index.noindex" -mindepth 1 -print -quit | grep -q .
}

prepare_config_xcconfig() {
    local config_dir="$REPO_PATH/Unstoppable/Unstoppable/Configuration"
    local template="$config_dir/Config.template.xcconfig"
    local config="$config_dir/Config.xcconfig"

    if [[ -f "$config" ]]; then
        return 0
    fi
    if [[ ! -d "$config_dir" ]]; then
        log "Config.xcconfig directory not present; skipping UW config prepare"
        return 0
    fi
    [[ -f "$template" ]] || die "Config.xcconfig missing and template not found: $template"

    log "preparing Config.xcconfig from $template"
    run_cmd cp "$template" "$config"
}

run_xcodebuild_build() {
    local status
    if [[ "$DRY_RUN" == "true" ]]; then
        run_cmd xcrun xcodebuild \
            "$BUILD_FLAG" "$BUILD_ARTIFACT" \
            -scheme "$SCHEME_NAME" \
            -destination "$DESTINATION" \
            -derivedDataPath "$DERIVED_DATA" \
            -IDEIndexDisable=NO \
            -IDEBuildLocationStyle=Custom \
            CODE_SIGNING_ALLOWED=NO \
            CODE_SIGNING_REQUIRED=NO \
            build
        return 0
    fi

    set +e
    xcrun xcodebuild \
        "$BUILD_FLAG" "$BUILD_ARTIFACT" \
        -scheme "$SCHEME_NAME" \
        -destination "$DESTINATION" \
        -derivedDataPath "$DERIVED_DATA" \
        -IDEIndexDisable=NO \
        -IDEBuildLocationStyle=Custom \
        CODE_SIGNING_ALLOWED=NO \
        CODE_SIGNING_REQUIRED=NO \
        build
    status=$?
    set -e

    if [[ "$status" -eq 0 ]]; then
        return 0
    fi
    if xcodebuild_emitted_index; then
        log "xcodebuild exited $status after producing index data; continuing to SCIP emit"
        return 0
    fi
    return "$status"
}

merge_scip_index_env_mapping() {
    merge_env_json_mapping "PALACE_SCIP_INDEX_PATHS" "$@"
}

merge_indexstore_env_mapping() {
    merge_env_json_mapping "PALACE_INDEXSTORE_PATHS" "$@"
}

merge_env_json_mapping() {
    local env_key="$1"
    local env_file="$2"
    local slug="$3"
    local value="$4"

    if [[ "$DRY_RUN" == "true" ]]; then
        printf 'DRY-RUN: merge %s %s[%s]=%s\n' \
            "$env_file" "$env_key" "$slug" "$value"
        return 0
    fi

    python3 - "$env_key" "$env_file" "$slug" "$value" <<'PY'
import json
import sys
from pathlib import Path

env_key = sys.argv[1]
env_file = Path(sys.argv[2])
slug = sys.argv[3]
value = sys.argv[4]
env_file.parent.mkdir(parents=True, exist_ok=True)
lines = env_file.read_text(encoding="utf-8").splitlines() if env_file.exists() else []

merged = {}
new_lines = []
found = False
for line in lines:
    if not line.startswith(f"{env_key}="):
        new_lines.append(line)
        continue
    if found:
        continue
    found = True
    raw = line.split("=", 1)[1]
    if raw.strip():
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"{env_key} is not valid JSON in {env_file}: {exc}")
        if not isinstance(parsed, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in parsed.items()
        ):
            raise SystemExit(f"{env_key} must be a JSON object of string paths")
        merged.update(parsed)
    merged[slug] = value
    encoded = json.dumps(merged, sort_keys=True, separators=(",", ":"))
    new_lines.append(f"{env_key}={encoded}")

if not found:
    merged[slug] = value
    encoded = json.dumps(merged, sort_keys=True, separators=(",", ":"))
    new_lines.append(f"{env_key}={encoded}")

env_file.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
PY
}

detect_store_format() {
    python3 - "$REPO_ROOT/services/palace-mcp/src" "$1" <<'PY'
import sys

sys.path.insert(0, sys.argv[1])

from palace_mcp.code.call_hierarchy import _detect_store_format

result = _detect_store_format(sys.argv[2])
if result:
    print(result)
PY
}

verify_v5_indexstore() {
    local data_store_path="$1"
    local fmt

    fmt="$(detect_store_format "$data_store_path")"
    if [[ "$fmt" == "unidb" ]]; then
        die "IndexStore at $data_store_path is UniDB format. palace.code.call_hierarchy requires v5 DataStore; stop here and report the toolchain limitation."
    fi
    [[ "$fmt" == "v5" ]] || die "IndexStore path missing or unrecognized at $data_store_path"
    find "$data_store_path/v5" -name '*.IDXU' -print -quit | grep -q . || \
        die "IndexStore at $data_store_path is missing v5/*.IDXU records"
}

REPO_PATH=""
WORKSPACE_REL="Wallet.xcworkspace"
PROJECT_REL=""
SCHEME_NAME="$DEFAULT_SCHEME"
DESTINATION="$DEFAULT_DESTINATION"
DERIVED_DATA_ARG=""
OUTPUT_ARG=""
SLUG="$DEFAULT_SLUG"
RELATIVE_PATH="$DEFAULT_RELATIVE_PATH"
CONTAINER_SCIP_PATH_ARG=""
CONTAINER_INDEXSTORE_PATH_ARG=""
ENV_FILE=""
REMOTE_HOST="$DEFAULT_REMOTE_HOST"
REMOTE_BASE="$DEFAULT_REMOTE_BASE"
EMITTER_DIR="$DEFAULT_EMITTER_DIR"
EMITTER_BIN=""
NO_REMOTE_COPY="false"
DRY_RUN="false"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --repo-path=*)  REPO_PATH="${1#*=}"; shift ;;
        --repo-path)    [[ $# -ge 2 ]] || die "--repo-path requires a value"; REPO_PATH="$2"; shift 2 ;;
        --workspace=*)  WORKSPACE_REL="${1#*=}"; PROJECT_REL=""; shift ;;
        --workspace)    [[ $# -ge 2 ]] || die "--workspace requires a value"; WORKSPACE_REL="$2"; PROJECT_REL=""; shift 2 ;;
        --project=*)    PROJECT_REL="${1#*=}"; WORKSPACE_REL=""; shift ;;
        --project)      [[ $# -ge 2 ]] || die "--project requires a value"; PROJECT_REL="$2"; WORKSPACE_REL=""; shift 2 ;;
        --scheme=*)     SCHEME_NAME="${1#*=}"; shift ;;
        --scheme)       [[ $# -ge 2 ]] || die "--scheme requires a value"; SCHEME_NAME="$2"; shift 2 ;;
        --destination=*) DESTINATION="${1#*=}"; shift ;;
        --destination)  [[ $# -ge 2 ]] || die "--destination requires a value"; DESTINATION="$2"; shift 2 ;;
        --derived-data=*) DERIVED_DATA_ARG="${1#*=}"; shift ;;
        --derived-data) [[ $# -ge 2 ]] || die "--derived-data requires a value"; DERIVED_DATA_ARG="$2"; shift 2 ;;
        --output=*)     OUTPUT_ARG="${1#*=}"; shift ;;
        --output)       [[ $# -ge 2 ]] || die "--output requires a value"; OUTPUT_ARG="$2"; shift 2 ;;
        --slug=*)       SLUG="${1#*=}"; shift ;;
        --slug)         [[ $# -ge 2 ]] || die "--slug requires a value"; SLUG="$2"; shift 2 ;;
        --relative-path=*) RELATIVE_PATH="${1#*=}"; shift ;;
        --relative-path) [[ $# -ge 2 ]] || die "--relative-path requires a value"; RELATIVE_PATH="$2"; shift 2 ;;
        --container-scip-path=*) CONTAINER_SCIP_PATH_ARG="${1#*=}"; shift ;;
        --container-scip-path) [[ $# -ge 2 ]] || die "--container-scip-path requires a value"; CONTAINER_SCIP_PATH_ARG="$2"; shift 2 ;;
        --container-indexstore-path=*) CONTAINER_INDEXSTORE_PATH_ARG="${1#*=}"; shift ;;
        --container-indexstore-path) [[ $# -ge 2 ]] || die "--container-indexstore-path requires a value"; CONTAINER_INDEXSTORE_PATH_ARG="$2"; shift 2 ;;
        --env-file=*)   ENV_FILE="${1#*=}"; shift ;;
        --env-file)     [[ $# -ge 2 ]] || die "--env-file requires a value"; ENV_FILE="$2"; shift 2 ;;
        --remote-host=*) REMOTE_HOST="${1#*=}"; shift ;;
        --remote-host)  [[ $# -ge 2 ]] || die "--remote-host requires a value"; REMOTE_HOST="$2"; shift 2 ;;
        --remote-base=*) REMOTE_BASE="${1#*=}"; shift ;;
        --remote-base)  [[ $# -ge 2 ]] || die "--remote-base requires a value"; REMOTE_BASE="$2"; shift 2 ;;
        --emitter-dir=*) EMITTER_DIR="${1#*=}"; shift ;;
        --emitter-dir)  [[ $# -ge 2 ]] || die "--emitter-dir requires a value"; EMITTER_DIR="$2"; shift 2 ;;
        --emitter-bin=*) EMITTER_BIN="${1#*=}"; shift ;;
        --emitter-bin)  [[ $# -ge 2 ]] || die "--emitter-bin requires a value"; EMITTER_BIN="$2"; shift 2 ;;
        --no-remote-copy) NO_REMOTE_COPY="true"; shift ;;
        --dry-run)      DRY_RUN="true"; shift ;;
        --help|-h)      usage; exit 0 ;;
        --*)            die "unknown option: $1" ;;
        *)              die "unexpected positional argument: $1" ;;
    esac
done

[[ -n "$REPO_PATH" ]] || { usage >&2; die "--repo-path is required"; }
[[ -d "$REPO_PATH" ]] || die "repo path not found: $REPO_PATH"

require_command python3
require_command xcrun
require_command ssh
require_command scp
require_full_xcode

if [[ -n "$WORKSPACE_REL" ]]; then
    BUILD_ARTIFACT="$REPO_PATH/$WORKSPACE_REL"
    BUILD_FLAG="-workspace"
    [[ -d "$BUILD_ARTIFACT" ]] || die "workspace not found: $BUILD_ARTIFACT"
else
    BUILD_ARTIFACT="$REPO_PATH/$PROJECT_REL"
    BUILD_FLAG="-project"
    [[ -d "$BUILD_ARTIFACT" ]] || die "project not found: $BUILD_ARTIFACT"
    [[ -f "$BUILD_ARTIFACT/project.pbxproj" ]] || die "project.pbxproj missing inside $BUILD_ARTIFACT"
fi

[[ -d "$EMITTER_DIR" ]] || die "emitter package dir not found: $EMITTER_DIR"
if [[ -z "$EMITTER_BIN" ]]; then
    EMITTER_BIN="$EMITTER_DIR/.build/release/palace-swift-scip-emit-cli"
fi

DERIVED_DATA="${DERIVED_DATA_ARG:-$REPO_PATH/.palace-scip-derived-data-app}"
OUTPUT_PATH="${OUTPUT_ARG:-$REPO_PATH/scip/index.scip}"
META_PATH="${OUTPUT_PATH}.meta.json"
REMOTE_DEST_DIR="$REMOTE_BASE/$RELATIVE_PATH/scip"
REMOTE_DEST_PATH="$REMOTE_DEST_DIR/index.scip"
REMOTE_META_PATH="$REMOTE_DEST_DIR/index.scip.meta.json"
CONTAINER_SCIP_PATH="${CONTAINER_SCIP_PATH_ARG:-/repos-hs/$RELATIVE_PATH/scip/index.scip}"
DATA_STORE_PATH="$DERIVED_DATA/Index.noindex/DataStore"
REMOTE_INDEXSTORE_DIR="$REMOTE_BASE/$RELATIVE_PATH/.palace-scip-derived-data-app/Index.noindex"
REMOTE_INDEXSTORE_PATH="$REMOTE_INDEXSTORE_DIR/DataStore"
CONTAINER_INDEXSTORE_PATH="${CONTAINER_INDEXSTORE_PATH_ARG:-/repos-hs/$RELATIVE_PATH/.palace-scip-derived-data-app/Index.noindex/DataStore}"

log "slug=$SLUG repo=$REPO_PATH workspace=$BUILD_ARTIFACT scheme=$SCHEME_NAME"

if [[ ! -x "$EMITTER_BIN" ]]; then
    log "building palace-swift-scip-emit"
    run_cmd xcrun swift build -c release --package-path "$EMITTER_DIR"
fi
[[ "$DRY_RUN" == "true" || -x "$EMITTER_BIN" ]] || die "emitter binary not found after build: $EMITTER_BIN"

log "preparing build directories"
if [[ "$DRY_RUN" == "false" ]]; then
    rm -rf "$DERIVED_DATA"
    mkdir -p "$DERIVED_DATA" "$(dirname "$OUTPUT_PATH")"
else
    printf 'DRY-RUN: rm -rf %q\n' "$DERIVED_DATA"
    printf 'DRY-RUN: mkdir -p %q %q\n' "$DERIVED_DATA" "$(dirname "$OUTPUT_PATH")"
fi

prepare_config_xcconfig

log "building app with xcodebuild (scheme=$SCHEME_NAME destination=$DESTINATION)"
run_xcodebuild_build

log "verifying retained IndexStore at $DATA_STORE_PATH"
verify_v5_indexstore "$DATA_STORE_PATH"

log "emitting SCIP"
run_cmd "$EMITTER_BIN" \
    --derived-data "$DERIVED_DATA" \
    --project-root "$REPO_PATH" \
    --output "$OUTPUT_PATH" \
    --verbose

if [[ "$DRY_RUN" == "false" ]]; then
    [[ -s "$OUTPUT_PATH" ]] || die "generated SCIP file is missing or empty: $OUTPUT_PATH"
    HEAD_SHA="$(git -C "$REPO_PATH" rev-parse HEAD 2>/dev/null || echo unknown)"
    python3 - "$META_PATH" "$SLUG" "$REPO_PATH" "$REMOTE_BASE/$RELATIVE_PATH" "$HEAD_SHA" "$EMITTER_NAME" "$EMITTER_VERSION" "$SCHEME_NAME" <<'PY'
import json
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path

meta_path = Path(sys.argv[1])
payload = {
    "slug": sys.argv[2],
    "repo_head_sha": sys.argv[5],
    "emitter_name": sys.argv[6],
    "emitter_version": sys.argv[7],
    "artifact_origin": "remote_copy",
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "package_path": "Wallet.xcworkspace",
    "scheme": sys.argv[8],
    "generator_host": socket.gethostname(),
    "source_repo_path": str(Path(sys.argv[3]).resolve()),
    "destination_repo_path": str(Path(sys.argv[4]).resolve()),
}
meta_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
PY
    log "metadata written: $META_PATH"
fi

if [[ -n "$ENV_FILE" ]]; then
    log "merging PALACE_SCIP_INDEX_PATHS for $SLUG into $ENV_FILE"
    merge_scip_index_env_mapping "$ENV_FILE" "$SLUG" "$CONTAINER_SCIP_PATH"
    log "merging PALACE_INDEXSTORE_PATHS for $SLUG into $ENV_FILE"
    merge_indexstore_env_mapping "$ENV_FILE" "$SLUG" "$CONTAINER_INDEXSTORE_PATH"
fi

if [[ "$NO_REMOTE_COPY" == "true" ]]; then
    log "skipping remote copy (--no-remote-copy)"
else
    log "creating remote destination"
    run_cmd ssh "$REMOTE_HOST" "mkdir -p $REMOTE_DEST_DIR $REMOTE_INDEXSTORE_DIR && rm -rf $REMOTE_INDEXSTORE_PATH"
    log "copying SCIP to remote host"
    run_cmd scp "$OUTPUT_PATH" "$REMOTE_HOST:$REMOTE_DEST_PATH"
    log "copying retained IndexStore to remote host"
    run_cmd scp -r "$DATA_STORE_PATH" "$REMOTE_HOST:$REMOTE_INDEXSTORE_PATH"
    if [[ -f "$META_PATH" ]]; then
        run_cmd scp "$META_PATH" "$REMOTE_HOST:$REMOTE_META_PATH"
    fi
fi

if [[ "$DRY_RUN" == "false" ]]; then
    size_bytes="$(stat -f%z "$OUTPUT_PATH" 2>/dev/null || stat -c%s "$OUTPUT_PATH" 2>/dev/null || echo 0)"
    cat <<EOF
slug=$SLUG
source=$OUTPUT_PATH
destination=$REMOTE_HOST:$REMOTE_DEST_PATH
metadata=$REMOTE_HOST:$REMOTE_META_PATH
container_scip_path=$CONTAINER_SCIP_PATH
index_store_path=$DATA_STORE_PATH
container_indexstore_path=$CONTAINER_INDEXSTORE_PATH
index_store_format=v5
size_bytes=$size_bytes
scip_size_bytes=$size_bytes
dry_run=false
EOF
else
    cat <<EOF
slug=$SLUG
source=$OUTPUT_PATH
destination=$REMOTE_HOST:$REMOTE_DEST_PATH
metadata=$REMOTE_HOST:$REMOTE_META_PATH
container_scip_path=$CONTAINER_SCIP_PATH
index_store_path=$DATA_STORE_PATH
container_indexstore_path=$CONTAINER_INDEXSTORE_PATH
index_store_format=v5
size_bytes=0
scip_size_bytes=0
dry_run=true
EOF
fi
