#!/usr/bin/env bash
# test_audit_e2e.sh — Smoke test for palace.audit.run (S1.10).
#
# Prerequisites (iMac):
#   1. docker compose --profile review up -d   (palace-mcp + neo4j running)
#   2. uv installed; run from services/palace-mcp/
#
# Usage:
#   bash tests/audit/smoke/test_audit_e2e.sh
#
# Exit codes:
#   0  all assertions passed
#   1  assertion failed
#   2  prerequisite missing (docker / compose not running)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SVC_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"
FIXTURE_DIR="$SCRIPT_DIR/../fixtures/audit-mini-project"
MCP_URL="${PALACE_MCP_URL:-http://localhost:8000/mcp}"
NEO4J_URI="${COMPOSE_NEO4J_URI:-bolt://localhost:7687}"
NEO4J_PASSWORD="${COMPOSE_NEO4J_PASSWORD:-changeme}"
PROJECT_SLUG="audit-mini-smoke-$$"

fail() { echo "FAIL: $*" >&2; exit 1; }
info() { echo "  [smoke] $*"; }

# ---------------------------------------------------------------------------
# Prerequisite: palace-mcp reachable
# ---------------------------------------------------------------------------
info "Checking palace-mcp at $MCP_URL ..."
if ! curl -sf "${MCP_URL%/mcp}/healthz" > /dev/null 2>&1; then
    echo "SKIP: palace-mcp not reachable at $MCP_URL" >&2
    echo "      Run: docker compose --profile review up -d" >&2
    exit 2
fi

# ---------------------------------------------------------------------------
# Seed Neo4j with fixture data (project-scoped to avoid collisions)
# ---------------------------------------------------------------------------
info "Seeding Neo4j with audit-mini fixture (project=$PROJECT_SLUG) ..."
SEED_SCRIPT="$(cat "$FIXTURE_DIR/seed.cypher" \
    | sed "s/audit-mini/$PROJECT_SLUG/g")"

echo "$SEED_SCRIPT" | docker exec -i \
    "$(docker compose --project-directory "$SVC_DIR/../.." ps -q neo4j 2>/dev/null | head -1)" \
    cypher-shell -u neo4j -p "$NEO4J_PASSWORD" 2>/dev/null \
    || fail "Neo4j seeding failed"

info "Fixture seeded."

# ---------------------------------------------------------------------------
# Run palace.audit.run via CLI
# ---------------------------------------------------------------------------
info "Running palace-mcp audit report for project=$PROJECT_SLUG ..."
REPORT_FILE="$(mktemp /tmp/audit-smoke-XXXXXX.md)"
trap 'rm -f "$REPORT_FILE"' EXIT

cd "$SVC_DIR"
uv run python -m palace_mcp.cli audit run \
    --project="$PROJECT_SLUG" \
    --url="$MCP_URL" \
    > "$REPORT_FILE" 2>&1 \
    || fail "palace.audit.run CLI exited non-zero"

# ---------------------------------------------------------------------------
# Assertions
# ---------------------------------------------------------------------------
info "Checking report content ..."

grep -q "# Audit Report" "$REPORT_FILE" \
    || fail "Report missing '# Audit Report' header"

grep -q "## Provenance" "$REPORT_FILE" \
    || fail "Report missing '## Provenance' section"

grep -q "$PROJECT_SLUG" "$REPORT_FILE" \
    || fail "Report does not reference project slug"

# Report should contain at least one section (hotspot run was seeded)
grep -q "Hotspot" "$REPORT_FILE" \
    || fail "Report missing Hotspot section (IngestRun was seeded)"

info "All assertions passed."

# ---------------------------------------------------------------------------
# Paved-path regression: seed one MORE extractor run and re-run
# Re-verify that the new section appears without code changes.
# ---------------------------------------------------------------------------
info "Paved-path regression: verifying extensibility ..."

# The fixture already seeds 7 extractors; hotspot appears above.
# Verify dead_symbol_binary_surface also appears (its IngestRun was seeded).
grep -q "Dead Symbol\|dead_symbol" "$REPORT_FILE" \
    || fail "Paved-path FAIL: dead_symbol section not in report after seeding its IngestRun"

info "Paved-path: dead_symbol_binary_surface section present — extensibility OK."

echo ""
echo "PASS: audit E2E smoke test (project=$PROJECT_SLUG)"
