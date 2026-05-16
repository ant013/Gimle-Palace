#!/usr/bin/env bash
# imac-agents-deploy.sh — idempotent AGENTS.md deploy on iMac production checkout
# Deploys from origin/main via temporary git worktree (never mutates local main).
# See paperclips/scripts/imac-agents-deploy.README.md for prerequisites + rollback.

# Gotcha #4: PATH augmentation so bash -s over SSH finds git + homebrew tools
export PATH="/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:$PATH"

# No pipefail at top level (see GIM-106 Gotcha #2: pipefail breaks git|head pipelines).
set -eu

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
DEPLOY_LOG="$SCRIPT_DIR/imac-agents-deploy.log"
RUN_LOG="/tmp/imac-agents-deploy-$(date -u +%Y%m%dT%H%M%SZ).log"

EXPECTED_CWD="/Users/Shared/Ios/Gimle-Palace"
EXPECTED_BRANCH="develop"
WORKTREE_PATH="/tmp/gimle-agents-deploy"

# Agent IDs for verify step
COMPANY_ID="9d8f432c-ff7d-4e3a-bbe3-3cd355f73b64"
CTO_AGENT_ID="7fb0fdbb-e17f-4487-a4da-16993a907bec"

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
TARGET_SHA=""
VERIFY_MARKER="Phase 4.2"

usage() {
    cat <<EOF
Usage: $(basename "$0") [--target-sha <sha>] [--verify-marker <text>] [--help]

  --target-sha <sha>        Deploy specific main SHA instead of origin/main tip
  --verify-marker <text>    Grep deployed CTO AGENTS.md for this marker
                            (default: "Phase 4.2")
  --help                    Show this message
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --target-sha)
            [[ $# -ge 2 ]] || { echo "ERROR: --target-sha requires an argument" >&2; exit 1; }
            TARGET_SHA="$2"; shift 2 ;;
        --verify-marker)
            [[ $# -ge 2 ]] || { echo "ERROR: --verify-marker requires an argument" >&2; exit 1; }
            VERIFY_MARKER="$2"; shift 2 ;;
        --help|-h)
            usage; exit 0 ;;
        *)
            echo "ERROR: unknown argument: $1" >&2; usage >&2; exit 1 ;;
    esac
done

# ---------------------------------------------------------------------------
# Logging helpers — tee all output to per-run transient log
# ---------------------------------------------------------------------------
exec > >(tee -a "$RUN_LOG") 2>&1
log()  { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }
die()  { log "ERROR: $*" >&2; exit "${2:-1}"; }

log "=== imac-agents-deploy.sh start (run log: $RUN_LOG) ==="

# ---------------------------------------------------------------------------
# Cleanup trap — guaranteed worktree removal on exit, error, or ctrl-C
# Gotcha #2: trap EXIT fires on all exit paths, including signal exits.
# ---------------------------------------------------------------------------
cleanup() {
    log "--- Cleanup ---"
    # Return to repo root before removing worktree (worktree may be cwd)
    cd "$REPO_ROOT" 2>/dev/null || cd / 2>/dev/null || true
    if [ -d "$WORKTREE_PATH" ]; then
        if git worktree remove "$WORKTREE_PATH" --force 2>/dev/null; then
            log "Worktree removed: $WORKTREE_PATH"
        else
            # Gotcha #2: fallback when git worktree remove fails (e.g. locks)
            log "WARN: git worktree remove failed — falling back to rm -rf + prune"
            rm -rf "$WORKTREE_PATH" 2>/dev/null || true
            git worktree prune 2>/dev/null || true
            log "Worktree cleaned via rm -rf"
        fi
    else
        log "Worktree already clean (${WORKTREE_PATH} not present)"
    fi
    # Gotcha #3: verify production checkout still on develop after cleanup
    local current
    current="$(cd "$REPO_ROOT" && git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")"
    if [[ "$current" != "$EXPECTED_BRANCH" ]]; then
        log "WARNING: production checkout on '${current}', expected '${EXPECTED_BRANCH}'"
    else
        log "Production checkout: ${current} (OK)"
    fi
}
trap cleanup EXIT

