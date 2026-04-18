"""Idempotent schema assertion. Called from FastAPI lifespan or before
first ingest. Safe to run repeatedly: constraints + indexes are
IF NOT EXISTS and the backfill is WHERE-IS-NULL guarded.
"""

from neo4j import AsyncDriver

from palace_mcp.memory.cypher import (
    BACKFILL_GROUP_ID,
    CREATE_CONSTRAINTS,
    CREATE_INDEXES,
)


async def ensure_schema(driver: AsyncDriver, *, default_group_id: str) -> None:
    async with driver.session() as session:
        for stmt in CREATE_CONSTRAINTS:
            await session.run(stmt)
        for stmt in CREATE_INDEXES:
            await session.run(stmt)
        await session.run(BACKFILL_GROUP_ID, default=default_group_id)


# Back-compat shim for any stray callers. Remove in the next slice.
async def ensure_constraints(driver: AsyncDriver) -> None:
    await ensure_schema(driver, default_group_id="project/gimle")
