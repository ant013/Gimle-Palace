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
  --scheme <name>             Xcode scheme
                             (default: matching shared scheme, else repo dir basename w/o .Swift)
  --manifest <path>           Manifest used for slug -> relative_path lookup
  --remote-host <host>        SSH host for the iMac
  --remote-base <path>        Remote base dir that contains kit repos
  --remote-relative-path <p>  Override remote repo-relative path
  --emitter-dir <path>        palace-swift-scip-emit package dir
  --emitter-bin <path>        Explicit emitter binary path
  --scheme-only-check         Print resolved scheme/toolchain and exit 0
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

repo_relative_path() {
    python3 - "$1" "$2" <<'PY'
import os
import sys

print(os.path.relpath(sys.argv[1], sys.argv[2]))
PY
}

resolve_swift_toolchain() {
    python3 - "$1" <<'PY'
import os
import re
import sys
from pathlib import Path

repo_path = Path(sys.argv[1]).resolve()
version_file = (repo_path / ".swift-version")
if not version_file.exists():
    raise SystemExit(0)

lines = [line.strip() for line in version_file.resolve().read_text(encoding="utf-8").splitlines()]
raw = next((line for line in lines if line), "")
if not raw:
    raise SystemExit(0)

full_name_re = re.compile(r"^(swift-(\d+)\.(\d+)\.(\d+)-RELEASE)(?:\.xctoolchain)?$")
full_version_re = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
partial_name_re = re.compile(r"^swift-(\d+)\.(\d+)(?:-RELEASE)?$")
partial_version_re = re.compile(r"^(\d+)\.(\d+)$")

roots = []
developer_dir = os.environ.get("DEVELOPER_DIR")
if developer_dir:
    roots.append(Path(developer_dir) / "Toolchains")
roots.extend(
    [
        Path("/Library/Developer/Toolchains"),
        Path.home() / "Library/Developer/Toolchains",
    ]
)

installed = {}
for root in roots:
    if not root.exists():
        continue
    for child in root.iterdir():
        if child.suffix != ".xctoolchain":
            continue
        match = full_name_re.match(child.name)
        if not match:
            continue
        installed[match.group(1)] = tuple(int(part) for part in match.groups()[1:4])

def fail(name: str) -> None:
    print(f"ERROR: toolchain not installed: {name}", file=sys.stderr)
    raise SystemExit(1)

match = full_name_re.match(raw)
if match:
    resolved = match.group(1)
    if resolved not in installed:
        fail(resolved)
    print(resolved)
    raise SystemExit(0)

match = full_version_re.match(raw)
if match:
    resolved = f"swift-{raw}-RELEASE"
    if resolved not in installed:
        fail(resolved)
    print(resolved)
    raise SystemExit(0)

match = partial_name_re.match(raw) or partial_version_re.match(raw)
if match:
    major = int(match.group(1))
    minor = int(match.group(2))
    matches = [
        (version, name)
        for name, version in installed.items()
        if version[:2] == (major, minor)
    ]
    if not matches:
        fail(f"swift-{major}.{minor}.*-RELEASE")
    matches.sort()
    print(matches[-1][1])
    raise SystemExit(0)

print(f"ERROR: invalid .swift-version value: {raw}", file=sys.stderr)
raise SystemExit(1)
PY
}

discover_workspace_rel() {
    local repo_path="$1"
    local repo_workspace=""
    local package_workspace=""
    local repo_workspace_count=0
    local package_workspace_count=0
    local workspace

    while IFS= read -r workspace; do
        if [[ "$workspace" == */.swiftpm/xcode/package.xcworkspace ]]; then
            package_workspace_count=$((package_workspace_count + 1))
            if [[ "$package_workspace_count" -eq 1 ]]; then
                package_workspace="$workspace"
            fi
            continue
        fi
        repo_workspace_count=$((repo_workspace_count + 1))
        if [[ "$repo_workspace_count" -eq 1 ]]; then
            repo_workspace="$workspace"
        fi
    done < <(
        find "$repo_path" \
            -path '*/.build/*' -prune -o \
            -type d -name '*.xcworkspace' ! -path '*/project.xcworkspace' -print | sort
    )

    if [[ "$repo_workspace_count" -eq 1 ]]; then
        repo_relative_path "$repo_workspace" "$repo_path"
        return 0
    fi
    if [[ "$package_workspace_count" -eq 1 ]]; then
        repo_relative_path "$package_workspace" "$repo_path"
        return 0
    fi
    return 1
}

