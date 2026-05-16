#!/usr/bin/env bash
# UAA Phase C: validate that a project's manifest is path-free + UUID-free.
# Wraps paperclips/scripts/validate_manifest.py (Python implementation).

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# shellcheck source=lib/_common.sh
source "${SCRIPT_DIR}/lib/_common.sh"

usage() {
  cat <<EOF
Usage: $(basename "$0") <project-key>

Validates that paperclips/projects/<project-key>/paperclip-agent-assembly.yaml
contains no literal UUIDs, no absolute paths, and no forbidden host-local keys
(per UAA spec §6.2). Exit 0 if clean; non-zero with diagnostic if not.
EOF
}

case "${1:-}" in
  -h|--help) usage; exit 0 ;;
  "") usage; exit 2 ;;
esac

project_key="$1"
manifest="${REPO_ROOT}/paperclips/projects/${project_key}/paperclip-agent-assembly.yaml"
[ -f "$manifest" ] || die "manifest not found: $manifest"

require_command python3
PYTHONPATH="${REPO_ROOT}" python3 -m paperclips.scripts.validate_manifest "$manifest"
