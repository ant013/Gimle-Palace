"""Module owner resolution for cross-module contract extraction."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Literal

from neo4j import AsyncDriver
from pydantic import BaseModel, Field

_MODULE_OWNER_MAP_PATH = Path(".palace/cross-module-contract/module-owners.json")


class ModuleOwnerRoot(BaseModel):
    """One module name with one or more source roots."""

    model_config = {"frozen": True}

    module_name: str
    roots: list[str] = Field(default_factory=list)


class ModuleOwnerMap(BaseModel):
    """Committed fallback module-owner mapping."""

    model_config = {"frozen": True}

    modules: list[ModuleOwnerRoot] = Field(default_factory=list)


class ModuleOwnerResolution(BaseModel):
    """Result of resolving file_path → module_name."""

    model_config = {"frozen": True}

    status: Literal["resolved", "unresolved", "ambiguous"]
    module_name: str | None = None
    source: Literal["graph", "fixture_map", "graph_and_fixture_map", "none"] = "none"
    reason: str | None = None

    @classmethod
    def resolved(
        cls,
        module_name: str,
        *,
        source: Literal["graph", "fixture_map", "graph_and_fixture_map"],
    ) -> "ModuleOwnerResolution":
        return cls(status="resolved", module_name=module_name, source=source)

    @classmethod
    def unresolved(cls, reason: str) -> "ModuleOwnerResolution":
        return cls(status="unresolved", reason=reason)

    @classmethod
    def ambiguous(cls, reason: str) -> "ModuleOwnerResolution":
        return cls(status="ambiguous", reason=reason)


def resolve_module_owner_from_map(
    mapping: ModuleOwnerMap, file_path: str
) -> ModuleOwnerResolution:
    """Resolve a file path from a committed module-root map."""

    matched_modules = sorted(
        {
            module.module_name
            for module in mapping.modules
            if any(
                file_path == root or file_path.startswith(f"{root.rstrip('/')}/")
                for root in module.roots
            )
        }
    )
    if len(matched_modules) == 1:
        return ModuleOwnerResolution.resolved(matched_modules[0], source="fixture_map")
    if len(matched_modules) > 1:
        return ModuleOwnerResolution.ambiguous("consumer_module_ambiguous")
    return ModuleOwnerResolution.unresolved("consumer_module_unresolved")


async def resolve_module_owner(
    *,
    driver: AsyncDriver,
    group_id: str,
    repo_path: Path,
    file_path: str,
) -> ModuleOwnerResolution:
    """Resolve module ownership from graph facts first, then fixture fallback."""

    graph_modules = await _resolve_from_graph(
        driver=driver, group_id=group_id, file_path=file_path
    )
    map_resolution = await _resolve_from_map(repo_path=repo_path, file_path=file_path)

    if len(graph_modules) > 1:
        return ModuleOwnerResolution.ambiguous("consumer_module_ambiguous")
    if len(graph_modules) == 1:
        graph_module = graph_modules[0]
        if (
            map_resolution is not None
            and map_resolution.status == "resolved"
            and map_resolution.module_name != graph_module
        ):
            return ModuleOwnerResolution.ambiguous("consumer_module_conflict")
        return ModuleOwnerResolution.resolved(
            graph_module,
            source="graph_and_fixture_map"
            if map_resolution is not None and map_resolution.status == "resolved"
            else "graph",
        )
    if map_resolution is not None:
        return map_resolution
    return ModuleOwnerResolution.unresolved("consumer_module_unresolved")


async def _resolve_from_graph(
    *, driver: AsyncDriver, group_id: str, file_path: str
) -> list[str]:
    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (module:Module {group_id: $group_id})-[:CONTAINS]->
                  (file:File {group_id: $group_id, path: $file_path})
            RETURN collect(DISTINCT module.name) AS module_names
            """,
            group_id=group_id,
            file_path=file_path,
        )
        record = await result.single()
    if record is None:
        return []
    module_names = record["module_names"]
    if not isinstance(module_names, list):
        return []
    return sorted(str(name) for name in module_names if name)


async def _resolve_from_map(
    *, repo_path: Path, file_path: str
) -> ModuleOwnerResolution | None:
    map_path = repo_path / _MODULE_OWNER_MAP_PATH
    if not map_path.exists():
        return None
    raw = await asyncio.to_thread(map_path.read_text, encoding="utf-8")
    mapping = ModuleOwnerMap.model_validate(json.loads(raw))
    return resolve_module_owner_from_map(mapping, file_path)
