#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
DEFAULT_EMITTER_DIR="$REPO_ROOT/services/palace-mcp/scip_emit_swift"
DEFAULT_REMOTE_HOST="${IMAC_HOST:-imac-ssh.ant013.work}"
DEFAULT_REMOTE_BASE="${IMAC_HS_PATH:-/Users/Shared/Ios/HorizontalSystems}"
EMITTER_NAME="palace-swift-scip-emit-cli"
EMITTER_VERSION="2026-05-15"
DEFAULT_DESTINATION="generic/platform=iOS Simulator"

usage() {
    cat <<'EOF'
Usage: scip_emit_xcode_app.sh --repo-path <path> --scheme <name> --slug <name> --relative-path <name> [options]

Emit a SCIP index for an Xcode app from a workspace build on a dev Mac with
full Xcode, then copy it to the iMac repo mirror.

Required:
  --repo-path <path>          Local path to the Xcode app checkout
                              (must contain the .xcworkspace / .xcodeproj)
  --scheme <name>             xcodebuild scheme
  --slug <name>               Palace project slug
  --relative-path <name>      Remote-side relative path under remote-base

Options:
  --workspace <relpath>       Workspace path relative to --repo-path
                              (default: auto-detected first *.xcworkspace)
  --project <relpath>         Use -project instead of -workspace
                              (mutually exclusive with --workspace)
  --destination <spec>        xcodebuild destination
                              (default: 'generic/platform=iOS Simulator')
  --derived-data <path>       Explicit DerivedData root
                              (default: <repo>/.palace-scip-derived-data-app)
  --output <path>             SCIP output path
                              (default: <repo>/scip/index.scip)
  --remote-host <host>        SSH host for the iMac mirror
  --remote-base <path>        Remote base dir for repo mirrors
  --emitter-dir <path>        palace-swift-scip-emit package dir
  --emitter-bin <path>        Explicit emitter binary path
  --no-remote-copy            Skip scp + remote metadata write
  --dry-run                   Print intended actions without changing state
  --help, -h                  Show this message

Notes:
  - xcodebuild requires full Xcode (Command Line Tools alone are insufficient).
  - Workspace build pulls SwiftPM dependencies into DerivedData.
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

REPO_PATH=""
WORKSPACE_REL=""
PROJECT_REL=""
SCHEME_NAME=""
DESTINATION="$DEFAULT_DESTINATION"
DERIVED_DATA_ARG=""
OUTPUT_ARG=""
SLUG=""
RELATIVE_PATH=""
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

[[ -n "$REPO_PATH" ]]     || { usage >&2; die "--repo-path is required"; }
[[ -n "$SCHEME_NAME" ]]   || { usage >&2; die "--scheme is required"; }
[[ -n "$SLUG" ]]          || { usage >&2; die "--slug is required"; }
[[ -n "$RELATIVE_PATH" ]] || { usage >&2; die "--relative-path is required"; }
[[ -d "$REPO_PATH" ]]     || die "repo path not found: $REPO_PATH"

require_command python3
require_command xcrun
require_command ssh
require_command scp
require_full_xcode

if [[ -n "$WORKSPACE_REL" ]]; then
    BUILD_ARTIFACT="$REPO_PATH/$WORKSPACE_REL"
    BUILD_FLAG="-workspace"
    [[ -d "$BUILD_ARTIFACT" ]] || die "workspace not found: $BUILD_ARTIFACT"
elif [[ -n "$PROJECT_REL" ]]; then
    BUILD_ARTIFACT="$REPO_PATH/$PROJECT_REL"
    BUILD_FLAG="-project"
    [[ -d "$BUILD_ARTIFACT" ]] || die "project not found: $BUILD_ARTIFACT"
    [[ -f "$BUILD_ARTIFACT/project.pbxproj" ]] || die "project.pbxproj missing inside $BUILD_ARTIFACT"
else
    shopt -s nullglob
    ws_candidates=("$REPO_PATH"/*.xcworkspace)
    shopt -u nullglob
    [[ ${#ws_candidates[@]} -gt 0 ]] || die "no *.xcworkspace found in $REPO_PATH; use --workspace or --project"
    BUILD_ARTIFACT="${ws_candidates[0]}"
    BUILD_FLAG="-workspace"
    log "auto-detected workspace: $(basename "$BUILD_ARTIFACT")"
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

log "slug=$SLUG repo=$REPO_PATH workspace=$BUILD_ARTIFACT scheme=$SCHEME_NAME"

if [[ ! -x "$EMITTER_BIN" ]]; then
    log "building palace-swift-scip-emit"
    run_cmd xcrun swift build -c release --package-path "$EMITTER_DIR"
fi
[[ "$DRY_RUN" == "true" || -x "$EMITTER_BIN" ]] || die "emitter binary not found after build: $EMITTER_BIN"

log "preparing build directories"
if [[ "$DRY_RUN" == "false" ]]; then
    rm -rf "$DERIVED_DATA"
    mkdir -p "$DERIVED_DATA/Index.noindex" "$(dirname "$OUTPUT_PATH")"
else
    printf 'DRY-RUN: rm -rf %q\n' "$DERIVED_DATA"
    printf 'DRY-RUN: mkdir -p %q %q\n' "$DERIVED_DATA/Index.noindex" "$(dirname "$OUTPUT_PATH")"
fi

log "building app with xcodebuild (scheme=$SCHEME_NAME destination=$DESTINATION)"
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

log "emitting SCIP"
run_cmd "$EMITTER_BIN" \
    --derived-data "$DERIVED_DATA" \
    --project-root "$REPO_PATH" \
    --output "$OUTPUT_PATH" \
    --verbose

if [[ "$DRY_RUN" == "false" ]]; then
    [[ -s "$OUTPUT_PATH" ]] || die "generated SCIP file is missing or empty: $OUTPUT_PATH"
    HEAD_SHA="$(git -C "$REPO_PATH" rev-parse HEAD 2>/dev/null || echo unknown)"
    python3 - "$META_PATH" "$SLUG" "$REPO_PATH" "$REMOTE_BASE/$RELATIVE_PATH" "$HEAD_SHA" "$EMITTER_NAME" "$EMITTER_VERSION" "$SCHEME_NAME" "$(basename "$BUILD_ARTIFACT")" <<'PY'
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
    "package_path": sys.argv[9],
    "scheme": sys.argv[8],
    "generator_host": socket.gethostname(),
    "source_repo_path": str(Path(sys.argv[3]).resolve()),
    "destination_repo_path": str(Path(sys.argv[4]).resolve()),
}
meta_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
PY
    log "metadata written: $META_PATH"
fi

if [[ "$NO_REMOTE_COPY" == "true" ]]; then
    log "skipping remote copy (--no-remote-copy)"
else
    log "creating remote destination"
    run_cmd ssh "$REMOTE_HOST" "mkdir -p $REMOTE_DEST_DIR"
    log "copying SCIP to remote host"
    run_cmd scp "$OUTPUT_PATH" "$REMOTE_HOST:$REMOTE_DEST_PATH"
    if [[ -f "$META_PATH" ]]; then
        run_cmd scp "$META_PATH" "$REMOTE_HOST:$REMOTE_META_PATH"
    fi
fi

if [[ "$DRY_RUN" == "false" ]]; then
    cat <<EOF
slug=$SLUG
source=$OUTPUT_PATH
destination=$REMOTE_HOST:$REMOTE_DEST_PATH
metadata=$REMOTE_HOST:$REMOTE_META_PATH
size_bytes=$(stat -f%z "$OUTPUT_PATH" 2>/dev/null || stat -c%s "$OUTPUT_PATH" 2>/dev/null || echo 0)
EOF
else
    cat <<EOF
slug=$SLUG
source=$OUTPUT_PATH
destination=$REMOTE_HOST:$REMOTE_DEST_PATH
metadata=$REMOTE_HOST:$REMOTE_META_PATH
size_bytes=0
dry_run=true
EOF
fi
