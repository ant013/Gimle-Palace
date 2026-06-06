#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
EMIT_SCRIPT="$SCRIPT_DIR/scip_emit_cocoapods_kit.sh"
INGEST_SCRIPT="$SCRIPT_DIR/ingest_swift_kit.sh"
DEFAULT_MANIFEST="$REPO_ROOT/services/palace-mcp/scripts/uw-ios-bundle-manifest.json"
DEFAULT_REPO_BASE="${PALACE_SWIFT_KIT_REPO_BASE:-/repos-hs}"
DEFAULT_HOST_REPO_BASE="${PALACE_SWIFT_KIT_HOST_REPO_BASE:-/Users/Shared/Ios/HorizontalSystems}"

usage() {
    cat <<'EOF'
Usage: ingest_cocoapods_kit.sh <slug-or-repo> [options]

Generate SCIP for a CocoaPods/Xcode-only kit in place, then reuse
ingest_swift_kit.sh for project registration and extractor execution.

Options:
  --project-slug <slug>      Explicit Palace project slug
  --repo-path <path>         Explicit local repo checkout
  --relative-path <path>     Repo-relative path under repo-base
                             (default: repo dir basename)
  --repo-base <path>         Container-visible repo base (default: /repos-hs)
  --host-repo-base <path>    Host repo base (default: /Users/Shared/Ios/HorizontalSystems)
  --manifest <path>          Manifest used for repo-slug -> project-slug mapping
  --podfile-dir <relpath>    Podfile dir relative to repo root (default: Example)
  --workspace <relpath>      Workspace path relative to repo root
  --project <relpath>        Use -project instead of -workspace
  --scheme <name>            xcodebuild scheme
  --destination <spec>       xcodebuild destination
  --derived-data <path>      Explicit DerivedData root
  --output <path>            SCIP output path
  --bundle <name>            Optional bundle to add the project to
  --extractors <csv>         Override extractor list
  --mcp-url <url>            palace-mcp MCP URL
  --env-file <path>          Env file to update atomically
  --parent-mount <name>      Explicit register_project parent_mount
  --emitter-dir <path>       palace-swift-scip-emit package dir
  --emitter-bin <path>       Explicit emitter binary path
  --help, -h                 Show this message

Notes:
  - If <slug-or-repo> ends with -ios and the manifest contains the stripped
    slug, the stripped slug is used for project registration while the repo dir
    stays <slug-or-repo>.
  - This wrapper runs the emitter with --no-remote-copy because it expects the
    repo checkout and palace-mcp runtime to share the same host repo base.
EOF
}

die() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

manifest_contains_slug() {
    local manifest="$1"
    local slug="$2"
    [[ -f "$manifest" ]] || return 1
    python3 - "$manifest" "$slug" <<'PY'
import json
import sys
from pathlib import Path

manifest = json.loads(Path(sys.argv[1]).read_text())
slug = sys.argv[2]
raise SystemExit(0 if any(member.get("slug") == slug for member in manifest.get("members", [])) else 1)
PY
}

resolve_project_slug() {
    local input_name="$1"
    local manifest="$2"
    local candidate

    if [[ "$input_name" == *-ios ]]; then
        candidate="${input_name%-ios}"
        if manifest_contains_slug "$manifest" "$candidate"; then
            printf '%s' "$candidate"
            return 0
        fi
    fi
    printf '%s' "$input_name"
}

