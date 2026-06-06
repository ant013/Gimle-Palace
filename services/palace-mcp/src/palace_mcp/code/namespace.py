"""Canonical namespace resolution between Palace slugs and CM project names."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from neo4j import AsyncDriver

from palace_mcp.memory.projects import UnknownProjectError

logger = logging.getLogger(__name__)

_LOOKUP_PROJECT_NAMESPACE = """
MATCH (p:Project)
WHERE p.slug = $value OR p.cm_project_name = $value
RETURN p
ORDER BY CASE WHEN p.slug = $value THEN 0 ELSE 1 END, p.slug
LIMIT 1
"""


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
        result = await session.run(_LOOKUP_PROJECT_NAMESPACE, value=value)
        row = await result.single()

    if row is None:
        raise UnknownProjectError(value)

    project = row["p"]
    slug = project["slug"]
    cm_project_name = project.get("cm_project_name")
    if not cm_project_name:
        raise SlugRegisteredButUnmapped(slug)

    resolution = NamespaceResolution(slug=slug, cm_project_name=cm_project_name)
    _CACHE[value] = resolution
    _CACHE[slug] = resolution
    _CACHE[cm_project_name] = resolution
    logger.debug(
        "namespace.resolve requested=%s slug=%s cm_project_name=<redacted>",
        _requested_log_value(value, resolution),
        slug,
    )
    return resolution


async def assert_known_project(driver: AsyncDriver, value: str) -> None:
    await resolve(driver, value)
