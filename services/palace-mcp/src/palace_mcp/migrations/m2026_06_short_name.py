"""Back-fill :Symbol.short_name for human-name resolution (GIM-1099, PALACE-S1F2).

Run via:
    python services/palace-mcp/scripts/migrate_short_name.py
"""

from __future__ import annotations

import asyncio
import logging
import os

from neo4j import AsyncDriver

from palace_mcp.extractors.scip_parser import decode_scip_short_name

_FETCH_BATCH = """
MATCH (s:Symbol)
WHERE s.short_name IS NULL OR trim(toString(s.short_name)) = ''
RETURN s.uuid AS uuid,
       coalesce(s.qualified_name, '') AS qualified_name,
       coalesce(s.name, '') AS name
ORDER BY s.uuid
LIMIT $limit
"""

_APPLY_BATCH = """
UNWIND $rows AS row
MATCH (s:Symbol {uuid: row.uuid})
SET s.short_name = row.short_name
RETURN count(*) AS updated
"""

_logger = logging.getLogger(__name__)


def short_name_for_symbol(qualified_name: str, name: str) -> str:
    short_name = decode_scip_short_name(qualified_name)
    if short_name:
        return short_name
    if name.strip():
        return name.strip()
    return qualified_name.strip()


async def run_migration(driver: AsyncDriver, *, batch_size: int = 1000) -> int:
    """Back-fill missing short_name values in bounded batches."""
    migrated = 0
    while True:
        async with driver.session() as session:
            fetch_result = await session.run(_FETCH_BATCH, limit=batch_size)
            rows = [dict(record) async for record in fetch_result]
        if not rows:
            break

        updates = [
            {
                "uuid": row["uuid"],
                "short_name": short_name_for_symbol(
                    row.get("qualified_name", ""), row.get("name", "")
                ),
            }
            for row in rows
        ]

        async with driver.session() as session:
            update_result = await session.run(_APPLY_BATCH, rows=updates)
            record = await update_result.single()
        migrated += int(record["updated"]) if record else 0
        _logger.info("m2026_06_short_name: migrated %d rows so far", migrated)

    return migrated


def main() -> None:
    from neo4j import AsyncGraphDatabase

    neo4j_uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    neo4j_user = os.environ.get("NEO4J_USER", "neo4j")
    neo4j_password = os.environ.get("NEO4J_PASSWORD", "changeme")

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    async def _run() -> None:
        driver = AsyncGraphDatabase.driver(
            neo4j_uri, auth=(neo4j_user, neo4j_password)
        )
        try:
            migrated = await run_migration(driver)
            print(f"migrated {migrated} rows")
        finally:
            await driver.close()

    asyncio.run(_run())


if __name__ == "__main__":
    main()
