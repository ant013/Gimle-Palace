"""Idempotent schema assertion. Called from FastAPI lifespan or before
first ingest. Safe to run repeatedly: constraints + indexes are
IF NOT EXISTS guarded.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

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


GROUP_ID_TRIGGER_DATABASE = "neo4j"
GROUP_ID_TRIGGER_NAME = "require_group_id"
GROUP_ID_TRIGGER_QUERY = """
UNWIND $createdNodes AS n
WITH n
WHERE NOT (n:Bundle OR n:Project OR n:IngestRun OR n:IngestCheckpoint OR n:Author)
  AND apoc.util.validatePredicate(
    n.group_id IS NULL,
    "node label=%s cm_id=%s missing required group_id",
    [labels(n)[0], coalesce(n.cm_id, "<none>")]
  )
RETURN count(*) AS checked
""".strip()
GROUP_ID_TRIGGER_SELECTOR = {"phase": "before"}


def _group_id_trigger_matches(row: dict[str, Any]) -> bool:
    return bool(
        row["query"] == GROUP_ID_TRIGGER_QUERY
        and row["selector"] == GROUP_ID_TRIGGER_SELECTOR
        and row["params"] == {}
    )


async def _ensure_group_id_trigger(driver: AsyncDriver) -> None:
    async with driver.session(database="system") as session:
        result = await session.run(
            "CALL apoc.trigger.show($database_name) "
            "YIELD name, query, selector, params, installed, paused "
            "RETURN query AS query, selector AS selector, "
            "params AS params, paused AS paused, name AS name",
            database_name=GROUP_ID_TRIGGER_DATABASE,
        )
        rows = [dict(record) async for record in result]
        row = next(
            (item for item in rows if item["name"] == GROUP_ID_TRIGGER_NAME),
            None,
        )

        if row is None:
            await session.run(
                "CALL apoc.trigger.install("
                "$database_name, $trigger_name, $trigger_query, $selector, {}"
                ")",
                database_name=GROUP_ID_TRIGGER_DATABASE,
                trigger_name=GROUP_ID_TRIGGER_NAME,
                trigger_query=GROUP_ID_TRIGGER_QUERY,
                selector=GROUP_ID_TRIGGER_SELECTOR,
            )
            return

        if not _group_id_trigger_matches(dict(row)):
            await session.run(
                "CALL apoc.trigger.drop($database_name, $trigger_name)",
                database_name=GROUP_ID_TRIGGER_DATABASE,
                trigger_name=GROUP_ID_TRIGGER_NAME,
            )
            await session.run(
                "CALL apoc.trigger.install("
                "$database_name, $trigger_name, $trigger_query, $selector, {}"
                ")",
                database_name=GROUP_ID_TRIGGER_DATABASE,
                trigger_name=GROUP_ID_TRIGGER_NAME,
                trigger_query=GROUP_ID_TRIGGER_QUERY,
                selector=GROUP_ID_TRIGGER_SELECTOR,
            )
            return

        if row["paused"]:
            await session.run(
                "CALL apoc.trigger.start($database_name, $trigger_name)",
                database_name=GROUP_ID_TRIGGER_DATABASE,
                trigger_name=GROUP_ID_TRIGGER_NAME,
            )


async def ensure_schema(driver: AsyncDriver, *, default_group_id: str) -> None:
    default_slug = default_group_id.removeprefix("project/")
    now = datetime.now(timezone.utc).isoformat()

    async with driver.session() as session:
        for stmt in CREATE_CONSTRAINTS:
            await session.run(stmt)
        for stmt in CREATE_INDEXES:
            await session.run(stmt)
        await session.run(
            BOOTSTRAP_PROJECT,
            slug=default_slug,
            name=_bootstrap_name_for(default_slug),
            tags=["bootstrap"],
            language=None,
            framework=None,
            repo_url=None,
            parent_mount=None,
            relative_path=None,
            language_profile=None,
            now=now,
        )

    await _ensure_group_id_trigger(driver)

    async with driver.session() as session:
        result = await session.run(UNREGISTERED_GROUP_IDS)
        row = await result.single()
        unregistered = row["unregistered"] if row else []

    if unregistered:
        raise SchemaIntegrityError(
            f"group_ids present on entities but no matching :Project: "
            f"{sorted(unregistered)}. Register via palace.memory.register_project."
        )
