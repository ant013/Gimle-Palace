"""Aggregate + apply constraints/indexes declared by registered extractors.

Called in main.py lifespan after memory.constraints.ensure_schema().
Idempotent — extractor declarations use IF NOT EXISTS.
"""

from __future__ import annotations

import logging

from neo4j import AsyncDriver

from palace_mcp.extractors import registry

logger = logging.getLogger(__name__)


async def ensure_extractors_schema(driver: AsyncDriver) -> None:
    """Apply all declared constraints + indexes from registered extractors."""
    statements: list[str] = []
    for extractor in registry.list_all():
        statements.extend(extractor.constraints)
        statements.extend(extractor.indexes)
    if not statements:
        logger.info("extractors.schema.noop", extra={"registered": 0})
        return
    async with driver.session() as session:
        for stmt in statements:
            await session.run(stmt)
    logger.info(
        "extractors.schema.applied",
        extra={"statement_count": len(statements)},
    )
