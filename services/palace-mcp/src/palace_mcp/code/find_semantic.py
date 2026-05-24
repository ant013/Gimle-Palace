"""palace.code.semantic_search — semantic search over embedded :Symbol nodes."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, Any
from typing import cast

from palace_mcp import code_router
from palace_mcp.embeddings import get_embedding_dispatcher
from palace_mcp.extractors.foundation.identifiers import symbol_id_for
from palace_mcp.extractors.foundation.tantivy_bridge import TantivyBridge

if TYPE_CHECKING:
    from palace_mcp.config import Settings


_MAX_SCOPE_PROJECTS = 10
_MAX_LIMIT = 50
_MAX_CONTEXT_LIMIT = 10
_USAGE_PREVIEW_PHASES = ("phase1_defs", "phase2_user_uses", "phase3_vendor_uses")

_VALIDATE_PROJECTS_QUERY = """
MATCH (p:Project)
WHERE p.slug IN $projects
RETURN collect(p.slug) AS found_projects
""".strip()

_COUNT_EMBEDDED_SYMBOLS_QUERY = """
MATCH (s:Symbol)
WHERE s.group_id IN $group_ids AND s.embedding IS NOT NULL
RETURN count(s) AS embedded_symbol_count
""".strip()

_VECTOR_QUERY = """
CALL db.index.vector.queryNodes('symbol_embedding_idx', $candidate_limit, $embedding)
YIELD node, score
WITH node AS s, score
WHERE s:Symbol AND s.group_id IN $group_ids
RETURN
  s.group_id AS group_id,
  s.qualified_name AS qualified_name,
  s.kind AS kind,
  s.file_path AS file_path,
  s.module_name AS module_name,
  s.embedding_input_hash AS embedding_input_hash,
  s.commit_sha AS commit_sha,
  score AS score
