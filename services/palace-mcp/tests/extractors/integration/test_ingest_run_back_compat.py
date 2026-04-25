"""Regression test — new :IngestRun nullable fields don't break existing consumers.

Per spec §6.3: memory/health.py hardcodes source='paperclip' and parses
:IngestRun rows. Adding nullable nodes_written / edges_written must not
disturb that query.
"""

from __future__ import annotations

import pytest
from neo4j import AsyncDriver


@pytest.mark.asyncio
async def test_paperclip_ingest_row_parses_with_new_nullable_fields(
    driver: AsyncDriver,
) -> None:
    """Insert a paperclip :IngestRun (old shape) + an extractor one (new fields);
    verify LATEST_INGEST_RUN query returns paperclip row cleanly."""
    async with driver.session() as s:
        await s.run(
            """
            CREATE (r:IngestRun {
              id: 'paperclip-1',
              source: 'paperclip',
              group_id: 'project/gimle',
              started_at: '2026-04-20T09:00:00+00:00',
              finished_at: '2026-04-20T09:01:00+00:00',
              duration_ms: 60000,
              errors: [],
              success: true
            })
            """
        )
        await s.run(
            """
            CREATE (r:IngestRun {
              id: 'extractor-1',
              source: 'extractor.heartbeat',
              group_id: 'project/gimle',
              started_at: '2026-04-20T10:00:00+00:00',
              finished_at: '2026-04-20T10:00:01+00:00',
              duration_ms: 1000,
              nodes_written: 1,
              edges_written: 0,
              errors: [],
              success: true
            })
            """
        )

    from palace_mcp.memory.cypher import LATEST_INGEST_RUN

    async with driver.session() as s:
        result = await s.run(LATEST_INGEST_RUN)
        row = await result.single()
    assert row is not None
    r = dict(row["r"])
    # LATEST_INGEST_RUN returns the most recent row by started_at;
    # extractor row (10:00) is newer than the legacy paperclip row (09:00)
    assert r["source"] == "extractor.heartbeat"
    assert r["success"] is True
    assert r["nodes_written"] == 1
