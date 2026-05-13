"""Cypher query strings. Parameters use $name syntax — never string
interpolation. Keys are whitelisted in filters.py; values arrive as
named parameters only.
"""

# --- Constraints (idempotent MERGE-safe uniqueness) ---
# Graphiti entity schema is managed by graphiti_core.build_indices_and_constraints().
# Only palace-mcp-specific node types need DDL here.
CREATE_CONSTRAINTS = [
    "CREATE CONSTRAINT project_slug IF NOT EXISTS FOR (p:Project) REQUIRE p.slug IS UNIQUE",
    # GIM-182: bundle name uniqueness
    "CREATE CONSTRAINT bundle_name IF NOT EXISTS FOR (b:Bundle) REQUIRE b.name IS UNIQUE",
]

# --- Indexes (non-unique; speeds up group_id filter) ---
CREATE_INDEXES = [
    "CREATE INDEX project_group_id IF NOT EXISTS FOR (p:Project) ON (p.group_id)",
    # GIM-182: bundle group_id filter
    "CREATE INDEX bundle_group_id IF NOT EXISTS FOR (b:Bundle) ON (b.group_id)",
]

# --- Bundle DDL (GIM-182) ---

CHECK_PROJECT_SLUG_EXISTS = """
MATCH (p:Project {slug: $slug})
RETURN p.slug AS slug
LIMIT 1
"""

CHECK_BUNDLE_NAME_EXISTS = """
MATCH (b:Bundle {name: $name})
RETURN b.name AS b_name
LIMIT 1
"""

UPSERT_BUNDLE = """
MERGE (b:Bundle {name: $name})
ON CREATE SET
    b.group_id    = 'bundle/' + $name,
    b.description = $description,
    b.created_at  = $created_at
RETURN b
"""

GET_BUNDLE_MEMBERS = """
MATCH (b:Bundle {name: $bundle})-[c:CONTAINS]->(p:Project)
RETURN p.slug AS slug, c.tier AS tier, c.added_at AS added_at
ORDER BY p.slug ASC
"""

GET_BUNDLE_MEMBERS_WITH_INGEST = """
MATCH (b:Bundle {name: $bundle})-[c:CONTAINS]->(p:Project)
OPTIONAL MATCH (r:IngestRun)
    WHERE r.group_id = ('project/' + p.slug)
    AND r.finished_at IS NOT NULL
WITH p, c, r
ORDER BY r.started_at DESC
WITH p, c, collect(r)[0] AS latest_run
RETURN
    p.slug AS slug,
    c.tier AS tier,
    c.added_at AS added_at,
    latest_run.finished_at AS last_run_completed_at,
    CASE
        WHEN latest_run IS NULL THEN null
        WHEN size(latest_run.errors) = 0 THEN true
        ELSE false
    END AS last_run_ok
ORDER BY p.slug ASC
"""

MERGE_BUNDLE_CONTAINS_PROJECT = """
MATCH (b:Bundle {name: $bundle})
MATCH (p:Project {slug: $project})
MERGE (b)-[c:CONTAINS {tier: $tier}]->(p)
ON CREATE SET c.added_at = $added_at
"""

COUNT_BUNDLE_MEMBERS = """
MATCH (b:Bundle {name: $name})-[:CONTAINS]->(:Project)
RETURN count(*) AS member_count
"""

DELETE_BUNDLE_CASCADE = """
MATCH (b:Bundle {name: $name})
DETACH DELETE b
"""

DELETE_BUNDLE_NO_CASCADE = """
MATCH (b:Bundle {name: $name})
DELETE b
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
MATCH (r:IngestRun)
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
    p.parent_mount        = $parent_mount,
    p.relative_path       = $relative_path,
    p.language_profile    = coalesce($language_profile, p.language_profile),
    p.source              = 'paperclip',
    p.source_created_at   = coalesce(p.source_created_at, $now),
    p.source_updated_at   = $now
RETURN p
"""

LIST_PROJECT_SLUGS = "MATCH (p:Project) RETURN p.name AS slug ORDER BY slug"

LIST_PROJECTS = "MATCH (p:Project) RETURN p ORDER BY p.slug"

GET_PROJECT = """
MATCH (p:Project {slug: $slug})
RETURN p
"""

