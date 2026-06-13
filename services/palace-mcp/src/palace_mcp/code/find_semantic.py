"""palace.code.semantic_search — semantic search over embedded :Symbol nodes."""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any
from typing import cast

from neo4j.exceptions import Neo4jError

from palace_mcp import code_router
from palace_mcp.code.semantic_contract import ScoreComponents
from palace_mcp.code.snippet_provider import resolve_snippet
from palace_mcp.embeddings import get_embedding_dispatcher
from palace_mcp.extractors.foundation.identifiers import symbol_id_for
from palace_mcp.extractors.foundation.tantivy_bridge import TantivyBridge

if TYPE_CHECKING:
    from palace_mcp.config import Settings


logger = logging.getLogger(__name__)

_MAX_SCOPE_PROJECTS = 10
_MAX_LIMIT = 50
_MAX_CONTEXT_LIMIT = 10
_USAGE_PREVIEW_PHASES = ("phase1_defs", "phase2_user_uses", "phase3_vendor_uses")
_vector_search_supported: bool | None = None
_vector_legacy_fallback_warned = False

_VALIDATE_PROJECTS_QUERY = """
MATCH (p:Project)
WHERE p.slug IN $projects
RETURN collect(p.slug) AS found_projects
""".strip()

_COUNT_EMBEDDED_SYMBOLS_QUERY = """
MATCH (s:Symbol)
WHERE s.group_id IN $group_ids
  AND s.embedding IS NOT NULL
  AND ($include_deprecated OR NOT s:Deprecated)
RETURN count(s) AS embedded_symbol_count
""".strip()

_COVERAGE_QUERY = """
MATCH (s:Symbol)
WHERE s.group_id IN $group_ids
  AND ($include_deprecated OR NOT s:Deprecated)
WITH s.source_scope AS source_scope, s.embedding IS NOT NULL AS has_embed
RETURN source_scope, count(*) AS total, sum(CASE WHEN has_embed THEN 1 ELSE 0 END) AS embedded_cnt
""".strip()

_VECTOR_SEARCH_QUERY = """
CYPHER 25
MATCH (s:Symbol)
  SEARCH s IN (
    VECTOR INDEX symbol_embedding_idx
    FOR $embedding
    LIMIT $query_k
  ) SCORE AS score
WHERE s.group_id IN $group_ids
  AND ($include_deprecated OR NOT s:Deprecated)
RETURN
  s.group_id AS group_id,
  s.qualified_name AS qualified_name,
  s.kind AS kind,
  s.file_path AS file_path,
  properties(s)[$line_start_key] AS line_start,
  properties(s)[$line_end_key] AS line_end,
  s.module_name AS module_name,
  s.source_scope AS source_scope,
  s.embedding_input_hash AS embedding_input_hash,
  s.commit_sha AS commit_sha,
  score AS score
ORDER BY score DESC
""".strip()

_VECTOR_LEGACY_QUERY = """
CALL db.index.vector.queryNodes('symbol_embedding_idx', $query_k, $embedding)
YIELD node, score
WITH node AS s, score
WHERE s:Symbol
  AND s.group_id IN $group_ids
  AND ($include_deprecated OR NOT s:Deprecated)
RETURN
  s.group_id AS group_id,
  s.qualified_name AS qualified_name,
  s.kind AS kind,
  s.file_path AS file_path,
  properties(s)[$line_start_key] AS line_start,
  properties(s)[$line_end_key] AS line_end,
  s.module_name AS module_name,
  s.source_scope AS source_scope,
  s.embedding_input_hash AS embedding_input_hash,
  s.commit_sha AS commit_sha,
  score AS score
ORDER BY score DESC
""".strip()

_VECTOR_QUERY = _VECTOR_SEARCH_QUERY

_MISSING_HITS_QUERY = """
UNWIND $hits AS hit
OPTIONAL MATCH (s:Symbol {group_id: hit.group_id, qualified_name: hit.qualified_name})
WITH hit, count(s) AS match_count
WHERE match_count = 0
RETURN
  hit.group_id AS group_id,
  hit.qualified_name AS qualified_name
""".strip()