discover_project_rel() {
    local repo_path="$1"
    local project=""
    local first_project=""
    local project_count=0

    while IFS= read -r project; do
        project_count=$((project_count + 1))
        if [[ "$project_count" -eq 1 ]]; then
            first_project="$project"
        fi
    done < <(
        find "$repo_path" \
            -path '*/.build/*' -prune -o \
            -type d -name '*.xcodeproj' -print | sort
    )

    if [[ "$project_count" -eq 1 ]]; then
        repo_relative_path "$first_project" "$repo_path"
        return 0
    fi
    return 1
}

discover_scheme() {
    local repo_path="$1"
    shift
    local -a preferred_names=("$@")
    local preferred_name
    local scheme
    local first_scheme=""
    local scheme_count=0

    while IFS= read -r scheme; do
        scheme_count=$((scheme_count + 1))
        if [[ "$scheme_count" -eq 1 ]]; then
            first_scheme="$scheme"
        fi
        for preferred_name in "${preferred_names[@]}"; do
            if [[ -n "$preferred_name" && "$scheme" == "$preferred_name" ]]; then
                printf '%s' "$scheme"
                return 0
            fi
        done
    done < <(
        find "$repo_path" \
            -path '*/.build/*' -prune -o \
            -type f -path '*/xcshareddata/xcschemes/*.xcscheme' \
            -exec basename {} .xcscheme \; | sort -u
    )

    if [[ "$scheme_count" -eq 1 ]]; then
        printf '%s' "$first_scheme"
        return 0
    fi
    return 1
}

select_xcodebuild_scheme() {
    local repo_path="$1"
    local build_target_flag="$2"
    local build_target_path="$3"
    local preferred_scheme="$4"
    local scheme
    local first_scheme=""

    command -v xcodebuild >/dev/null 2>&1 || return 1
    while IFS= read -r scheme; do
        [[ -n "$scheme" ]] || continue
        if [[ -z "$first_scheme" ]]; then
            first_scheme="$scheme"
        fi
        if [[ -n "$preferred_scheme" && "$scheme" == "$preferred_scheme" ]]; then
            printf '%s' "$scheme"
            return 0
        fi
    done < <(
        (
            cd "$repo_path"
            if [[ -n "$build_target_flag" ]]; then
                xcodebuild -list -json "$build_target_flag" "$build_target_path"
            else
                xcodebuild -list -json
            fi
        ) 2>/dev/null | jq -r '(.workspace.schemes // .project.schemes // [])[]?' 2>/dev/null || true
    )

    [[ -n "$first_scheme" ]] || return 1
    printf '%s' "$first_scheme"
}

SLUG=""
REPO_ROOT_ARG="${HS_REPO_ROOT:-$PWD}"
REPO_PATH_ARG=""
SCHEME_NAME=""
SCHEME_ONLY_CHECK="false"
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
        --scheme-only-check)
            SCHEME_ONLY_CHECK="true"
            shift
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
require_command jq
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
LOCAL_REPO_PATH="$(cd "$LOCAL_REPO_PATH" && pwd -P)"
[[ -f "$LOCAL_REPO_PATH/Package.swift" ]] || \
    die "Package.swift not found in $LOCAL_REPO_PATH (expected SwiftPM kit repo)"
[[ -d "$EMITTER_DIR" ]] || die "emitter package dir not found: $EMITTER_DIR"

WORKSPACE_REL="$(discover_workspace_rel "$LOCAL_REPO_PATH" || true)"
PROJECT_REL=""
BUILD_TARGET_DESC="package-root"
BUILD_TARGET_FLAG=""
BUILD_TARGET_PATH=""
PREFERRED_REPO_SCHEME_NAME="$(basename "$LOCAL_REPO_PATH")"
PREFERRED_SCHEME_BASENAME="$PREFERRED_REPO_SCHEME_NAME"

if [[ -n "$WORKSPACE_REL" ]]; then
    BUILD_TARGET_FLAG="-workspace"
    BUILD_TARGET_PATH="$LOCAL_REPO_PATH/$WORKSPACE_REL"
    BUILD_TARGET_DESC="workspace=$WORKSPACE_REL"
    PREFERRED_SCHEME_BASENAME="$(basename "$WORKSPACE_REL")"
else
    PROJECT_REL="$(discover_project_rel "$LOCAL_REPO_PATH" || true)"
    if [[ -n "$PROJECT_REL" ]]; then
        BUILD_TARGET_FLAG="-project"
        BUILD_TARGET_PATH="$LOCAL_REPO_PATH/$PROJECT_REL"
        BUILD_TARGET_DESC="project=$PROJECT_REL"
        PREFERRED_SCHEME_BASENAME="$(basename "$PROJECT_REL")"
    fi
