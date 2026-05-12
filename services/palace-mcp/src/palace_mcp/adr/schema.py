"""ADR Neo4j schema — constraints + indexes for AdrDocument and AdrSection nodes."""

from __future__ import annotations

import logging

from neo4j import AsyncDriver

logger = logging.getLogger(__name__)

_CONSTRAINTS: tuple[str, ...] = (
    "CREATE CONSTRAINT adr_document_slug IF NOT EXISTS "
    "FOR (d:AdrDocument) REQUIRE d.slug IS UNIQUE",
    "CREATE CONSTRAINT adr_section_unique IF NOT EXISTS "
    "FOR (s:AdrSection) REQUIRE (s.doc_slug, s.section_name) IS NODE KEY",
)

_INDEXES: tuple[str, ...] = (
    "CREATE INDEX adr_document_status IF NOT EXISTS "
    "FOR (d:AdrDocument) ON (d.status)",
    "CREATE INDEX adr_section_name IF NOT EXISTS "
    "FOR (s:AdrSection) ON (s.section_name)",
)


async def ensure_adr_schema(driver: AsyncDriver) -> None:
    """Apply ADR constraints + indexes idempotently. Called from main.py lifespan."""
    async with driver.session() as session:
        for stmt in [*_CONSTRAINTS, *_INDEXES]:
            await session.run(stmt)
    logger.info("adr.schema.applied")
