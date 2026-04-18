"""Cypher query strings. Parameters use $name syntax — never string
interpolation. Keys are whitelisted in filters.py; values arrive as
named parameters only.
"""

# --- Constraints (idempotent MERGE-safe uniqueness) ---
CREATE_CONSTRAINTS = [
    "CREATE CONSTRAINT issue_id IF NOT EXISTS FOR (i:Issue) REQUIRE i.id IS UNIQUE",
    "CREATE CONSTRAINT comment_id IF NOT EXISTS FOR (c:Comment) REQUIRE c.id IS UNIQUE",
    "CREATE CONSTRAINT agent_id IF NOT EXISTS FOR (a:Agent) REQUIRE a.id IS UNIQUE",
    "CREATE CONSTRAINT project_slug IF NOT EXISTS FOR (p:Project) REQUIRE p.slug IS UNIQUE",
]

# --- Indexes (non-unique; speeds up group_id filter + GC cutoff) ---
CREATE_INDEXES = [
    "CREATE INDEX issue_group_id IF NOT EXISTS FOR (n:Issue) ON (n.group_id)",
    "CREATE INDEX comment_group_id IF NOT EXISTS FOR (n:Comment) ON (n.group_id)",
    "CREATE INDEX agent_group_id IF NOT EXISTS FOR (n:Agent) ON (n.group_id)",
    "CREATE INDEX ingest_run_group_id IF NOT EXISTS FOR (n:IngestRun) ON (n.group_id)",
    "CREATE INDEX project_group_id IF NOT EXISTS FOR (p:Project) ON (p.group_id)",
]

# --- Backfill: WHERE IS NULL guard makes this a no-op after first run ---
BACKFILL_GROUP_ID = """
CALL () {
    MATCH (n:Issue)     WHERE n.group_id IS NULL SET n.group_id = $default
}
CALL () {
    MATCH (n:Comment)   WHERE n.group_id IS NULL SET n.group_id = $default
}
CALL () {
    MATCH (n:Agent)     WHERE n.group_id IS NULL SET n.group_id = $default
}
CALL () {
    MATCH (n:IngestRun) WHERE n.group_id IS NULL SET n.group_id = $default
}
"""

# --- Upserts (idempotent — safe to re-run on transient failure retry) ---
UPSERT_AGENTS = """
UNWIND $batch AS row
MERGE (a:Agent {id: row.id})
SET a.group_id             = $group_id,
    a.name                 = row.name,
    a.url_key              = row.url_key,
    a.role                 = row.role,
    a.source               = 'paperclip',
    a.source_created_at    = row.source_created_at,
    a.source_updated_at    = row.source_updated_at,
    a.palace_last_seen_at  = row.palace_last_seen_at
"""

UPSERT_ISSUES = """
UNWIND $batch AS row
MERGE (i:Issue {id: row.id})
SET i.group_id             = $group_id,
    i.key                  = row.key,
    i.title                = row.title,
    i.description          = row.description,
    i.status               = row.status,
    i.source               = 'paperclip',
    i.source_created_at    = row.source_created_at,
    i.source_updated_at    = row.source_updated_at,
    i.palace_last_seen_at  = row.palace_last_seen_at
WITH i, row
OPTIONAL MATCH (i)-[old:ASSIGNED_TO]->()
DELETE old
WITH i, row
WHERE row.assignee_agent_id IS NOT NULL
MATCH (a:Agent {id: row.assignee_agent_id})
MERGE (i)-[:ASSIGNED_TO]->(a)
"""

UPSERT_COMMENTS = """
UNWIND $batch AS row
MERGE (c:Comment {id: row.id})
SET c.group_id             = $group_id,
    c.body                 = row.body,
    c.source               = 'paperclip',
    c.source_created_at    = row.source_created_at,
    c.source_updated_at    = row.source_updated_at,
    c.palace_last_seen_at  = row.palace_last_seen_at
WITH c, row
OPTIONAL MATCH (c)-[oldOn:ON]->()
DELETE oldOn
WITH c, row
MATCH (i:Issue {id: row.issue_id})
MERGE (c)-[:ON]->(i)
WITH c, row
OPTIONAL MATCH (c)-[oldAuth:AUTHORED_BY]->()
DELETE oldAuth
WITH c, row
WHERE row.author_agent_id IS NOT NULL
MATCH (a:Agent {id: row.author_agent_id})
MERGE (c)-[:AUTHORED_BY]->(a)
"""