# ---------------------------------------------------------------------------
# Pre-flight (exit code 1)
# ---------------------------------------------------------------------------
log "--- Pre-flight checks ---"

if [[ "$REPO_ROOT" != "$EXPECTED_CWD" ]]; then
    die "must run from $EXPECTED_CWD (got $REPO_ROOT)" 1
fi
cd "$REPO_ROOT"

CURRENT_BRANCH="$(git rev-parse --abbrev-ref HEAD)"
if [[ "$CURRENT_BRANCH" != "$EXPECTED_BRANCH" ]]; then
    die "branch must be '${EXPECTED_BRANCH}' (got '${CURRENT_BRANCH}')" 1
fi

log "Pre-flight OK (branch=${CURRENT_BRANCH})"

# ---------------------------------------------------------------------------
# Git fetch (exit code 2 on failure)
# ---------------------------------------------------------------------------
log "--- Git fetch ---"
git fetch origin || die "git fetch failed" 2

# Resolve deploy ref
if [[ -n "$TARGET_SHA" ]]; then
    if ! git rev-parse --verify --quiet "${TARGET_SHA}^{commit}" >/dev/null 2>&1; then
        die "--target-sha ${TARGET_SHA} is not a valid commit in this repo" 1
    fi
    DEPLOY_REF="$TARGET_SHA"
    log "Target SHA: ${DEPLOY_REF}"
else
    DEPLOY_REF="origin/main"
    log "Deploying from: origin/main"
fi

# ---------------------------------------------------------------------------
# Worktree creation (exit code 2)
# Gotcha #1: worktrees from detached HEAD — never mutates local main branch.
# ---------------------------------------------------------------------------
log "--- Creating worktree at ${WORKTREE_PATH} ---"

# Remove stale worktree for idempotency (e.g. previous run aborted after trap)
if [ -d "$WORKTREE_PATH" ]; then
    log "Stale worktree found — removing before recreating"
    git worktree remove "$WORKTREE_PATH" --force 2>/dev/null || {
        rm -rf "$WORKTREE_PATH" 2>/dev/null || true
        git worktree prune 2>/dev/null || true
    }
fi

if ! git worktree add --detach "$WORKTREE_PATH" "$DEPLOY_REF"; then
    die "git worktree add failed" 2
fi

MAIN_SHA="$(cd "$WORKTREE_PATH" && git rev-parse HEAD)"
log "Worktree created (SHA: ${MAIN_SHA})"

# ---------------------------------------------------------------------------
# Submodule init (exit code 2)
# Gotcha #1: git worktree add does NOT auto-init submodules.
# ---------------------------------------------------------------------------
log "--- Submodule init ---"
cd "$WORKTREE_PATH"

if ! git submodule update --init --recursive; then
    die "git submodule update failed — SSH key for submodule repo accessible?" 2
fi
log "Submodules initialised"

# ---------------------------------------------------------------------------
# Build (exit code 3)
# ---------------------------------------------------------------------------
log "--- Build: paperclips/build.sh ---"

if ! bash paperclips/build.sh; then
    die "paperclips/build.sh (claude) failed" 3
fi
log "Build (claude) complete"

if ! bash paperclips/build.sh --target codex; then
    die "paperclips/build.sh --target codex failed" 3
fi
log "Build (codex) complete"

# ---------------------------------------------------------------------------
# Deploy Claude side (exit code 3)
# ---------------------------------------------------------------------------
log "--- Deploy: paperclips/deploy-agents.sh --local ---"

if ! bash paperclips/deploy-agents.sh --local; then
    die "paperclips/deploy-agents.sh --local failed" 3
fi
log "Deploy (claude) complete"

# ---------------------------------------------------------------------------
# Deploy Codex side (exit code 3)
# Requires PAPERCLIP_API_KEY — codex deploy is API-only (no local mode).
# Falls back to a warning if the key is absent so the Claude-side
# deploy still counts as "success" — operator can re-run after exporting.
# ---------------------------------------------------------------------------
log "--- Deploy: paperclips/deploy-codex-agents.sh --api ---"

