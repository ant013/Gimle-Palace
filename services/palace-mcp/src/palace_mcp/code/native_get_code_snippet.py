"""Native get_code_snippet implementation for Palace-known projects."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from palace_mcp.code.native_detect_changes import FALLBACK_TO_CM
from palace_mcp.code.snippet_provider import resolve_snippet
from palace_mcp.code.snippet_short_name import (
    snippet_short_name,
    snippet_short_name_candidates,
)
from palace_mcp.git.path_resolver import (
    ProjectNotRegistered,
    resolve_registered_project,
)

_LOOKUP_SYMBOL = """
MATCH (s:Symbol)
WHERE s.group_id = $group_id
  AND ($include_deprecated OR NOT s:Deprecated)
  AND (
    s.qualified_name = $qualified_name
    OR coalesce(s.short_name, '') IN $short_names
    OR coalesce(s.name, '') IN $short_names
    OR last(split(coalesce(s.qualified_name, ''), '.')) IN $short_names
  )
RETURN s.qualified_name AS qualified_name,
       coalesce(s.file_path, s.path) AS file_path,
       s.commit_sha AS commit_sha,
       s.line_start AS line_start,
       s.line_end AS line_end
ORDER BY CASE WHEN s.qualified_name = $qualified_name THEN 0 ELSE 1 END,
         s.qualified_name
LIMIT 2
""".strip()

_LOOKUP_FUNCTION = """
MATCH (fn:Function)
WHERE fn.project_id = $project_id
  AND coalesce(fn.file_path, fn.path) = $file_path
  AND (
    coalesce(fn.qualified_name, '') = $qualified_name
    OR coalesce(fn.display_name, '') IN $short_names
    OR coalesce(fn.name, '') IN $short_names
  )
RETURN coalesce(fn.file_path, fn.path) AS file_path,
       fn.start_line AS start_line,
       fn.end_line AS end_line,
       fn.qualified_name AS qualified_name
ORDER BY CASE WHEN fn.qualified_name = $qualified_name THEN 0 ELSE 1 END,
         fn.start_line
