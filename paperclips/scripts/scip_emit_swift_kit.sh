#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
DEFAULT_MANIFEST="$REPO_ROOT/services/palace-mcp/scripts/uw-ios-bundle-manifest.json"
DEFAULT_EMITTER_DIR="$REPO_ROOT/services/palace-mcp/scip_emit_swift"
DEFAULT_REMOTE_HOST="${IMAC_HOST:-imac-ssh.ant013.work}"
DEFAULT_REMOTE_BASE="${IMAC_HS_PATH:-/Users/Shared/Ios/HorizontalSystems}"
EMITTER_NAME="palace-swift-scip-emit-cli"
EMITTER_VERSION="2026-05-15"

usage() {
    cat <<'EOF'
Usage: scip_emit_swift_kit.sh <kit-slug> [options]

Emit a single HorizontalSystems Swift Kit SCIP index on a dev Mac, then copy it
to the iMac repo mount.

Options:
  --repo-root <path>          Parent dir containing kit repos (default: $PWD)
  --repo-path <path>          Explicit local repo path; bypass manifest lookup
  --scheme <name>             Xcode scheme (default: repo dir basename w/o .Swift)
  --manifest <path>           Manifest used for slug -> relative_path lookup
  --remote-host <host>        SSH host for the iMac
  --remote-base <path>        Remote base dir that contains kit repos
  --remote-relative-path <p>  Override remote repo-relative path
  --emitter-dir <path>        palace-swift-scip-emit package dir
  --emitter-bin <path>        Explicit emitter binary path
  --no-remote-copy            Generate local SCIP only; skip SSH/SCP copy
  --dry-run                   Print intended actions without changing state
  --help, -h                  Show this message

Notes:
  - Slug validation matches Palace project slugs.
  - When a manifest contains the slug, its relative_path is used so kit slugs
    like tron-kit resolve to repo dirs like TronKit.Swift.
  - This script currently targets SwiftPM-style kit repos with Package.swift.
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

resolve_manifest_relative_path() {
    local manifest="$1"
    local slug="$2"
    [[ -f "$manifest" ]] || return 0
    python3 - "$manifest" "$slug" <<'PY'
import json
import sys
from pathlib import Path

manifest_path = Path(sys.argv[1])
slug = sys.argv[2]
data = json.loads(manifest_path.read_text())
for member in data.get("members", []):
    if member.get("slug") == slug:
        print(member.get("relative_path", ""))
        raise SystemExit(0)
PY
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

SLUG=""
REPO_ROOT_ARG="${HS_REPO_ROOT:-$PWD}"
REPO_PATH_ARG=""
SCHEME_NAME=""
MANIFEST_PATH="$DEFAULT_MANIFEST"
REMOTE_HOST="$DEFAULT_REMOTE_HOST"
REMOTE_BASE="$DEFAULT_REMOTE_BASE"
REMOTE_RELATIVE_PATH=""
EMITTER_DIR="$DEFAULT_EMITTER_DIR"
EMITTER_BIN=""
NO_REMOTE_COPY="false"
DRY_RUN="false"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --repo-root=*)
            REPO_ROOT_ARG="${1#*=}"
            shift
            ;;
        --repo-root)
            [[ $# -ge 2 ]] || die "--repo-root requires a value"
            REPO_ROOT_ARG="$2"
            shift 2
            ;;
        --repo-path=*)
            REPO_PATH_ARG="${1#*=}"
            shift
            ;;
        --repo-path)
            [[ $# -ge 2 ]] || die "--repo-path requires a value"
            REPO_PATH_ARG="$2"
            shift 2
            ;;
        --scheme=*)
            SCHEME_NAME="${1#*=}"
            shift
            ;;
        --scheme)
            [[ $# -ge 2 ]] || die "--scheme requires a value"
            SCHEME_NAME="$2"
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
        --remote-relative-path=*)
            REMOTE_RELATIVE_PATH="${1#*=}"
            shift
            ;;
        --remote-relative-path)
            [[ $# -ge 2 ]] || die "--remote-relative-path requires a value"
            REMOTE_RELATIVE_PATH="$2"
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
        --no-remote-copy)
            NO_REMOTE_COPY="true"
            shift
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
            if [[ -z "$SLUG" ]]; then
                SLUG="$1"
                shift
            else
                die "unexpected positional argument: $1"
            fi
            ;;
    esac
done

[[ -n "$SLUG" ]] || {
    usage >&2
    exit 2
}

validate_slug "$SLUG"
ACTIVE_DEVELOPER_DIR="$(xcode-select -p 2>/dev/null || true)"
if [[ -z "${DEVELOPER_DIR:-}" && "$ACTIVE_DEVELOPER_DIR" == "/Library/Developer/CommandLineTools" ]] && \
    [[ -d "/Applications/Xcode.app/Contents/Developer" ]]; then
    export DEVELOPER_DIR="/Applications/Xcode.app/Contents/Developer"
    log "using DEVELOPER_DIR=$DEVELOPER_DIR"
fi

require_command python3
require_command xcrun
require_command swift
if [[ "$NO_REMOTE_COPY" == "false" ]]; then
    require_command ssh
    require_command scp
fi
if [[ "$DRY_RUN" == "false" ]]; then
    require_command xcodebuild
    xcodebuild -version >/dev/null 2>&1 || die "xcodebuild requires full Xcode; install Xcode or set DEVELOPER_DIR"
fi

MANIFEST_RELATIVE_PATH="$(resolve_manifest_relative_path "$MANIFEST_PATH" "$SLUG" || true)"
RELATIVE_PATH="${REMOTE_RELATIVE_PATH:-${MANIFEST_RELATIVE_PATH:-$SLUG}}"

if [[ -n "$REPO_PATH_ARG" ]]; then
    LOCAL_REPO_PATH="$REPO_PATH_ARG"
else
    LOCAL_REPO_PATH="$REPO_ROOT_ARG/$RELATIVE_PATH"
fi

[[ -d "$LOCAL_REPO_PATH" ]] || die "repo path not found: $LOCAL_REPO_PATH"
[[ -f "$LOCAL_REPO_PATH/Package.swift" ]] || \
    die "Package.swift not found in $LOCAL_REPO_PATH (expected SwiftPM kit repo)"
[[ -d "$EMITTER_DIR" ]] || die "emitter package dir not found: $EMITTER_DIR"

if [[ -z "$SCHEME_NAME" ]]; then
    SCHEME_NAME="$(basename "$LOCAL_REPO_PATH")"
    # Case-insensitive strip of .Swift / .swift suffix.
    shopt -s nocasematch
    [[ "$SCHEME_NAME" =~ \.swift$ ]] && SCHEME_NAME="${SCHEME_NAME%.*}"
    shopt -u nocasematch
    # If the guess does not match an actual Xcode scheme, fall back to
    # the first scheme whose name (case-insensitive) starts with the
    # guess — covers kits like HsCryptoKit.Swift whose real scheme is
    # `HsCryptoKit.Swift` (suffix retained) and case-mismatched kits
    # like HDWalletKit.Swift whose real scheme is `HdWalletKit`. (GIM-984)
    if command -v xcodebuild >/dev/null 2>&1 && [[ -d "$LOCAL_REPO_PATH" ]]; then
        AVAILABLE_SCHEMES="$(cd "$LOCAL_REPO_PATH" && xcodebuild -list -json 2>/dev/null \
            | python3 -c 'import sys,json
try:
    d=json.load(sys.stdin)
    print("\n".join((d.get("workspace") or d.get("project") or {}).get("schemes") or []))
except Exception:
    pass' 2>/dev/null)"
        if [[ -n "$AVAILABLE_SCHEMES" ]] && ! grep -qFx "$SCHEME_NAME" <<<"$AVAILABLE_SCHEMES"; then
            MATCH="$(grep -i -E "^${SCHEME_NAME}(\\.swift)?\$" <<<"$AVAILABLE_SCHEMES" | head -1)"
            if [[ -n "$MATCH" ]]; then
                log "scheme '$SCHEME_NAME' not found in xcodebuild -list; using '$MATCH'"
                SCHEME_NAME="$MATCH"
            fi
        fi
    fi
fi

if [[ -z "$EMITTER_BIN" ]]; then
    EMITTER_BIN="$EMITTER_DIR/.build/release/palace-swift-scip-emit-cli"
fi

SCRATCH_PATH="$LOCAL_REPO_PATH/.palace-scip-build"
DERIVED_DATA="$LOCAL_REPO_PATH/.palace-scip-derived-data"
OUTPUT_PATH="$LOCAL_REPO_PATH/scip/index.scip"
META_PATH="$LOCAL_REPO_PATH/scip/index.scip.meta.json"
REMOTE_DEST_DIR="$REMOTE_BASE/$RELATIVE_PATH/scip"
REMOTE_DEST_PATH="$REMOTE_DEST_DIR/index.scip"
REMOTE_META_PATH="$REMOTE_DEST_DIR/index.scip.meta.json"

log "slug=$SLUG scheme=$SCHEME_NAME local_repo=$LOCAL_REPO_PATH remote_path=$REMOTE_DEST_PATH"

if [[ ! -x "$EMITTER_BIN" ]]; then
    log "building palace-swift-scip-emit"
    run_cmd xcrun swift build -c release --package-path "$EMITTER_DIR"
fi
[[ "$DRY_RUN" == "true" || -x "$EMITTER_BIN" ]] || die "emitter binary not found after build: $EMITTER_BIN"

log "preparing local build directories"
if [[ "$DRY_RUN" == "false" ]]; then
    rm -rf "$SCRATCH_PATH" "$DERIVED_DATA"
    mkdir -p "$DERIVED_DATA" "$(dirname "$OUTPUT_PATH")"
else
    printf 'DRY-RUN: rm -rf %q %q\n' "$SCRATCH_PATH" "$DERIVED_DATA"
    printf 'DRY-RUN: mkdir -p %q %q\n' "$DERIVED_DATA" "$(dirname "$OUTPUT_PATH")"
fi

log "building Swift package with xcodebuild"
(
    cd "$LOCAL_REPO_PATH"
    run_cmd xcodebuild \
        -scheme "$SCHEME_NAME" \
        -configuration Debug \
        -sdk iphonesimulator \
        -destination "generic/platform=iOS Simulator" \
        -derivedDataPath "$DERIVED_DATA" \
        SYMROOT="$SCRATCH_PATH" \
        CODE_SIGNING_ALLOWED=NO \
        CODE_SIGNING_REQUIRED=NO \
        build
)

log "emitting SCIP"
run_cmd "$EMITTER_BIN" \
    --derived-data "$DERIVED_DATA" \
    --project-root "$LOCAL_REPO_PATH" \
    --output "$OUTPUT_PATH" \
    --verbose

if [[ "$DRY_RUN" == "false" ]]; then
    [[ -s "$OUTPUT_PATH" ]] || die "generated SCIP file is missing or empty: $OUTPUT_PATH"
    HEAD_SHA="$(git -C "$LOCAL_REPO_PATH" rev-parse HEAD)"
    ARTIFACT_ORIGIN="remote_copy"
    DESTINATION_REPO_PATH="$REMOTE_BASE/$RELATIVE_PATH"
    if [[ "$NO_REMOTE_COPY" == "true" ]]; then
        ARTIFACT_ORIGIN="local"
        DESTINATION_REPO_PATH="$LOCAL_REPO_PATH"
    fi
    python3 - "$META_PATH" "$SLUG" "$LOCAL_REPO_PATH" "$DESTINATION_REPO_PATH" "$HEAD_SHA" "$EMITTER_NAME" "$EMITTER_VERSION" "$ARTIFACT_ORIGIN" <<'PY'
import json
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path

meta_path = Path(sys.argv[1])
slug = sys.argv[2]
source_repo = Path(sys.argv[3]).resolve()
destination_repo = Path(sys.argv[4]).resolve()
head_sha = sys.argv[5]
emitter_name = sys.argv[6]
emitter_version = sys.argv[7]
artifact_origin = sys.argv[8]
payload = {
    "slug": slug,
    "repo_head_sha": head_sha,
    "emitter_name": emitter_name,
    "emitter_version": emitter_version,
    "artifact_origin": artifact_origin,
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "package_path": "Package.swift",
    "generator_host": socket.gethostname(),
    "source_repo_path": str(source_repo),
    "destination_repo_path": str(destination_repo),
}
meta_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
PY
fi

if [[ "$NO_REMOTE_COPY" == "false" ]]; then
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
    size_bytes="$(wc -c < "$OUTPUT_PATH" | tr -d ' ')"
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
size_bytes=$size_bytes
dry_run=$DRY_RUN
remote_copy=$([[ "$NO_REMOTE_COPY" == "true" ]] && printf 'false' || printf 'true')
EOF
