#!/usr/bin/env bash
# imac-deploy.sh — idempotent palace-mcp deploy on iMac production checkout
# Run directly on iMac (not over SSH from elsewhere; SSH user invokes it).
# See paperclips/scripts/imac-deploy.README.md for prerequisites + rollback.

# Gotcha #1: PATH augmentation so bash -s over SSH finds docker + git
export PATH="/Applications/Docker.app/Contents/Resources/bin:/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:$PATH"

# Use set -eu without pipefail at script level (gotcha #2: pipefail breaks git|head pipelines).
# Where we need pipefail semantics we use explicit checks.
set -eu

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
DEPLOY_LOG="$SCRIPT_DIR/imac-deploy.log"
RUN_LOG="/tmp/imac-deploy-$(date -u +%Y%m%dT%H%M%SZ).log"

EXPECTED_CWD="/Users/Shared/Ios/Gimle-Palace"
EXPECTED_BRANCH="develop"
COMPOSE_PROFILE="review"
PALACE_CONTAINER="gimle-palace-palace-mcp-1"
NEO4J_CONTAINER="gimle-palace-neo4j-1"
HEALTH_POLL_MAX=180   # 180 × 2s = 360s (gotcha-addressed: was 45×2s=90s)
HEALTH_POLL_SLEEP=2

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
TARGET_SHA=""
EXPECT_EXTRACTOR=""

