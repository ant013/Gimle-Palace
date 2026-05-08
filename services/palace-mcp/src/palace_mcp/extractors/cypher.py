"""Cypher statements for extractor :IngestRun lifecycle.

Isolated from memory/cypher.py — extractor concerns stay in extractor
package. The new nullable fields (nodes_written, edges_written) are
additive on :IngestRun; existing paperclip ingest rows parse unchanged
(NULL for these fields).
"""

from __future__ import annotations

CREATE_INGEST_RUN = """
CREATE (r:IngestRun {
  id: $id,
  source: $source,
  group_id: $group_id,
  extractor_name: $extractor_name,
  project: $project,
  started_at: $started_at,
  finished_at: null,
  duration_ms: null,
  nodes_written: null,
  edges_written: null,
  errors: [],
  success: null
})
RETURN r
"""

FINALIZE_INGEST_RUN = """
MATCH (r:IngestRun {id: $id})
SET r.finished_at  = $finished_at,
    r.duration_ms  = $duration_ms,
    r.nodes_written = $nodes_written,
    r.edges_written = $edges_written,
    r.errors       = $errors,
    r.success      = $success
RETURN r
"""
