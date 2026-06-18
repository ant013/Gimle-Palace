"""Canonical namespace resolution between Palace slugs and CM project names."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from neo4j import AsyncDriver

from palace_mcp.memory.cypher import LOOKUP_PROJECT_NAMESPACE
from palace_mcp.memory.projects import UnknownProjectError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class NamespaceResolution:
    slug: str
    cm_project_name: str


class SlugRegisteredButUnmapped(UnknownProjectError):
    """Raised when a registered project lacks a canonical CM namespace."""

    def __init__(self, slug: str) -> None:
        super().__init__(
            f"registered project {slug!r} is missing cm_project_name; run the Phase 1 migration"
        )
        self.slug = slug


_CACHE: dict[str, NamespaceResolution] = {}


def invalidate() -> None:
    _CACHE.clear()


def _requested_log_value(value: str, resolution: NamespaceResolution) -> str:
    if value == resolution.cm_project_name:
        return "<cm_project_name>"
    return value


def _project_fields(row: object) -> tuple[str, str | None]:
    try:
        project = row["p"]
    except KeyError:
        project = row
    slug = project["slug"]
    if hasattr(project, "get"):
        return slug, project.get("cm_project_name")
    return slug, project["cm_project_name"]


async def resolve(driver: AsyncDriver, value: str) -> NamespaceResolution:
    cached = _CACHE.get(value)
    if cached is not None:
        logger.debug(
            "namespace.resolve requested=%s slug=%s cm_project_name=<redacted>",
            _requested_log_value(value, cached),
            cached.slug,
        )
        return cached

    async with driver.session() as session:
        result = await session.run(LOOKUP_PROJECT_NAMESPACE, value=value)
        row = await result.single()

    if row is None:
        raise UnknownProjectError(value)

    slug, cm_project_name = _project_fields(row)
    if not cm_project_name:
        raise SlugRegisteredButUnmapped(slug)

    resolution = NamespaceResolution(slug=slug, cm_project_name=cm_project_name)
    _CACHE[value] = resolution
    logger.debug(
        "namespace.resolve requested=%s slug=%s cm_project_name=<redacted>",
        _requested_log_value(value, resolution),
        slug,
    )
    return resolution


async def assert_known_project(driver: AsyncDriver, value: str) -> None:
    await resolve(driver, value)
