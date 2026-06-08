#!/bin/sh
# Startup preflight checks for palace-mcp container.
# Fails fast on bad configuration before MCP server starts.
# Prints auth/exposure status without revealing secret values.

set -e

# ── 1. Tantivy index directory ────────────────────────────────────────────────

TANTIVY_DIR="${PALACE_TANTIVY_INDEX_PATH:-/var/lib/palace/tantivy}"

if [ ! -d "$TANTIVY_DIR" ]; then
    echo "ERROR: Tantivy index directory '$TANTIVY_DIR' does not exist." >&2
    echo "       Mount the 'palace-tantivy-data' volume at $TANTIVY_DIR." >&2
    exit 1
fi

if [ ! -w "$TANTIVY_DIR" ]; then
    echo "ERROR: Tantivy index directory '$TANTIVY_DIR' is not writable by UID $(id -u)." >&2
    echo "       Expected volume ownership: 1000:1000 (appuser)." >&2
    echo "       Current owner: $(stat -c '%u:%g' "$TANTIVY_DIR" 2>/dev/null || stat -f '%u:%g' "$TANTIVY_DIR")" >&2
    exit 1
fi

# ── 2. Neo4j auth preflight ───────────────────────────────────────────────────

NEO4J_URI="${NEO4J_URI:-}"
NEO4J_PASSWORD="${NEO4J_PASSWORD:-}"

if [ -n "$NEO4J_URI" ]; then
    if [ -z "$NEO4J_PASSWORD" ]; then
        echo "ERROR: NEO4J_PASSWORD is not set but NEO4J_URI is configured ($NEO4J_URI)." >&2
        echo "       Set NEO4J_PASSWORD in .env to a strong unique password." >&2
        echo "       Generate: openssl rand -base64 32" >&2
        exit 1
    fi

    if [ "$NEO4J_PASSWORD" = "changeme" ] || [ "$NEO4J_PASSWORD" = "neo4j" ]; then
        echo "ERROR: NEO4J_PASSWORD is a well-known default ('changeme' or 'neo4j')." >&2
        echo "       Replace it with a strong unique password in .env." >&2
        echo "       Generate: openssl rand -base64 32" >&2
        exit 1
    fi

    echo "[preflight] neo4j-uri=$NEO4J_URI auth=configured"
fi

# ── 3. Model cache status (informational) ─────────────────────────────────────

HF_CACHE="${PALACE_HF_CACHE_DIR:-/data/hf-cache}"
LOCAL_ONLY="${PALACE_EMBEDDING_LOCAL_ONLY:-0}"

if [ -d "$HF_CACHE" ]; then
    echo "[preflight] hf-cache=$HF_CACHE local-only=$LOCAL_ONLY"
else
    if [ "$LOCAL_ONLY" = "1" ] || [ "$LOCAL_ONLY" = "true" ] || [ "$LOCAL_ONLY" = "yes" ]; then
        echo "ERROR: HF cache directory '$HF_CACHE' does not exist and PALACE_EMBEDDING_LOCAL_ONLY=1." >&2
        echo "       Pre-warm the cache first:" >&2
        echo "       docker compose -f docker-compose.server.yml --profile cache-warm run cache-warm" >&2
        exit 1
    fi
    echo "[preflight] hf-cache=$HF_CACHE status=absent (will download on first use)"
fi

# ── 4. Repo mounts (informational) ───────────────────────────────────────────

for repo in /repos/gimle /repos/uw-ios /repos/uw-android /repos/uw-ios-mini; do
    if [ -d "$repo" ]; then
        echo "[preflight] repo=$repo status=mounted"
    else
        echo "[preflight] repo=$repo status=absent (extractors for this project will be skipped)"
    fi
done

exec "$@"
