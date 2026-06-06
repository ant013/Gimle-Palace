"""Back-fill canonical CM project names on :Project nodes."""

from __future__ import annotations

import asyncio
import logging
import os

from neo4j import AsyncDriver

from palace_mcp.memory.projects import derive_cm_project_name

_LIST_PROJECTS = """
MATCH (p:Project)
RETURN p.slug AS slug,
       p.parent_mount AS parent_mount,
       p.relative_path AS relative_path,
       p.cm_project_name AS cm_project_name
ORDER BY p.slug
"""

_SET_PROJECT_CM_NAME = """
MATCH (p:Project {slug: $slug})
SET p.cm_project_name = $cm_project_name
RETURN p.slug AS slug
"""

logger = logging.getLogger(__name__)


async def run_migration(driver: AsyncDriver) -> int:
    async with driver.session() as session:
        result = await session.run(_LIST_PROJECTS)
        rows = [dict(row) async for row in result]

    derived_by_slug: dict[str, str] = {}
    owners_by_cm_name: dict[str, list[str]] = {}
    for row in rows:
        cm_project_name = derive_cm_project_name(
            slug=row["slug"],
            parent_mount=row["parent_mount"],
            relative_path=row["relative_path"],
        )
        if cm_project_name is None:
            continue
        derived_by_slug[row["slug"]] = cm_project_name
        owners_by_cm_name.setdefault(cm_project_name, []).append(row["slug"])

    collisions = {
        cm_name: slugs for cm_name, slugs in owners_by_cm_name.items() if len(slugs) > 1
    }
    if collisions:
        details = ", ".join(
            f"{cm_name}: {', '.join(sorted(slugs))}"
            for cm_name, slugs in sorted(collisions.items())
        )
        raise ValueError(f"cm_project_name collision pre-flight failed: {details}")

    migrated = 0
    async with driver.session() as session:
        for row in rows:
            cm_project_name = derived_by_slug.get(row["slug"])
            if cm_project_name is None or row.get("cm_project_name") == cm_project_name:
                continue
            result = await session.run(
                _SET_PROJECT_CM_NAME,
                slug=row["slug"],
                cm_project_name=cm_project_name,
            )
            record = await result.single()
            if record is not None:
                migrated += 1

    logger.info("m2026_06_backfill_project_cm_project_name: migrated %d rows", migrated)
    return migrated


def main() -> None:
    from neo4j import AsyncGraphDatabase

    neo4j_uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    neo4j_user = os.environ.get("NEO4J_USER", "neo4j")
    neo4j_password = os.environ.get("NEO4J_PASSWORD", "changeme")

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    async def _run() -> None:
        driver = AsyncGraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))
        try:
            migrated = await run_migration(driver)
            print(f"migrated {migrated} rows")
        finally:
            await driver.close()

    asyncio.run(_run())


if __name__ == "__main__":
    main()
