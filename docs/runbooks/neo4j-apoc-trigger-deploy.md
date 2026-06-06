# Neo4j APOC Trigger Deploy

Use this runbook to install APOC Core into the review stack, enable Neo4j 5
trigger support, verify `require_group_id`, and re-apply the setup after
container recreation.

## Preconditions

- `.env` contains the current `NEO4J_PASSWORD`.
- Run commands from the repo root.
- If the default `gimle-palace` stack already has a persisted `neo4j_data`
  volume with a different password, do not wipe that shared volume blindly.
  Use the isolated project flow in the last section.

## Deploy

```bash
docker compose --profile review up -d neo4j palace-mcp
```

## Manual verification

```bash
PW="$(grep '^NEO4J_PASSWORD=' .env | cut -d= -f2-)"
docker compose exec neo4j cypher-shell -u neo4j -p "$PW" \
  "RETURN apoc.version() AS apoc_version"
docker compose exec neo4j cypher-shell -d system -u neo4j -p "$PW" \
  "CALL apoc.trigger.show('neo4j') YIELD name, paused, selector \
   RETURN name, paused, selector"
docker compose exec neo4j cypher-shell -d system -u neo4j -p "$PW" \
  "CALL apoc.trigger.list()"
```

The first command must return a version string. In the second command, find the
`require_group_id` row and verify `paused = false` and
`selector = {phase: before}`.
`apoc.trigger.list()` is optional on Neo4j 5; if it is unavailable, rely on
`apoc.trigger.show('neo4j')`.

Negative write:

```bash
docker compose exec neo4j cypher-shell -u neo4j -p "$PW" \
  "CREATE (:Function {cm_id: 'test-no-gid'})"
```

This must fail with `missing required group_id`.

Positive writes:

```bash
docker compose exec neo4j cypher-shell -u neo4j -p "$PW" \
  "CREATE (:Function {cm_id: 'test-with-gid', group_id: 'project/test'})"
docker compose exec neo4j cypher-shell -u neo4j -p "$PW" \
  "CREATE (:Bundle {slug: 'bundle-test'})"
docker compose exec neo4j cypher-shell -u neo4j -p "$PW" \
  "MATCH (n) WHERE n.cm_id IN ['test-with-gid', 'test-no-gid'] DETACH DELETE n"
docker compose exec neo4j cypher-shell -u neo4j -p "$PW" \
  "MATCH (n:Bundle {slug: 'bundle-test'}) DETACH DELETE n"
```

Ingest smoke:

```bash
bash paperclips/scripts/ingest_swift_kit.sh bitcoin-core
```

For the isolated stack, use this variant to avoid hitting the default compose
project ports:

```bash
COMPOSE_PROJECT_NAME=gimle-apoc \
COMPOSE_OVERRIDE_FILE=/tmp/gimle-apoc-override.yml \
PALACE_MCP_URL=http://localhost:18080/mcp \
bash paperclips/scripts/ingest_swift_kit.sh bitcoin-core
```

## Recreate / redeploy

If the Neo4j container is recreated, re-run the standard deploy and verification
steps:

```bash
docker compose --profile review up -d --force-recreate neo4j palace-mcp
```

APOC is installed at container start via `NEO4J_PLUGINS=["apoc"]`. The trigger
is re-installed by `palace_mcp.memory.constraints.ensure_schema()` when the
service boots against a clean database.

## Isolated fresh-volume flow

Use this when the default stack's persisted `neo4j_data` volume was created with
an older password and `palace-mcp` hits `Neo.ClientError.Security.AuthenticationRateLimit`.

```bash
PW="$(grep '^NEO4J_PASSWORD=' .env | cut -d= -f2-)"

cat > /tmp/gimle-apoc-override.yml <<'YAML'
services:
  neo4j:
    ports:
      - "17687:7687"
  palace-mcp:
    ports:
      - "18080:8000"
YAML

docker compose -p gimle-apoc \
  --env-file .env \
  -f docker-compose.yml \
  -f /tmp/gimle-apoc-override.yml \
  --profile review up -d neo4j palace-mcp

docker compose -p gimle-apoc \
  --env-file .env \
  -f docker-compose.yml \
  -f /tmp/gimle-apoc-override.yml \
  exec neo4j cypher-shell -u neo4j -p "$PW" \
  "RETURN apoc.version() AS apoc_version"
```

Point manual host-side probes at `localhost:17687` and the MCP URL at
`http://localhost:18080/mcp` for that isolated stack.
