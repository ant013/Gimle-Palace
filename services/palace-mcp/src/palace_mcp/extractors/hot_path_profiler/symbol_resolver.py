"""Resolve profiler symbol names to existing :Function qualified names."""

from __future__ import annotations

import re
from typing import Any

from palace_mcp.extractors.hot_path_profiler.models import HotPathSample

_FUNCTION_LOOKUP_CYPHER = """
MATCH (fn:Function {project_id: $project_id})
RETURN coalesce(fn.qualified_name, fn.symbol_qualified_name, fn.name) AS qualified_name,
       fn.name AS name,
       coalesce(fn.display_name, fn.name) AS display_name
ORDER BY qualified_name ASC
""".strip()
_SPLIT_RE = re.compile(r"[.:/#]+")
_PARENS_RE = re.compile(r"\(.*?\)")


async def resolve_samples(
    driver: Any,
    *,
    project_id: str,
    samples: list[HotPathSample],
) -> tuple[list[HotPathSample], list[HotPathSample]]:
    """Split samples into resolved and unresolved groups."""

    lookup = await _load_lookup(driver, project_id=project_id)
    resolved: list[HotPathSample] = []
    unresolved: list[HotPathSample] = []
    for sample in samples:
        qualified_name = resolve_symbol_name(sample.symbol_name, lookup)
        if qualified_name is None and sample.qualified_name:
            qualified_name = resolve_symbol_name(sample.qualified_name, lookup)
        if qualified_name is None:
            unresolved.append(sample)
            continue
        resolved.append(sample.model_copy(update={"qualified_name": qualified_name}))
    return resolved, unresolved


def resolve_symbol_name(symbol_name: str, lookup: dict[str, str]) -> str | None:
    """Resolve one trace symbol name against a prebuilt lookup table."""

    for candidate in _candidate_keys(symbol_name):
        matched = lookup.get(candidate)
        if matched is not None:
            return matched
    return None


async def _load_lookup(driver: Any, *, project_id: str) -> dict[str, str]:
    lookup: dict[str, str] = {}
    async with driver.session() as session:
        result = await session.run(_FUNCTION_LOOKUP_CYPHER, project_id=project_id)
        async for row in result:
            qualified_name = row["qualified_name"]
            if not isinstance(qualified_name, str) or not qualified_name.strip():
                continue
            canonical = qualified_name.strip()
            for key in _row_keys(row):
                lookup.setdefault(key, canonical)
    return lookup


def _row_keys(row: Any) -> set[str]:
    values = {row.get("qualified_name"), row.get("name"), row.get("display_name")}
    keys: set[str] = set()
    for value in values:
        if isinstance(value, str) and value.strip():
            keys.update(_candidate_keys(value))
    return keys


def _candidate_keys(value: str) -> set[str]:
    raw = value.strip()
    if not raw:
        return set()
    no_parens = _PARENS_RE.sub("", raw)
    parts = [part for part in _SPLIT_RE.split(no_parens) if part]
    candidates = {
        _normalise(raw),
        _normalise(no_parens),
    }
    if parts:
        candidates.add(_normalise(parts[-1]))
        if len(parts) >= 2:
            candidates.add(_normalise(".".join(parts[-2:])))
    return {candidate for candidate in candidates if candidate}


def _normalise(value: str) -> str:
    return re.sub(r"\s+", "", value).lower()
