#!/usr/bin/env python3
"""Migrate :Symbol nodes: dedup duplicates + add unique constraint.

Run once against an existing Neo4j instance before starting palace-mcp
with the symbol_unique constraint enabled.

Usage:
    NEO4J_URI=bolt://localhost:7687 \\
    NEO4J_USER=neo4j \\
    NEO4J_PASSWORD=secret \\
    uv run scripts/migrate_symbol_constraint.py
"""

from __future__ import annotations

import asyncio
import logging
import os

from neo4j import AsyncGraphDatabase

logger = logging.getLogger(__name__)

NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "password")

_DEDUP_BATCH = """
MATCH (a:Symbol), (b:Symbol)
WHERE a.qualified_name = b.qualified_name
  AND a.group_id = b.group_id
  AND id(a) < id(b)
WITH b LIMIT 500
DETACH DELETE b
RETURN count(b) AS deleted
"""

_DROP_OLD_INDEX = "DROP INDEX symbol_qname_group_lookup IF EXISTS"

_CREATE_CONSTRAINT = (
    "CREATE CONSTRAINT symbol_unique IF NOT EXISTS "
    "FOR (s:Symbol) REQUIRE (s.qualified_name, s.group_id) IS UNIQUE"
)


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    driver = AsyncGraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        total_deleted = 0
        async with driver.session() as session:
            while True:
                result = await session.run(_DEDUP_BATCH)
                record = await result.single()
                batch_deleted = int(record["deleted"]) if record else 0
                total_deleted += batch_deleted
                logger.info(
                    "Dedup batch: removed %d duplicate Symbol nodes", batch_deleted
                )
                if batch_deleted == 0:
                    break

            logger.info("Dedup complete: %d total duplicates removed", total_deleted)

            await session.run(_DROP_OLD_INDEX)
            logger.info("Dropped index symbol_qname_group_lookup (if existed)")

            await session.run(_CREATE_CONSTRAINT)
            logger.info("Created constraint symbol_unique")

    finally:
        await driver.close()

    logger.info("Migration complete")


if __name__ == "__main__":
    asyncio.run(main())