# ---------------------------------------------------------------------------
# Ranking formula (v1 — dense-only, GIM-919)
#
# final_score = W_VECTOR  * vector_score
#             + W_SCOPE   * scope_score(source_scope)
#             + W_KIND    * kind_score(symbol_kind)
#             + W_LEXICAL * lexical_score(query, qualified_name)
#             - penalty(symbol_kind, qualified_name)
#
# Weights are chosen so that scope preference can override up to 0.20 of
# vector score gap (W_SCOPE=0.15 × Δscope_max=1.0 / W_VECTOR=0.75 ≈ 0.20).
#
# Tie-breaking order (produces total ordering):
#   1. final_score DESC
#   2. source_scope priority ASC  (project < workspace_package < … < sdk)
#   3. symbol kind priority ASC   (function < class < variable < accessor)
#   4. project slug ASC           (alphabetical)
#   5. qualified_name ASC         (alphabetical)
#
# Tolerance: scores are quantized to _SCORE_TOLERANCE bins in the sort key
# so that near-equal final scores fall into the same bucket and tie-breakers
# resolve the ordering deterministically.
# ---------------------------------------------------------------------------

_W_VECTOR: float = 0.75
_W_SCOPE: float = 0.15
_W_KIND: float = 0.05
_W_LEXICAL: float = 0.05
_ACCESSOR_PENALTY: float = 0.15
_SCORE_TOLERANCE: float = 0.001

# source_scope → component score (higher = preferred)
_SCOPE_SCORE: dict[str, float] = {
    "project": 1.00,
    "workspace_package": 0.85,
    "dependency": 0.50,
    "generated": 0.30,
    "derived": 0.20,
    "sdk": 0.10,
}

# source_scope → ascending tie-break priority (lower = ranked first)
_SCOPE_PRIORITY: dict[str, int] = {
    "project": 0,
    "workspace_package": 1,
    "dependency": 2,
    "generated": 3,
    "derived": 4,
    "sdk": 5,
}

# symbol kind → component score (higher = preferred)
_KIND_SCORE: dict[str, float] = {
    "function": 1.00,
    "method": 1.00,
    "initializer": 1.00,
    "deinitializer": 1.00,
    "constructor": 1.00,
    "destructor": 1.00,
    "class": 0.90,
    "struct": 0.90,
    "protocol": 0.90,
    "interface": 0.90,
    "actor": 0.90,
    "extension": 0.80,
    "enum": 0.80,
    "enumCase": 0.75,
    "enum_case": 0.75,
    "variable": 0.70,
    "constant": 0.70,
    "property": 0.70,
    "field": 0.70,
    "macro": 0.65,
    "typealias": 0.60,
    "typeAlias": 0.60,
    "associatedtype": 0.60,
    "accessor": 0.30,
}

# symbol kind → ascending tie-break priority (lower = ranked first)
_KIND_PRIORITY: dict[str, int] = {
    "function": 0,
    "method": 0,
    "initializer": 1,
    "deinitializer": 1,
    "constructor": 1,
    "destructor": 1,
    "class": 2,
    "struct": 2,
    "protocol": 2,
    "interface": 2,
    "actor": 2,
    "extension": 3,
    "enum": 3,
    "enumCase": 4,
    "enum_case": 4,
    "variable": 5,
    "constant": 5,
    "property": 5,
    "field": 5,
    "macro": 6,
    "typealias": 7,
    "typeAlias": 7,
    "associatedtype": 7,
    "accessor": 10,
}

_ACCESSOR_SUFFIXES: tuple[str, ...] = (".getter", ".setter")


def _lexical_score(query: str, qualified_name: str) -> float:
    """1.0 if any query word (length ≥ 3) appears as a substring in qualified_name."""
    qn_lower = qualified_name.lower()
    for word in query.lower().split():
        if len(word) >= 3 and word in qn_lower:
            return 1.0
    return 0.0


def _accessor_penalty(kind: str | None, qualified_name: str) -> float:
    """Return _ACCESSOR_PENALTY for generated accessor symbols, else 0.0."""
    if kind == "accessor":
        return _ACCESSOR_PENALTY
    qn_lower = qualified_name.lower()
    for suffix in _ACCESSOR_SUFFIXES:
        if qn_lower.endswith(suffix):
            return _ACCESSOR_PENALTY
    return 0.0


