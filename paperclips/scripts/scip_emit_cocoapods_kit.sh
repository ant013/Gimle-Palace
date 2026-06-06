#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
DEFAULT_EMITTER_DIR="$REPO_ROOT/services/palace-mcp/scip_emit_swift"
DEFAULT_REMOTE_HOST="${IMAC_HOST:-imac-ssh.ant013.work}"
DEFAULT_REMOTE_BASE="${IMAC_HS_PATH:-/Users/Shared/Ios/HorizontalSystems}"
EMITTER_NAME="palace-swift-scip-emit-cli"
EMITTER_VERSION="2026-05-28"
DEFAULT_DESTINATION="generic/platform=iOS Simulator"
DEFAULT_PODFILE_DIR="Example"

usage() {
    cat <<'EOF'
Usage: scip_emit_cocoapods_kit.sh <project-slug> --repo-path <path> [options]

Run pod install for a CocoaPods/Xcode-only kit, build it with xcodebuild, and
emit SCIP from the resulting DerivedData index.

Required:
  <project-slug>             Palace project slug for metadata output
  --repo-path <path>         Local repo checkout that contains Example/Podfile

Options:
  --podfile-dir <relpath>    Podfile dir relative to --repo-path
                             (default: Example)
  --workspace <relpath>      Workspace path relative to --repo-path
                             (default: auto-detect one in --podfile-dir)
  --project <relpath>        Use -project instead of -workspace
  --scheme <name>            xcodebuild scheme
                             (default: auto-detect shared scheme)
  --destination <spec>       xcodebuild destination
                             (default: 'generic/platform=iOS Simulator')
  --derived-data <path>      Explicit DerivedData root
                             (default: <repo>/.palace-scip-derived-data-cocoapods)
  --output <path>            SCIP output path
                             (default: <repo>/scip/index.scip)
  --relative-path <name>     Remote-side relative path under remote-base
                             (default: repo dir basename)
  --remote-host <host>       SSH host for the iMac mirror
  --remote-base <path>       Remote base dir for repo mirrors
  --emitter-dir <path>       palace-swift-scip-emit package dir
  --emitter-bin <path>       Explicit emitter binary path
  --no-remote-copy           Skip scp + remote metadata write
  --dry-run                  Print intended actions without changing state
  --help, -h                 Show this message

Notes:
  - Auto scheme detection prefers <WorkspaceName>, then <WorkspaceName>Example,
    then the only shared scheme if there is exactly one.
  - xcodebuild requires full Xcode (Command Line Tools alone are insufficient).
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

validate_slug() {
    local slug="$1"
    [[ "$slug" =~ ^[a-z0-9]([a-z0-9-]{0,62}[a-z0-9])?$ ]] || \
        die "invalid slug '$slug' (must match [a-z0-9-]{1,64})"
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

run_in_dir() {
    local dir="$1"
    shift
    if [[ "$DRY_RUN" == "true" ]]; then
        printf 'DRY-RUN: (cd %q &&' "$dir"
        printf ' %q' "$@"
        printf ')\n'
        return 0
    fi
    (
        cd "$dir"
        "$@"
    )
}

xcodebuild_emitted_index() {
    [[ -d "$DERIVED_DATA/Index.noindex" ]] || return 1
    find "$DERIVED_DATA/Index.noindex" -mindepth 1 -print -quit | grep -q .
}

discover_workspace_rel() {
    local podfile_dir="$1"
    local -a workspaces

    while IFS= read -r workspace; do
        workspaces+=("$workspace")
    done < <(find "$podfile_dir" -maxdepth 1 -type d -name '*.xcworkspace' | sort)
    if [[ "${#workspaces[@]}" -eq 1 ]]; then
        printf '%s' "${workspaces[0]#$REPO_PATH/}"
        return 0
    fi
    if [[ "${#workspaces[@]}" -eq 0 ]]; then
        die "no .xcworkspace found under $podfile_dir; pass --workspace explicitly"
    fi
    die "multiple .xcworkspace directories found under $podfile_dir; pass --workspace explicitly"
}

discover_scheme() {
    local workspace_base="$1"
    local -a schemes
    local scheme

    while IFS= read -r scheme; do
        schemes+=("$scheme")
    done < <(
        find "$PODFILE_DIR" -type f -path '*/xcshareddata/xcschemes/*.xcscheme' \
            -exec basename {} .xcscheme \; | sort -u
    )

    for scheme in "${schemes[@]}"; do
        if [[ "$scheme" == "$workspace_base" ]]; then
            printf '%s' "$scheme"
            return 0
        fi
    done
    for scheme in "${schemes[@]}"; do
        if [[ "$scheme" == "${workspace_base}Example" ]]; then
            printf '%s' "$scheme"
            return 0
        fi
    done
    if [[ "${#schemes[@]}" -eq 1 ]]; then
        printf '%s' "${schemes[0]}"
        return 0
    fi
    if [[ "${#schemes[@]}" -eq 0 ]]; then
        die "no shared xcode schemes found under $PODFILE_DIR; pass --scheme explicitly"
    fi
    die "multiple shared xcode schemes found under $PODFILE_DIR (${schemes[*]}); pass --scheme explicitly"
}

run_xcodebuild_build() {
    local status
    if [[ "$DRY_RUN" == "true" ]]; then
        run_cmd xcrun xcodebuild \
            "$BUILD_FLAG" "$BUILD_ARTIFACT" \
            -scheme "$SCHEME_NAME" \
            -sdk iphonesimulator \
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
        -sdk iphonesimulator \
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

repo_relative_path() {
    python3 - "$1" "$2" <<'PY'
import os
import sys

print(os.path.relpath(sys.argv[1], sys.argv[2]))
PY
}

SLUG=""
REPO_PATH=""
PODFILE_DIR_REL="$DEFAULT_PODFILE_DIR"
WORKSPACE_REL=""
PROJECT_REL=""
SCHEME_NAME=""
DESTINATION="$DEFAULT_DESTINATION"
DERIVED_DATA_ARG=""
OUTPUT_ARG=""
RELATIVE_PATH=""
REMOTE_HOST="$DEFAULT_REMOTE_HOST"
REMOTE_BASE="$DEFAULT_REMOTE_BASE"
EMITTER_DIR="$DEFAULT_EMITTER_DIR"
EMITTER_BIN=""
NO_REMOTE_COPY="false"
DRY_RUN="false"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --repo-path=*)      REPO_PATH="${1#*=}"; shift ;;
        --repo-path)        [[ $# -ge 2 ]] || die "--repo-path requires a value"; REPO_PATH="$2"; shift 2 ;;
        --podfile-dir=*)    PODFILE_DIR_REL="${1#*=}"; shift ;;
        --podfile-dir)      [[ $# -ge 2 ]] || die "--podfile-dir requires a value"; PODFILE_DIR_REL="$2"; shift 2 ;;
        --workspace=*)      WORKSPACE_REL="${1#*=}"; PROJECT_REL=""; shift ;;
        --workspace)        [[ $# -ge 2 ]] || die "--workspace requires a value"; WORKSPACE_REL="$2"; PROJECT_REL=""; shift 2 ;;
        --project=*)        PROJECT_REL="${1#*=}"; WORKSPACE_REL=""; shift ;;
        --project)          [[ $# -ge 2 ]] || die "--project requires a value"; PROJECT_REL="$2"; WORKSPACE_REL=""; shift 2 ;;
        --scheme=*)         SCHEME_NAME="${1#*=}"; shift ;;
        --scheme)           [[ $# -ge 2 ]] || die "--scheme requires a value"; SCHEME_NAME="$2"; shift 2 ;;
        --destination=*)    DESTINATION="${1#*=}"; shift ;;
        --destination)      [[ $# -ge 2 ]] || die "--destination requires a value"; DESTINATION="$2"; shift 2 ;;
        --derived-data=*)   DERIVED_DATA_ARG="${1#*=}"; shift ;;
        --derived-data)     [[ $# -ge 2 ]] || die "--derived-data requires a value"; DERIVED_DATA_ARG="$2"; shift 2 ;;
        --output=*)         OUTPUT_ARG="${1#*=}"; shift ;;
        --output)           [[ $# -ge 2 ]] || die "--output requires a value"; OUTPUT_ARG="$2"; shift 2 ;;
        --relative-path=*)  RELATIVE_PATH="${1#*=}"; shift ;;
        --relative-path)    [[ $# -ge 2 ]] || die "--relative-path requires a value"; RELATIVE_PATH="$2"; shift 2 ;;
        --remote-host=*)    REMOTE_HOST="${1#*=}"; shift ;;
        --remote-host)      [[ $# -ge 2 ]] || die "--remote-host requires a value"; REMOTE_HOST="$2"; shift 2 ;;
        --remote-base=*)    REMOTE_BASE="${1#*=}"; shift ;;
        --remote-base)      [[ $# -ge 2 ]] || die "--remote-base requires a value"; REMOTE_BASE="$2"; shift 2 ;;
        --emitter-dir=*)    EMITTER_DIR="${1#*=}"; shift ;;
        --emitter-dir)      [[ $# -ge 2 ]] || die "--emitter-dir requires a value"; EMITTER_DIR="$2"; shift 2 ;;
        --emitter-bin=*)    EMITTER_BIN="${1#*=}"; shift ;;
        --emitter-bin)      [[ $# -ge 2 ]] || die "--emitter-bin requires a value"; EMITTER_BIN="$2"; shift 2 ;;
        --no-remote-copy)   NO_REMOTE_COPY="true"; shift ;;
        --dry-run)          DRY_RUN="true"; shift ;;
        --help|-h)          usage; exit 0 ;;
        --*)                die "unknown option: $1" ;;
        *)
            if [[ -z "$SLUG" ]]; then
                SLUG="$1"
                shift
            else
                die "unexpected positional argument: $1"
            fi
            ;;
    esac