PROJECT_ENTITY_COUNTS = """
MATCH (n)
WHERE (n:Episode OR n:Iteration OR n:Decision OR n:IterationNote OR n:Finding
    OR n:Module OR n:File OR n:Symbol OR n:APIEndpoint OR n:Model
    OR n:Repository OR n:ExternalLib OR n:Trace)
  AND n.group_id = $group_id
RETURN labels(n) AS labels, count(n) AS c
"""

UNREGISTERED_GROUP_IDS = """
MATCH (n)
WHERE (n:Episode OR n:Iteration OR n:Decision OR n:IterationNote OR n:Finding
    OR n:Module OR n:File OR n:Symbol OR n:APIEndpoint OR n:Model
    OR n:Repository OR n:ExternalLib OR n:Trace)
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
    MATCH (n:Episode)      WHERE n.group_id = p.group_id RETURN 'Episode'      AS type, count(n) AS cnt
    UNION ALL
    MATCH (n:Iteration)    WHERE n.group_id = p.group_id RETURN 'Iteration'    AS type, count(n) AS cnt
    UNION ALL
    MATCH (n:Decision)     WHERE n.group_id = p.group_id RETURN 'Decision'     AS type, count(n) AS cnt
    UNION ALL
    MATCH (n:IterationNote) WHERE n.group_id = p.group_id RETURN 'IterationNote' AS type, count(n) AS cnt
    UNION ALL
    MATCH (n:Finding)      WHERE n.group_id = p.group_id RETURN 'Finding'      AS type, count(n) AS cnt
    UNION ALL
    MATCH (n:Module)       WHERE n.group_id = p.group_id RETURN 'Module'       AS type, count(n) AS cnt
    UNION ALL
    MATCH (n:File)         WHERE n.group_id = p.group_id RETURN 'File'         AS type, count(n) AS cnt
    UNION ALL
    MATCH (n:Symbol)       WHERE n.group_id = p.group_id RETURN 'Symbol'       AS type, count(n) AS cnt
    UNION ALL
    MATCH (n:APIEndpoint)  WHERE n.group_id = p.group_id RETURN 'APIEndpoint'  AS type, count(n) AS cnt
    UNION ALL
    MATCH (n:Model)        WHERE n.group_id = p.group_id RETURN 'Model'        AS type, count(n) AS cnt
    UNION ALL
    MATCH (n:Repository)   WHERE n.group_id = p.group_id RETURN 'Repository'   AS type, count(n) AS cnt
    UNION ALL
    MATCH (n:ExternalLib)  WHERE n.group_id = p.group_id RETURN 'ExternalLib'  AS type, count(n) AS cnt
    UNION ALL
    MATCH (n:Trace)        WHERE n.group_id = p.group_id RETURN 'Trace'        AS type, count(n) AS cnt
}
RETURN p.name AS slug, type, cnt
"""

# --- Entity counts (health) ---
ENTITY_COUNTS = """
CALL () {
    MATCH (n:Episode)      RETURN 'Episode'      AS type, count(n) AS count
    UNION ALL
    MATCH (n:Iteration)    RETURN 'Iteration'    AS type, count(n) AS count
    UNION ALL
    MATCH (n:Decision)     RETURN 'Decision'     AS type, count(n) AS count
    UNION ALL
    MATCH (n:IterationNote) RETURN 'IterationNote' AS type, count(n) AS count
    UNION ALL
    MATCH (n:Finding)      RETURN 'Finding'      AS type, count(n) AS count
    UNION ALL
    MATCH (n:Module)       RETURN 'Module'       AS type, count(n) AS count
    UNION ALL
    MATCH (n:File)         RETURN 'File'         AS type, count(n) AS count
    UNION ALL
    MATCH (n:Symbol)       RETURN 'Symbol'       AS type, count(n) AS count
    UNION ALL
    MATCH (n:APIEndpoint)  RETURN 'APIEndpoint'  AS type, count(n) AS count
    UNION ALL
    MATCH (n:Model)        RETURN 'Model'        AS type, count(n) AS count
    UNION ALL
    MATCH (n:Repository)   RETURN 'Repository'   AS type, count(n) AS count
    UNION ALL
    MATCH (n:ExternalLib)  RETURN 'ExternalLib'  AS type, count(n) AS count
    UNION ALL
    MATCH (n:Trace)        RETURN 'Trace'        AS type, count(n) AS count
}
RETURN type, count
"""