ORDER BY score DESC
LIMIT $limit
""".strip()


def _error(code: str, message: str, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"ok": False, "error_code": code, "message": message}
    payload.update(extra)
    return payload


def _warning(code: str, message: str, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"code": code, "message": message}
    payload.update(extra)
    return payload


def _normalize_query(value: str) -> str | None:
    normalized = value.strip()
    return normalized or None


def _normalize_scope(
    *,
    project: str | None,
    projects: list[str] | None,
) -> tuple[list[str], dict[str, Any]] | dict[str, Any]:
    if (project is None) == (projects is None):
        return _error(
            "invalid_scope",
            "specify exactly one of project= or projects=",
        )

    if project is not None:
        slug = project.strip()
        if not slug:
            return _error("invalid_scope", "project must be a non-empty slug")
        return [slug], {"project": slug}

    assert projects is not None
    if not projects:
        return _error("invalid_scope", "projects must not be empty")
    if len(projects) > _MAX_SCOPE_PROJECTS:
        return _error(
            "invalid_scope",
            f"projects must contain at most {_MAX_SCOPE_PROJECTS} entries",
        )

    normalized: list[str] = []
    seen: set[str] = set()
    for value in projects:
        slug = value.strip()
        if not slug:
            return _error("invalid_scope", "projects entries must be non-empty slugs")
        if slug in seen:
            continue
        seen.add(slug)
        normalized.append(slug)
    if not normalized:
        return _error("invalid_scope", "projects must not be empty")
    return normalized, {"projects": normalized}


def _candidate_limit(limit: int, scope_size: int) -> int:
    return min(max(limit * scope_size * 10, 50), 500)


def _project_from_group_id(group_id: str) -> str:
    if group_id.startswith("project/"):
        return group_id.removeprefix("project/")
    return group_id


def _translate_cm_project(project: str) -> str:
    if project.startswith("repos-"):
        return project
    return f"repos-{project}"


async def _validate_projects(driver: Any, projects: list[str]) -> list[str]:
    async with driver.session() as session:
        result = await session.run(_VALIDATE_PROJECTS_QUERY, projects=projects)
        record = await result.single()
    found = set(record["found_projects"] or []) if record is not None else set()
    return [slug for slug in projects if slug not in found]


async def _count_embedded_symbols(driver: Any, group_ids: list[str]) -> int:
    async with driver.session() as session:
        result = await session.run(_COUNT_EMBEDDED_SYMBOLS_QUERY, group_ids=group_ids)
        record = await result.single()
    return int(record["embedded_symbol_count"] if record is not None else 0)


async def _vector_search(
    driver: Any,
    *,
    embedding: list[float],
    group_ids: list[str],
    limit: int,
    candidate_limit: int,
) -> list[dict[str, Any]]:
    async with driver.session() as session:
        result = await session.run(
            _VECTOR_QUERY,
            embedding=embedding,
            group_ids=group_ids,
            limit=limit,
            candidate_limit=candidate_limit,
        )
        return cast(list[dict[str, Any]], await result.data())


async def _load_snippet_context(
    *,
    qualified_name: str,
    project: str,
) -> tuple[dict[str, Any] | None, str | None, str | None]:
    session = code_router.get_cm_session()
    if session is None:
        return None, "snippet_provider_unavailable", "snippet provider unavailable"

    try:
        raw = await session.call_tool(
            "get_code_snippet",
            arguments={
                "qualified_name": qualified_name,
                "project": _translate_cm_project(project),
            },
        )
    except Exception as exc:
        return None, "snippet_provider_unavailable", str(exc)

    if raw.isError:
        parsed = code_router.parse_cm_result(raw)
        message = str(parsed.get("_raw", "snippet provider unavailable"))
        return None, "snippet_provider_unavailable", message

    parsed = code_router.parse_cm_result(raw)
    return (
        {
            "language": parsed.get("language", ""),
            "start_line": parsed.get("start_line"),
            "end_line": parsed.get("end_line"),
            "source": parsed.get("source", ""),
        },
        None,
        None,
    )


async def _load_usage_preview(
    *,
    settings: Settings | None,
    qualified_name: str,
    commit_sha: str | None,
    context_limit: int,
) -> tuple[list[dict[str, Any]], str | None, str | None]:
    if context_limit == 0:
        return [], None, None
    if settings is None or not commit_sha:
        return (
            [],
            "usage_preview_unavailable",
            "commit-scoped usage preview unavailable",
        )

    symbol_id = symbol_id_for(qualified_name)
    try:
        async with TantivyBridge(
            Path(settings.palace_tantivy_index_path),
            heap_size_mb=settings.palace_tantivy_heap_mb,
        ) as bridge:
            matches = await bridge.search_occurrences_async(
                symbol_id=symbol_id,
                commit_sha=commit_sha,
                phases=_USAGE_PREVIEW_PHASES,
                limit=context_limit,
            )
    except Exception as exc:
        return [], "usage_preview_unavailable", str(exc)

    return (
        [
            {
                "file_path": match.file_path,
                "line": match.line,
                "col_start": match.col_start,
                "col_end": match.col_end,
            }
            for match in matches
        ],
        None,
        None,
    )


async def _hydrate_context(
    *,
    settings: Settings | None,
    project: str,
    qualified_name: str,
    commit_sha: str | None,
    context_limit: int,
) -> dict[str, Any]:
    snippet, snippet_code, snippet_message = await _load_snippet_context(
        qualified_name=qualified_name,
        project=project,
    )
    usages_preview, usage_code, usage_message = await _load_usage_preview(
        settings=settings,
        qualified_name=qualified_name,
        commit_sha=commit_sha,
        context_limit=context_limit,
    )

    context: dict[str, Any] = {"available": bool(snippet or usages_preview)}
    if snippet is not None:
        context["snippet"] = snippet
    if snippet is not None or context_limit == 0 or usages_preview:
        context["usages_preview"] = usages_preview

    warning_code = snippet_code or usage_code
    warning_message = snippet_message or usage_message
    if warning_code is not None:
        context["warning_code"] = warning_code
    if warning_message is not None:
        context["warning"] = warning_message

    return context


async def semantic_search(
    *,
    driver: Any,
    query: str,
    project: str | None = None,
    projects: list[str] | None = None,
    limit: int = 10,
    backend: str | None = None,
    include_context: bool = True,
    context_limit: int = 3,
    settings: Settings | None = None,
) -> dict[str, Any]:
    normalized_query = _normalize_query(query)
    if normalized_query is None:
        return _error("invalid_query", "query must be a non-empty string")

    if limit < 1 or limit > _MAX_LIMIT:
        return _error("invalid_limit", f"limit must be between 1 and {_MAX_LIMIT}")
    if context_limit < 0 or context_limit > _MAX_CONTEXT_LIMIT:
        return _error(
            "invalid_context_limit",
            f"context_limit must be between 0 and {_MAX_CONTEXT_LIMIT}",
        )

    scope = _normalize_scope(project=project, projects=projects)
    if isinstance(scope, dict):
        return scope
    scope_projects, scope_payload = scope

    missing_projects = await _validate_projects(driver, scope_projects)
    if missing_projects:
        return _error(
            "project_not_registered",
            "one or more requested projects are not registered",
            missing_projects=missing_projects,
        )

    group_ids = [f"project/{slug}" for slug in scope_projects]

    try:
        dispatcher = get_embedding_dispatcher()
    except Exception as exc:
        return _error("embedding_backend_unavailable", str(exc))

    try:
        resolved_backend = dispatcher.resolve_backend_name(backend)
        embedding_backend = dispatcher.backend(resolved_backend)
    except ValueError as exc:
        return _error("unknown_embedding_backend", str(exc))
    except Exception as exc:
        return _error("embedding_backend_unavailable", str(exc))

    try:
        query_embedding = await asyncio.to_thread(
            embedding_backend.embed_text, normalized_query
        )
    except Exception as exc:
        return _error("embedding_backend_failed", str(exc))

    embedded_symbol_count = await _count_embedded_symbols(driver, group_ids)
    warnings: list[dict[str, Any]] = []
    if embedded_symbol_count == 0:
        warnings.append(
            _warning(
                "embeddings_not_ready",
                "requested scope has no embedded symbols yet",
            )
        )
        return {
            "ok": True,
            "scope": scope_payload,
            "query": normalized_query,
            "backend": resolved_backend,
            "include_context": include_context,
            "limit": limit,
            "candidate_limit": _candidate_limit(limit, len(scope_projects)),
            "embedded_symbol_count": 0,
            "returned_count": 0,
            "warnings": warnings,
            "result": [],
        }

    candidate_limit = _candidate_limit(limit, len(scope_projects))
    rows = await _vector_search(
        driver,
        embedding=query_embedding,
        group_ids=group_ids,
        limit=limit,
        candidate_limit=candidate_limit,
    )

    result_rows: list[dict[str, Any]] = []
    for row in rows:
        group_id = str(row["group_id"])
        qualified_name = str(row["qualified_name"])
        hit: dict[str, Any] = {
            "project": _project_from_group_id(group_id),
            "group_id": group_id,
            "qualified_name": qualified_name,
            "occurrence_symbol_id": symbol_id_for(qualified_name),
            "kind": row.get("kind"),
            "file_path": row.get("file_path"),
            "module_name": row.get("module_name"),
            "score": float(row["score"]),
        }
        embedding_input_hash = row.get("embedding_input_hash")
        if embedding_input_hash is not None:
            hit["embedding_input_hash"] = embedding_input_hash
        if include_context:
            hit["context"] = await _hydrate_context(
                settings=settings,
                project=hit["project"],
                qualified_name=qualified_name,
                commit_sha=row.get("commit_sha"),
                context_limit=context_limit,
            )
        result_rows.append(hit)

    if len(result_rows) < limit:
        warnings.append(
            _warning(
                "scope_filter_underfilled",
                "vector search returned fewer scoped hits than requested",
                requested_limit=limit,
                returned_count=len(result_rows),
                candidate_limit=candidate_limit,
            )
        )

    return {
        "ok": True,
        "scope": scope_payload,
        "query": normalized_query,
        "backend": resolved_backend,
        "include_context": include_context,
        "limit": limit,
        "candidate_limit": candidate_limit,
        "embedded_symbol_count": embedded_symbol_count,
        "returned_count": len(result_rows),
        "warnings": warnings,
        "result": result_rows,
    }
