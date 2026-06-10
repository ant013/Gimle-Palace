#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PREPARE_SCRIPT="${PALACE_REGEN_PERIPHERY_PREPARE_SCRIPT:-$REPO_ROOT/paperclips/scripts/prepare_swift_kit_artifacts.sh}"

usage() {
    cat <<'EOF'
Usage: regen-periphery.sh <kit-slug> [prepare_swift_kit_artifacts.sh options]

Refresh the Periphery fixture inputs required by dead_symbol_binary_surface for a
single Swift kit. This is a thin wrapper over
paperclips/scripts/prepare_swift_kit_artifacts.sh --periphery-only, so it does
not refresh the paired .swiftinterface artefacts used by public_api_surface.

Examples:
  bash bench/regen-periphery.sh bitcoin-core
  bash bench/regen-periphery.sh dash-kit --repo-base /Users/Shared/Ios/HorizontalSystems
  bash bench/regen-periphery.sh litecoin-kit --dry-run
EOF
}

if [[ $# -eq 0 ]]; then
    usage >&2
    exit 2
fi

case "${1:-}" in
    -h|--help)
        usage
        exit 0
        ;;
esac

kit_slug="$1"
shift

exec bash "$PREPARE_SCRIPT" --slug "$kit_slug" --periphery-only "$@"
