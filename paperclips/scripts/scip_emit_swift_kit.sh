#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
DEFAULT_MANIFEST="$REPO_ROOT/services/palace-mcp/scripts/uw-ios-bundle-manifest.json"
DEFAULT_EMITTER_DIR="$REPO_ROOT/services/palace-mcp/scip_emit_swift"
DEFAULT_REMOTE_HOST="${IMAC_HOST:-imac-ssh.ant013.work}"
DEFAULT_REMOTE_BASE="${IMAC_HS_PATH:-/Users/Shared/Ios/HorizontalSystems}"

usage() {
    cat <<'EOF'
Usage: scip_emit_swift_kit.sh <kit-slug> [options]

Emit a single HorizontalSystems Swift Kit SCIP index on a dev Mac, then copy it
to the iMac repo mount.

Options:
  --repo-root <path>          Parent dir containing kit repos (default: $PWD)
  --repo-path <path>          Explicit local repo path; bypass manifest lookup
  --manifest <path>           Manifest used for slug -> relative_path lookup
  --scheme <name>             xcodebuild scheme (default: auto-detect from Package.swift name)
  --destination <spec>        xcodebuild -destination (default: 'generic/platform=iOS Simulator')
  --remote-host <host>        SSH host for the iMac
  --remote-base <path>        Remote base dir that contains kit repos
  --remote-relative-path <p>  Override remote repo-relative path
  --emitter-dir <path>        palace-swift-scip-emit package dir
  --emitter-bin <path>        Explicit emitter binary path
  --dry-run                   Print intended actions without changing state
  --help, -h                  Show this message

Notes:
  - Slug validation matches Palace project slugs.
  - When a manifest contains the slug, its relative_path is used so kit slugs
    like tron-kit resolve to repo dirs like TronKit.Swift.
  - Targets SwiftPM-style kit repos with Package.swift; built via xcodebuild
    against iOS Simulator (the canonical target for HS Kits). This avoids
    the macOS-platform compatibility cascade hit by `swift build` when Kit
    Package.swift declares only `.iOS(...)` in `platforms`.
  - xcodebuild writes index store into <derived-data>/Index.noindex/DataStore
    directly; no intermediate copy step needed.
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
MANIFEST_PATH="$DEFAULT_MANIFEST"
SCHEME=""
DESTINATION="${SCIP_EMIT_DESTINATION:-generic/platform=iOS Simulator}"
REMOTE_HOST="$DEFAULT_REMOTE_HOST"
REMOTE_BASE="$DEFAULT_REMOTE_BASE"
REMOTE_RELATIVE_PATH=""
EMITTER_DIR="$DEFAULT_EMITTER_DIR"
EMITTER_BIN=""
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
        --manifest=*)
            MANIFEST_PATH="${1#*=}"
            shift
            ;;
        --manifest)
            [[ $# -ge 2 ]] || die "--manifest requires a value"
            MANIFEST_PATH="$2"
            shift 2
            ;;
        --scheme=*)
            SCHEME="${1#*=}"
            shift
            ;;
        --scheme)
            [[ $# -ge 2 ]] || die "--scheme requires a value"
            SCHEME="$2"
            shift 2
            ;;
        --destination=*)
            DESTINATION="${1#*=}"
            shift
            ;;
        --destination)
            [[ $# -ge 2 ]] || die "--destination requires a value"
            DESTINATION="$2"
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
require_command python3
require_command xcrun
require_command swift
require_command xcodebuild
require_command ssh
require_command scp

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

if [[ -z "$EMITTER_BIN" ]]; then
    EMITTER_BIN="$EMITTER_DIR/.build/release/palace-swift-scip-emit-cli"
fi

DERIVED_DATA="$LOCAL_REPO_PATH/.palace-scip-derived-data"
OUTPUT_PATH="$LOCAL_REPO_PATH/scip/index.scip"
REMOTE_DEST_DIR="$REMOTE_BASE/$RELATIVE_PATH/scip"
REMOTE_DEST_PATH="$REMOTE_DEST_DIR/index.scip"

# Auto-detect scheme from Package.swift `name: "..."` if not provided.
if [[ -z "$SCHEME" ]]; then
    SCHEME="$(grep -oE 'name:[[:space:]]*"[^"]+"' "$LOCAL_REPO_PATH/Package.swift" | head -1 | sed -E 's/.*"([^"]+)"/\1/')"
fi
[[ -n "$SCHEME" ]] || die "could not derive xcodebuild scheme; pass --scheme"

log "slug=$SLUG scheme=$SCHEME destination='$DESTINATION' local_repo=$LOCAL_REPO_PATH remote_path=$REMOTE_DEST_PATH"

if [[ ! -x "$EMITTER_BIN" ]]; then
    log "building palace-swift-scip-emit"
    run_cmd xcrun swift build -c release --package-path "$EMITTER_DIR"
fi
[[ "$DRY_RUN" == "true" || -x "$EMITTER_BIN" ]] || die "emitter binary not found after build: $EMITTER_BIN"

log "preparing local build directories"
if [[ "$DRY_RUN" == "false" ]]; then
    rm -rf "$DERIVED_DATA"
    mkdir -p "$DERIVED_DATA/Index.noindex" "$(dirname "$OUTPUT_PATH")"
else
    printf 'DRY-RUN: rm -rf %q\n' "$DERIVED_DATA"
    printf 'DRY-RUN: mkdir -p %q %q\n' "$DERIVED_DATA/Index.noindex" "$(dirname "$OUTPUT_PATH")"
fi

log "building Swift package via xcodebuild ($DESTINATION)"
if [[ "$DRY_RUN" == "true" ]]; then
    printf 'DRY-RUN: (cd %q && xcodebuild build -scheme %q -destination %q -derivedDataPath %q)\n' \
        "$LOCAL_REPO_PATH" "$SCHEME" "$DESTINATION" "$DERIVED_DATA"
else
    (cd "$LOCAL_REPO_PATH" && xcodebuild build \
        -scheme "$SCHEME" \
        -destination "$DESTINATION" \
        -derivedDataPath "$DERIVED_DATA" \
        -quiet)
fi

# xcodebuild writes index store into $DERIVED_DATA/Index.noindex/DataStore directly.
if [[ "$DRY_RUN" == "false" && ! -d "$DERIVED_DATA/Index.noindex/DataStore" ]]; then
    die "expected index data store not found at $DERIVED_DATA/Index.noindex/DataStore (xcodebuild did not emit index)"
fi

log "emitting SCIP"
run_cmd "$EMITTER_BIN" \
    --derived-data "$DERIVED_DATA" \
    --project-root "$LOCAL_REPO_PATH" \
    --output "$OUTPUT_PATH" \
    --verbose

if [[ "$DRY_RUN" == "false" ]]; then
    [[ -s "$OUTPUT_PATH" ]] || die "generated SCIP file is missing or empty: $OUTPUT_PATH"
fi

log "creating remote destination"
run_cmd ssh "$REMOTE_HOST" "mkdir -p $(printf '%q' "$REMOTE_DEST_DIR")"

log "copying SCIP to remote host"
run_cmd scp "$OUTPUT_PATH" "$REMOTE_HOST:$REMOTE_DEST_PATH"

if [[ "$DRY_RUN" == "false" ]]; then
    size_bytes="$(wc -c < "$OUTPUT_PATH" | tr -d ' ')"
else
    size_bytes="0"
fi

cat <<EOF
slug=$SLUG
source=$OUTPUT_PATH
destination=$REMOTE_HOST:$REMOTE_DEST_PATH
size_bytes=$size_bytes
dry_run=$DRY_RUN
EOF