# --- GC (run only after clean-success upserts) ---
# {label} is substituted by a closed tuple ("Issue", "Comment", "Agent") in runner.py,
# NOT user input. Labels are hardcoded; this is intentional.
GC_BY_LABEL = """
MATCH (n:{label})
WHERE n.source = 'paperclip'
  AND n.group_id = $group_id
  AND n.palace_last_seen_at < $cutoff
DETACH DELETE n
"""

# --- IngestRun meta-node (read by palace.memory.health) ---
CREATE_INGEST_RUN = """
CREATE (r:IngestRun {
    id: $id,
    group_id: $group_id,
    source: $source,
    started_at: $started_at,
    finished_at: null,
    duration_ms: null,
    errors: []
})
"""

FINALIZE_INGEST_RUN = """
MATCH (r:IngestRun {id: $id})
SET r.finished_at = $finished_at,
    r.duration_ms = $duration_ms,
    r.errors      = $errors
"""

LATEST_INGEST_RUN = """
MATCH (r:IngestRun {source: $source})
RETURN r
ORDER BY r.started_at DESC
LIMIT 1
"""

LATEST_INGEST_RUN_FOR_GROUP = """
MATCH (r:IngestRun {source: $source})
WHERE r.group_id = $group_id
RETURN r
ORDER BY r.started_at DESC
LIMIT 1
"""

# --- Project DDL (read/write) ---
UPSERT_PROJECT = """
MERGE (p:Project {slug: $slug})
SET p.group_id            = 'project/' + $slug,
    p.name                = $name,
    p.tags                = $tags,
    p.language            = $language,
    p.framework           = $framework,
    p.repo_url            = $repo_url,
    p.source              = 'paperclip',
    p.source_created_at   = coalesce(p.source_created_at, $now),
    p.source_updated_at   = $now
RETURN p
"""

LIST_PROJECT_SLUGS = "MATCH (p:Project) RETURN p.slug AS slug ORDER BY slug"

GET_PROJECT = """
MATCH (p:Project {slug: $slug})
RETURN p
"""

PROJECT_ENTITY_COUNTS = """
MATCH (n)
WHERE (n:Issue OR n:Comment OR n:Agent OR n:IngestRun)
  AND n.group_id = $group_id
RETURN labels(n) AS labels, count(n) AS c
"""

UNREGISTERED_GROUP_IDS = """
MATCH (n)
WHERE (n:Issue OR n:Comment OR n:Agent OR n:IngestRun)
WITH DISTINCT n.group_id AS g
WHERE g IS NOT NULL AND NOT EXISTS {
    MATCH (p:Project) WHERE p.group_id = g
}
RETURN collect(g) AS unregistered
"""

PROJECT_LAST_INGEST = """
MATCH (r:IngestRun {source: $source})
WHERE r.group_id = $group_id
RETURN r
ORDER BY r.started_at DESC
LIMIT 1
"""

ENTITY_COUNTS_BY_PROJECT = """
MATCH (p:Project)
CALL (p) {
    MATCH (n:Issue) WHERE n.group_id = p.group_id RETURN 'Issue' AS type, count(n) AS cnt
    UNION ALL
    MATCH (n:Comment) WHERE n.group_id = p.group_id RETURN 'Comment' AS type, count(n) AS cnt
    UNION ALL
    MATCH (n:Agent) WHERE n.group_id = p.group_id RETURN 'Agent' AS type, count(n) AS cnt
}
RETURN p.slug AS slug, type, cnt
"""

# --- Entity counts (health) ---
ENTITY_COUNTS = """
CALL () {
    MATCH (n:Issue) RETURN 'Issue' AS type, count(n) AS count
    UNION ALL
    MATCH (n:Comment) RETURN 'Comment' AS type, count(n) AS count
    UNION ALL
    MATCH (n:Agent) RETURN 'Agent' AS type, count(n) AS count
}
RETURN type, count
"""
