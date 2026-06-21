"""Idempotent schema assertion. Called from FastAPI lifespan or before
first ingest. Safe to run repeatedly: constraints + indexes are
IF NOT EXISTS guarded.
"""

from __future__ import annotations

from datetime import datetime, timezone

from neo4j import AsyncDriver

from palace_mcp.memory.cypher import (
    BOOTSTRAP_PROJECT,
    CREATE_CONSTRAINTS,
    CREATE_INDEXES,
    UNREGISTERED_GROUP_IDS,
)


def _bootstrap_name_for(slug: str) -> str:
    return slug.replace("-", " ").replace("_", " ").title() + " (bootstrap)"


class SchemaIntegrityError(RuntimeError):
    pass


PRUNE_SWIFT_SYMBOLS_CONSTRAINTS = [
    "CREATE CONSTRAINT deprecation_event_id IF NOT EXISTS "
    "FOR (e:DeprecationEvent) REQUIRE e.event_id IS UNIQUE",
]

PRUNE_SWIFT_SYMBOLS_INDEXES = [
    "CREATE INDEX symbol_last_seen_in_run IF NOT EXISTS "
    "FOR (s:Symbol) ON (s.project_id, s.last_seen_in_run_id)",
    "CREATE INDEX file_last_seen_in_run IF NOT EXISTS "
    "FOR (f:File) ON (f.project_id, f.last_seen_in_run_id)",
    "CREATE INDEX deprecation_event_project_time IF NOT EXISTS "
    "FOR (e:DeprecationEvent) ON (e.project_id, e.occurred_at)",
]


async def ensure_schema(driver: AsyncDriver, *, default_group_id: str) -> None:
    from palace_mcp.memory.projects import derive_cm_project_name

    default_slug = default_group_id.removeprefix("project/")
    now = datetime.now(timezone.utc).isoformat()

    async with driver.session() as session:
        for stmt in [*CREATE_CONSTRAINTS, *PRUNE_SWIFT_SYMBOLS_CONSTRAINTS]:
            await session.run(stmt)
        for stmt in [*CREATE_INDEXES, *PRUNE_SWIFT_SYMBOLS_INDEXES]:
            await session.run(stmt)
        await session.run(
            BOOTSTRAP_PROJECT,
            slug=default_slug,
            cm_project_name=derive_cm_project_name(slug=default_slug),
            name=_bootstrap_name_for(default_slug),
            tags=["bootstrap"],
            language=None,
            framework=None,
            repo_url=None,
            parent_mount=None,
            relative_path=None,
            language_profile=None,
            expected_profile=False,
            now=now,
        )

    async with driver.session() as session:
        result = await session.run(UNREGISTERED_GROUP_IDS)
        row = await result.single()
        unregistered = row["unregistered"] if row else []

    if unregistered:
        raise SchemaIntegrityError(
            f"group_ids present on entities but no matching :Project: "
            f"{sorted(unregistered)}. Register via palace.memory.register_project."
        )
