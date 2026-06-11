#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
DEFAULT_MANIFEST="$REPO_ROOT/services/palace-mcp/scripts/uw-ios-bundle-manifest.json"
DEFAULT_REPO_BASE="${PALACE_SWIFT_KIT_HOST_REPO_BASE:-/Users/Shared/Ios/Gimle-Repos/HorizontalSystems}"

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
                         (default: /Users/Shared/Ios/Gimle-Repos/HorizontalSystems)
  --manifest <path>      Manifest for slug -> relative_path lookup
  --dry-run              Print actions without mutating state
  --periphery-only       Refresh only Periphery report + contract.json
  --public-api-only      Refresh only .swiftinterface snapshots
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

discover_public_api_modules() {
    local repo_path="$1"
    (
        cd "$repo_path"
        xcrun swift package describe --type json
    ) | python3 -c '
import json
import sys

try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)

targets = []
for product in data.get("products", []):
    product_type = product.get("type", {})
    if isinstance(product_type, dict) and "library" in product_type:
        targets.extend(product.get("targets", []))

if not targets and data.get("name"):
    targets.append(data["name"])

seen = set()
for target in targets:
    if target and target not in seen:
        print(target)
        seen.add(target)
'
}

SLUG=""
REPO_PATH=""
REPO_BASE="$DEFAULT_REPO_BASE"
MANIFEST_PATH="$DEFAULT_MANIFEST"
DRY_RUN="false"
PERIPHERY_ONLY="false"
PUBLIC_API_ONLY="false"

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
        --public-api-only)  PUBLIC_API_ONLY="true"; shift ;;
        --help|-h)  usage; exit 0 ;;
        --*)  die "unknown option: $1" ;;
        *)    die "unexpected positional argument: $1" ;;
    esac
done

[[ -n "$SLUG" || -n "$REPO_PATH" ]] || { usage >&2; exit 2; }
[[ -z "$SLUG" || -z "$REPO_PATH" ]] || die "provide --slug or --repo-path, not both"
[[ "$PERIPHERY_ONLY" != "true" || "$PUBLIC_API_ONLY" != "true" ]] || \
    die "provide --periphery-only or --public-api-only, not both"

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

periphery_dir="$REPO_PATH/$PERIPHERY_DIR"
report_path="$periphery_dir/$PERIPHERY_REPORT_NAME"
contract_path="$periphery_dir/contract.json"

if [[ "$PUBLIC_API_ONLY" == "true" ]]; then
    log "public-api-only: skipping Periphery artefact refresh"
else
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
xcodebuild_scratch="${TMPDIR:-/tmp}/palace-prepare-$$.xcodebuild"
trap '[[ -d "$build_scratch" ]] && rm -rf "$build_scratch"; [[ -d "$xcodebuild_scratch" ]] && rm -rf "$xcodebuild_scratch"' EXIT

public_api_modules=()
if [[ "$DRY_RUN" == "false" ]]; then
    require_command python3
    while IFS= read -r module_name; do
        [[ -n "$module_name" ]] && public_api_modules+=("$module_name")
    done < <(discover_public_api_modules "$REPO_PATH")
    if [[ "${#public_api_modules[@]}" -eq 0 ]]; then
        fallback_module="$(basename "$REPO_PATH")"
        fallback_module="${fallback_module%.Swift}"
        public_api_modules+=("$fallback_module")
        warn "could not discover library products; falling back to module name '$fallback_module'"
    fi
fi

should_copy_public_interface() {
    local base="$1"
    [[ "$base" != *.private.swiftinterface ]] || return 1
    [[ "$base" != *.package.swiftinterface ]] || return 1

    if [[ "${#public_api_modules[@]}" -eq 0 ]]; then
        return 0
    fi

    local module_name
    for module_name in "${public_api_modules[@]}"; do
        [[ "$base" == "$module_name.swiftinterface" ]] && return 0
    done
    return 1
}

copy_public_interfaces_from() {
    local source_dir="$1"
    local copied=0
    local ifile base target
    while IFS= read -r -d '' ifile; do
        base="$(basename "$ifile")"
        should_copy_public_interface "$base" || continue
        target="$swift_interface_out/$base"
        cp "$ifile" "$target"
        copied=$((copied + 1))
        log "copied: $base"
    done < <(find "$source_dir" -name "*.swiftinterface" -print0 2>/dev/null)
    COPIED_INTERFACE_COUNT="$copied"
}

if [[ "$DRY_RUN" == "true" ]]; then
    printf 'DRY-RUN: mkdir -p %q\n' "$swift_interface_out"
    printf 'DRY-RUN: swift build -c release --build-path %q -Xswiftc -enable-library-evolution\n' \
        "$build_scratch"
    printf 'DRY-RUN: if swift build emits no root interfaces, run xcodebuild iOS Simulator fallback\n'
    printf 'DRY-RUN: xcodebuild -scheme <package-library> -destination %q -configuration Release -derivedDataPath %q SKIP_INSTALL=NO SWIFT_EMIT_MODULE_INTERFACE=YES CODE_SIGNING_ALLOWED=NO ONLY_ACTIVE_ARCH=YES ARCHS=arm64 build\n' \
        "generic/platform=iOS Simulator" "$xcodebuild_scratch"
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

    copy_public_interfaces_from "$build_scratch"
    found="$COPIED_INTERFACE_COUNT"

    if [[ "$found" -eq 0 ]]; then
        require_command xcodebuild
        xcodebuild_scheme="${PALACE_SWIFT_KIT_XCODEBUILD_SCHEME:-${public_api_modules[0]}}"
        log "swift build emitted no root .swiftinterface files; trying xcodebuild scheme '$xcodebuild_scheme'"
        xcodebuild_log="${TMPDIR:-/tmp}/palace-prepare-$$.xcodebuild.log"
        set +e
        (
            cd "$REPO_PATH"
            xcodebuild \
                -scheme "$xcodebuild_scheme" \
                -destination "generic/platform=iOS Simulator" \
                -configuration Release \
                -derivedDataPath "$xcodebuild_scratch" \
                SKIP_INSTALL=NO \
                SWIFT_EMIT_MODULE_INTERFACE=YES \
                CODE_SIGNING_ALLOWED=NO \
                ONLY_ACTIVE_ARCH=YES \
                ARCHS=arm64 \
                build
        ) >"$xcodebuild_log" 2>&1
        xcodebuild_rc=$?
        set -e
        if [[ $xcodebuild_rc -ne 0 ]]; then
            warn "xcodebuild exited $xcodebuild_rc; checking for emitted interfaces before failing"
        fi

        copy_public_interfaces_from "$xcodebuild_scratch"
        found="$COPIED_INTERFACE_COUNT"
    fi

    if [[ "$found" -eq 0 ]]; then
        die "no .swiftinterface files emitted; ensure the package has library targets and can build with swift build or the xcodebuild iOS Simulator fallback"
    fi
    rm -f "$build_log" "${xcodebuild_log:-}"
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
    if [[ "$PUBLIC_API_ONLY" == "true" ]]; then
        log "public-api-only complete"
    else
        log "prepare complete"
        printf '  periphery report: %s\n' "$report_path"
        printf '  periphery contract: %s\n' "$contract_path"
    fi
    printf '  swiftinterface dir: %s\n' "$swift_interface_out"
fi