done

[[ -n "$SLUG" ]] || { usage >&2; exit 2; }
[[ -n "$REPO_PATH" ]] || die "--repo-path is required"

validate_slug "$SLUG"
[[ -d "$REPO_PATH" ]] || die "repo path not found: $REPO_PATH"

require_command python3
require_command xcrun
require_command pod
if [[ "$NO_REMOTE_COPY" == "false" ]]; then
    require_command ssh
    require_command scp
fi
if [[ "$DRY_RUN" == "false" ]]; then
    require_full_xcode
fi

PODFILE_DIR="$REPO_PATH/$PODFILE_DIR_REL"
[[ -d "$PODFILE_DIR" ]] || die "podfile dir not found: $PODFILE_DIR"
[[ -f "$PODFILE_DIR/Podfile" ]] || die "Podfile not found in $PODFILE_DIR"

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
    WORKSPACE_REL="$(discover_workspace_rel "$PODFILE_DIR")"
    BUILD_ARTIFACT="$REPO_PATH/$WORKSPACE_REL"
    BUILD_FLAG="-workspace"
fi

WORKSPACE_BASE="$(basename "$BUILD_ARTIFACT")"
WORKSPACE_BASE="${WORKSPACE_BASE%.*}"
if [[ -z "$SCHEME_NAME" ]]; then
    SCHEME_NAME="$(discover_scheme "$WORKSPACE_BASE")"
