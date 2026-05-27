#!/usr/bin/env bash
# palace-cleanup.sh — tiered cleanup for palace-mcp Docker resources.
#
# Levels:
#   safe        — Docker builder cache + temp workdirs. Safe to run anytime.
#   reclaim     — Stopped containers + dangling images. Does NOT touch volumes.
#   destructive — Named volumes (neo4j_data, palace-hf-cache, palace-tantivy-data).
#                 Requires --destructive flag AND interactive confirmation.
#                 MODEL CACHES WILL BE LOST. Only run with explicit operator approval.
#
# Usage:
#   ./scripts/palace-cleanup.sh --level=safe            # dry-run by default
#   ./scripts/palace-cleanup.sh --level=safe --execute
#   ./scripts/palace-cleanup.sh --level=reclaim --execute
#   ./scripts/palace-cleanup.sh --level=destructive --execute
#
# Safety invariants:
#   - Dry-run by default (--execute required for any real action).
#   - Realpath guards refuse /, $HOME, paths outside app-owned dirs.
#   - No broad `docker volume prune` — named volumes listed explicitly.
#   - Destructive level requires y/yes confirmation even with --execute.

set -euo pipefail

LEVEL=""
EXECUTE=false
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# App-owned volume names (must match docker-compose.yml).
SAFE_VOLUMES=()
RECLAIM_VOLUMES=()
DESTRUCTIVE_VOLUMES=(
    "palace-hf-cache"
    "palace-tantivy-data"
    "neo4j_data"
    "neo4j_logs"
    "codebase-memory-cache"
)

usage() {
    sed -n '2,/^$/p' "$0" | sed 's/^# //' | sed 's/^#//'
    exit 1
}

log()  { echo "[palace-cleanup] $*"; }
dry()  { echo "[DRY-RUN] would run: $*"; }
run()  { if $EXECUTE; then "$@"; else dry "$@"; fi; }

# ── Argument parsing ──────────────────────────────────────────────────────────
for arg in "$@"; do
    case "$arg" in
        --level=*)   LEVEL="${arg#--level=}" ;;
        --execute)   EXECUTE=true ;;
        --help|-h)   usage ;;
        *) echo "Unknown argument: $arg"; usage ;;
    esac
done

[[ -z "$LEVEL" ]] && { echo "ERROR: --level required."; usage; }

case "$LEVEL" in
    safe|reclaim|destructive) ;;
    *) echo "ERROR: invalid level '$LEVEL'. Must be safe|reclaim|destructive."; exit 1 ;;
esac

# ── Realpath guard ────────────────────────────────────────────────────────────
_guard_path() {
    local p
    p="$(realpath "$1" 2>/dev/null || echo "")"
    if [[ -z "$p" ]]; then
        echo "ERROR: path '$1' does not exist or cannot be resolved" >&2; exit 1
    fi

    local home_real
    home_real="$(realpath "$HOME")"

    if [[ "$p" == "/" ]]; then
        echo "ERROR: refusing to operate on /" >&2; exit 1
    fi
    if [[ "$p" == "$home_real" ]]; then
        echo "ERROR: refusing to operate on \$HOME ($HOME)" >&2; exit 1
    fi
    # Must be under REPO_ROOT or /tmp or /var or /data
    local allowed=("$REPO_ROOT" "/tmp" "/var" "/data")
    local ok=false
    for a in "${allowed[@]}"; do
        if [[ "$p" == "$a" || "$p" == "$a/"* ]]; then ok=true; break; fi
    done
    if ! $ok; then
        echo "ERROR: path $p is outside allowed dirs (${allowed[*]})" >&2; exit 1
    fi
}

# ── Cleanup functions ─────────────────────────────────────────────────────────
cleanup_safe() {
    log "Level: safe — Docker builder cache + temp dirs"
    # Docker builder cache (keep last 1GB to preserve recent layers).
    run docker builder prune --keep-storage 1GB --force
    # Temp workdir cleanup inside repo.
    local tmp_dir="$REPO_ROOT/.tmp"
    _guard_path "$tmp_dir"
    if [[ -d "$tmp_dir" ]]; then
        run rm -rf "$tmp_dir"
    else
        log "No .tmp dir found — skipping"
    fi
}

cleanup_reclaim() {
    cleanup_safe
    log "Level: reclaim — stopped containers + dangling images (no volumes)"
    run docker container prune --force
    run docker image prune --force
}

cleanup_destructive() {
    cleanup_reclaim
    log "Level: destructive — named volumes (ML model caches WILL be lost)"
    log "Volumes to remove: ${DESTRUCTIVE_VOLUMES[*]}"

    if $EXECUTE; then
        echo ""
        echo "WARNING: This will permanently remove ALL named volumes including"
        echo "         the HuggingFace/Qodo model cache (palace-hf-cache)."
        echo "         Re-downloading may take 5-15 min on first startup."
        echo ""
        read -r -p "Type 'yes' to confirm destructive cleanup: " confirm
        if [[ "$confirm" != "yes" ]]; then
            echo "Aborted."
            exit 0
        fi
        for vol in "${DESTRUCTIVE_VOLUMES[@]}"; do
            if docker volume inspect "$vol" &>/dev/null; then
                log "Removing volume: $vol"
                docker volume rm "$vol" || log "WARNING: could not remove $vol"
            else
                log "Volume $vol not found — skipping"
            fi
        done
    else
        for vol in "${DESTRUCTIVE_VOLUMES[@]}"; do
            dry docker volume rm "$vol"
        done
    fi
}

# ── Main ──────────────────────────────────────────────────────────────────────
if ! $EXECUTE; then
    log "DRY-RUN mode (pass --execute to apply changes)"
fi

case "$LEVEL" in
    safe)        cleanup_safe ;;
    reclaim)     cleanup_reclaim ;;
    destructive) cleanup_destructive ;;
esac

log "Done (level=$LEVEL execute=$EXECUTE)"
