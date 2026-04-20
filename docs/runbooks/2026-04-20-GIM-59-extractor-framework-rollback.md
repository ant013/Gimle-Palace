# GIM-59 extractor framework rollback

**Spec:** `docs/superpowers/specs/2026-04-20-extractor-framework-substrate-design.md`

**Trigger conditions:**
- `ensure_extractors_schema` fails at palace-mcp startup, crash-looping.
- `palace.ingest.run_extractor` or `list_extractors` breaks existing
  `palace.memory.*` tools (regression).
- Neo4j schema drift after `:ExtractorHeartbeat` constraint / indexes cause
  migration issues.

## Pre-rollback snapshot

```bash
PRE_SHA=$(git rev-parse origin/develop)
echo "PRE_SHA=$PRE_SHA" | tee /tmp/extractor-framework-rollback.env
```

## Steps

### 1. Revert the merge commit on develop

```bash
MERGE_SHA=$(git log origin/develop --oneline | grep 'GIM-59' | head -1 | awk '{print $1}')
git fetch origin
git switch -c rollback/GIM-59-extractor-framework origin/develop
git revert -m 1 $MERGE_SHA
git push origin rollback/GIM-59-extractor-framework
```

Open PR `rollback: GIM-59 extractor framework` against develop and merge.

### 2. Clean up Neo4j schema

On the iMac neo4j container:

```cypher
// Drop heartbeat schema
DROP CONSTRAINT extractor_heartbeat_id IF EXISTS;
DROP INDEX extractor_heartbeat_group_id IF EXISTS;
DROP INDEX extractor_heartbeat_ts IF EXISTS;

// Delete any heartbeat nodes produced during testing
MATCH (n:ExtractorHeartbeat) DETACH DELETE n;

// Optional: delete extractor-source IngestRun records
MATCH (r:IngestRun) WHERE r.source STARTS WITH 'extractor.' DETACH DELETE r;
```

### 3. Rebuild palace-mcp container

```bash
# On iMac:
cd /Users/Shared/Ios/Gimle-Palace
git pull origin develop
docker compose --profile review up -d --build palace-mcp
docker compose --profile review logs palace-mcp --tail 50
# Verify ensure_schema runs cleanly; no ensure_extractors_schema log entries.
```

### 4. Smoke test

From Claude Code:
```
palace.memory.health()
```
Expected: response matches pre-migration shape (no extractor-related fields, if any).

## Post-rollback

- Record in `project_backlog.md`: slice rolled back with reason + pre/post SHAs.
- Investigate root cause; open followup slice to re-attempt with fix.
- Do not re-apply before root cause confirmed.

## Time budget

Steps 1-4: ~15-20 min total.