fi

[[ -d "$EMITTER_DIR" ]] || die "emitter package dir not found: $EMITTER_DIR"
if [[ -z "$EMITTER_BIN" ]]; then
    EMITTER_BIN="$EMITTER_DIR/.build/release/palace-swift-scip-emit-cli"
fi

DERIVED_DATA="${DERIVED_DATA_ARG:-$REPO_PATH/.palace-scip-derived-data-cocoapods}"
OUTPUT_PATH="${OUTPUT_ARG:-$REPO_PATH/scip/index.scip}"
META_PATH="${OUTPUT_PATH}.meta.json"
RELATIVE_PATH="${RELATIVE_PATH:-$(basename "$REPO_PATH")}"
REMOTE_DEST_DIR="$REMOTE_BASE/$RELATIVE_PATH/scip"
REMOTE_DEST_PATH="$REMOTE_DEST_DIR/index.scip"
REMOTE_META_PATH="$REMOTE_DEST_DIR/index.scip.meta.json"
PODFILE_PATH="$PODFILE_DIR/Podfile"

log "slug=$SLUG repo=$REPO_PATH podfile_dir=$PODFILE_DIR workspace=$BUILD_ARTIFACT scheme=$SCHEME_NAME"

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

log "running pod install in $PODFILE_DIR"
run_in_dir "$PODFILE_DIR" pod install

