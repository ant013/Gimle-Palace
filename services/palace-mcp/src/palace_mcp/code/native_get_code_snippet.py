"""Native get_code_snippet implementation for Palace-known projects."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from palace_mcp.code.native_detect_changes import FALLBACK_TO_CM
from palace_mcp.code.snippet_provider import inspect_freshness, resolve_snippet
from palace_mcp.code.snippet_scope import (
    TYPE_FILES_QUERY,
    build_documents,
    order_type_files,
    plan_type_scope,
)
from palace_mcp.code.snippet_short_name import (
    snippet_short_name,
    snippet_short_name_candidates,
)
from palace_mcp.git.path_resolver import (
    ProjectNotRegistered,
    resolve_registered_project,
)
from palace_mcp.symbol_identity import (
    canonical_symbol_kind,
    canonical_symbol_label,
    canonical_symbol_short_name,
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
       coalesce(s.short_name, '') AS short_name,
       coalesce(s.kind, '') AS kind,
       coalesce(s.label, '') AS label,
       coalesce(s.commit_sha, s.last_seen_in_commit) AS commit_sha,
       coalesce(s.module_name, '') AS module_name,
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
    indexed_commit: str | None = None,
    commits_behind_head: int | None = None,
    stale: bool | None = None,
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
    if indexed_commit is not None:
        result["indexed_commit"] = indexed_commit
    if commits_behind_head is not None:
        result["commits_behind_head"] = commits_behind_head
    if stale is not None:
        result["stale"] = stale
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


def _exact_bounds(row: dict[str, Any]) -> tuple[int, int] | None:
    line_start = row.get("line_start", row.get("start_line"))
    line_end = row.get("line_end", row.get("end_line"))
    if not isinstance(line_start, int) or line_start < 1:
        return None
    if not isinstance(line_end, int) or line_end < line_start:
        return None
    return line_start, line_end


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


async def _scope_response(
    *,
    project: str,
    scope: str,
    effective_scope: str,
    plan: Any,
    symbol_row: dict[str, Any],
    file_path: str,
    type_files_rows: list[dict[str, Any]],
    requested_qualified_name: str,
    include_deprecated: bool,
) -> dict[str, Any] | object:
    """Assemble a scope=file|type response: whole-file docs + honest rollup."""
    repo_path = await _resolve_repo_path(project)
    commit_sha = str(symbol_row.get("commit_sha") or "") or None
    freshness = await asyncio.to_thread(inspect_freshness, repo_path, commit_sha)

    deprecated_suppressed = 0
    if effective_scope == "type":
        files = [
            str(r.get("file_path") or "")
            for r in type_files_rows
            if r.get("file_path")
        ]
        if not include_deprecated:
            deprecated_suppressed = sum(int(r.get("dep_count") or 0) for r in type_files_rows)
        if file_path and file_path not in files:
            files.append(file_path)
        file_roles = order_type_files(file_path, files)
    else:
        file_roles = [(file_path, "file")]

    docs, rollup = await asyncio.to_thread(
        build_documents,
        file_roles,
        project=project,
        repo_path=repo_path,
        commit_sha=commit_sha,
        freshness=freshness,
    )

    # File scope with a single unreadable doc that maps to a CM-fallback code
    # mirrors the symbol path's FALLBACK_TO_CM behaviour.
    if (
        effective_scope == "file"
        and len(docs) == 1
        and docs[0].error_code in _CM_FALLBACK_CODES
    ):
        return FALLBACK_TO_CM

    complete = (
        rollup["documents_failed"] == 0
        and rollup["documents_truncated"] == 0
        and not rollup["dropped_files"]
    )
    if effective_scope == "type":
        quality = "whole_type" if complete else "whole_type_partial"
        completeness_note = (
            "moniker-prefix grouping; extensions with divergent monikers or "
            "off-disk files may be absent"
        )
        type_completeness = "best_effort"
    else:
        quality = "whole_file"
        completeness_note = None
        type_completeness = "verified"

    first = docs[0]
    resolved_qn = str(symbol_row.get("qualified_name") or requested_qualified_name)
    resp: dict[str, Any] = {
        "qualified_name": resolved_qn,
        "requested_qualified_name": requested_qualified_name,
        "project": project,
        "file_path": first.file_path,
        "short_name": canonical_symbol_short_name(
            resolved_qn, short_name=str(symbol_row.get("short_name") or "")
        ),
        "kind": canonical_symbol_kind(str(symbol_row.get("kind") or "")),
        "label": canonical_symbol_label(
            str(symbol_row.get("label") or symbol_row.get("kind") or "")
        ),
        "language": first.language,
        "requested_scope": scope,
        "effective_scope": effective_scope,
        "scope_downgraded": bool(plan.scope_downgraded) if plan else False,
        "downgrade_reason": plan.downgrade_reason if plan else None,
        "snippet_quality": quality,
        "complete": complete,
        "type_completeness": type_completeness,
        "completeness_note": completeness_note,
        "documents_total": rollup["documents_total"],
        "documents_failed": rollup["documents_failed"],
        "documents_truncated": rollup["documents_truncated"],
        "dropped_files": rollup["dropped_files"],
        "deprecated_extensions_suppressed": deprecated_suppressed,
        "stale": freshness.stale,
        "indexed_commit": freshness.indexed_commit,
        "commits_behind_head": freshness.commits_behind_head,
        "documents": [d.as_dict() for d in docs],
    }
    # Legacy top-level source only for a single-file result (top-level == the one
    # doc, so no "read declaration, miss extensions" footgun).
    if len(docs) == 1 and first.source is not None:
        resp["source"] = first.source
        resp["start_line"] = first.start_line
        resp["end_line"] = first.end_line
        resp["truncated"] = first.truncated
    return resp


async def native_get_code_snippet(
    qualified_name: str,
    project: str | None = None,
    include_deprecated: bool = False,
    scope: str = "symbol",
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
    if scope not in ("symbol", "file", "type"):
        return _error(
            "validation_error",
            f"scope must be one of symbol|file|type (got {scope!r})",
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

        plan = None
        effective_scope = "file"
        type_files_rows: list[dict[str, Any]] = []
        function_rows: list[dict[str, Any]] = []

        if scope == "symbol":
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
        elif scope == "type":
            plan = plan_type_scope(
                canonical_symbol_kind(str(symbol_row.get("kind") or "")),
                file_path,
            )
            effective_scope = plan.effective_scope
            if effective_scope == "type":
                type_files_rows = await _collect_rows(
                    await session.run(
                        TYPE_FILES_QUERY,
                        {
                            "group_id": f"project/{project}",
                            "module_name": str(symbol_row.get("module_name") or ""),
                            "type_qn": str(symbol_row.get("qualified_name") or ""),
                        },
                    )
                )

    if scope != "symbol":
        return await _scope_response(
            project=project,
            scope=scope,
            effective_scope=effective_scope,
            plan=plan,
            symbol_row=symbol_row,
            file_path=file_path,
            type_files_rows=type_files_rows,
            requested_qualified_name=qualified_name,
            include_deprecated=include_deprecated,
        )

    snippet_quality = "file_head"
    line_start = 1
    line_end = _FILE_HEAD_LINES
    if (bounds := _exact_bounds(symbol_row)) is not None:
        line_start, line_end = bounds
        snippet_quality = "exact"
    elif function_rows:
        bounds = _window_bounds(function_rows[0])
        if bounds is not None:
            line_start, line_end = bounds
            snippet_quality = "approximate_function_match"
    elif (bounds := _window_bounds(symbol_row)) is not None:
        line_start, line_end = bounds
        snippet_quality = "approximate_window"

    repo_path = await _resolve_repo_path(project)
    commit_sha = str(symbol_row.get("commit_sha") or "") or None
    freshness = await asyncio.to_thread(inspect_freshness, repo_path, commit_sha)
    snippet, warning_code, warning_message = await asyncio.to_thread(
        resolve_snippet,
        project=project,
        repo_path=repo_path,
        file_path=file_path or None,
        line_start=line_start,
        line_end=line_end,
        commit_sha=commit_sha,
        freshness=freshness,
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
            indexed_commit=freshness.indexed_commit,
            commits_behind_head=freshness.commits_behind_head,
            stale=freshness.stale,
        )

    return {
        "qualified_name": str(symbol_row.get("qualified_name") or requested),
        "requested_qualified_name": qualified_name,
        "project": project,
        "file_path": file_path,
        "short_name": canonical_symbol_short_name(
            str(symbol_row.get("qualified_name") or requested),
            short_name=str(symbol_row.get("short_name") or ""),
        ),
        "kind": canonical_symbol_kind(str(symbol_row.get("kind") or "")),
        "label": canonical_symbol_label(
            str(symbol_row.get("label") or symbol_row.get("kind") or "")
        ),
        "start_line": snippet.start_line,
        "end_line": snippet.end_line,
        "source": snippet.source,
        "language": snippet.language,
        "truncated": snippet.truncated,
        "stale": freshness.stale,
        "indexed_commit": freshness.indexed_commit,
        "commits_behind_head": freshness.commits_behind_head,
        "snippet_quality": snippet_quality,
    }