TARGET_NAME=""
PROJECT_SLUG=""
REPO_PATH=""
RELATIVE_PATH=""
REPO_BASE="$DEFAULT_REPO_BASE"
HOST_REPO_BASE="$DEFAULT_HOST_REPO_BASE"
MANIFEST_PATH="$DEFAULT_MANIFEST"
PODFILE_DIR_REL=""
WORKSPACE_REL=""
PROJECT_REL=""
SCHEME_NAME=""
DESTINATION=""
DERIVED_DATA_ARG=""
OUTPUT_ARG=""
BUNDLE=""
EXTRACTORS_CSV=""
MCP_URL=""
ENV_FILE=""
PARENT_MOUNT=""
EMITTER_DIR=""
EMITTER_BIN=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --project-slug=*)    PROJECT_SLUG="${1#*=}"; shift ;;
        --project-slug)      [[ $# -ge 2 ]] || die "--project-slug requires a value"; PROJECT_SLUG="$2"; shift 2 ;;
        --repo-path=*)       REPO_PATH="${1#*=}"; shift ;;
        --repo-path)         [[ $# -ge 2 ]] || die "--repo-path requires a value"; REPO_PATH="$2"; shift 2 ;;
        --relative-path=*)   RELATIVE_PATH="${1#*=}"; shift ;;
        --relative-path)     [[ $# -ge 2 ]] || die "--relative-path requires a value"; RELATIVE_PATH="$2"; shift 2 ;;
        --repo-base=*)       REPO_BASE="${1#*=}"; shift ;;
        --repo-base)         [[ $# -ge 2 ]] || die "--repo-base requires a value"; REPO_BASE="$2"; shift 2 ;;
        --host-repo-base=*)  HOST_REPO_BASE="${1#*=}"; shift ;;
        --host-repo-base)    [[ $# -ge 2 ]] || die "--host-repo-base requires a value"; HOST_REPO_BASE="$2"; shift 2 ;;
        --manifest=*)        MANIFEST_PATH="${1#*=}"; shift ;;
        --manifest)          [[ $# -ge 2 ]] || die "--manifest requires a value"; MANIFEST_PATH="$2"; shift 2 ;;
        --podfile-dir=*)     PODFILE_DIR_REL="${1#*=}"; shift ;;
        --podfile-dir)       [[ $# -ge 2 ]] || die "--podfile-dir requires a value"; PODFILE_DIR_REL="$2"; shift 2 ;;
        --workspace=*)       WORKSPACE_REL="${1#*=}"; shift ;;
        --workspace)         [[ $# -ge 2 ]] || die "--workspace requires a value"; WORKSPACE_REL="$2"; shift 2 ;;
        --project=*)         PROJECT_REL="${1#*=}"; shift ;;
        --project)           [[ $# -ge 2 ]] || die "--project requires a value"; PROJECT_REL="$2"; shift 2 ;;
        --scheme=*)          SCHEME_NAME="${1#*=}"; shift ;;
        --scheme)            [[ $# -ge 2 ]] || die "--scheme requires a value"; SCHEME_NAME="$2"; shift 2 ;;
        --destination=*)     DESTINATION="${1#*=}"; shift ;;
        --destination)       [[ $# -ge 2 ]] || die "--destination requires a value"; DESTINATION="$2"; shift 2 ;;
        --derived-data=*)    DERIVED_DATA_ARG="${1#*=}"; shift ;;
        --derived-data)      [[ $# -ge 2 ]] || die "--derived-data requires a value"; DERIVED_DATA_ARG="$2"; shift 2 ;;
        --output=*)          OUTPUT_ARG="${1#*=}"; shift ;;
        --output)            [[ $# -ge 2 ]] || die "--output requires a value"; OUTPUT_ARG="$2"; shift 2 ;;
        --bundle=*)          BUNDLE="${1#*=}"; shift ;;
        --bundle)            [[ $# -ge 2 ]] || die "--bundle requires a value"; BUNDLE="$2"; shift 2 ;;
        --extractors=*)      EXTRACTORS_CSV="${1#*=}"; shift ;;
        --extractors)        [[ $# -ge 2 ]] || die "--extractors requires a value"; EXTRACTORS_CSV="$2"; shift 2 ;;
        --mcp-url=*)         MCP_URL="${1#*=}"; shift ;;
        --mcp-url)           [[ $# -ge 2 ]] || die "--mcp-url requires a value"; MCP_URL="$2"; shift 2 ;;
        --env-file=*)        ENV_FILE="${1#*=}"; shift ;;
        --env-file)          [[ $# -ge 2 ]] || die "--env-file requires a value"; ENV_FILE="$2"; shift 2 ;;
        --parent-mount=*)    PARENT_MOUNT="${1#*=}"; shift ;;
        --parent-mount)      [[ $# -ge 2 ]] || die "--parent-mount requires a value"; PARENT_MOUNT="$2"; shift 2 ;;
        --emitter-dir=*)     EMITTER_DIR="${1#*=}"; shift ;;
        --emitter-dir)       [[ $# -ge 2 ]] || die "--emitter-dir requires a value"; EMITTER_DIR="$2"; shift 2 ;;
        --emitter-bin=*)     EMITTER_BIN="${1#*=}"; shift ;;
        --emitter-bin)       [[ $# -ge 2 ]] || die "--emitter-bin requires a value"; EMITTER_BIN="$2"; shift 2 ;;
        --help|-h)           usage; exit 0 ;;
        --*)                 die "unknown option: $1" ;;
        *)
            if [[ -z "$TARGET_NAME" ]]; then
                TARGET_NAME="$1"
                shift
            else
                die "unexpected positional argument: $1"
            fi
            ;;
    esac
