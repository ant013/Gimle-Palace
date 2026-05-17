#!/usr/bin/env bash
# UAA Phase H2: thin wrapper around bootstrap-project.sh --reuse-bindings.
#
# Supersedes the legacy per-target deploy scripts. The new
# bootstrap-project.sh handles claude + codex + workspace setup in one
# place via the 13-step lifecycle (see spec §9.2). When passed
# --reuse-bindings, it skips re-hire and only re-deploys per-agent
# AGENTS.md to existing hired agents.
#
# Pre-condition: ~/.paperclip/projects/<project-key>/bindings.yaml must
# exist (run bootstrap-project.sh once for the project before using
# this wrapper).

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# shellcheck source=lib/_common.sh
source "${SCRIPT_DIR}/lib/_common.sh"

usage() {
  cat <<EOF
Usage: $(basename "$0") <project-key>

iMac wrapper: re-deploys per-agent AGENTS.md to all hired agents of
<project-key> using bootstrap-project.sh --reuse-bindings.

Use after AGENTS.md template / fragment changes are merged to develop
and need to land on the iMac runtime.

Project-keys with bindings on this host:
$(ls "${HOME}/.paperclip/projects/" 2>/dev/null | sed 's/^/  /' || echo "  (none - run bootstrap-project.sh first)")
EOF
}

[ "$#" -eq 1 ] || { usage; exit 2; }
project_key="$1"

bindings="${HOME}/.paperclip/projects/${project_key}/bindings.yaml"
[ -f "$bindings" ] || die "no bindings for project '${project_key}' on this machine - run bootstrap-project.sh first"

log info "iMac re-deploy for ${project_key} (using existing bindings at ${bindings})"
"${SCRIPT_DIR}/bootstrap-project.sh" "${project_key}" --reuse-bindings "$bindings"
log ok "iMac deploy complete for ${project_key}"
