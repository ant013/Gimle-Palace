"""Idempotent constraint assertion. Called from FastAPI lifespan or
before first ingest. Safe to run repeatedly (`IF NOT EXISTS` guard).
"""

from neo4j import AsyncDriver

from palace_mcp.memory.cypher import CREATE_CONSTRAINTS


async def ensure_constraints(driver: AsyncDriver) -> None:
    async with driver.session() as session:
        for stmt in CREATE_CONSTRAINTS:
            await session.run(stmt)