usage() {
    cat <<EOF
Usage: $(basename "$0") [--target <sha>] [--expect-extractor <name>] [--help]

  --target <sha>           After git pull, assert HEAD == <sha> (deploy-pinning)
  --expect-extractor <name>  Assert this extractor appears in the registry
  --help                   Show this message
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --target)
            [[ $# -ge 2 ]] || { echo "ERROR: --target requires an argument" >&2; exit 4; }
            TARGET_SHA="$2"; shift 2 ;;
        --expect-extractor)
            [[ $# -ge 2 ]] || { echo "ERROR: --expect-extractor requires an argument" >&2; exit 4; }
            EXPECT_EXTRACTOR="$2"; shift 2 ;;
        --help|-h)
            usage; exit 0 ;;
        *)
            echo "ERROR: unknown argument: $1" >&2; usage >&2; exit 4 ;;
    esac
done

# ---------------------------------------------------------------------------
# Logging helpers — tee all output to per-run transient log
# ---------------------------------------------------------------------------
exec > >(tee -a "$RUN_LOG") 2>&1
log()  { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }
die()  { log "ERROR: $*" >&2; exit "${2:-1}"; }

log "=== imac-deploy.sh start (run log: $RUN_LOG) ==="

# ---------------------------------------------------------------------------
# Pre-flight (exit code 1)
# ---------------------------------------------------------------------------
log "--- Pre-flight checks ---"

# Assert cwd
if [[ "$REPO_ROOT" != "$EXPECTED_CWD" ]]; then
    die "must run from $EXPECTED_CWD (got $REPO_ROOT)" 1
fi
cd "$REPO_ROOT"

# Assert branch
CURRENT_BRANCH="$(git rev-parse --abbrev-ref HEAD)"
if [[ "$CURRENT_BRANCH" != "$EXPECTED_BRANCH" ]]; then
    die "branch must be '$EXPECTED_BRANCH' (got '$CURRENT_BRANCH')" 1
fi

# Assert tracked tree clean (gotcha #4: untracked files are OK — report but don't abort)
DIRTY="$(git status --porcelain --untracked-files=no)"
if [[ -n "$DIRTY" ]]; then
    die "tracked-tree dirty — commit or stash before deploying:\n$DIRTY" 1
fi

# Report untracked files for visibility (not an abort condition — e.g. scip/ fixture)
UNTRACKED_COUNT="$(git ls-files --others --exclude-standard | wc -l | tr -d ' ')"
if [[ "$UNTRACKED_COUNT" -gt 0 ]]; then
    log "INFO: $UNTRACKED_COUNT untracked file(s) present (not blocking deploy)"
    git ls-files --others --exclude-standard | head -20 | while read -r f; do
        log "  untracked: $f"
    done
fi

log "Pre-flight OK (branch=$CURRENT_BRANCH, tracked-tree=clean)"

# ---------------------------------------------------------------------------
# Git pull (exit code 1 on non-FF)
# ---------------------------------------------------------------------------
log "--- Git fetch + pull ---"
git fetch origin develop
OLD_SHA="$(git rev-parse HEAD)"

# Attempt FF-only pull; abort on non-fast-forward
if ! git pull --ff-only origin develop; then
    die "git pull --ff-only failed — diverged history? Resolve manually." 1
fi

NEW_SHA="$(git rev-parse HEAD)"
if [[ "$OLD_SHA" == "$NEW_SHA" ]]; then
    log "Already up to date (HEAD=$NEW_SHA)"
else
    log "Pulled: $OLD_SHA -> $NEW_SHA"
fi

# Optional --target SHA assertion (gotcha #2: use rev-parse --verify, not git log | grep)
if [[ -n "$TARGET_SHA" ]]; then
    # Verify commit object exists before comparing (avoids SIGPIPE on piped git log | grep)
    if ! git rev-parse --verify --quiet "${TARGET_SHA}^{commit}" >/dev/null 2>&1; then
        die "--target $TARGET_SHA is not a valid commit in this repo" 1
    fi
    RESOLVED="$(git rev-parse "$TARGET_SHA")"
    if [[ "$(git rev-parse HEAD)" != "$RESOLVED" ]]; then
        die "HEAD $(git rev-parse HEAD) != target $RESOLVED after pull" 1
    fi
    log "Target SHA verified: $RESOLVED"
fi

# ---------------------------------------------------------------------------
# Capture prev-image-id for rollback (before rebuild)
# ---------------------------------------------------------------------------
log "--- Capturing prev image ID for rollback ---"
PREV_IMAGE_ID=""
if docker inspect --format='{{.Image}}' "$PALACE_CONTAINER" >/dev/null 2>&1; then
    PREV_IMAGE_ID="$(docker inspect --format='{{.Image}}' "$PALACE_CONTAINER" 2>/dev/null || true)"
    log "Prev palace-mcp image: $PREV_IMAGE_ID"
else
    log "INFO: container $PALACE_CONTAINER not running — no prev image to capture"
fi

# ---------------------------------------------------------------------------
# Docker build + up (exit code 2)
# ---------------------------------------------------------------------------
log "--- docker compose build palace-mcp ---"
if ! docker compose --profile "$COMPOSE_PROFILE" build palace-mcp; then
    die "docker compose build failed" 2
fi

log "--- docker compose up palace-mcp neo4j ---"
if ! docker compose --profile "$COMPOSE_PROFILE" up -d palace-mcp neo4j; then
    die "docker compose up failed" 2
fi

# ---------------------------------------------------------------------------
# Healthcheck polling — BOTH neo4j and palace-mcp (gotcha #2 in timeout scope)
# ---------------------------------------------------------------------------
log "--- Waiting for containers to be healthy (timeout: $((HEALTH_POLL_MAX * HEALTH_POLL_SLEEP))s) ---"

wait_healthy() {
    local container="$1"
    local poll=0
    while [[ $poll -lt $HEALTH_POLL_MAX ]]; do
        local status
        status="$(docker inspect --format='{{.State.Health.Status}}' "$container" 2>/dev/null || echo "missing")"
        if [[ "$status" == "healthy" ]]; then
            log "$container: healthy"
            return 0
        fi
        log "$container: $status (poll $((poll+1))/$HEALTH_POLL_MAX)"
        sleep "$HEALTH_POLL_SLEEP"
        poll=$((poll + 1))
    done
    die "$container did not become healthy within $((HEALTH_POLL_MAX * HEALTH_POLL_SLEEP))s" 2
}

wait_healthy "$NEO4J_CONTAINER"
wait_healthy "$PALACE_CONTAINER"

# ---------------------------------------------------------------------------
# In-container extractor registry verify (gotcha #3: one-liner python in docker exec)
# ---------------------------------------------------------------------------
log "--- Verifying extractor registry ---"

# Gotcha #3: use one-liner with ; separators — no multi-line python -c in docker exec
EXTRACTOR_LIST="$(docker exec "$PALACE_CONTAINER" python3 -c "import asyncio; from palace_mcp.extractors.registry import EXTRACTORS; print('\n'.join(sorted(EXTRACTORS.keys())))")"
log "Registered extractors:"
echo "$EXTRACTOR_LIST" | while read -r name; do log "  - $name"; done

if [[ -n "$EXPECT_EXTRACTOR" ]]; then
    if ! echo "$EXTRACTOR_LIST" | grep -qx "$EXPECT_EXTRACTOR"; then
        die "expected extractor '$EXPECT_EXTRACTOR' not found in registry. Found: $(echo "$EXTRACTOR_LIST" | tr '\n' ' ')" 3
    fi
    log "Expected extractor '$EXPECT_EXTRACTOR': found"
fi

# ---------------------------------------------------------------------------
# Baseline log append
# ---------------------------------------------------------------------------
SOURCE_SHA="$(git rev-parse HEAD)"
NEW_IMAGE_ID="$(docker inspect --format='{{.Image}}' "$PALACE_CONTAINER" 2>/dev/null || echo "unknown")"
CONTAINER_ID="$(docker inspect --format='{{.Id}}' "$PALACE_CONTAINER" 2>/dev/null | cut -c1-12 || echo "unknown")"
UTC_NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

LOG_LINE="$UTC_NOW\tsource=$SOURCE_SHA\tprev_image=$PREV_IMAGE_ID\tnew_image=$NEW_IMAGE_ID\tcontainer=$CONTAINER_ID"
printf "%b\n" "$LOG_LINE" >> "$DEPLOY_LOG"
log "Baseline log: $LOG_LINE"

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------
log "=== imac-deploy.sh SUCCESS ==="
log "  Source SHA : $SOURCE_SHA"
log "  New image  : $NEW_IMAGE_ID"
log "  Container  : $CONTAINER_ID"
log "  Run log    : $RUN_LOG"
log "  Baseline   : $DEPLOY_LOG"