done

[[ -n "$TARGET_NAME" ]] || { usage >&2; exit 2; }

if [[ -z "$PROJECT_SLUG" ]]; then
    PROJECT_SLUG="$(resolve_project_slug "$TARGET_NAME" "$MANIFEST_PATH")"
fi
if [[ -z "$REPO_PATH" ]]; then
    REPO_PATH="$HOST_REPO_BASE/$TARGET_NAME"
fi
if [[ -z "$RELATIVE_PATH" ]]; then
    RELATIVE_PATH="$(basename "$REPO_PATH")"
fi

emit_cmd=("$EMIT_SCRIPT" "$PROJECT_SLUG" --repo-path "$REPO_PATH" --relative-path "$RELATIVE_PATH" --no-remote-copy)
if [[ -n "$PODFILE_DIR_REL" ]]; then
    emit_cmd+=(--podfile-dir "$PODFILE_DIR_REL")
fi
if [[ -n "$WORKSPACE_REL" ]]; then
    emit_cmd+=(--workspace "$WORKSPACE_REL")
fi
if [[ -n "$PROJECT_REL" ]]; then
    emit_cmd+=(--project "$PROJECT_REL")
fi
if [[ -n "$SCHEME_NAME" ]]; then
    emit_cmd+=(--scheme "$SCHEME_NAME")
fi
if [[ -n "$DESTINATION" ]]; then
    emit_cmd+=(--destination "$DESTINATION")
fi
if [[ -n "$DERIVED_DATA_ARG" ]]; then
    emit_cmd+=(--derived-data "$DERIVED_DATA_ARG")
fi
if [[ -n "$OUTPUT_ARG" ]]; then
    emit_cmd+=(--output "$OUTPUT_ARG")
fi
if [[ -n "$EMITTER_DIR" ]]; then
    emit_cmd+=(--emitter-dir "$EMITTER_DIR")
fi
if [[ -n "$EMITTER_BIN" ]]; then
    emit_cmd+=(--emitter-bin "$EMITTER_BIN")
fi

ingest_cmd=("$INGEST_SCRIPT" "$PROJECT_SLUG" --repo-base "$REPO_BASE" --host-repo-base "$HOST_REPO_BASE" --relative-path "$RELATIVE_PATH" --manifest "$MANIFEST_PATH")
if [[ -n "$BUNDLE" ]]; then
    ingest_cmd+=(--bundle "$BUNDLE")
fi
if [[ -n "$EXTRACTORS_CSV" ]]; then
    ingest_cmd+=(--extractors "$EXTRACTORS_CSV")
fi
if [[ -n "$MCP_URL" ]]; then
    ingest_cmd+=(--mcp-url "$MCP_URL")
fi
if [[ -n "$ENV_FILE" ]]; then
    ingest_cmd+=(--env-file "$ENV_FILE")
fi
if [[ -n "$PARENT_MOUNT" ]]; then
    ingest_cmd+=(--parent-mount "$PARENT_MOUNT")
fi

"${emit_cmd[@]}"
"${ingest_cmd[@]}"
