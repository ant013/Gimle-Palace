"""Project-scoping helpers for palace-memory tools."""

from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import TYPE_CHECKING

from neo4j import AsyncManagedTransaction

from palace_mcp.memory.cypher import LIST_PROJECT_SLUGS, LOOKUP_PROJECT_NAMESPACE

if TYPE_CHECKING:
    from palace_mcp.config import Settings


_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9\-]{0,62}$")
_PARENT_MOUNT_RE = re.compile(r"^[a-z][a-z0-9-]{0,15}$")
_RELATIVE_PATH_RE = re.compile(r"^[A-Za-z0-9._-]+(/[A-Za-z0-9._-]+)*$")


class InvalidSlug(ValueError):
    """Raised when a project slug fails format validation.

    Slug format: `[a-z0-9][a-z0-9\\-]{0,62}` (1–63 chars,
    lowercase alphanumerics plus hyphen, no leading hyphen).
    """

    def __init__(self, slug: str) -> None:
        super().__init__(f"invalid project slug: {slug!r}")
        self.slug = slug


def validate_slug(slug: str) -> None:
    """Validate a project slug. Raise InvalidSlug if invalid."""
    if not isinstance(slug, str) or not _SLUG_RE.match(slug):
        raise InvalidSlug(slug)


def validate_parent_mount(value: str) -> None:
    if not _PARENT_MOUNT_RE.match(value):
        raise ValueError(
            f"invalid parent_mount name: {value!r} (must match ^[a-z][a-z0-9-]{{0,15}}$)"
        )


def validate_relative_path(value: str) -> None:
    if not _RELATIVE_PATH_RE.match(value):
        raise ValueError(
            f"invalid relative_path: {value!r} "
            r"(must match ^[A-Za-z0-9._-]+(/[A-Za-z0-9._-]+)*$)"
        )
    for part in value.split("/"):
        if part == "..":
            raise ValueError(f"invalid relative_path: {value!r} (contains '..')")


def derive_cm_project_name(
    *,
    slug: str,
    parent_mount: str | None = None,
    relative_path: str | None = None,
) -> str | None:
    if parent_mount is None and relative_path is None:
        return "-".join(PurePosixPath("/repos", slug).parts[1:])
    if parent_mount is None or relative_path is None:
        return None

    validate_parent_mount(parent_mount)
    validate_relative_path(relative_path)
    return "-".join(PurePosixPath(f"/repos-{parent_mount}", relative_path).parts[1:])


class UnknownProjectError(ValueError):
    """Raised when a project arg references a slug that has no :Project node."""


async def _list_known_slugs(tx: AsyncManagedTransaction) -> list[str]:
    result = await tx.run(LIST_PROJECT_SLUGS)
    return [row["slug"] async for row in result]


async def _resolve_known_slug(tx: AsyncManagedTransaction, value: str) -> str:
    result = await tx.run(LOOKUP_PROJECT_NAMESPACE, value=value)
    row = await result.single()
    if row is None:
        raise UnknownProjectError(value)
    try:
        project = row["p"]
    except KeyError:
        project = row
    return project["slug"]


async def resolve_group_ids(
    tx: AsyncManagedTransaction,
    project: str | list[str] | None,
    *,
    default_group_id: str,
) -> list[str]:
    if project is None:
        return [default_group_id]

    known = await _list_known_slugs(tx)

    if project == "*":
        return [f"project/{s}" for s in known]

    if isinstance(project, str):
        return [f"project/{await _resolve_known_slug(tx, project)}"]

    if isinstance(project, list):
        group_ids: list[str] = []
        unknown: list[str] = []
        for value in project:
            try:
                slug = await _resolve_known_slug(tx, value)
            except UnknownProjectError:
                unknown.append(value)
                continue
            group_ids.append(f"project/{slug}")
        if unknown:
            raise UnknownProjectError(", ".join(unknown))
        return group_ids

    raise TypeError(f"project must be str, list, or None; got {type(project).__name__}")


def get_anchor_qnames(group_ids: list[str], settings: Settings) -> list[str]:
    """Return anchor qualified names from config for the given group IDs.

    Reads palace_anchor_symbols — a group_id-keyed dict — and returns the
    combined list for all requested group IDs.  No DB access; pure config
    look-up suitable for ingest-time anchor marking.
    """
    result: list[str] = []
    for gid in group_ids:
        result.extend(settings.palace_anchor_symbols.get(gid, []))
    return result
