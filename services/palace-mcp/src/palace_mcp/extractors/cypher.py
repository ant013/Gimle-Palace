"""Cypher statements for extractor :IngestRun lifecycle.

Isolated from memory/cypher.py — extractor concerns stay in extractor
package. The new nullable fields (nodes_written, edges_written) are
additive on :IngestRun; existing paperclip ingest rows parse unchanged
(NULL for these fields).
"""

from __future__ import annotations

CREATE_INGEST_RUN = """
MERGE (r:IngestRun {run_id: $run_id})
ON CREATE SET
  r.source = $source,
  r.group_id = $group_id,
  r.extractor_name = $extractor_name,
  r.project = $project,
  r.started_at = $started_at,
  r.finished_at = null,
  r.duration_ms = null,
  r.nodes_written = null,
  r.edges_written = null,
  r.errors = [],
  r.success = null
ON MATCH SET
  r.extractor_name = COALESCE(r.extractor_name, $extractor_name),
  r.project = COALESCE(r.project, $project)
RETURN r
"""

FINALIZE_INGEST_RUN = """
MATCH (r:IngestRun {run_id: $run_id})
SET r.finished_at  = $finished_at,
    r.duration_ms  = $duration_ms,
    r.nodes_written = $nodes_written,
    r.edges_written = $edges_written,
    r.errors       = $errors,
    r.success      = $success
RETURN r
"""