LIMIT 2
""".strip()

_WINDOW_BEFORE = 20
_WINDOW_AFTER = 40
_FILE_HEAD_LINES = 80
_CM_FALLBACK_CODES = frozenset({"missing_file_path", "project_not_mounted"})


def _error(
    code: str,
    message: str,
    *,
    project: str,
    requested_qualified_name: str,
    resolved_qualified_name: str | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "ok": False,
        "error_code": code,
        "message": message,
        "project": project,
        "requested_qualified_name": requested_qualified_name,
    }
    if resolved_qualified_name is not None:
        result["qualified_name"] = resolved_qualified_name
    return result


def _symbol_not_found(project: str, qualified_name: str) -> dict[str, Any]:
    return _error(
        "symbol_not_found",
        (
            f"qualified_name '{qualified_name}' not found in project "
            f"'{project}' (no exact or short-name match)"
        ),
        project=project,
        requested_qualified_name=qualified_name,
    )


def _ambiguous(
    project: str, qualified_name: str, rows: list[dict[str, Any]]
) -> dict[str, Any]:
    return {
        "ok": False,
        "error_code": "ambiguous_qualified_name",
        "message": (
            f"qualified_name '{qualified_name}' matched {len(rows)} symbols in project "
            f"'{project}' — refine to uniquely identify"
        ),
        "project": project,
        "requested_qualified_name": qualified_name,
        "matches": [
            {
                "qualified_name": str(row.get("qualified_name") or ""),
                "file_path": str(row.get("file_path") or ""),
            }
            for row in rows
        ],
    }


def _window_bounds(row: dict[str, Any]) -> tuple[int, int] | None:
    line_start = row.get("line_start", row.get("start_line"))
    if not isinstance(line_start, int) or line_start < 1:
        return None
    line_end = row.get("line_end", row.get("end_line"))
    if isinstance(line_end, int) and line_end >= line_start:
        return max(1, line_start - _WINDOW_BEFORE), line_end
    return max(1, line_start - _WINDOW_BEFORE), line_start + _WINDOW_AFTER


async def _collect_rows(result: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    async for record in result:
        rows.append(dict(record))
    return rows


async def _resolve_repo_path(project: str) -> Path | None:
    from palace_mcp.mcp_server import get_driver
    from palace_mcp.memory.cypher import GET_PROJECT

    driver = get_driver()
    if driver is None:
        return None

    async with driver.session() as session:
        result = await session.run(GET_PROJECT, slug=project)
        row = await result.single()

    try:
        return resolve_registered_project(
            project,
            project_node=row["p"] if row is not None else None,
        )
    except (ProjectNotRegistered, ValueError):
        return None


async def native_get_code_snippet(
    qualified_name: str,
    project: str | None = None,
    include_deprecated: bool = False,
    **_: Any,
) -> dict[str, Any] | object:
    if project is None:
        return FALLBACK_TO_CM
    requested = qualified_name.strip()
    if not requested:
        return _error(
            "validation_error",
            "qualified_name is required",
            project=project,
            requested_qualified_name=qualified_name,
        )

    from palace_mcp.mcp_server import get_driver

    driver = get_driver()
    if driver is None:
        return _error(
            "neo4j_unavailable",
            "Neo4j driver not initialised",
            project=project,
            requested_qualified_name=qualified_name,
        )

    short_names = snippet_short_name_candidates(requested)
    if not short_names:
        short_names = [snippet_short_name(requested) or requested]

    async with driver.session() as session:
        symbol_rows = await _collect_rows(
            await session.run(
                _LOOKUP_SYMBOL,
                {
                    "group_id": f"project/{project}",
                    "qualified_name": requested,
                    "short_names": short_names,
                    "include_deprecated": include_deprecated,
                },
            )
        )

        if not symbol_rows:
            return _symbol_not_found(project, requested)

        exact_rows = [
            row for row in symbol_rows if row.get("qualified_name") == requested
        ]
        if exact_rows:
            symbol_row = exact_rows[0]
        elif len(symbol_rows) > 1:
            return _ambiguous(project, requested, symbol_rows)
        else:
            symbol_row = symbol_rows[0]

        file_path = str(symbol_row.get("file_path") or "")
        function_rows = await _collect_rows(
            await session.run(
                _LOOKUP_FUNCTION,
                {
                    "project_id": f"project/{project}",
                    "file_path": file_path,
                    "qualified_name": str(symbol_row["qualified_name"]),
                    "short_names": short_names,
                },
            )
        )

    snippet_quality = "file_head"
    line_start = 1
    line_end = _FILE_HEAD_LINES
    if function_rows:
        bounds = _window_bounds(function_rows[0])
        if bounds is not None:
            line_start, line_end = bounds
            snippet_quality = "approximate_function_match"
    elif (bounds := _window_bounds(symbol_row)) is not None:
        line_start, line_end = bounds
        snippet_quality = "approximate_window"

    repo_path = await _resolve_repo_path(project)
    snippet, warning_code, warning_message = await asyncio.to_thread(
        resolve_snippet,
        project=project,
        repo_path=repo_path,
        file_path=file_path or None,
        line_start=line_start,
        line_end=line_end,
        commit_sha=str(symbol_row.get("commit_sha") or "") or None,
    )
    if snippet is None:
        if warning_code in _CM_FALLBACK_CODES:
            return FALLBACK_TO_CM
        return _error(
            warning_code or "snippet_unavailable",
            warning_message or "unable to resolve snippet",
            project=project,
            requested_qualified_name=qualified_name,
            resolved_qualified_name=str(symbol_row.get("qualified_name") or requested),
        )

    return {
        "qualified_name": str(symbol_row.get("qualified_name") or requested),
        "requested_qualified_name": qualified_name,
        "project": project,
        "file_path": file_path,
        "start_line": snippet.start_line,
        "end_line": snippet.end_line,
        "source": snippet.source,
        "language": snippet.language,
        "truncated": snippet.truncated,
        "stale": snippet.stale,
        "snippet_quality": snippet_quality,
    }
