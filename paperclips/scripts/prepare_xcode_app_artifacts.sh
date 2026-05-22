#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Hardcoded to match extractor.py:355 — do NOT change without updating the extractor
PERIPHERY_REPORT_NAME="periphery-3.7.4-swiftpm.json"
PERIPHERY_DIR="periphery"
SWIFT_INTERFACE_DIR=".palace/public-api/swift"

DEFAULT_DESTINATION="generic/platform=iOS Simulator"
DEFAULT_DERIVED_DATA_SUBDIR=".palace-prepare-derived-data"

usage() {
    cat <<'EOF'
Usage: prepare_xcode_app_artifacts.sh --repo-path <path> --scheme <name> [options]

Prepare artefacts required by the palace-mcp extractor cascade for an Xcode app.
Runs a Periphery dead-symbol scan and emits .swiftinterface snapshots via
xcodebuild -derivedDataPath. Optionally copies .palace/profiles/ if present.

Required:
  --repo-path <path>        Host path to the Xcode app repo
                            (must contain .xcworkspace or .xcodeproj, NOT Package.swift)
  --scheme <name>           xcodebuild scheme (required for swiftinterface emission)

Options:
  --workspace <relpath>     Workspace path relative to --repo-path (auto-detected if omitted)
  --project <relpath>       Use .xcodeproj instead of .xcworkspace (mutually exclusive)
  --slug <name>             Optional palace project slug (for log labelling only)
  --destination <spec>      xcodebuild destination
                            (default: 'generic/platform=iOS Simulator')
  --derived-data <path>     Explicit DerivedData root
                            (default: <repo>/.palace-prepare-derived-data)
  --dry-run                 Print actions without mutating state
  --help, -h                Show this message

Output artefacts:
  periphery/contract.json                      Periphery run metadata
  periphery/periphery-3.7.4-swiftpm.json       Periphery dead-symbol results
  .palace/public-api/swift/*.swiftinterface    Swift module interface snapshots

Notes:
  - periphery must be on PATH (brew install periphery or direct binary).
  - xcodebuild requires full Xcode (Command Line Tools alone are insufficient).
  - Use prepare_swift_kit_artifacts.sh for SwiftPM kits (Package.swift).
  - Script is idempotent: re-running overwrites existing artefacts.
  - Profiles copy (.palace/profiles/) is optional and skipped if absent.
EOF
}

log() {
    printf '[%s] %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$*"
}

die() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

warn() {
    printf 'WARN: %s\n' "$*" >&2
}

require_command() {
    command -v "$1" >/dev/null 2>&1 || die "missing required command: $1"
}

require_full_xcode() {
    local dev_dir
    dev_dir="$(xcode-select -p 2>/dev/null || true)"
    if [[ -z "$dev_dir" || "$dev_dir" == *"CommandLineTools"* ]]; then
        die "xcodebuild requires full Xcode; current developer dir: ${dev_dir:-<none>}. Install Xcode and run: sudo xcode-select -s /Applications/Xcode.app/Contents/Developer"
    fi
    xcrun -f xcodebuild >/dev/null 2>&1 || \
        die "xcrun cannot locate xcodebuild even though DEVELOPER_DIR=$dev_dir"
}

run_or_dry() {
    if [[ "$DRY_RUN" == "true" ]]; then
        printf 'DRY-RUN:'
        printf ' %q' "$@"
        printf '\n'
    else
        "$@"
    fi
}

REPO_PATH=""
WORKSPACE_REL=""
PROJECT_REL=""
SCHEME_NAME=""
SLUG=""
DESTINATION="$DEFAULT_DESTINATION"
DERIVED_DATA_ARG=""
DRY_RUN="false"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --repo-path=*)    REPO_PATH="${1#*=}"; shift ;;
        --repo-path)      [[ $# -ge 2 ]] || die "--repo-path requires a value"; REPO_PATH="$2"; shift 2 ;;
        --workspace=*)    WORKSPACE_REL="${1#*=}"; PROJECT_REL=""; shift ;;
        --workspace)      [[ $# -ge 2 ]] || die "--workspace requires a value"; WORKSPACE_REL="$2"; PROJECT_REL=""; shift 2 ;;
        --project=*)      PROJECT_REL="${1#*=}"; WORKSPACE_REL=""; shift ;;
        --project)        [[ $# -ge 2 ]] || die "--project requires a value"; PROJECT_REL="$2"; WORKSPACE_REL=""; shift 2 ;;
        --scheme=*)       SCHEME_NAME="${1#*=}"; shift ;;
        --scheme)         [[ $# -ge 2 ]] || die "--scheme requires a value"; SCHEME_NAME="$2"; shift 2 ;;
        --slug=*)         SLUG="${1#*=}"; shift ;;
        --slug)           [[ $# -ge 2 ]] || die "--slug requires a value"; SLUG="$2"; shift 2 ;;
        --destination=*)  DESTINATION="${1#*=}"; shift ;;
        --destination)    [[ $# -ge 2 ]] || die "--destination requires a value"; DESTINATION="$2"; shift 2 ;;
        --derived-data=*) DERIVED_DATA_ARG="${1#*=}"; shift ;;
        --derived-data)   [[ $# -ge 2 ]] || die "--derived-data requires a value"; DERIVED_DATA_ARG="$2"; shift 2 ;;
        --dry-run)        DRY_RUN="true"; shift ;;
        --help|-h)        usage; exit 0 ;;
        --*)              die "unknown option: $1" ;;
        *)                die "unexpected positional argument: $1" ;;
    esac
done

[[ -n "$REPO_PATH" ]]   || { usage >&2; die "--repo-path is required"; }
[[ -n "$SCHEME_NAME" ]] || { usage >&2; die "--scheme is required"; }

[[ -d "$REPO_PATH" ]] || die "repo path not found: $REPO_PATH"
[[ ! -f "$REPO_PATH/Package.swift" ]] || \
    die "Package.swift found in $REPO_PATH — use prepare_swift_kit_artifacts.sh for SwiftPM kits"

# Auto-detect workspace / project
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
    if [[ ${#ws_candidates[@]} -gt 0 ]]; then
        BUILD_ARTIFACT="${ws_candidates[0]}"
        BUILD_FLAG="-workspace"
        log "auto-detected workspace: $(basename "$BUILD_ARTIFACT")"
    else
        shopt -s nullglob
        proj_candidates=("$REPO_PATH"/*.xcodeproj)
        shopt -u nullglob
        [[ ${#proj_candidates[@]} -gt 0 ]] || \
            die "no *.xcworkspace or *.xcodeproj found in $REPO_PATH; use --workspace or --project"
        BUILD_ARTIFACT="${proj_candidates[0]}"
        BUILD_FLAG="-project"
        log "auto-detected project: $(basename "$BUILD_ARTIFACT")"
    fi
fi

DERIVED_DATA="${DERIVED_DATA_ARG:-$REPO_PATH/$DEFAULT_DERIVED_DATA_SUBDIR}"

label="${SLUG:-$(basename "$REPO_PATH")}"
log "repo=$REPO_PATH build_artifact=$(basename "$BUILD_ARTIFACT") scheme=$SCHEME_NAME label=$label"

# ── Step 1: Periphery scan ────────────────────────────────────────────────────

if [[ "$DRY_RUN" == "false" ]]; then
    require_command jq
fi

periphery_bin="$(command -v periphery 2>/dev/null || true)"
if [[ "$DRY_RUN" == "false" ]]; then
    [[ -n "$periphery_bin" ]] || die "periphery not found on PATH; install: brew install periphery"
fi

periphery_version=""
if [[ -n "$periphery_bin" ]]; then
    periphery_version="$("$periphery_bin" version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1 || true)"
    [[ -n "$periphery_version" ]] || \
        periphery_version="$("$periphery_bin" --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1 || true)"
fi
if [[ "$DRY_RUN" == "false" && -z "$periphery_version" ]]; then
    die "could not determine periphery version"
fi
periphery_version="${periphery_version:-<unknown>}"

schema_version="periphery-json-${periphery_version}"
periphery_dir="$REPO_PATH/$PERIPHERY_DIR"
report_path="$periphery_dir/$PERIPHERY_REPORT_NAME"
contract_path="$periphery_dir/contract.json"

log "periphery version: $periphery_version (schema_version=$schema_version)"
log "report path: $report_path"

if [[ "$DRY_RUN" == "true" ]]; then
    printf 'DRY-RUN: mkdir -p %q\n' "$periphery_dir"
    printf 'DRY-RUN: periphery scan %s %q --scheme %q --format json --relative-results --disable-update-check --write-results %q\n' \
        "$BUILD_FLAG" "$BUILD_ARTIFACT" "$SCHEME_NAME" "$report_path"
    printf 'DRY-RUN: write contract.json with tool_output_schema_version=%q\n' "$schema_version"
else
    mkdir -p "$periphery_dir"
    log "running periphery scan"
    (
        cd "$REPO_PATH"
        "$periphery_bin" scan \
            "$BUILD_FLAG" "$BUILD_ARTIFACT" \
            --scheme "$SCHEME_NAME" \
            --format json \
            --relative-results \
            --disable-update-check \
            --write-results "$report_path"
    )
    log "writing contract.json"
    jq -nc \
        --arg tool_name "Periphery" \
        --arg tool_version "$periphery_version" \
        --arg schema_version "$schema_version" \
        --arg captured_at "$(date -u +%Y-%m-%d)" \
        --arg raw_output_file "$PERIPHERY_REPORT_NAME" \
        '{
            tool_name: $tool_name,
            tool_version: $tool_version,
            output_format: "json",
            tool_output_schema_version: $schema_version,
            captured_at: $captured_at,
            raw_output_file: $raw_output_file
        }' > "$contract_path"
    log "periphery artefacts written to $periphery_dir"
fi

# ── Step 2: Emit .swiftinterface via xcodebuild ───────────────────────────────

swift_interface_out="$REPO_PATH/$SWIFT_INTERFACE_DIR"
trap '[[ -d "$DERIVED_DATA" ]] && rm -rf "$DERIVED_DATA"' EXIT

if [[ "$DRY_RUN" == "true" ]]; then
    printf 'DRY-RUN: mkdir -p %q\n' "$swift_interface_out"
    printf 'DRY-RUN: xcrun xcodebuild %s %q -scheme %q -destination %q -derivedDataPath %q OTHER_SWIFT_FLAGS="-emit-module-interface -enable-library-evolution" build\n' \
        "$BUILD_FLAG" "$BUILD_ARTIFACT" "$SCHEME_NAME" "$DESTINATION" "$DERIVED_DATA"
    printf 'DRY-RUN: copy *.swiftinterface from %q -> %q\n' "$DERIVED_DATA" "$swift_interface_out"
else
    require_command xcrun
    require_command find
    require_full_xcode
    mkdir -p "$swift_interface_out"
    log "building with xcodebuild to emit .swiftinterface files"
    build_log="${TMPDIR:-/tmp}/palace-prepare-xcode-$$.build.log"
    set +e
    xcrun xcodebuild \
        "$BUILD_FLAG" "$BUILD_ARTIFACT" \
        -scheme "$SCHEME_NAME" \
        -destination "$DESTINATION" \
        -derivedDataPath "$DERIVED_DATA" \
        CODE_SIGNING_ALLOWED=NO \
        CODE_SIGNING_REQUIRED=NO \
        OTHER_SWIFT_FLAGS="-emit-module-interface -enable-library-evolution" \
        build \
        >"$build_log" 2>&1
    build_rc=$?
    set -e
    if [[ $build_rc -ne 0 ]]; then
        warn "xcodebuild exited $build_rc (link/signing errors may be expected; checking for .swiftinterface output)"
    fi

    found=0
    while IFS= read -r -d '' ifile; do
        target="$swift_interface_out/$(basename "$ifile")"
        cp "$ifile" "$target"
        found=$((found + 1))
        log "copied: $(basename "$ifile")"
    done < <(find "$DERIVED_DATA" -name "*.swiftinterface" -print0 2>/dev/null)

    if [[ "$found" -eq 0 ]]; then
        die "no .swiftinterface files found under $DERIVED_DATA; ensure the scheme has Swift targets and library evolution is supported"
    fi
    rm -f "$build_log"
    log "emitted $found .swiftinterface file(s) to $swift_interface_out"
fi

# ── Step 3: Optional profiles copy (graceful skip) ───────────────────────────

profiles_src="$REPO_PATH/.palace/profiles"
if [[ -d "$profiles_src" ]]; then
    if [[ "$DRY_RUN" == "true" ]]; then
        printf 'DRY-RUN: profiles already in place at %q\n' "$profiles_src"
    else
        log "profiles directory present at $profiles_src (already in place)"
    fi
else
    if [[ "$DRY_RUN" == "true" ]]; then
        printf 'DRY-RUN: no profiles dir found; skipping (optional)\n'
    else
        log "no .palace/profiles directory found; skipping (optional)"
    fi
fi

# ── Summary ───────────────────────────────────────────────────────────────────

if [[ "$DRY_RUN" == "true" ]]; then
    printf 'DRY-RUN: prepare complete (no mutations)\n'
else
    log "prepare complete"
    printf '  periphery report: %s\n' "$report_path"
    printf '  periphery contract: %s\n' "$contract_path"
    printf '  swiftinterface dir: %s\n' "$swift_interface_out"
fi
