#!/usr/bin/env bash

set -euo pipefail

DRY_RUN=0
ACTION=""
ROLLBACK_SNAPSHOT=""
NEO4J_URI="${NEO4J_URI:-bolt://localhost:7687}"
NEO4J_USER="${NEO4J_USER:-neo4j}"
NEO4J_PASSWORD="${NEO4J_PASSWORD:-}"

usage() {
  cat <<'EOF'
Usage:
  migrate_path_to_file_path.sh --dry-run
  migrate_path_to_file_path.sh [--dry-run] --apply-step-1
  migrate_path_to_file_path.sh [--dry-run] --apply-step-3
  migrate_path_to_file_path.sh [--dry-run] --rollback-snapshot <dump-path>

Notes:
  - Step 1 copies legacy `path` into `file_path` for :Symbol|:File|:Function|:Module.
  - Step 3 removes legacy `path` after callers dual-read via coalesce(n.file_path, n.path).
  - Live execution uses cypher-shell for step 1/3 and neo4j-admin for rollback.
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --apply-step-1)
      ACTION="step1"
      shift
      ;;
    --apply-step-3)
      ACTION="step3"
      shift
      ;;
    --rollback-snapshot)
      ACTION="rollback"
      ROLLBACK_SNAPSHOT="${2:-}"
      [ -n "$ROLLBACK_SNAPSHOT" ] || {
        echo "rollback snapshot path required" >&2
        exit 1
      }
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

step1_cypher() {
  cat <<'EOF'
CALL apoc.periodic.iterate(
  'MATCH (n)
   WHERE (n:Symbol OR n:File OR n:Function OR n:Module)
     AND n.path IS NOT NULL
     AND n.file_path IS NULL
   RETURN n',
  'SET n.file_path = n.path',
  {batchSize: 1000, parallel: false}
);
EOF
}

step3_cypher() {
  cat <<'EOF'
CALL apoc.periodic.iterate(
  'MATCH (n)
   WHERE (n:Symbol OR n:File OR n:Function OR n:Module)
     AND n.path IS NOT NULL
     AND n.file_path IS NOT NULL
   RETURN n',
  'REMOVE n.path',
  {batchSize: 1000, parallel: false}
);
EOF
}

rollback_cmd() {
  printf '%s\n' \
    "neo4j-admin database load --from-path=${ROLLBACK_SNAPSHOT} --overwrite-destination=true neo4j"
}

run_cypher() {
  local query="$1"
  [ -n "$NEO4J_PASSWORD" ] || {
    echo "NEO4J_PASSWORD is required for live execution" >&2
    exit 1
  }
  printf '%s\n' "$query" | cypher-shell -a "$NEO4J_URI" -u "$NEO4J_USER" -p "$NEO4J_PASSWORD"
}

print_plan() {
  cat <<'EOF'
Dual-read expectation during migration:
  coalesce(n.file_path, n.path)

Available actions:
  --apply-step-1
  --apply-step-3
  --rollback-snapshot <dump-path>
EOF
  printf '\n--apply-step-1\n%s\n' "$(step1_cypher)"
  printf '\n--apply-step-3\n%s\n' "$(step3_cypher)"
}

if [ -z "$ACTION" ]; then
  if [ "$DRY_RUN" -eq 1 ]; then
    print_plan
    exit 0
  fi
  usage >&2
  exit 1
fi

case "$ACTION" in
  step1)
    QUERY="$(step1_cypher)"
    if [ "$DRY_RUN" -eq 1 ]; then
      printf '%s\n' "$QUERY"
      exit 0
    fi
    run_cypher "$QUERY"
    ;;
  step3)
    QUERY="$(step3_cypher)"
    if [ "$DRY_RUN" -eq 1 ]; then
      printf '%s\n' "$QUERY"
      exit 0
    fi
    run_cypher "$QUERY"
    ;;
  rollback)
    CMD="$(rollback_cmd)"
    if [ "$DRY_RUN" -eq 1 ]; then
      printf '%s\n' "$CMD"
      exit 0
    fi
    eval "$CMD"
    ;;
esac
