#!/usr/bin/env bash
# UAA Phase H2: per-project AGENTS.md re-deploy on iMac.
#
# Wraps bootstrap-project.sh --reuse-bindings inside the safety envelope
# the legacy 280-line script provided:
#   - PATH augmentation (for bash -s over SSH)
#   - Worktree from origin/main (release-cut content, not develop)
#   - --target-sha pinning for rollback
#   - PHASE-A-ONLY sentinel guard (refuse to ship slim-craft-only bundles)
#   - EXPECTED_CWD + EXPECTED_BRANCH preflight
#   - Deploy log append (GIM-244 watchdog reads it)
#   - Cleanup trap on EXIT
#
# Pre-condition: ~/.paperclip/projects/<project-key>/bindings.yaml must exist.
# Operator populates it via:
#   migrate-bindings.sh <project-key>
#   bootstrap-project.sh <project-key>           # first time
# After that, this wrapper is the per-deploy entry point.

# Gotcha #4: PATH augmentation so bash -s over SSH finds git + homebrew tools.
export PATH="/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:$PATH"

# No pipefail at top level (GIM-106 Gotcha #2: pipefail breaks git|head pipelines).
set -eu

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
DEPLOY_LOG="$SCRIPT_DIR/imac-agents-deploy.log"
RUN_LOG="/tmp/imac-agents-deploy-$(date -u +%Y%m%dT%H%M%SZ).log"

EXPECTED_CWD="/Users/Shared/Ios/Gimle-Palace"
EXPECTED_BRANCH="develop"
WORKTREE_PATH="/tmp/gimle-agents-deploy"

# shellcheck source=lib/_common.sh
source "$SCRIPT_DIR/lib/_common.sh"

usage() {
  cat <<EOF
Usage: $(basename "$0") <project-key> [--target-sha <sha>] [--from-develop] [--help]

iMac AGENTS.md re-deploy for <project-key>. Uses a temporary worktree at
origin/main (release-cut content) and invokes bootstrap-project.sh
--reuse-bindings against \$HOME/.paperclip/projects/<project-key>/bindings.yaml.

Args:
  <project-key>           Required. Examples: gimle, trading, uaudit.
  --target-sha <sha>      Deploy specific SHA instead of origin/main tip.
                          Used for rollback per imac-agents-deploy.README.md.
  --from-develop          Deploy from origin/develop instead of origin/main.
                          For pre-release-cut smoke tests only.
  --help                  Show this message.

Project-keys with bindings on this host:
$(ls "${HOME}/.paperclip/projects/" 2>/dev/null | sed 's/^/  /' || echo "  (none - run migrate-bindings.sh + bootstrap-project.sh first)")
EOF
}

# ---- Arg parsing ----
PROJECT_KEY=""
TARGET_SHA=""
FROM_DEVELOP=0

while [ "$#" -gt 0 ]; do
  case "$1" in
    --target-sha)
      [ "$#" -ge 2 ] || die "--target-sha requires an argument"
      TARGET_SHA="$2"; shift 2 ;;
    --from-develop)
      FROM_DEVELOP=1; shift ;;
    -h|--help) usage; exit 0 ;;
    -*) die "unknown flag: $1 (try --help)" ;;
    *)
      [ -z "$PROJECT_KEY" ] || die "unexpected positional arg: $1 (project-key already set to $PROJECT_KEY)"
      PROJECT_KEY="$1"; shift ;;
  esac
done

[ -n "$PROJECT_KEY" ] || { usage >&2; exit 2; }

# Security CRIT (PR #207 audit): path-traversal validation per CRIT-5 contract.
# Without this guard, PROJECT_KEY=../etc would escape ~/.paperclip/projects/
# AND log-inject into DEPLOY_LOG (which GIM-244 watchdog parses).
validate_project_key "$PROJECT_KEY"

# ---- Log tee + dual-write (file + stdout) ----
exec > >(tee -a "$RUN_LOG") 2>&1
log info "=== imac-agents-deploy.sh start (project=$PROJECT_KEY, run log: $RUN_LOG) ==="

# ---- Pre-condition: host-local bindings.yaml ----
bindings="${HOME}/.paperclip/projects/${PROJECT_KEY}/bindings.yaml"
if [ ! -f "$bindings" ]; then
  die "no bindings for project '${PROJECT_KEY}' on this machine - run migrate-bindings.sh ${PROJECT_KEY} + bootstrap-project.sh ${PROJECT_KEY} first"
fi
log info "Using bindings at $bindings"

# ---- Pre-flight: cwd + branch ----
if [ "$REPO_ROOT" != "$EXPECTED_CWD" ]; then
  die "must run from $EXPECTED_CWD (got $REPO_ROOT)"
