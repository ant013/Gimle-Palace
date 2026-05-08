"""Back-fill extractor_name + project on legacy Path A :IngestRun nodes (GIM-228, S0.1).

Path A (runner.py) historically omitted the canonical fields that Path B
(foundation/checkpoint.py) already writes.  This migration fills the gap
so that audit-discovery Cypher can query uniformly on
(extractor_name, project) regardless of which path created the node.

Idempotent: the WHERE clause excludes rows that already have extractor_name,
so repeated runs produce 0 net writes after the first successful execution.

Run via:
    docker compose exec palace-mcp python -m palace_mcp.migrations.m2026_05_unify_ingest_run
"""

from __future__ import annotations

import asyncio
import logging
import os

from neo4j import AsyncDriver

_MIGRATION_CYPHER = """
MATCH (r:IngestRun)
WHERE r.extractor_name IS NULL
  AND r.source STARTS WITH 'extractor.'
CALL {
  WITH r
  SET r.extractor_name = substring(r.source, 10),
      r.project = CASE
        WHEN r.group_id STARTS WITH 'project/'
        THEN substring(r.group_id, 8)
        ELSE r.group_id
      END
} IN TRANSACTIONS OF 100 ROWS
RETURN count(*) AS migrated
"""

_logger = logging.getLogger(__name__)


async def run_migration(driver: AsyncDriver) -> int:
    """Back-fill Path A :IngestRun nodes with canonical fields.

    Returns the number of rows migrated (0 on subsequent idempotent runs).
    """
    async with driver.session() as session:
        result = await session.run(_MIGRATION_CYPHER)
        record = await result.single()
    migrated = int(record["migrated"]) if record else 0
    _logger.info("m2026_05_unify_ingest_run: migrated %d rows", migrated)
    return migrated


def main() -> None:
    from neo4j import AsyncGraphDatabase

    neo4j_uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    neo4j_user = os.environ.get("NEO4J_USER", "neo4j")
    neo4j_password = os.environ.get("NEO4J_PASSWORD", "changeme")

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    async def _run() -> None:
        drv = AsyncGraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))
        try:
            migrated = await run_migration(drv)
            print(f"migrated {migrated} rows")
        finally:
            await drv.close()

    asyncio.run(_run())


if __name__ == "__main__":
    main()