if [ -z "${PAPERCLIP_API_KEY:-}" ]; then
    log "WARNING: PAPERCLIP_API_KEY not set — skipping Codex deploy."
    log "         Re-run with PAPERCLIP_API_KEY exported to push Codex bundles."
elif ! bash paperclips/deploy-codex-agents.sh --api; then
    die "paperclips/deploy-codex-agents.sh --api failed" 3
else
    log "Deploy (codex) complete"
fi

# Capture agent count before cleanup removes worktree/dist
DEPLOYED_COUNT=0
DIST_DIR="$WORKTREE_PATH/paperclips/dist"
if [ -d "$DIST_DIR" ]; then
    DEPLOYED_COUNT="$(ls -1 "$DIST_DIR"/*.md 2>/dev/null | wc -l | tr -d ' ')"
fi
DEPLOYED_COUNT_CODEX=0
DIST_DIR_CODEX="$WORKTREE_PATH/paperclips/dist/codex"
if [ -d "$DIST_DIR_CODEX" ]; then
    DEPLOYED_COUNT_CODEX="$(ls -1 "$DIST_DIR_CODEX"/*.md 2>/dev/null | wc -l | tr -d ' ')"
fi

# Return to repo root so cleanup trap finds it cleanly
cd "$REPO_ROOT"

# ---------------------------------------------------------------------------
# Verify (exit code 4)
# Grep a known marker in CTO AGENTS.md — proves content was actually updated.
# ---------------------------------------------------------------------------
log "--- Verify ---"

PAPERCLIP_DATA="${PAPERCLIP_DATA_DIR:-$HOME/.paperclip/instances/default}"
CTO_AGENTS_MD="$PAPERCLIP_DATA/companies/$COMPANY_ID/agents/$CTO_AGENT_ID/instructions/AGENTS.md"

if [ ! -f "$CTO_AGENTS_MD" ]; then
    die "CTO AGENTS.md not found at ${CTO_AGENTS_MD} — deploy may have failed" 4
fi

if ! grep -qF "$VERIFY_MARKER" "$CTO_AGENTS_MD"; then
    die "marker '${VERIFY_MARKER}' not found in deployed CTO AGENTS.md (${CTO_AGENTS_MD})" 4
fi

# UAA Phase A deploy guard: refuse to deploy slim-craft files (Phase A intermediate state).
# Per spec §10.5: slim crafts are inert until Phase B's compose_agent_prompt composes
# universal/profile/role/overlay into a runnable AGENTS.md. Deploying as-is = broken agents.
if grep -qF "PHASE-A-ONLY: not deployable without Phase B" "$CTO_AGENTS_MD"; then
    die "PHASE-A-ONLY sentinel detected in CTO AGENTS.md — Phase B compose engine not yet active. Refusing to deploy slim-craft files (would cripple live agents). See UAA spec §10.5." 5
fi
log "Verify OK: marker '${VERIFY_MARKER}' found in CTO AGENTS.md (no Phase A sentinel)"

# ---------------------------------------------------------------------------
# Baseline log append
# ---------------------------------------------------------------------------
UTC_NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
LOG_LINE="${UTC_NOW}\tmain_sha=${MAIN_SHA}\tdeployed_claude=${DEPLOYED_COUNT}\tdeployed_codex=${DEPLOYED_COUNT_CODEX}"
printf "%b\n" "$LOG_LINE" >> "$DEPLOY_LOG"
log "Baseline log: ${LOG_LINE}"

# ---------------------------------------------------------------------------
# Done (cleanup trap fires after this — removes worktree)
# ---------------------------------------------------------------------------
log "=== imac-agents-deploy.sh SUCCESS ==="
log "  Main SHA        : ${MAIN_SHA}"
log "  Deployed Claude : ${DEPLOYED_COUNT}"
log "  Deployed Codex  : ${DEPLOYED_COUNT_CODEX}"
log "  Run log         : ${RUN_LOG}"
log "  Baseline        : ${DEPLOY_LOG}"
