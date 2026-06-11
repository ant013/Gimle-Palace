#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PREPARE_SCRIPT="${PALACE_REGEN_PUBLIC_API_PREPARE_SCRIPT:-$REPO_ROOT/paperclips/scripts/prepare_swift_kit_artifacts.sh}"

usage() {
    cat <<'EOF'
Usage: regen-public-api.sh <kit-slug> [prepare_swift_kit_artifacts.sh options]

Refresh the .swiftinterface inputs required by public_api_surface for a single
Swift kit. This is a thin wrapper over
paperclips/scripts/prepare_swift_kit_artifacts.sh --public-api-only, so it does
not refresh the paired Periphery artefacts used by dead_symbol_binary_surface.

Examples:
  bash bench/regen-public-api.sh evm-kit
  bash bench/regen-public-api.sh bitcoin-core --repo-base /Users/Shared/Ios/Gimle-Repos/HorizontalSystems
  bash bench/regen-public-api.sh dash-kit --dry-run
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

exec bash "$PREPARE_SCRIPT" --slug "$kit_slug" --public-api-only "$@"