def _compute_score_components(
    *,
    vector_score: float,
    query: str,
    source_scope: str | None,
    kind: str | None,
    qualified_name: str,
) -> tuple[float, ScoreComponents]:
    """Compute final ranking score and its component breakdown.

    Returns (final_score, ScoreComponents).
    """
    scope_s = _SCOPE_SCORE.get(source_scope or "", 0.10)
    kind_s = _KIND_SCORE.get(kind or "", 0.30)
    lexical = _lexical_score(query, qualified_name)
    pen = _accessor_penalty(kind, qualified_name)

    final = (
        _W_VECTOR * vector_score
        + _W_SCOPE * scope_s
        + _W_KIND * kind_s
        + _W_LEXICAL * lexical
        - pen
    )
    return final, ScoreComponents(
        vector_score_normalized=vector_score,
        source_scope_score=scope_s,
        symbol_kind_boost=kind_s,
        lexical_match=lexical,
        penalty=pen,
    )


def _rank_key(hit: dict[str, Any]) -> tuple[int, int, int, str, str]:
    """Quantized sort key — scores within _SCORE_TOLERANCE share a bucket."""
    return (
        -round(hit["score"] / _SCORE_TOLERANCE),
        _SCOPE_PRIORITY.get(hit.get("source_scope") or "", 99),
        _KIND_PRIORITY.get(hit.get("kind") or "", 99),
        hit.get("project") or "",
        hit.get("qualified_name") or "",
    )