fi
cd "$REPO_ROOT"

CURRENT_BRANCH="$(git rev-parse --abbrev-ref HEAD)"
if [ "$CURRENT_BRANCH" != "$EXPECTED_BRANCH" ]; then
  die "branch must be '${EXPECTED_BRANCH}' (got '${CURRENT_BRANCH}')"
fi
log info "Pre-flight OK (cwd=$REPO_ROOT, branch=$CURRENT_BRANCH)"

# ---- Cleanup trap ----
cleanup() {
  log info "--- Cleanup ---"
  cd "$REPO_ROOT" 2>/dev/null || cd / 2>/dev/null || true
  if [ -d "$WORKTREE_PATH" ]; then
    if git worktree remove "$WORKTREE_PATH" --force 2>/dev/null; then
      log info "Worktree removed: $WORKTREE_PATH"
    else
      log warn "git worktree remove failed - fallback rm -rf + prune"
      rm -rf "$WORKTREE_PATH" 2>/dev/null || true
      git worktree prune 2>/dev/null || true
    fi
  fi
  current="$(cd "$REPO_ROOT" && git rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)"
  if [ "$current" != "$EXPECTED_BRANCH" ]; then
    log warn "production checkout on '${current}', expected '${EXPECTED_BRANCH}'"
  fi
}
trap cleanup EXIT

# ---- Fetch + resolve deploy ref ----
log info "--- Git fetch ---"
git fetch origin || die "git fetch failed"

if [ -n "$TARGET_SHA" ]; then
  git rev-parse --verify --quiet "${TARGET_SHA}^{commit}" >/dev/null 2>&1 \
    || die "--target-sha ${TARGET_SHA} is not a valid commit in this repo"
  DEPLOY_REF="$TARGET_SHA"
  log info "Target SHA: ${DEPLOY_REF}"
elif [ "$FROM_DEVELOP" -eq 1 ]; then
  DEPLOY_REF="origin/develop"
  log warn "Deploying from origin/develop (pre-release-cut smoke - NOT for production)"
else
  DEPLOY_REF="origin/main"
  log info "Deploying from origin/main (default release-cut content)"
fi

# ---- Worktree ----
log info "--- Worktree at $WORKTREE_PATH ---"
if [ -d "$WORKTREE_PATH" ]; then
  log info "Stale worktree found - removing"
  git worktree remove "$WORKTREE_PATH" --force 2>/dev/null || {
    rm -rf "$WORKTREE_PATH" 2>/dev/null || true
    git worktree prune 2>/dev/null || true
  }
fi
git worktree add --detach "$WORKTREE_PATH" "$DEPLOY_REF" || die "git worktree add failed"
SHA="$(cd "$WORKTREE_PATH" && git rev-parse HEAD)"
log info "Worktree created (SHA: ${SHA})"

# ---- Submodule init (worktrees don't auto-init) ----
log info "--- Submodule init ---"
cd "$WORKTREE_PATH"
git submodule update --init --recursive || die "git submodule update failed"

# ---- PHASE-A-ONLY sentinel guard ----
log info "--- PHASE-A-ONLY sentinel check ---"
if grep -RlE "PHASE-A-ONLY: not deployable" paperclips/dist/ 2>/dev/null | head -1 | grep -q .; then
  bad=$(grep -RlE "PHASE-A-ONLY: not deployable" paperclips/dist/ | head -3)
  die "PHASE-A-ONLY sentinel present in dist (would cripple live agents): ${bad}"
fi
log ok "No PHASE-A-ONLY sentinels in dist"

# ---- Hand off to bootstrap-project.sh ----
log info "--- bootstrap-project.sh ${PROJECT_KEY} --reuse-bindings ${bindings} ---"
# Phase H2-followup-3: skip --reuse-bindings when bindings already at
# canonical location (avoids "cp: source and dest identical" error on
# idempotent re-deploy).
canonical="${HOME}/.paperclip/projects/${PROJECT_KEY}/bindings.yaml"
if [ "$bindings" = "$canonical" ]; then
  bash "$WORKTREE_PATH/paperclips/scripts/bootstrap-project.sh" "$PROJECT_KEY" \
    || die "bootstrap-project.sh failed"
else
  bash "$WORKTREE_PATH/paperclips/scripts/bootstrap-project.sh" \
    "$PROJECT_KEY" --reuse-bindings "$bindings" \
    || die "bootstrap-project.sh failed"
fi

# ---- Append deploy log (GIM-244 watchdog reads this) ----
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] deploy=${PROJECT_KEY} sha=${SHA} ok run_log=${RUN_LOG}" >> "$DEPLOY_LOG"

log ok "=== imac-agents-deploy.sh complete for ${PROJECT_KEY} (SHA=${SHA}) ==="
