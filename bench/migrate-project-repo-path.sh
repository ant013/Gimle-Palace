#!/usr/bin/env bash
# One-off backfill: populate :Project.repo_path on Neo4j for existing projects
# registered before PR #418 (which added repo_path to the registration path).
#
# Without repo_path, native get_code_snippet + detect_changes fall back to
# CM-sidecar with "project_not_mounted" warning, breaking analog-driven
# workflows that need real source code.
#
# Idempotent: only updates rows where repo_path IS NULL AND parent_mount +
# relative_path are present.
#
# Convention used here:
#   parent_mount=fresh    -> /Users/ant013/Ios-fresh/<relative_path>
#   parent_mount=baseline -> /Users/ant013/Ios/<relative_path>
#   parent_mount=<other>  -> /Users/ant013/Ios/<relative_path>
#
# If your :Project layout differs, edit the CASE expression below.
#
# Usage:
#   bench/migrate-project-repo-path.sh              # apply
#   bench/migrate-project-repo-path.sh --dry-run    # show what would change

set -euo pipefail

DRY_RUN=0
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=1

NEO4J_URI="${NEO4J_URI:-bolt://localhost:7687}"
NEO4J_USER="${NEO4J_USER:-neo4j}"
NEO4J_PASSWORD="${NEO4J_PASSWORD:?NEO4J_PASSWORD env var required (read from services/palace-mcp/.env)}"

CY_BACKFILL='
MATCH (p:Project)
WHERE p.repo_path IS NULL AND p.parent_mount IS NOT NULL AND p.relative_path IS NOT NULL
SET p.repo_path =
  CASE p.parent_mount
    WHEN "fresh" THEN "/Users/ant013/Ios-fresh/" + p.relative_path
    WHEN "baseline" THEN "/Users/ant013/Ios/" + p.relative_path
    ELSE "/Users/ant013/Ios/" + p.relative_path
  END
RETURN p.slug AS slug, p.repo_path AS repo_path
ORDER BY slug;
'

CY_DRY='
MATCH (p:Project)
WHERE p.repo_path IS NULL AND p.parent_mount IS NOT NULL AND p.relative_path IS NOT NULL
RETURN
  p.slug AS slug,
  p.parent_mount AS mount,
  p.relative_path AS rel,
  CASE p.parent_mount
    WHEN "fresh" THEN "/Users/ant013/Ios-fresh/" + p.relative_path
    WHEN "baseline" THEN "/Users/ant013/Ios/" + p.relative_path
    ELSE "/Users/ant013/Ios/" + p.relative_path
  END AS would_set_to
ORDER BY slug;
'

if [[ $DRY_RUN -eq 1 ]]; then
    echo "[dry-run] would update:"
    cypher-shell -a "$NEO4J_URI" -u "$NEO4J_USER" -p "$NEO4J_PASSWORD" --format plain "$CY_DRY"
    exit 0
fi

echo "[apply] backfilling :Project.repo_path..."
cypher-shell -a "$NEO4J_URI" -u "$NEO4J_USER" -p "$NEO4J_PASSWORD" --format plain "$CY_BACKFILL"

echo
echo "[verify] :Project rows still missing repo_path (should be 0 for migratable rows):"
cypher-shell -a "$NEO4J_URI" -u "$NEO4J_USER" -p "$NEO4J_PASSWORD" --format plain '
MATCH (p:Project)
WHERE p.repo_path IS NULL AND p.parent_mount IS NOT NULL AND p.relative_path IS NOT NULL
RETURN count(p) AS still_missing;
'
