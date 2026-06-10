#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
DEFAULT_MANIFEST="$REPO_ROOT/services/palace-mcp/scripts/uw-ios-bundle-manifest.json"
DEFAULT_REPO_BASE="${PALACE_SWIFT_KIT_HOST_REPO_BASE:-/Users/Shared/Ios/HorizontalSystems}"

# Hardcoded to match extractor.py:355 — do NOT change without updating the extractor
PERIPHERY_REPORT_NAME="periphery-3.7.4-swiftpm.json"
PERIPHERY_DIR="periphery"
SWIFT_INTERFACE_DIR=".palace/public-api/swift"

usage() {
    cat <<'EOF'
Usage: prepare_swift_kit_artifacts.sh --slug <name> [options]
       prepare_swift_kit_artifacts.sh --repo-path <path> [options]

Prepare artefacts required by the palace-mcp extractor cascade for a Swift kit.
Runs a Periphery dead-symbol scan, emits .swiftinterface snapshots, and
optionally copies .palace/profiles/ if present.

Required (one of):
  --slug <name>          Kit slug resolved via manifest
  --repo-path <path>     Explicit repo path (bypasses manifest lookup)

Options:
  --repo-base <path>     Base dir for slug resolution
                         (default: /Users/Shared/Ios/HorizontalSystems)
  --manifest <path>      Manifest for slug -> relative_path lookup
  --dry-run              Print actions without mutating state
  --periphery-only       Refresh only Periphery report + contract.json
  --help, -h             Show this message

Output artefacts:
  periphery/contract.json                      Periphery run metadata
  periphery/periphery-3.7.4-swiftpm.json       Periphery dead-symbol results
  .palace/public-api/swift/*.swiftinterface    Swift module interface snapshots

Notes:
  - periphery must be on PATH (brew install periphery or direct binary).
  - Requires Xcode command-line tools for swiftinterface emission.
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
import json, sys
from pathlib import Path
data = json.loads(Path(sys.argv[1]).read_text())
for m in data.get("members", []):
    if m.get("slug") == sys.argv[2]:
        print(m.get("relative_path", sys.argv[2]))
        raise SystemExit(0)
PY
}

run_or_dry() {
    if [[ "$DRY_RUN" == "true" ]]; then
        printf 'DRY-RUN: %s\n' "$*"
    else
        "$@"
    fi
}

SLUG=""
REPO_PATH=""
REPO_BASE="$DEFAULT_REPO_BASE"
MANIFEST_PATH="$DEFAULT_MANIFEST"
DRY_RUN="false"
PERIPHERY_ONLY="false"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --slug=*)  SLUG="${1#*=}"; shift ;;
        --slug)    [[ $# -ge 2 ]] || die "--slug requires a value"; SLUG="$2"; shift 2 ;;
        --repo-path=*)  REPO_PATH="${1#*=}"; shift ;;
        --repo-path)    [[ $# -ge 2 ]] || die "--repo-path requires a value"; REPO_PATH="$2"; shift 2 ;;
        --repo-base=*)  REPO_BASE="${1#*=}"; shift ;;
        --repo-base)    [[ $# -ge 2 ]] || die "--repo-base requires a value"; REPO_BASE="$2"; shift 2 ;;
        --manifest=*)   MANIFEST_PATH="${1#*=}"; shift ;;
        --manifest)     [[ $# -ge 2 ]] || die "--manifest requires a value"; MANIFEST_PATH="$2"; shift 2 ;;
        --dry-run)  DRY_RUN="true"; shift ;;
        --periphery-only)  PERIPHERY_ONLY="true"; shift ;;
        --help|-h)  usage; exit 0 ;;
        --*)  die "unknown option: $1" ;;
        *)    die "unexpected positional argument: $1" ;;
    esac
done

[[ -n "$SLUG" || -n "$REPO_PATH" ]] || { usage >&2; exit 2; }
[[ -z "$SLUG" || -z "$REPO_PATH" ]] || die "provide --slug or --repo-path, not both"

if [[ -n "$SLUG" ]]; then
    validate_slug "$SLUG"
    require_command python3
    relative_path="$(resolve_manifest_relative_path "$MANIFEST_PATH" "$SLUG" || true)"
    relative_path="${relative_path:-$SLUG}"
    REPO_PATH="$REPO_BASE/$relative_path"
fi

[[ -d "$REPO_PATH" ]] || die "repo not found: $REPO_PATH"
[[ -f "$REPO_PATH/Package.swift" ]] || die "Package.swift not found in $REPO_PATH (SwiftPM kit required)"

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
    printf 'DRY-RUN: (cd %q && periphery scan --quiet --format json --disable-update-check > %q)\n' \
        "$REPO_PATH" "$report_path"
    printf 'DRY-RUN: write contract.json with tool_output_schema_version=%q\n' "$schema_version"
else
    mkdir -p "$periphery_dir"
    log "running periphery scan"
    tmp_report="$(mktemp "$periphery_dir/.${PERIPHERY_REPORT_NAME}.tmp.XXXXXX")"
    if (
        cd "$REPO_PATH"
        "$periphery_bin" scan \
            --quiet \
            --format json \
            --disable-update-check > "$tmp_report"
    ); then
        mv "$tmp_report" "$report_path"
    else
        rc=$?
        rm -f "$tmp_report"
        exit "$rc"
    fi
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

if [[ "$PERIPHERY_ONLY" == "true" ]]; then
    if [[ "$DRY_RUN" == "true" ]]; then
        printf 'DRY-RUN: periphery-only complete (no .swiftinterface emission)\n'
    else
        log "periphery-only complete"
        printf '  periphery report: %s\n' "$report_path"
        printf '  periphery contract: %s\n' "$contract_path"
    fi
    exit 0
fi

# ── Step 2: Emit .swiftinterface ──────────────────────────────────────────────

swift_interface_out="$REPO_PATH/$SWIFT_INTERFACE_DIR"
build_scratch="${TMPDIR:-/tmp}/palace-prepare-$$.build"
trap '[[ -d "$build_scratch" ]] && rm -rf "$build_scratch"' EXIT

if [[ "$DRY_RUN" == "true" ]]; then
    printf 'DRY-RUN: mkdir -p %q\n' "$swift_interface_out"
    printf 'DRY-RUN: swift build -c release --build-path %q -Xswiftc -enable-library-evolution\n' \
        "$build_scratch"
    printf 'DRY-RUN: copy *.swiftinterface -> %q\n' "$swift_interface_out"
else
    require_command xcrun
    require_command find
    mkdir -p "$swift_interface_out"
    log "building with library evolution to emit .swiftinterface files"
    set +e
    build_log="${TMPDIR:-/tmp}/palace-prepare-$$.build.log"
    (
        cd "$REPO_PATH"
        xcrun swift build \
            -c release \
            --build-path "$build_scratch" \
            -Xswiftc -enable-library-evolution
    ) >"$build_log" 2>&1
    build_rc=$?
    set -e
    if [[ $build_rc -ne 0 ]]; then
        warn "swift build exited $build_rc (link errors are expected for iOS-only packages; continuing)"
    fi

    found=0
    while IFS= read -r -d '' ifile; do
        target="$swift_interface_out/$(basename "$ifile")"
        cp "$ifile" "$target"
        found=$((found + 1))
        log "copied: $(basename "$ifile")"
    done < <(find "$build_scratch" -name "*.swiftinterface" -print0 2>/dev/null)

    if [[ "$found" -eq 0 ]]; then
        die "no .swiftinterface files emitted; ensure the package has library targets and library evolution is supported (swift-tools-version ≥ 5.4 recommended)"
    fi
    rm -f "$build_log"
    log "emitted $found .swiftinterface file(s) to $swift_interface_out"
fi

# ── Step 3: Optional profiles copy (graceful skip) ───────────────────────────

profiles_src="$REPO_PATH/.palace/profiles"
if [[ -d "$profiles_src" ]]; then
    profiles_dest="$REPO_PATH/.palace/profiles"
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
