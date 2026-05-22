# Neo4j APOC plugin + G0b require_group_id trigger deployment

Production deploy of APOC plugin (per GIM-765) + post-deploy trigger registration. Closes Layer 2 защита gap (Python `ScopeTaggedWriter` is Layer 1; APOC trigger is DB-side guard).

## Deploy steps

After this PR merges to develop and iMac pulls:

```bash
# 1. Pull latest develop on iMac
cd /Users/Shared/Ios/Gimle-Palace
git pull origin develop --ff-only

# 2. Recreate neo4j with APOC plugin
docker compose up -d --force-recreate neo4j

# 3. Wait healthy (~30 sec)
for i in 1 2 3 4 5 6 7 8 9; do
  s=$(docker inspect -f "{{.State.Health.Status}}" gimle-palace-neo4j-1 2>/dev/null)
  echo "  t+${i}: $s"
  [ "$s" = "healthy" ] && break
  sleep 5
done

# 4. Verify APOC loaded
PW=$(grep ^NEO4J_PASSWORD= /Users/Shared/Ios/Gimle-Palace/.env | cut -d= -f2)
docker exec gimle-palace-neo4j-1 cypher-shell -u neo4j -p "$PW" \
  "RETURN apoc.version()"
# expected: "5.26.0" or similar

# 5. Deploy require_group_id trigger
docker exec gimle-palace-neo4j-1 cypher-shell -u neo4j -p "$PW" "
CALL apoc.trigger.add('require_group_id',
  'UNWIND \$createdNodes AS n
   WITH n WHERE NOT (n:Bundle OR n:Project OR n:IngestRun OR n:IngestCheckpoint)
   CALL apoc.util.validate(
     n.group_id IS NULL,
     \"node label=%s cm_id=%s missing required group_id\",
     [labels(n)[0], coalesce(n.cm_id, \"<none>\")]
   ) YIELD value
   RETURN value',
  {phase:'before'}
)"
```

## Verification (must pass)

```bash
# 1. Trigger registered
docker exec gimle-palace-neo4j-1 cypher-shell -u neo4j -p "$PW" \
  "CALL apoc.trigger.show('neo4j') YIELD name, paused, selector RETURN name, paused, selector"
# expected: row for require_group_id, paused=false, selector={phase: "before"}

# 2. Raw write WITHOUT group_id REJECTED
docker exec gimle-palace-neo4j-1 cypher-shell -u neo4j -p "$PW" \
  "CREATE (n:Function {cm_id: 'verify-no-gid-' + toString(timestamp())}) RETURN n"
# expected: ERROR "node label=Function ... missing required group_id"

# 3. Raw write WITH group_id SUCCEEDS
docker exec gimle-palace-neo4j-1 cypher-shell -u neo4j -p "$PW" \
  "CREATE (n:Function {cm_id: 'verify-with-gid-' + toString(timestamp()), group_id: 'project/test'}) RETURN n.cm_id"
# expected: row returned; cleanup with DELETE

# 4. Bundle write SUCCEEDS without group_id (exempt label)
docker exec gimle-palace-neo4j-1 cypher-shell -u neo4j -p "$PW" \
  "CREATE (n:Bundle {cm_id: 'verify-bundle-' + toString(timestamp())}) RETURN n.cm_id"
# expected: row returned; cleanup with DELETE
```

## Rollback

If trigger blocks too aggressively or extractor regression:

```bash
docker exec gimle-palace-neo4j-1 cypher-shell -u neo4j -p "$PW" \
  "CALL apoc.trigger.drop('neo4j', 'require_group_id')"
```

This disables Layer 2; Layer 1 (`ScopeTaggedWriter`) continues protecting.

To completely roll back APOC:

```bash
# Revert this PR; pull; recreate neo4j without APOC env
git revert <merge-commit>
git push
docker compose up -d --force-recreate neo4j
```

## Re-deploy after container recreate

Trigger lives in Neo4j DB (persisted across restarts via `neo4j_data` volume). After APOC plugin is installed once (in image), trigger survives container recreate. Only re-register if `neo4j_data` volume is wiped.

## References

- GIM-765 — original APOC plugin task (validated on isolated `gimle-apoc` stack 2026-05-22)
- Phase 2 spec §G0b Layer 2 — defense-in-depth design rationale
- AgentSpec arxiv 2503.18666 — runtime enforcement model (applies at MCP tool layer, not DB; this is complementary)