log "building kit with xcodebuild (scheme=$SCHEME_NAME destination=$DESTINATION)"
run_xcodebuild_build

log "emitting SCIP"
run_cmd "$EMITTER_BIN" \
    --derived-data "$DERIVED_DATA" \
    --project-root "$REPO_PATH" \
    --output "$OUTPUT_PATH" \
    --verbose

if [[ "$DRY_RUN" == "false" ]]; then
    [[ -s "$OUTPUT_PATH" ]] || die "generated SCIP file is missing or empty: $OUTPUT_PATH"
    HEAD_SHA="$(git -C "$REPO_PATH" rev-parse HEAD 2>/dev/null || echo unknown)"
    ARTIFACT_ORIGIN="remote_copy"
    DESTINATION_REPO_PATH="$REMOTE_BASE/$RELATIVE_PATH"
    if [[ "$NO_REMOTE_COPY" == "true" ]]; then
        ARTIFACT_ORIGIN="local"
        DESTINATION_REPO_PATH="$REPO_PATH"
    fi
    python3 - "$META_PATH" "$SLUG" "$REPO_PATH" "$DESTINATION_REPO_PATH" "$HEAD_SHA" "$EMITTER_NAME" "$EMITTER_VERSION" "$BUILD_ARTIFACT" "$PODFILE_PATH" "$SCHEME_NAME" <<'PY'
import json
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path

meta_path = Path(sys.argv[1])
repo_path = Path(sys.argv[3]).resolve()
payload = {
    "slug": sys.argv[2],
    "repo_head_sha": sys.argv[5],
    "emitter_name": sys.argv[6],
    "emitter_version": sys.argv[7],
    "artifact_origin": "local" if Path(sys.argv[4]).resolve() == repo_path else "remote_copy",
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "package_path": str(Path(sys.argv[8]).resolve().relative_to(repo_path)),
    "podfile_path": str(Path(sys.argv[9]).resolve().relative_to(repo_path)),
    "scheme": sys.argv[10],
    "generator_host": socket.gethostname(),
    "source_repo_path": str(repo_path),
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
    run_cmd ssh "$REMOTE_HOST" "mkdir -p $(printf '%q' "$REMOTE_DEST_DIR")"
    log "copying SCIP to remote host"
    run_cmd scp "$OUTPUT_PATH" "$REMOTE_HOST:$REMOTE_DEST_PATH"
    if [[ "$DRY_RUN" == "false" ]]; then
        log "copying SCIP metadata to remote host"
        run_cmd scp "$META_PATH" "$REMOTE_HOST:$REMOTE_META_PATH"
    fi
fi

if [[ "$DRY_RUN" == "false" ]]; then
    size_bytes="$(stat -f%z "$OUTPUT_PATH" 2>/dev/null || stat -c%s "$OUTPUT_PATH" 2>/dev/null || echo 0)"
else
    size_bytes="0"
fi

OUTPUT_DESTINATION="$OUTPUT_PATH"
METADATA_DESTINATION="$META_PATH"
if [[ "$NO_REMOTE_COPY" == "false" ]]; then
    OUTPUT_DESTINATION="$REMOTE_HOST:$REMOTE_DEST_PATH"
    METADATA_DESTINATION="$REMOTE_HOST:$REMOTE_META_PATH"
fi

cat <<EOF
slug=$SLUG
source=$OUTPUT_PATH
destination=$OUTPUT_DESTINATION
metadata=$METADATA_DESTINATION
podfile_dir=$PODFILE_DIR
workspace=$BUILD_ARTIFACT
scheme=$SCHEME_NAME
size_bytes=$size_bytes
dry_run=$DRY_RUN
remote_copy=$([[ "$NO_REMOTE_COPY" == "true" ]] && printf 'false' || printf 'true')
EOF
