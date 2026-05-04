"""Business logic for palace.memory.register_project, list_projects, get_project_overview."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any

from neo4j import AsyncDriver

from palace_mcp.memory.cypher import (
    CHECK_BUNDLE_NAME_EXISTS,
    GET_PROJECT,
    LIST_PROJECTS,
    PROJECT_ENTITY_COUNTS,
    PROJECT_LAST_INGEST,
    UPSERT_PROJECT,
)
from palace_mcp.memory.schema import ProjectInfo

logger = logging.getLogger(__name__)

# §6.5 regexes — mirrored from path_resolver to keep validation at the boundary
_PARENT_MOUNT_RE = re.compile(r"^[a-z][a-z0-9-]{0,15}$")
_RELATIVE_PATH_RE = re.compile(r"^[A-Za-z0-9._-]+(/[A-Za-z0-9._-]+)*$")


def _validate_parent_mount(value: str) -> None:
    if not _PARENT_MOUNT_RE.match(value):
        raise ValueError(
            f"invalid parent_mount name: {value!r} (must match ^[a-z][a-z0-9-]{{0,15}}$)"
        )


def _validate_relative_path(value: str) -> None:
    if not _RELATIVE_PATH_RE.match(value):
        raise ValueError(
            f"invalid relative_path: {value!r} "
            r"(must match ^[A-Za-z0-9._-]+(/[A-Za-z0-9._-]+)*$)"
        )
    # Explicit rejection of .. components — regex allows "." but not intended for traversal
    for part in value.split("/"):
        if part == "..":
            raise ValueError(f"invalid relative_path: {value!r} (contains '..')")


def _project_info_from_row(
    row: Any, *, entity_counts: dict[str, int] | None = None
) -> ProjectInfo:
    p = row["p"]
    return ProjectInfo(
        slug=p["slug"],
        name=p["name"],
        tags=list(p.get("tags") or []),
        language=p.get("language"),
        framework=p.get("framework"),
        repo_url=p.get("repo_url"),
        parent_mount=p.get("parent_mount"),
        relative_path=p.get("relative_path"),
        source_created_at=p["source_created_at"],
        source_updated_at=p["source_updated_at"],
        entity_counts=entity_counts or {},
    )


async def register_project(
    driver: AsyncDriver,
    *,
    slug: str,
    name: str,
    tags: list[str],
    language: str | None = None,
    framework: str | None = None,
    repo_url: str | None = None,
    parent_mount: str | None = None,
    relative_path: str | None = None,
) -> ProjectInfo:
    from palace_mcp.memory.bundle import ProjectSlugConflictsWithBundle
    from palace_mcp.memory.projects import validate_slug

    validate_slug(slug)

    # §6.5: validate parent_mount and relative_path at boundary, before I/O
    if parent_mount is not None:
        _validate_parent_mount(parent_mount)
    if relative_path is not None:
        _validate_relative_path(relative_path)

    now = datetime.now(timezone.utc).isoformat()
    async with driver.session() as session:
        # §8.15/16 namespace guard: project slug must not conflict with bundle name
        b_result = await session.run(CHECK_BUNDLE_NAME_EXISTS, name=slug)
        b_row = await b_result.single()
        if b_row is not None:
            raise ProjectSlugConflictsWithBundle(slug)

        await session.run(
            UPSERT_PROJECT,
            slug=slug,
            name=name,
            tags=list(tags),
            language=language,
            framework=framework,
            repo_url=repo_url,
            parent_mount=parent_mount,
            relative_path=relative_path,
            now=now,
        )
        result = await session.run(GET_PROJECT, slug=slug)
        row = await result.single()
    assert row is not None, f"Project not found after upsert: {slug!r}"
    return _project_info_from_row(row)


async def list_projects(driver: AsyncDriver) -> list[ProjectInfo]:
    """Return all :Project nodes ordered by slug."""
    async with driver.session() as session:
        result = await session.run(LIST_PROJECTS)
        return [_project_info_from_row(row) async for row in result]


async def get_project_overview(
    driver: AsyncDriver,
    *,
    slug: str,
    source: str = "paperclip",
) -> ProjectInfo:
    """Return a :Project with entity_counts and last ingest metadata."""
    from palace_mcp.memory.projects import UnknownProjectError

    group_id = f"project/{slug}"
    async with driver.session() as session:
        result = await session.run(GET_PROJECT, slug=slug)
        row = await result.single()
        if row is None:
            raise UnknownProjectError(slug)
        base = _project_info_from_row(row)

        counts_result = await session.run(PROJECT_ENTITY_COUNTS, group_id=group_id)
        counts: dict[str, int] = {}
        async for count_row in counts_result:
            for lbl in count_row["labels"]:
                if lbl in ("Issue", "Comment", "Agent", "IngestRun"):
                    counts[lbl] = counts.get(lbl, 0) + int(count_row["c"])

        last_ingest: dict[str, Any] | None = None
        try:
            ingest_result = await session.run(
                PROJECT_LAST_INGEST, group_id=group_id, source=source
            )
            lr = await ingest_result.single()
            if lr is not None:
                last_ingest = dict(lr["r"])
        except Exception as exc:
            logger.warning("get_project_overview last_ingest query failed: %s", exc)

    return base.model_copy(
        update={
            "entity_counts": counts,
            "last_ingest_started_at": last_ingest.get("started_at")
            if last_ingest
            else None,
            "last_ingest_finished_at": last_ingest.get("finished_at")
            if last_ingest
            else None,
        }
    )
