#!/usr/bin/env bash
# freeze.sh — regenerate docs/specs/gold-corpus/manifest.json from live state.
#
# Queries live Neo4j + git repos to pin the exact corpus state for Gate 1
# benchmark reproducibility. Idempotent: running again overwrites with current
# state.
#
# Usage:
#   bash docs/specs/gold-corpus/freeze.sh
#
# Prerequisites:
#   - NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD env vars (or defaults below)
#   - cypher-shell in PATH, or CYPHER_SHELL_CMD override
#   - sha256sum in PATH (Linux) or shasum (macOS)
#   - jq in PATH

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
MANIFEST_PATH="$REPO_ROOT/docs/specs/gold-corpus/manifest.json"
MATRIX_PATH="$REPO_ROOT/services/palace-mcp/tests/golden_matrix/semantic_search_matrix.yaml"
UW_IOS_REPO="${UW_IOS_REPO:-/repos/unstoppable-wallet-ios}"

NEO4J_URI="${NEO4J_URI:-bolt://localhost:7687}"
NEO4J_USER="${NEO4J_USER:-neo4j}"
NEO4J_PASSWORD="${NEO4J_PASSWORD:-}"
CYPHER_SHELL_CMD="${CYPHER_SHELL_CMD:-cypher-shell}"

# ── helpers ───────────────────────────────────────────────────────────────────

die() { echo "ERROR: $*" >&2; exit 1; }

sha256_file() {
    if command -v sha256sum &>/dev/null; then
        sha256sum "$1" | awk '{print $1}'
    elif command -v shasum &>/dev/null; then
        shasum -a 256 "$1" | awk '{print $1}'
    else
        die "Neither sha256sum nor shasum found"
    fi
}

cypher() {
    "$CYPHER_SHELL_CMD" \
        -a "$NEO4J_URI" \
        -u "$NEO4J_USER" \
        -p "$NEO4J_PASSWORD" \
        --format plain \
        "$@"
}

# ── palace_mcp_sha ────────────────────────────────────────────────────────────

palace_mcp_sha=$(git -C "$REPO_ROOT" rev-parse HEAD)

# ── uw_ios_sha ────────────────────────────────────────────────────────────────

uw_ios_sha=null

# Try mount path first
if [[ -f "$UW_IOS_REPO/.git/HEAD" ]]; then
    head_ref=$(cat "$UW_IOS_REPO/.git/HEAD")
    if [[ "$head_ref" == ref:* ]]; then
        ref_file="$UW_IOS_REPO/.git/${head_ref#ref: }"
        if [[ -f "$ref_file" ]]; then
            uw_ios_sha="\"$(cat "$ref_file" | tr -d '[:space]')\""
        fi
    else
        uw_ios_sha="\"$(echo "$head_ref" | tr -d '[:space:]')\""
    fi
fi

# Fall back to Neo4j :Project node
if [[ "$uw_ios_sha" == "null" ]]; then
    neo4j_sha=$(cypher \
        "MATCH (p:Project {slug: 'uw-ios-app'}) RETURN p.commit_sha LIMIT 1;" \
        2>/dev/null | tail -n1 | tr -d '"' | tr -d '[:space:]') || true
    if [[ -n "$neo4j_sha" && "$neo4j_sha" != "null" ]]; then
        uw_ios_sha="\"$neo4j_sha\""
    fi
fi

# ── neo4j_snapshot ────────────────────────────────────────────────────────────

echo "Querying Neo4j node counts…"

node_counts_raw=$(cypher \
    "MATCH (n) UNWIND labels(n) AS lbl RETURN lbl, count(n) AS cnt ORDER BY lbl;" \
    2>/dev/null) || die "Neo4j node count query failed (is Neo4j running?)"

rel_counts_raw=$(cypher \
    "MATCH ()-[r]->() RETURN type(r) AS rel, count(r) AS cnt ORDER BY rel;" \
    2>/dev/null) || true

# Build node_counts JSON object
node_counts_json="{"
first=1
while IFS=',' read -r lbl cnt; do
    lbl=$(echo "$lbl" | tr -d '"[:space:]')
    cnt=$(echo "$cnt" | tr -d '"[:space:]')
    [[ -z "$lbl" || "$lbl" == "lbl" ]] && continue
    [[ "$first" -eq 0 ]] && node_counts_json+=","
    node_counts_json+="\"$lbl\":$cnt"
    first=0
done <<< "$node_counts_raw"
node_counts_json+="}"

# Build relationship_counts JSON object
rel_counts_json="{"
first=1
while IFS=',' read -r rel cnt; do
    rel=$(echo "$rel" | tr -d '"[:space:]')
    cnt=$(echo "$cnt" | tr -d '"[:space:]')
    [[ -z "$rel" || "$rel" == "rel" ]] && continue
    [[ "$first" -eq 0 ]] && rel_counts_json+=","
    rel_counts_json+="\"$rel\":$cnt"
    first=0
done <<< "$rel_counts_raw"
rel_counts_json+="}"

# IngestRun states
echo "Querying IngestRun states…"
ingest_runs_raw=$(cypher \
    "MATCH (r:IngestRun) RETURN r.extractor AS extractor, r.status AS status, r.finished_at AS finished_at ORDER BY r.extractor;" \
    2>/dev/null) || true

ingest_runs_json="["
first=1
while IFS=',' read -r extractor status finished_at; do
    extractor=$(echo "$extractor" | tr -d '"[:space:]')
    status=$(echo "$status" | tr -d '"[:space:]')
    finished_at=$(echo "$finished_at" | tr -d '"[:space:]')
    [[ -z "$extractor" || "$extractor" == "extractor" ]] && continue
    [[ "$first" -eq 0 ]] && ingest_runs_json+=","
    ingest_runs_json+="{\"extractor\":\"$extractor\",\"status\":\"$status\",\"finished_at\":\"$finished_at\"}"
    first=0
done <<< "$ingest_runs_raw"
ingest_runs_json+="]"

# ── golden_matrix_sha ─────────────────────────────────────────────────────────

golden_matrix_sha=$(sha256_file "$MATRIX_PATH")

# ── frozen_at ─────────────────────────────────────────────────────────────────

frozen_at=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

# ── write manifest ────────────────────────────────────────────────────────────

cat > "$MANIFEST_PATH" <<EOF
{
  "schema_version": "1",
  "frozen_at": "$frozen_at",
  "palace_mcp_sha": "$palace_mcp_sha",
  "uw_ios_sha": $uw_ios_sha,
  "golden_matrix_sha": "$golden_matrix_sha",
  "neo4j_snapshot": {
    "node_counts": $node_counts_json,
    "relationship_counts": $rel_counts_json,
    "ingest_runs": $ingest_runs_json
  }
}
EOF

echo "Wrote $MANIFEST_PATH"
echo "  frozen_at:          $frozen_at"
echo "  palace_mcp_sha:     $palace_mcp_sha"
echo "  uw_ios_sha:         $uw_ios_sha"
echo "  golden_matrix_sha:  $golden_matrix_sha"