def _apply_ranking(query: str, hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Compute final scores in-place and sort hits by the ranking formula.

    Each hit must have: score (raw vector cosine), qualified_name,
    source_scope, kind.  After this call hit["score"] is the final score
    and hit["score_components"] contains the breakdown.
    Returns the same list (sorted in-place) for convenience.
    """
    for hit in hits:
        final, components = _compute_score_components(
            vector_score=float(hit["score"]),
            query=query,
            source_scope=hit.get("source_scope"),
            kind=hit.get("kind"),
            qualified_name=str(hit.get("qualified_name") or ""),
        )
        hit["score"] = final
        hit["score_components"] = components.model_dump()
    hits.sort(key=_rank_key)
    return hits


# Default source scopes returned without explicit overrides (first-party only).
_DEFAULT_SCOPES: frozenset[str] = frozenset({"project", "workspace_package"})


def _resolve_effective_scopes(
    source_scopes: list[str] | None,
    include_dependencies: bool,
    include_generated: bool,
    include_sdk: bool,
) -> frozenset[str]:
    """Return the set of source_scope values that should pass the filter.

    Precedence: explicit ``source_scopes`` list overrides all flags.
    Otherwise: start from the first-party default and add per-flag scopes.
    """
    if source_scopes is not None:
        return frozenset(source_scopes)
    scopes: set[str] = set(_DEFAULT_SCOPES)
    if include_dependencies:
        scopes.add("dependency")
    if include_generated:
        scopes.add("generated")
        scopes.add("derived")
    if include_sdk:
        scopes.add("sdk")
    return frozenset(scopes)


def _filter_by_scope(
    rows: list[dict[str, Any]],
    effective_scopes: frozenset[str],
) -> tuple[list[dict[str, Any]], int]:
    """Keep rows whose source_scope is in effective_scopes.

    Null source_scope (legacy symbols without the field) is treated as
    "dependency" so they are excluded from first-party-only defaults and
    included when dependency scopes are requested.

    Returns (kept_rows, excluded_count).
    """
    kept: list[dict[str, Any]] = []
    excluded = 0
    for row in rows:
        scope = row.get("source_scope") or "dependency"
        if scope in effective_scopes:
            kept.append(row)
        else:
            excluded += 1
    return kept, excluded


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


async def _count_embedded_symbols(
    driver: Any, group_ids: list[str], *, include_deprecated: bool
) -> int:
    async with driver.session() as session:
        result = await session.run(
            _COUNT_EMBEDDED_SYMBOLS_QUERY,
            group_ids=group_ids,
            include_deprecated=include_deprecated,
        )
        record = await result.single()
    return int(record["embedded_symbol_count"] if record is not None else 0)


def _read_max_symbols() -> int | None:
    raw = os.environ.get("PALACE_EMBEDDING_MAX_SYMBOLS", "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


async def _load_coverage(
    driver: Any, group_ids: list[str], *, include_deprecated: bool
) -> dict[str, Any]:
    async with driver.session() as session:
        result = await session.run(
            _COVERAGE_QUERY,
            group_ids=group_ids,
            include_deprecated=include_deprecated,
        )
        rows = cast(list[dict[str, Any]], await result.data())

    total_symbols = 0
    embedded_symbols = 0
    scope_counts: dict[str, int] = {}
    for row in rows:
        scope = str(row.get("source_scope") or "unknown")
        total = int(row.get("total") or 0)
        embedded = int(row.get("embedded_cnt") or 0)
        total_symbols += total
        embedded_symbols += embedded
        if embedded > 0:
            scope_counts[scope] = embedded

    max_symbols = _read_max_symbols()
    return {
        "bounded": max_symbols is not None,
        "max_symbols": max_symbols,
        "embedded_symbols": embedded_symbols,
        "eligible_symbols": total_symbols,
        "source_scope_counts": scope_counts,
    }


async def _vector_search(
    driver: Any,
    *,
    embedding: list[float],
    group_ids: list[str],
    query_k: int,
    include_deprecated: bool,
) -> list[dict[str, Any]]:
    global _vector_search_supported  # noqa: PLW0603

    async with driver.session() as session:
        if _vector_search_supported is False:
            return await _run_vector_query(
                session,
                _VECTOR_LEGACY_QUERY,
                embedding=embedding,
                group_ids=group_ids,
                query_k=query_k,
                include_deprecated=include_deprecated,
            )

        try:
            rows = await _run_vector_query(
                session,
                _VECTOR_SEARCH_QUERY,
                embedding=embedding,
                group_ids=group_ids,
                query_k=query_k,
                include_deprecated=include_deprecated,
            )
        except Exception as exc:
            if _vector_search_supported is not None or not _is_search_unsupported(exc):
                raise
            _vector_search_supported = False
            _warn_legacy_vector_fallback(exc)
            return await _run_vector_query(
                session,
                _VECTOR_LEGACY_QUERY,
                embedding=embedding,
                group_ids=group_ids,
                query_k=query_k,
                include_deprecated=include_deprecated,
            )

        _vector_search_supported = True
        return rows


async def _run_vector_query(
    session: Any,
    query: str,
    *,
    embedding: list[float],
    group_ids: list[str],
    query_k: int,
    include_deprecated: bool,
) -> list[dict[str, Any]]:
    result = await session.run(
        query,
        embedding=embedding,
        group_ids=group_ids,
        query_k=query_k,
        include_deprecated=include_deprecated,
        line_start_key="line_start",
        line_end_key="line_end",
    )
    return cast(list[dict[str, Any]], await result.data())


def _is_search_unsupported(exc: Exception) -> bool:
    if not isinstance(exc, Neo4jError):
        return False
    message = str(exc)
    if not any(token in message for token in ("SEARCH", "CYPHER 25", "CYPHER_25")):
        return False
    return any(
        token in message.lower()
        for token in (
            "syntax",
            "invalid input",
            "unsupported",
            "unrecognized",
            "not defined",
            "not supported",
        )
    )


def _warn_legacy_vector_fallback(exc: Exception) -> None:
    global _vector_legacy_fallback_warned  # noqa: PLW0603

    if _vector_legacy_fallback_warned:
        return
    _vector_legacy_fallback_warned = True
    logger.warning(
        "semantic_search.vector_search.legacy_fallback",
        extra={
            "error_type": type(exc).__name__,
            "error_code": getattr(exc, "code", None),
        },
    )


def _reset_vector_search_capability_for_tests() -> None:
    global _vector_search_supported, _vector_legacy_fallback_warned  # noqa: PLW0603

    _vector_search_supported = None
    _vector_legacy_fallback_warned = False


def _merge_per_project_results(
    per_project: list[list[dict[str, Any]]],
    final_limit: int,
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    for rows in per_project:
        merged.extend(rows)
    merged.sort(key=lambda r: float(r["score"]), reverse=True)
    return merged[:final_limit]


def _runtime_metadata(settings: Settings | None) -> dict[str, Any]:
    return {
        "git_sha": os.environ.get("PALACE_GIT_SHA", "unknown"),
        "neo4j_uri": settings.neo4j_uri if settings is not None else None,
    }


async def _find_missing_hits(
    driver: Any,
    rows: list[dict[str, Any]],
) -> list[dict[str, str]]:
    if not rows:
        return []
    hits = [
        {
            "group_id": str(row["group_id"]),
            "qualified_name": str(row["qualified_name"]),
        }
        for row in rows
    ]
    async with driver.session() as session:
        result = await session.run(_MISSING_HITS_QUERY, hits=hits)
        missing = cast(list[dict[str, Any]], await result.data())
    return [
        {
            "group_id": str(row["group_id"]),
            "qualified_name": str(row["qualified_name"]),
        }
        for row in missing
    ]


async def _resolve_registered_repo_path(project: str) -> Path | None:
    """Look up :Project.repo_path so snippet provider can use it.

    Same pattern as native_get_code_snippet — fetch the :Project node and
    delegate to resolve_registered_project which honors the persisted
    absolute path. Returns None if the project is not registered or has
    no resolvable on-disk path; callers fall back to the legacy
    REPOS_ROOT/<slug> layout via resolve_project.
    """
    from palace_mcp.git.path_resolver import (
        ProjectNotRegistered,
        resolve_registered_project,
    )
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


async def _load_snippet_context(
    *,
    project: str,
    file_path: str | None,
    line_start: int | None,
    line_end: int | None,
    commit_sha: str | None,
    qualified_name: str,
) -> tuple[dict[str, Any] | None, str | None, str | None]:
    # Primary: read directly from the mounted repo using path_resolver.
    # This validates file_path containment and enforces line/byte bounds.
    # Resolve repo_path from :Project node first so we honor PR #418 (GIM-1569)
    # repo_path field; fall back to REPOS_ROOT/<slug> layout if unset.
    repo_path = await _resolve_registered_repo_path(project)
    snippet, local_code, local_message = await asyncio.to_thread(
        resolve_snippet,
        project=project,
        repo_path=repo_path,
        file_path=file_path,
        line_start=line_start,
        line_end=line_end,
        commit_sha=commit_sha,
    )
    if snippet is not None:
        result: dict[str, Any] = {
            "language": snippet.language,
            "start_line": snippet.start_line,
            "end_line": snippet.end_line,
            "source": snippet.source,
        }
        if snippet.stale:
            result["status"] = "stale_source"
        return result, None, None

    # Fallback: codebase-memory MCP session (e.g. when project not mounted).
    if local_code in ("project_not_mounted", "missing_file_path"):
        session = code_router.get_cm_session()
        if session is not None:
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

            if not raw.isError:
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

    # Local read failed (path rejected, missing file, etc.) — surface warning.
    return None, local_code, local_message


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
    file_path: str | None,
    line_start: int | None,
    line_end: int | None,
    commit_sha: str | None,
    context_limit: int,
) -> dict[str, Any]:
    (
        (snippet, snippet_code, snippet_message),
        (usages_preview, usage_code, usage_message),
    ) = await asyncio.gather(
        _load_snippet_context(
            project=project,
            file_path=file_path,
            line_start=line_start,
            line_end=line_end,
            commit_sha=commit_sha,
            qualified_name=qualified_name,
        ),
        _load_usage_preview(
            settings=settings,
            qualified_name=qualified_name,
            commit_sha=commit_sha,
            context_limit=context_limit,
        ),
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
    source_scopes: list[str] | None = None,
    include_dependencies: bool = False,
    include_generated: bool = False,
    include_sdk: bool = False,
    include_deprecated: bool = False,
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

    coverage = await _load_coverage(
        driver, group_ids, include_deprecated=include_deprecated
    )
    embedded_symbol_count = coverage["embedded_symbols"]
    if settings is not None:
        live_embedded_symbol_count = await _count_embedded_symbols(
            driver, group_ids, include_deprecated=include_deprecated
        )
        if live_embedded_symbol_count != embedded_symbol_count:
            return _error(
                "semantic_search_backend_inconsistent",
                "embedding coverage disagrees with the live Neo4j embedded symbol count",
                inconsistency_kind="coverage_count_mismatch",
                embedded_symbol_count=embedded_symbol_count,
                live_embedded_symbol_count=live_embedded_symbol_count,
                embedding_coverage=coverage,
                runtime=_runtime_metadata(settings),
            )
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
            "embedding_coverage": coverage,
            "result": [],
        }

    candidate_limit = _candidate_limit(limit, len(scope_projects))
    if len(group_ids) == 1:
        per_project_k: int | None = None
        rows = await _vector_search(
            driver,
            embedding=query_embedding,
            group_ids=group_ids,
            query_k=candidate_limit,
            include_deprecated=include_deprecated,
        )
    else:
        per_project_k = _candidate_limit(limit, 1)
        per_project_results = await asyncio.gather(
            *[
                _vector_search(
                    driver,
                    embedding=query_embedding,
                    group_ids=[gid],
                    query_k=per_project_k,
                    include_deprecated=include_deprecated,
                )
                for gid in group_ids
            ]
        )
        rows = _merge_per_project_results(
            list(per_project_results), final_limit=candidate_limit
        )
    if settings is not None:
        missing_hits = await _find_missing_hits(driver, rows)
        if missing_hits:
            return _error(
                "semantic_search_backend_inconsistent",
                "vector search returned symbols that do not exist in live Neo4j",
                inconsistency_kind="missing_vector_hits",
                missing_hits=missing_hits[:10],
                missing_hit_count=len(missing_hits),
                candidate_limit=candidate_limit,
                embedding_coverage=coverage,
                runtime=_runtime_metadata(settings),
            )

    candidate_rows: list[dict[str, Any]] = []
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
            "source_scope": row.get("source_scope"),
            "score": float(row["score"]),
            "_commit_sha": row.get("commit_sha"),
            "_line_start": row.get("line_start"),
            "_line_end": row.get("line_end"),
        }
        embedding_input_hash = row.get("embedding_input_hash")
        if embedding_input_hash is not None:
            hit["embedding_input_hash"] = embedding_input_hash
        candidate_rows.append(hit)

    effective_scopes = _resolve_effective_scopes(
        source_scopes, include_dependencies, include_generated, include_sdk
    )
    candidate_rows, scope_excluded_count = _filter_by_scope(
        candidate_rows, effective_scopes
    )

    _apply_ranking(normalized_query, candidate_rows)
    result_rows = candidate_rows[:limit]

    context_available_count = 0
    warning_code_counts: dict[str, int] = {}
    total_line_count = 0
    total_byte_count = 0
    snippets_with_size = 0

    _hit_meta = [
        (
            hit.pop("_commit_sha", None),
            hit.pop("_line_start", None),
            hit.pop("_line_end", None),
        )
        for hit in result_rows
    ]
    if include_context:
        contexts = await asyncio.gather(
            *[
                _hydrate_context(
                    settings=settings,
                    project=hit["project"],
                    qualified_name=hit["qualified_name"],
                    file_path=hit.get("file_path"),
                    line_start=ls,
                    line_end=le,
                    commit_sha=cs,
                    context_limit=context_limit,
                )
                for hit, (cs, ls, le) in zip(result_rows, _hit_meta)
            ]
        )
        for hit, ctx in zip(result_rows, contexts):
            hit["context"] = ctx
            if ctx.get("available"):
                context_available_count += 1
            wc = ctx.get("warning_code")
            if wc:
                warning_code_counts[wc] = warning_code_counts.get(wc, 0) + 1
            snippet = ctx.get("snippet")
            if snippet:
                lc = snippet.get("end_line", 0) - snippet.get("start_line", 0) + 1
                bc = len((snippet.get("source") or "").encode("utf-8"))
                if lc > 0:
                    total_line_count += lc
                    total_byte_count += bc
                    snippets_with_size += 1

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

    context_metrics: dict[str, Any] = {}
    if include_context and result_rows:
        n = len(result_rows)
        context_metrics = {
            "context_available_rate": context_available_count / n,
            "warning_code_counts": warning_code_counts,
            "avg_snippet_line_count": total_line_count / snippets_with_size
            if snippets_with_size
            else None,
            "avg_snippet_byte_count": total_byte_count / snippets_with_size
            if snippets_with_size
            else None,
        }

    return {
        "ok": True,
        "scope": scope_payload,
        "query": normalized_query,
        "backend": resolved_backend,
        "include_context": include_context,
        "limit": limit,
        "candidate_limit": candidate_limit,
        "per_project_k": per_project_k,
        "embedded_symbol_count": embedded_symbol_count,
        "returned_count": len(result_rows),
        "scope_excluded_count": scope_excluded_count,
        "warnings": warnings,
        "embedding_coverage": coverage,
        "ranking_spec_version": "1",
        "context_metrics": context_metrics,
        "result": result_rows,
    }
