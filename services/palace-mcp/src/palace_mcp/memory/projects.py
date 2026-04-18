"""Project-scoping helpers for palace-memory tools."""

from __future__ import annotations

from neo4j import AsyncManagedTransaction

from palace_mcp.memory.cypher import LIST_PROJECT_SLUGS


class UnknownProjectError(ValueError):
    """Raised when a project arg references a slug that has no :Project node."""


async def _list_known_slugs(tx: AsyncManagedTransaction) -> list[str]:
    result = await tx.run(LIST_PROJECT_SLUGS)
    return [row["slug"] async for row in result]


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
        if project not in known:
            raise UnknownProjectError(project)
        return [f"project/{project}"]

    if isinstance(project, list):
        unknown = [s for s in project if s not in known]
        if unknown:
            raise UnknownProjectError(", ".join(unknown))
        return [f"project/{s}" for s in project]

    raise TypeError(
        f"project must be str, list, or None; got {type(project).__name__}"
    )