fi
PREFERRED_SCHEME_BASENAME="${PREFERRED_SCHEME_BASENAME%.xcworkspace}"
PREFERRED_SCHEME_BASENAME="${PREFERRED_SCHEME_BASENAME%.xcodeproj}"
PREFERRED_SCHEME_BASENAME="${PREFERRED_SCHEME_BASENAME%.Swift}"

if [[ -z "$SCHEME_NAME" ]]; then
    SCHEME_NAME="$(discover_scheme \
        "$LOCAL_REPO_PATH" \
        "$PREFERRED_SCHEME_BASENAME" \
        "$PREFERRED_REPO_SCHEME_NAME" \
        "${PREFERRED_REPO_SCHEME_NAME%.Swift}" || true)"
    if [[ -z "$SCHEME_NAME" ]]; then
        SCHEME_NAME="$(basename "$LOCAL_REPO_PATH")"
        SCHEME_NAME="${SCHEME_NAME%.Swift}"
    fi
    if RESOLVED_SCHEME="$(select_xcodebuild_scheme \
        "$LOCAL_REPO_PATH" \
        "$BUILD_TARGET_FLAG" \
        "$BUILD_TARGET_PATH" \
        "$SCHEME_NAME")"; then
        SCHEME_NAME="$RESOLVED_SCHEME"
    fi
fi

if [[ -z "$EMITTER_BIN" ]]; then
    EMITTER_BIN="$EMITTER_DIR/.build/release/palace-swift-scip-emit-cli"
fi

RESOLVED_TOOLCHAIN="$(resolve_swift_toolchain "$LOCAL_REPO_PATH")"
TOOLCHAIN_DESC="${RESOLVED_TOOLCHAIN:-default}"

if [[ "$SCHEME_ONLY_CHECK" == "true" ]]; then
    cat <<EOF
slug=$SLUG
scheme=$SCHEME_NAME
build_target=$BUILD_TARGET_DESC
toolchain=$TOOLCHAIN_DESC
EOF
    exit 0
fi

SCRATCH_PATH="$LOCAL_REPO_PATH/.palace-scip-build"
DERIVED_DATA="$LOCAL_REPO_PATH/.palace-scip-derived-data"
OUTPUT_PATH="$LOCAL_REPO_PATH/scip/index.scip"
META_PATH="$LOCAL_REPO_PATH/scip/index.scip.meta.json"
REMOTE_DEST_DIR="$REMOTE_BASE/$RELATIVE_PATH/scip"
REMOTE_DEST_PATH="$REMOTE_DEST_DIR/index.scip"
REMOTE_META_PATH="$REMOTE_DEST_DIR/index.scip.meta.json"

log "slug=$SLUG scheme=$SCHEME_NAME toolchain=$TOOLCHAIN_DESC build_target=$BUILD_TARGET_DESC local_repo=$LOCAL_REPO_PATH remote_path=$REMOTE_DEST_PATH"

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
    if [[ -n "$BUILD_TARGET_FLAG" ]]; then
        if [[ -n "$RESOLVED_TOOLCHAIN" ]]; then
            run_cmd xcodebuild \
                "$BUILD_TARGET_FLAG" "$BUILD_TARGET_PATH" \
                -scheme "$SCHEME_NAME" \
                -toolchain "$RESOLVED_TOOLCHAIN" \
                -configuration Debug \
                -sdk iphonesimulator \
                -destination "generic/platform=iOS Simulator" \
                -derivedDataPath "$DERIVED_DATA" \
                SYMROOT="$SCRATCH_PATH" \
                CODE_SIGNING_ALLOWED=NO \
                CODE_SIGNING_REQUIRED=NO \
                build
        else
            run_cmd xcodebuild \
                "$BUILD_TARGET_FLAG" "$BUILD_TARGET_PATH" \
                -scheme "$SCHEME_NAME" \
                -configuration Debug \
                -sdk iphonesimulator \
                -destination "generic/platform=iOS Simulator" \
                -derivedDataPath "$DERIVED_DATA" \
                SYMROOT="$SCRATCH_PATH" \
                CODE_SIGNING_ALLOWED=NO \
                CODE_SIGNING_REQUIRED=NO \
                build
        fi
    else
        if [[ -n "$RESOLVED_TOOLCHAIN" ]]; then
            run_cmd xcodebuild \
                -scheme "$SCHEME_NAME" \
                -toolchain "$RESOLVED_TOOLCHAIN" \
                -configuration Debug \
                -sdk iphonesimulator \
                -destination "generic/platform=iOS Simulator" \
                -derivedDataPath "$DERIVED_DATA" \
                SYMROOT="$SCRATCH_PATH" \
                CODE_SIGNING_ALLOWED=NO \
                CODE_SIGNING_REQUIRED=NO \
                build
        else
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
        fi
    fi
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
