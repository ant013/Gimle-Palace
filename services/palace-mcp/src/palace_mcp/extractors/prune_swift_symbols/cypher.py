"""Cypher constants for prune_swift_symbols."""

PRECHECK_STALE = """
MATCH (n:Symbol {project_id: $project_id})
WHERE n.last_seen_in_run_id IS NOT NULL
  AND n.last_seen_in_run_id <> $companion_run_id
  AND NOT n:Deprecated
WITH count(n) AS stale_symbols

MATCH (n:File {project_id: $project_id})
WHERE n.last_seen_in_run_id IS NOT NULL
  AND n.last_seen_in_run_id <> $companion_run_id
  AND NOT n:Deprecated
WITH stale_symbols, count(n) AS stale_files

MATCH (m {project_id: $project_id})
WHERE (m:Symbol OR m:File)
  AND NOT m:Deprecated
WITH stale_symbols + stale_files AS stale_total, count(m) AS overall_total
RETURN stale_total, overall_total
""".strip()

APPLY_DEPRECATION_BATCH = """
MATCH (n {project_id: $project_id})
WHERE (n:File OR n:Symbol)
  AND n.last_seen_in_run_id IS NOT NULL
  AND n.last_seen_in_run_id <> $companion_run_id
  AND NOT n:Deprecated
WITH n LIMIT $batch_size
SET n:Deprecated,
    n.deprecated_at = datetime(),
    n.deprecated_in_commit = $head_sha,
    n.last_seen_in_commit = COALESCE(n.last_seen_in_commit, $head_sha)
RETURN count(n) AS batch_count,
       sum(CASE WHEN n:File THEN 1 ELSE 0 END) AS batch_files,
       sum(CASE WHEN n:Symbol THEN 1 ELSE 0 END) AS batch_symbols
""".strip()

CREATE_DEPRECATION_EVENT = """
CREATE (e:DeprecationEvent {
    event_id: randomUUID(),
    project_id: $project_id,
    action: 'deprecate',
    run_id: $run_id,
    companion_run_id: $companion_run_id,
    head_sha: $head_sha,
    deprecated_count: $total_deprecated,
    deprecated_files: $total_files,
    deprecated_symbols: $total_symbols,
    threshold_ratio_effective: $threshold_ratio_effective,
    occurred_at: datetime()
})
RETURN e.event_id AS event_id
""".strip()
