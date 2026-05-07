"""Schema bootstrap for code_ownership extractor — idempotent constraints."""

from __future__ import annotations

from neo4j import AsyncDriver

_CONSTRAINTS = [
    """
    CREATE CONSTRAINT ownership_checkpoint_unique IF NOT EXISTS
    FOR (c:OwnershipCheckpoint) REQUIRE c.project_id IS UNIQUE
    """,
    """
    CREATE CONSTRAINT ownership_file_state_unique IF NOT EXISTS
    FOR (s:OwnershipFileState)
    REQUIRE (s.project_id, s.path) IS UNIQUE
    """,
]


async def ensure_ownership_schema(driver: AsyncDriver) -> None:
    """Idempotent schema bootstrap. Safe to call on every run.

    NO relationship-property index on :OWNED_BY.weight (rev2 design):
    find_owners traverses from :File PK; index would only help full-scans.
    """
    async with driver.session() as session:
        for stmt in _CONSTRAINTS:
            await session.run(stmt)
