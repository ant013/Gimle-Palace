"""palace.code.* composite (orchestrated) tools.

Distinct from code_router.py which only exposes raw passthroughs to CM.
Composites here build their behaviour on top of multiple CM calls.

Schema strategy: composite tools use FastMCP's closed schema (Pydantic-derived
from typed signature) — distinct from passthroughs which use open _OpenArgs
schema for flat-arg propagation (GIM-89). Composites have a fixed contract
owned by us; closed schema is correct for v1.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import re
from collections.abc import Callable, Hashable
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol
from urllib.parse import unquote

from mcp import ClientSession
from pydantic import BaseModel, Field, ValidationError, field_validator

from palace_mcp import code_router
from palace_mcp.code.namespace import resolve as resolve_project_namespace
from palace_mcp.errors import handle_tool_error
from palace_mcp.extractors.foundation.identifiers import symbol_id_for
from palace_mcp.extractors.foundation.tantivy_bridge import TantivyBridge
from palace_mcp.memory.bundle import bundle_status
from palace_mcp.memory.projects import UnknownProjectError


logger = logging.getLogger(__name__)

_SHORT_NAME_LABELS = ("Function", "Method", "Class", "Symbol")


# ---------------------------------------------------------------------------
# Bundle-aware slug resolution (GIM-182 §5.2)
# ---------------------------------------------------------------------------


@dataclass
class SlugResolution:
    """Result of resolving a user-provided slug to its kind."""

    kind: Literal["bundle", "project", "none"]
    member_slugs: list[str] = field(default_factory=list)


_RESOLVE_SLUG_QUERY = """
OPTIONAL MATCH (b:Bundle {name: $slug})
OPTIONAL MATCH (b)-[:CONTAINS]->(p:Project)
WITH b, collect(p.slug) AS bundle_members
OPTIONAL MATCH (proj:Project {slug: $slug})
RETURN
  CASE
    WHEN b IS NOT NULL THEN 'bundle'
    WHEN proj IS NOT NULL THEN 'project'
    ELSE 'none'
  END AS kind,
  bundle_members AS member_slugs
"""


async def _resolve_slug(driver: Any, slug: str) -> SlugResolution:
    """Detect whether slug is a :Bundle, :Project, or unknown (single Cypher)."""
    async with driver.session() as session:
        result = await session.run(_RESOLVE_SLUG_QUERY, slug=slug)
        row = await result.single()
    if row is None:
        return SlugResolution(kind="none")
    kind: Literal["bundle", "project", "none"] = row["kind"]
    member_slugs: list[str] = list(row["member_slugs"] or [])
    return SlugResolution(kind=kind, member_slugs=member_slugs)


_QN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*(\.[A-Za-z_][A-Za-z0-9_-]*)*$")


def _needs_human_resolution(qualified_name: str) -> bool:
    return (
        qualified_name.startswith("scip-")
        or "%3" in qualified_name
        or "." not in qualified_name
    )


class TestImpactRequest(BaseModel):
    """Input model for palace.code.test_impact."""

    qualified_name: str = Field(..., min_length=1, max_length=500)
    project: str | None = None
    include_indirect: bool = False
    max_hops: int = Field(3, ge=1, le=5)
    max_results: int = Field(50, ge=1, le=200)

    @field_validator("qualified_name")
    @classmethod
    def _qn_charset(cls, v: str) -> str:
        if not _QN_RE.match(v):
            raise ValueError(
                "qualified_name must be a dotted Python identifier "
                "(components match [A-Za-z_][A-Za-z0-9_-]*; allows slug-style hyphens)"
            )
        return v


class _ToolDecorator(Protocol):
    """Stricter type for `_tool` than Callable[[str, str], ...]."""

    def __call__(self, name: str, description: str) -> Callable[..., Any]: ...


_DESC = (
    "Given a Function's qualified_name, return tests transitively calling it. "
    "Default: :TESTS edge (hop=1, exact, homonym-immune). "
    "include_indirect=True: trace_call_path multi-hop with homonym caveat."
)


async def _resolve_qn(
    session: ClientSession | None,
    qualified_name: str,
    project: str,
    *,
    project_slug: str | None = None,
    label: str | None = "Function",
    driver: Any | None = None,
    max_candidates: int = 15,
    include_deprecated: bool = True,
) -> tuple[str, str] | dict[str, Any]:
    """Disambiguate qualified_name → (short_name, resolved_qn).

    Returns error envelope dict for symbol_not_found / ambiguous_qualified_name.
    Pass label=None to search all symbol types (Functions, Classes, Methods).
    """
    short_name = _decode_scip_short_name(qualified_name)
    can_try_short_name = _needs_human_resolution(qualified_name) and bool(short_name)

    async def _fallback_rows() -> list[dict[str, Any]] | dict[str, Any]:
        fallback_kwargs: dict[str, Any] = {}
        if project_slug is not None:
            fallback_kwargs["project_slug"] = project_slug
        if not include_deprecated:
            fallback_kwargs["include_deprecated"] = False
        if driver is not None:
            return await _resolve_short_name(
                driver,
                requested_qualified_name=qualified_name,
                short_name=short_name,
                project=project,
                max_candidates=max_candidates,
                **fallback_kwargs,
            )
        assert session is not None
        return await _resolve_short_name_via_query_graph(
            session,
            short_name=short_name,
            project=project,
            max_candidates=max_candidates,
            **fallback_kwargs,
        )

    if session is None:
        if not can_try_short_name:
            return {
                "ok": False,
                "error_code": "cm_error",
                "requested_qualified_name": qualified_name,
                "message": "CM session not available for exact qualified_name resolution",
            }
        fallback = await _fallback_rows()
        if isinstance(fallback, dict):
            return fallback
        results = fallback
        total = len(results)
        has_more = False
        match_source = "short-name search"
    else:
        _sg_args: dict[str, Any] = {
            "project": project,
            "qn_pattern": f".*{re.escape(qualified_name)}$",
            "limit": 10,
            "include_deprecated": include_deprecated,
        }
        if label is not None:
            _sg_args["label"] = label
        raw = await session.call_tool("search_graph", arguments=_sg_args)
        if raw.isError:
            if can_try_short_name:
                fallback = await _fallback_rows()
                if isinstance(fallback, dict):
                    return fallback
                results = fallback
                total = len(results)
                has_more = False
                match_source = "short-name search"
            else:
                cm_msg = code_router.parse_cm_result(raw).get("_raw", "")
                return {
                    "ok": False,
                    "error_code": "cm_error",
                    "requested_qualified_name": qualified_name,
                    "message": f"CM error from search_graph: {cm_msg}",
                }
        else:
            data = code_router.parse_cm_result(raw)
            results = data.get("results", [])
            total = data.get("total", len(results))
            has_more = data.get("has_more", False)
            match_source = "qn_pattern"

    if not results and can_try_short_name and session is not None:
        fallback = await _fallback_rows()
        if isinstance(fallback, dict):
            return fallback
        if fallback:
            results = fallback
            total = len(results)
            has_more = False
            match_source = "short-name search"

    if not results:
        suffix_label = label or "symbol"
        return {
            "ok": False,
            "error_code": "symbol_not_found",
            "requested_qualified_name": qualified_name,
            "message": (
                f"qualified_name '{qualified_name}' not found in project "
                f"'{project}' (no {suffix_label} suffix or short-name match)"
            ),
        }

    if len(results) > 1:
        count_phrase = f"at least {len(results)}" if has_more else f"{total}"
        return {
            "ok": False,
            "error_code": "ambiguous_qualified_name",
            "requested_qualified_name": qualified_name,
            "message": (
                f"{match_source} matched {count_phrase} symbols in project "
                f"'{project}' — refine to uniquely identify"
            ),
            "matches": [
                {
                    "qualified_name": r.get("qualified_name", ""),
                    "file_path": r.get("file_path", ""),
                }
                for r in results
            ],
        }

    target = results[0]
    return target["name"], target["qualified_name"]


def _escape_cypher_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _dedup_items(
    items: list[Any],
    *,
    key: Callable[[Any], Hashable],
) -> list[Any]:
    seen: set[Hashable] = set()
    deduped: list[Any] = []
    for item in items:
        item_key = key(item)
        if item_key in seen:
            continue
        seen.add(item_key)
        deduped.append(item)
    return deduped


def _short_name_candidates(row: dict[str, Any]) -> tuple[str, ...]:
    qualified_name = str(row.get("qualified_name") or "")
    terminal_name = qualified_name.rsplit(".", 1)[-1] if "." in qualified_name else ""
    return (
        str(row.get("short_name") or ""),
        str(row.get("name") or ""),
        str(row.get("symbol") or ""),
        terminal_name,
        _decode_scip_short_name(qualified_name),
    )


_QUERY_SYMBOL_BY_SHORT_NAME = """
MATCH (s:Symbol {group_id: $group_id, short_name: $short_name})
WHERE $include_deprecated OR NOT s:Deprecated
RETURN s.name AS name,
       s.short_name AS short_name,
       coalesce(s.symbol, '') AS symbol,
       s.qualified_name AS qualified_name,
       coalesce(s.file_path, '') AS file_path
ORDER BY s.qualified_name
LIMIT $limit
"""

_QUERY_SYMBOL_BY_SHORT_NAME_FOLD = """
MATCH (s:Symbol {group_id: $group_id})
WITH s, last(split(coalesce(s.qualified_name, ''), '.')) AS terminal_name
WHERE any(candidate IN [
          coalesce(s.short_name, ''),
          coalesce(s.name, ''),
          coalesce(s.symbol, ''),
          terminal_name
      ] WHERE toLower(candidate) = toLower($short_name))
  AND ($include_deprecated OR NOT s:Deprecated)
WITH s, terminal_name, coalesce(s.qualified_name, s.name, s.symbol, '') AS resolved_qn
WHERE resolved_qn <> ''
RETURN coalesce(s.name, s.symbol, terminal_name) AS name,
       coalesce(s.short_name, s.name, s.symbol, terminal_name) AS short_name,
       coalesce(s.symbol, '') AS symbol,
       resolved_qn AS qualified_name,
       coalesce(s.file_path, '') AS file_path
ORDER BY qualified_name
LIMIT $limit
"""

_QUERY_SYMBOL_BY_SHORT_NAME_REGEX = """
MATCH (s:Symbol {group_id: $group_id})
WITH s, last(split(coalesce(s.qualified_name, ''), '.')) AS terminal_name
WHERE any(candidate IN [
          coalesce(s.short_name, ''),
          coalesce(s.name, ''),
          coalesce(s.symbol, ''),
          terminal_name
      ] WHERE candidate <> '' AND candidate =~ $pattern)
  AND ($include_deprecated OR NOT s:Deprecated)
WITH s, terminal_name, coalesce(s.qualified_name, s.name, s.symbol, '') AS resolved_qn
WHERE resolved_qn <> ''
RETURN coalesce(s.name, s.symbol, terminal_name) AS name,
       coalesce(s.short_name, s.name, s.symbol, terminal_name) AS short_name,
       coalesce(s.symbol, '') AS symbol,
       resolved_qn AS qualified_name,
       coalesce(s.file_path, '') AS file_path
ORDER BY qualified_name
LIMIT $limit
"""

_QUERY_SYMBOL_BY_SCIP_SHORT_NAME = """
MATCH (s:Symbol {group_id: $group_id})
WITH s, coalesce(s.qualified_name, '') AS resolved_qn
WHERE resolved_qn =~ $pattern
  AND ($include_deprecated OR NOT s:Deprecated)
RETURN coalesce(s.name, s.symbol, '') AS name,
       coalesce(s.short_name, s.name, s.symbol, '') AS short_name,
       coalesce(s.symbol, '') AS symbol,
       resolved_qn AS qualified_name,
       coalesce(s.file_path, '') AS file_path
ORDER BY qualified_name
LIMIT $limit
"""

_QUERY_FUNCTION_BY_SHORT_NAME_REGEX = """
MATCH (fn:Function {group_id: $group_id})
WITH fn, coalesce(fn.qualified_name, fn.symbol_qualified_name, '') AS resolved_qn
WHERE resolved_qn =~ $pattern
RETURN coalesce(fn.display_name, fn.name, '') AS name,
       '' AS short_name,
       coalesce(fn.symbol_qualified_name, '') AS symbol,
       resolved_qn AS qualified_name,
       coalesce(fn.path, fn.file_path, '') AS file_path
ORDER BY qualified_name
LIMIT $limit
"""

_QUERY_SHADOW_BY_SHORT_NAME_REGEX = """
MATCH (shadow:SymbolOccurrenceShadow {group_id: $group_id})
WITH shadow, coalesce(shadow.symbol_qualified_name, '') AS resolved_qn
WHERE resolved_qn =~ $pattern
RETURN '' AS name,
       '' AS short_name,
       '' AS symbol,
       resolved_qn AS qualified_name,
       '' AS file_path
ORDER BY qualified_name
LIMIT $limit
"""


async def _query_symbol_candidates(
    driver: Any,
    query: str,
    **params: Any,
) -> list[dict[str, Any]]:
    session_ctx = driver.session()
    if inspect.isawaitable(session_ctx):
        session_ctx = await session_ctx
    async with session_ctx as session:
        result = await session.run(query, **params)
        rows = [dict(row) async for row in result]
    return _dedup_items(
        [row for row in rows if row.get("qualified_name")],
        key=lambda row: row["qualified_name"],
    )


def _filter_short_name_rows(
    rows: list[dict[str, Any]],
    short_name: str,
) -> list[dict[str, Any]]:
    folded_short_name = short_name.lower()
    matches: list[dict[str, Any]] = []

    for row in rows:
        qualified_name = str(row.get("qualified_name") or "")
        resolved_name = next(
            (
                candidate
                for candidate in _short_name_candidates(row)
                if candidate and candidate.lower() == folded_short_name
            ),
            "",
        )
        if not resolved_name or not qualified_name:
            continue
        matches.append(
            {
                "name": row.get("short_name", "") or resolved_name,
                "qualified_name": qualified_name,
                "file_path": row.get("file_path", ""),
                "symbol": row.get("symbol", ""),
                "short_name": row.get("short_name", "") or resolved_name,
            }
        )

    return _dedup_items(matches, key=lambda row: row["qualified_name"])


async def _resolve_short_name_via_query_graph(
    session: ClientSession,
    *,
    short_name: str,
    project: str,
    project_slug: str | None = None,
    max_candidates: int = 15,
    include_deprecated: bool = True,
) -> list[dict[str, Any]] | dict[str, Any]:
    escaped_short_name = _escape_cypher_string(short_name)
    deprecated_clause = "" if include_deprecated else "AND NOT s:Deprecated"
    group_slug = project_slug or project.removeprefix("repos-")
    query = f"""
MATCH (s:Symbol {{group_id: 'project/{group_slug}'}})
WITH s, last(split(coalesce(s.qualified_name, ''), '.')) AS terminal_name
WHERE any(candidate IN [
          coalesce(s.short_name, ''),
          coalesce(s.name, ''),
          coalesce(s.symbol, ''),
          terminal_name
      ] WHERE toLower(candidate) = toLower('{escaped_short_name}'))
{deprecated_clause}
RETURN coalesce(s.name, '') AS name,
       coalesce(s.qualified_name, '') AS qualified_name,
       coalesce(s.file_path, '') AS file_path,
       coalesce(s.symbol, '') AS symbol
ORDER BY qualified_name
LIMIT {max_candidates + 1}
"""
    raw = await session.call_tool(
        "query_graph",
        arguments={"project": project, "query": query},
    )
    if raw.isError:
        cm_msg = code_router.parse_cm_result(raw).get("_raw", "")
        return {
            "ok": False,
            "error_code": "cm_error",
            "requested_qualified_name": short_name,
            "message": f"CM error from query_graph: {cm_msg}",
        }
    data = code_router.parse_cm_result(raw)
    rows = [
        {
            "name": row[0] if len(row) > 0 else "",
            "qualified_name": row[1] if len(row) > 1 else "",
            "file_path": row[2] if len(row) > 2 else "",
            "symbol": row[3] if len(row) > 3 else "",
            "short_name": row[0] if len(row) > 0 else "",
        }
        for row in data.get("rows", [])
        if len(row) > 1 and row[1]
    ]
    return _filter_short_name_rows(rows, short_name)


async def _resolve_short_name(
    driver: Any,
    *,
    requested_qualified_name: str,
    short_name: str,
    project: str,
    project_slug: str | None = None,
    max_candidates: int = 15,
    include_deprecated: bool = True,
) -> list[dict[str, Any]] | dict[str, Any]:
    group_id = f"project/{project_slug or project.removeprefix('repos-')}"
    query_limit = max_candidates + 1
    queries = (
        (
            _QUERY_SYMBOL_BY_SHORT_NAME,
            {
                "group_id": group_id,
                "short_name": short_name,
                "limit": query_limit,
                "include_deprecated": include_deprecated,
            },
        ),
        (
            _QUERY_SYMBOL_BY_SHORT_NAME_FOLD,
            {
                "group_id": group_id,
                "short_name": short_name,
                "limit": query_limit,
                "include_deprecated": include_deprecated,
            },
        ),
        (
            _QUERY_SYMBOL_BY_SHORT_NAME_REGEX,
            {
                "group_id": group_id,
                "pattern": rf"(?i){re.escape(short_name)}.*",
                "limit": query_limit,
                "include_deprecated": include_deprecated,
            },
        ),
        (
            _QUERY_SYMBOL_BY_SCIP_SHORT_NAME,
            {
                "group_id": group_id,
                "pattern": rf"(?i).*[0-9]+{re.escape(short_name)}[VCPOAES].*",
                "limit": query_limit,
                "include_deprecated": include_deprecated,
            },
        ),
        (
            _QUERY_FUNCTION_BY_SHORT_NAME_REGEX,
            {
                "group_id": group_id,
                "pattern": rf"(?i).*{re.escape(short_name)}.*",
                "limit": query_limit,
            },
        ),
        (
            _QUERY_SHADOW_BY_SHORT_NAME_REGEX,
            {
                "group_id": group_id,
                "pattern": rf"(?i).*{re.escape(short_name)}.*",
                "limit": query_limit,
            },
        ),
    )

    for query, params in queries:
        rows = _filter_short_name_rows(
            await _query_symbol_candidates(driver, query, **params),
            short_name,
        )
        if rows:
            return rows

    return []


def _length_prefixed_identifiers(symbol: str) -> list[tuple[str, str]]:
    identifiers: list[tuple[str, str]] = []
    i = 0
    n = len(symbol)
    while i < n:
        if not symbol[i].isdigit():
            i += 1
            continue
        j = i
        while j < n and symbol[j].isdigit():
            j += 1
        length = int(symbol[i:j])
        if length <= 0 or j + length > n:
            i = j
            continue
        end = j + length
        next_char = symbol[end] if end < n else ""
        identifiers.append((symbol[j:end], next_char))
        i = end
    return identifiers


def _split_scip_top_level(symbol: str) -> list[str]:
    parts: list[str] = []
    cur: list[str] = []
    in_escape = False
    i = 0
    n = len(symbol)
    while i < n:
        c = symbol[i]
        if c == "`":
            if in_escape and i + 1 < n and symbol[i + 1] == "`":
                cur.append("``")
                i += 2
                continue
            cur.append(c)
            in_escape = not in_escape
            i += 1
            continue
        if c == " " and not in_escape:
            parts.append("".join(cur))
            cur = []
            i += 1
            continue
        cur.append(c)
        i += 1
    if cur:
        parts.append("".join(cur))
    return parts


def _decode_scip_short_name(symbol: str) -> str:
    raw = symbol.strip()
    if not raw:
        return ""

    parts = _split_scip_top_level(raw)
    candidate = parts[-1] if parts else raw
    decoded = unquote(candidate)
    identifiers = _length_prefixed_identifiers(decoded)
    if identifiers:
        type_marker_indexes = [
            idx
            for idx, (_name, next_char) in enumerate(identifiers)
            if next_char in "CPOVAE"
        ]
        if type_marker_indexes:
            boundary = type_marker_indexes[-1]
            if boundary + 1 < len(identifiers):
                return identifiers[boundary + 1][0]
            return identifiers[boundary][0]
        return identifiers[0][0]

    if "." in decoded:
        return decoded.rsplit(".", 1)[-1]
    if "/" in decoded:
        return decoded.rsplit("/", 1)[-1]
    return decoded.rstrip("#().:")


async def _test_impact_tests_edge(
    session: ClientSession,
    requested_qn: str,
    resolved_qn: str,
    project: str,
    max_results: int,
) -> dict[str, Any]:
    """Default path — direct Cypher over :TESTS edge."""
    safe_qn = resolved_qn.replace("\\", "\\\\").replace("'", "\\'")
    cypher = (
        f"MATCH (test)-[:TESTS]->(target) "
        f"WHERE target.qualified_name = '{safe_qn}' "
        f"RETURN test.name AS name, test.qualified_name AS qualified_name "
        f"ORDER BY test.qualified_name "
        f"LIMIT {max_results + 1}"
    )
    raw = await session.call_tool(
        "query_graph",
        arguments={"project": project, "query": cypher},
    )
    if raw.isError:
        cm_msg = code_router.parse_cm_result(raw).get("_raw", "")
        return {
            "ok": False,
            "error_code": "cm_error",
            "requested_qualified_name": requested_qn,
            "message": f"CM error from query_graph: {cm_msg}",
        }
    data = code_router.parse_cm_result(raw)
    rows = data.get("rows", [])
    rows = _dedup_items(rows, key=lambda row: (row[0], row[1]))
    truncated = len(rows) > max_results
    rows = rows[:max_results]
    tests = [{"name": r[0], "qualified_name": r[1], "hop": 1} for r in rows]
    total_found = len(rows) + (1 if truncated else 0)
    return {
        "ok": True,
        "requested_qualified_name": requested_qn,
        "qualified_name": resolved_qn,
        "project": project,
        "method": "tests_edge",
        "tests": tests,
        "total_found": total_found,
        "max_hops_used": None,
        "truncated": truncated,
    }


async def _test_impact_trace(
    session: ClientSession,
    requested_qn: str,
    resolved_qn: str,
    short_name: str,
    project: str,
    max_hops: int,
    max_results: int,
) -> dict[str, Any]:
    """Opt-in path — multi-hop via trace_call_path (homonym risk applies)."""
    raw = await session.call_tool(
        "trace_call_path",
        arguments={
            "project": project,
            "function_name": short_name,
            "direction": "inbound",
            "depth": max_hops,
            "include_tests": True,
        },
    )
    if raw.isError:
        cm_msg = code_router.parse_cm_result(raw).get("_raw", "")
        return {
            "ok": False,
            "error_code": "cm_error",
            "requested_qualified_name": requested_qn,
            "message": f"CM error from trace_call_path: {cm_msg}",
        }
    data = code_router.parse_cm_result(raw)
    callers = data.get("callers", [])
    tests = [c for c in callers if c.get("is_test")]
    tests.sort(key=lambda c: c["hop"])  # KeyError on contract drift = fail loud
    tests = _dedup_items(tests, key=lambda caller: caller["qualified_name"])
    total_found = len(tests)
    truncated = total_found > max_results
    tests = tests[:max_results]
    return {
        "ok": True,
        "requested_qualified_name": requested_qn,
        "qualified_name": resolved_qn,
        "project": project,
        "method": "trace_call_path",
        "disambiguation_caveat": "trace uses short-name; collisions possible",
        "tests": [
            {"name": c["name"], "qualified_name": c["qualified_name"], "hop": c["hop"]}
            for c in tests
        ],
        "total_found": total_found,
        "max_hops_used": max_hops,
        "truncated": truncated,
    }


class FindReferencesRequest(BaseModel):
    """Input model for palace.code.find_references."""

    qualified_name: str = Field(..., min_length=1, max_length=500)
    project: str | None = None
    max_results: int = Field(100, ge=1, le=500)


class CallHierarchyRequest(BaseModel):
    """Input model for palace.code.call_hierarchy."""

    qualified_name: str = Field(..., min_length=1, max_length=500)
    project: str | None = None
    max_results: int = Field(50, ge=1, le=500)
    index_store_path: str | None = None


class GetSnippetRichRequest(BaseModel):
    """Input model for palace.code.get_snippet_rich."""

    qualified_name: str = Field(..., min_length=1, max_length=500)
    project: str | None = None
    max_recent_commits: int = Field(10, ge=1, le=50)
    max_usages: int = Field(20, ge=1, le=200)
    max_owners: int = Field(5, ge=1, le=20)

    @field_validator("qualified_name")
    @classmethod
    def _qn_charset(cls, v: str) -> str:
        if not _QN_RE.match(v):
            raise ValueError(
                "qualified_name must be a dotted Python identifier "
                "(components match [A-Za-z_][A-Za-z0-9_-]*; allows slug-style hyphens)"
            )
        return v


_QUERY_HOTSPOT_SCORE = """
MATCH (f:File {project_id: $project_id})
WHERE coalesce(f.file_path, f.path) = $path
RETURN f.hotspot_score AS hotspot_score
"""

_QUERY_INGEST_RUN = """
MATCH (r:IngestRun {project: $project, extractor_name: $extractor_name})
WHERE r.success = true
RETURN r.run_id AS run_id, r.success AS success, r.error_code AS error_code
ORDER BY r.started_at DESC
LIMIT 1
"""

_QUERY_ANY_INGEST_RUN = """
MATCH (r:IngestRun {project: $project})
WHERE r.success = true
RETURN r.run_id AS run_id, r.success AS success, r.extractor_name AS extractor_name
ORDER BY r.started_at DESC
LIMIT 1
"""

_QUERY_EVICTION_RECORD = """
MATCH (e:EvictionRecord {symbol_qualified_name: $qn, project: $project})
RETURN e.eviction_round AS eviction_round,
       e.evicted_at AS evicted_at,
       e.run_id AS run_id
LIMIT 1
"""

_COUNT_EVICTED_FOR_SYMBOL = """
MATCH (e:EvictionRecord {project: $project})
WHERE e.symbol_qualified_name STARTS WITH $qn_prefix
RETURN count(e) AS total_evicted
"""


async def _query_ingest_run_for_project(
    driver: Any, project: str, extractor_name: str
) -> dict[str, Any] | None:
    """Check if a successful IngestRun exists for this project+extractor."""
    async with driver.session() as session:
        result = await session.run(
            _QUERY_INGEST_RUN,
            project=project,
            extractor_name=extractor_name,
        )
        record = await result.single()
        return None if record is None else dict(record)


async def _query_any_ingest_run_for_project(
    driver: Any, project: str
) -> dict[str, Any] | None:
    """Check if any successful IngestRun exists for this project (any extractor)."""
    async with driver.session() as session:
        result = await session.run(_QUERY_ANY_INGEST_RUN, project=project)
        record = await result.single()
        return None if record is None else dict(record)


async def _query_eviction_record(
    driver: Any, qualified_name: str, project: str
) -> dict[str, Any] | None:
    """Check if an EvictionRecord exists for this symbol."""
    async with driver.session() as session:
        result = await session.run(
            _QUERY_EVICTION_RECORD,
            qn=qualified_name,
            project=project,
        )
        record = await result.single()
        if record is None:
            return None
        eviction_data = dict(record)
        count_result = await session.run(
            _COUNT_EVICTED_FOR_SYMBOL,
            project=project,
            qn_prefix=qualified_name.split(".")[0],
        )
        count_record = await count_result.single()
        eviction_data["total_evicted"] = (
            count_record.get("total_evicted", 0) if count_record else 0
        )
        return eviction_data


def _tantivy_doc_first_value(doc: dict[str, Any], field: str) -> Any | None:
    value = doc.get(field)
    if isinstance(value, list):
        return value[0] if value else None
    return value


def _parse_occurrence_doc_key(doc_key: str) -> tuple[str, int, int]:
    parts = doc_key.rsplit(":", 3)
    if len(parts) == 4 and parts[1].isdigit() and parts[2].isdigit():
        head, line_text, col_start_text, _commit_sha = parts
    else:
        head, line_text, col_start_text = doc_key.rsplit(":", 2)
    _symbol_id, file_path = head.split(":", 1)
    return file_path, int(line_text), int(col_start_text)


def _decode_tantivy_occurrence(
    raw_doc: dict[str, Any],
    *,
    fallback_qualified_name: str,
) -> dict[str, Any]:
    doc_key_value = _tantivy_doc_first_value(raw_doc, "doc_key")
    file_path = _tantivy_doc_first_value(raw_doc, "file_path")
    line = _tantivy_doc_first_value(raw_doc, "line")
    col_start = _tantivy_doc_first_value(raw_doc, "col_start")

    if doc_key_value:
        parsed_file_path, parsed_line, parsed_col_start = _parse_occurrence_doc_key(
            str(doc_key_value)
        )
        if not file_path:
            file_path = parsed_file_path
        if line is None:
            line = parsed_line
        if col_start is None:
            col_start = parsed_col_start

    if not file_path or line is None or col_start is None:
        raise KeyError("tantivy occurrence missing location fields")

    col_end = _tantivy_doc_first_value(raw_doc, "col_end")
    if col_end is None:
        col_end = col_start

    qualified_name = (
        _tantivy_doc_first_value(raw_doc, "symbol_qualified_name")
        or fallback_qualified_name
    )
    kind = _tantivy_doc_first_value(raw_doc, "kind") or "unknown"

    return {
        "file_path": str(file_path),
        "line": int(line),
        "col_start": int(col_start),
        "col_end": int(col_end),
        "kind": str(kind),
        "qualified_name": str(qualified_name),
    }


def _decode_unique_occurrences(
    raw_docs: list[dict[str, Any]],
    *,
    fallback_qualified_name: str,
    symbol_id: int,
) -> list[dict[str, Any]]:
    occurrences: list[dict[str, Any]] = []
    seen: set[tuple[str, int, int]] = set()
    for raw_doc in raw_docs:
        occurrence = _decode_tantivy_occurrence(
            raw_doc,
            fallback_qualified_name=fallback_qualified_name,
        )
        key = (occurrence["file_path"], occurrence["line"], symbol_id)
        if key in seen:
            continue
        seen.add(key)
        occurrences.append(occurrence)
    return occurrences


async def _search_unique_occurrences(
    bridge: TantivyBridge,
    *,
    symbol_id: int,
    fallback_qualified_name: str,
    max_results: int,
) -> tuple[list[dict[str, Any]], bool]:
    target_unique = max_results + 1
    limit = target_unique
    max_limit = target_unique * 8

    while True:
        raw_docs = await bridge.search_by_symbol_id_async(symbol_id, limit=limit)
        occurrences = _decode_unique_occurrences(
            raw_docs,
            fallback_qualified_name=fallback_qualified_name,
            symbol_id=symbol_id,
        )
        if len(occurrences) > max_results:
            return occurrences[:max_results], True
        if len(raw_docs) < limit:
            return occurrences, False
        if limit >= max_limit:
            return occurrences, True
        limit = min(limit * 2, max_limit)


_DESC_SNIPPET_RICH = (
    "Rich context card for a symbol: source snippet, definition location, "
    "usages, code owners, hotspot score, and recent commits. "
    "Single call replaces get_code_snippet + find_references + find_owners + "
    "find_hotspots + git.log."
)

_DESC_CALL_HIERARCHY = (
    "Return callers of a Swift symbol by reading DerivedData IndexStoreDB directly, "
    "bypassing sourcekit-lsp. Configure PALACE_INDEXSTORE_PATHS (JSON dict: project "
    "slug → DataStore path) or PALACE_SOURCEKIT_INDEX_STORE_PATH for single-project "
    "setups. Returns ok=False with error_code=index_store_not_configured when no path "
    "is available."
)


def register_code_composite_tools(
    tool_decorator: _ToolDecorator,
    default_project: str,
) -> None:
    """Register palace.code.* composite tools."""

    @tool_decorator("palace.code.test_impact", _DESC)
    async def palace_code_test_impact(
        qualified_name: str,
        project: str | None = None,
        include_indirect: bool = False,
        max_hops: int = 3,
        max_results: int = 50,
    ) -> dict[str, Any]:
        # Capture session once into local — TOCTOU-immune (D17)
        session = code_router.get_cm_session()
        if session is None and not _needs_human_resolution(qualified_name):
            handle_tool_error(
                RuntimeError(
                    "CM subprocess not started — set CODEBASE_MEMORY_MCP_BINARY"
                )
            )

        try:
            req = TestImpactRequest(
                qualified_name=qualified_name,
                project=project,
                include_indirect=include_indirect,
                max_hops=max_hops,
                max_results=max_results,
            )
        except ValidationError as e:
            return {
                "ok": False,
                "error_code": "validation_error",
                "requested_qualified_name": qualified_name,
                "message": str(e),
            }

        from palace_mcp.mcp_server import get_driver

        driver = get_driver()
        if driver is None:
            handle_tool_error(RuntimeError("Neo4j driver not initialised"))
            raise  # unreachable
        namespace = await resolve_project_namespace(
            driver, req.project or default_project
        )
        resolved_project = namespace.cm_project_name

        try:
            disambig = await _resolve_qn(
                session,
                req.qualified_name,
                resolved_project,
                driver=driver,
                project_slug=namespace.slug,
            )
        except Exception as e:
            handle_tool_error(e)
            raise  # unreachable; satisfies ruff RET503

        if isinstance(disambig, dict):
            return disambig
        short_name, resolved_qn = disambig
        if session is None:
            handle_tool_error(
                RuntimeError(
                    "CM subprocess not started — set CODEBASE_MEMORY_MCP_BINARY"
                )
            )

        try:
            if req.include_indirect:
                return await _test_impact_trace(
                    session,
                    requested_qn=req.qualified_name,
                    resolved_qn=resolved_qn,
                    short_name=short_name,
                    project=resolved_project,
                    max_hops=req.max_hops,
                    max_results=req.max_results,
                )
            return await _test_impact_tests_edge(
                session,
                requested_qn=req.qualified_name,
                resolved_qn=resolved_qn,
                project=resolved_project,
                max_results=req.max_results,
            )
        except Exception as e:
            handle_tool_error(e)
            raise  # unreachable

    _DESC_FIND_REFS = (
        "Find all references (occurrences) of a symbol by qualified_name. "
        "Returns 3-state distinction: genuinely-zero-refs (ok, no warning), "
        "project-not-indexed (warning: project_not_indexed), or "
        "partial-index-due-to-eviction (warning: partial_index + coverage_pct)."
    )

    @tool_decorator("palace.code.find_references", _DESC_FIND_REFS)
    async def palace_code_find_references(
        qualified_name: str,
        project: str | None = None,
        max_results: int = 100,
        include_deprecated: bool = True,
    ) -> dict[str, Any]:
        from pathlib import Path

        from palace_mcp.mcp_server import get_driver, get_settings

        driver = get_driver()
        if driver is None:
            handle_tool_error(RuntimeError("Neo4j driver not initialised"))
            raise  # unreachable

        settings = get_settings()
        if settings is None:
            handle_tool_error(RuntimeError("Settings not initialised"))
            raise  # unreachable

        try:
            req = FindReferencesRequest(
                qualified_name=qualified_name,
                project=project,
                max_results=max_results,
            )
        except ValidationError as e:
            return {
                "ok": False,
                "error_code": "validation_error",
                "requested_qualified_name": qualified_name,
                "message": str(e),
            }

        requested_project = req.project or default_project
        project_namespace = None
        try:
            project_namespace = await resolve_project_namespace(
                driver, requested_project
            )
        except UnknownProjectError:
            resolved_project = requested_project
            resolution = await _resolve_slug(driver, resolved_project)
        else:
            resolved_project = project_namespace.slug
            resolution = SlugResolution(kind="project")

        if resolution.kind == "none":
            return {
                "ok": False,
                "error_code": "project_not_found",
                "requested_qualified_name": qualified_name,
                "message": (
                    f"'{resolved_project}' is not a registered project or bundle"
                ),
            }

        if resolution.kind == "bundle":
            # §5.2 bundle path: single Tantivy search across all indexed members;
            # health classification (ingest_failed/never_ingested/stale) comes from
            # bundle_status; Tantivy failure → all member slugs into query_failed_slugs.
            health = await bundle_status(driver, bundle=resolved_project)
            sym_id = symbol_id_for(req.qualified_name)
            tantivy_path = Path(settings.palace_tantivy_index_path)
            query_time_failures: list[str] = []
            occurrences_bundle: list[dict[str, Any]] = []
            truncated = False
            try:
                async with TantivyBridge(
                    tantivy_path, heap_size_mb=settings.palace_tantivy_heap_mb
                ) as bridge:
                    occurrences_bundle, truncated = await _search_unique_occurrences(
                        bridge,
                        symbol_id=sym_id,
                        fallback_qualified_name=req.qualified_name,
                        max_results=req.max_results,
                    )
            except Exception:
                logger.warning(
                    "bundle_tantivy_query_failed bundle=%s qn=%s",
                    resolved_project,
                    req.qualified_name,
                    exc_info=True,
                )
                query_time_failures = list(resolution.member_slugs)

            if query_time_failures:
                health = health.model_copy(
                    update={
                        "query_failed_slugs": tuple(sorted(set(query_time_failures)))
                    }
                )
            return {
                "ok": True,
                "requested_qualified_name": req.qualified_name,
                "bundle": resolved_project,
                "occurrences": occurrences_bundle,
                "total_found": len(occurrences_bundle) + (1 if truncated else 0),
                "truncated": truncated,
                "bundle_health": health.model_dump(mode="json"),
            }

        # §5.2 project path — existing behaviour unchanged
        # State B: never-indexed — check for any successful IngestRun
        ingest_run = await _query_any_ingest_run_for_project(driver, resolved_project)
        if ingest_run is None:
            return {
                "ok": True,
                "occurrences": [],
                "total_found": 0,
                "warning": "project_not_indexed",
                "action_required": (
                    f"Run palace.ingest.run_extractor(<extractor_name>, "
                    f"'{resolved_project}') before relying on this answer"
                ),
            }

        # Optional: resolve via CM session for suffix-match disambiguation
        resolved_qn = req.qualified_name
        cm_session = code_router.get_cm_session()
        if cm_session is not None or _needs_human_resolution(req.qualified_name):
            cm_project = (
                project_namespace.cm_project_name
                if project_namespace is not None
                else resolved_project
            )
            project_slug = (
                project_namespace.slug if project_namespace is not None else None
            )
            try:
                disambig = await _resolve_qn(
                    cm_session,
                    req.qualified_name,
                    cm_project,
                    driver=driver,
                    project_slug=project_slug,
                    include_deprecated=include_deprecated,
                )
                if isinstance(disambig, dict):
                    if disambig.get("error_code") == "cm_error":
                        # CM is connected but search_graph failed (project not in CM graph).
                        # Fall back to literal QN instead of surfacing a CM infrastructure error.
                        resolved_qn = req.qualified_name
                    else:
                        return disambig  # symbol_not_found or ambiguous_qualified_name
                else:
                    _short_name, resolved_qn = disambig
            except Exception:
                logger.debug(
                    "CM symbol resolution failed for %s, using literal",
                    req.qualified_name,
                    exc_info=True,
                )
                resolved_qn = req.qualified_name  # fall back to literal

        # Query Tantivy for occurrences
        sym_id = symbol_id_for(resolved_qn)
        tantivy_path = Path(settings.palace_tantivy_index_path)
        async with TantivyBridge(
            tantivy_path, heap_size_mb=settings.palace_tantivy_heap_mb
        ) as bridge:
            occurrences, truncated = await _search_unique_occurrences(
                bridge,
                symbol_id=sym_id,
                fallback_qualified_name=resolved_qn,
                max_results=req.max_results,
            )

        # State C: evicted — attach partial_index warning
        eviction_info = await _query_eviction_record(
            driver, resolved_qn, resolved_project
        )

        response: dict[str, Any] = {
            "ok": True,
            "requested_qualified_name": req.qualified_name,
            "project": resolved_project,
            "occurrences": occurrences,
            "total_found": len(occurrences) + (1 if truncated else 0),
            "truncated": truncated,
        }

        if eviction_info:
            total_evicted = int(eviction_info.get("total_evicted", 0))
            response["warning"] = "partial_index"
            response["eviction_note"] = (
                f"{total_evicted} occurrences evicted "
                f"(round={eviction_info['eviction_round']}); coverage may be incomplete"
            )
            total = len(occurrences) + total_evicted
            response["coverage_pct"] = (
                int(100 * len(occurrences) / total) if total > 0 else 100
            )

        return response

    @tool_decorator("palace.code.get_snippet_rich", _DESC_SNIPPET_RICH)
    async def palace_code_get_snippet_rich(
        qualified_name: str,
        project: str | None = None,
        max_recent_commits: int = 10,
        max_usages: int = 20,
        max_owners: int = 5,
    ) -> dict[str, Any]:
        from pathlib import Path

        from palace_mcp.code.find_owners import find_owners as _find_owners
        from palace_mcp.git.tools import palace_git_log as _git_log
        from palace_mcp.mcp_server import get_driver, get_settings

        session = code_router.get_cm_session()
        if session is None:
            handle_tool_error(
                RuntimeError(
                    "CM subprocess not started — set CODEBASE_MEMORY_MCP_BINARY"
                )
            )
            raise  # unreachable

        driver = get_driver()
        if driver is None:
            handle_tool_error(RuntimeError("Neo4j driver not initialised"))
            raise  # unreachable

        settings = get_settings()
        if settings is None:
            handle_tool_error(RuntimeError("Settings not initialised"))
            raise  # unreachable

        try:
            req = GetSnippetRichRequest(
                qualified_name=qualified_name,
                project=project,
                max_recent_commits=max_recent_commits,
                max_usages=max_usages,
                max_owners=max_owners,
            )
        except ValidationError as e:
            return {
                "ok": False,
                "error_code": "validation_error",
                "requested_qualified_name": qualified_name,
                "message": str(e),
            }

        namespace = await resolve_project_namespace(
            driver, req.project or default_project
        )
        cm_project = namespace.cm_project_name
        neo4j_slug = namespace.slug

        # Step 1: Resolve qualified_name — all symbol types (F1 fix: label=None)
        try:
            disambig = await _resolve_qn(
                session,
                req.qualified_name,
                cm_project,
                project_slug=neo4j_slug,
                label=None,
                driver=driver,
            )
        except Exception as e:
            handle_tool_error(e)
            raise  # unreachable

        if isinstance(disambig, dict):
            return disambig
        _short_name, resolved_qn = disambig

        # Step 2: Get snippet — must succeed for the tool to return ok=true
        raw_snippet = await session.call_tool(
            "get_code_snippet",
            arguments={"qualified_name": resolved_qn, "project": cm_project},
        )
        if raw_snippet.isError:
            cm_msg = code_router.parse_cm_result(raw_snippet).get("_raw", "")
            return {
                "ok": False,
                "error_code": "cm_error",
                "requested_qualified_name": req.qualified_name,
                "message": f"CM error from get_code_snippet: {cm_msg}",
            }
        snippet_data = code_router.parse_cm_result(raw_snippet)
        file_path = snippet_data.get("file_path", "")
        start_line = snippet_data.get("start_line")
        end_line = snippet_data.get("end_line")
        snippet = {
            "source": snippet_data.get("source", ""),
            "language": snippet_data.get("language", ""),
            "file_path": file_path,
            "start_line": start_line,
            "end_line": end_line,
        }
        definition_location = {
            "file_path": file_path,
            "start_line": start_line,
            "end_line": end_line,
        }

        # Step 3: Fan-out — usages, owners, hotspot, commits in parallel
        async def _get_usages() -> list[dict[str, Any]]:
            sym_id = symbol_id_for(resolved_qn)
            tantivy_path = Path(settings.palace_tantivy_index_path)
            async with TantivyBridge(
                tantivy_path, heap_size_mb=settings.palace_tantivy_heap_mb
            ) as bridge:
                raw = await bridge.search_by_symbol_id_async(
                    sym_id, limit=req.max_usages + 1
                )
            return _decode_unique_occurrences(
                raw,
                fallback_qualified_name=resolved_qn,
                symbol_id=sym_id,
            )[: req.max_usages]

        async def _get_owners() -> list[dict[str, Any]]:
            result = await _find_owners(
                driver, file_path=file_path, project=neo4j_slug, top_n=req.max_owners
            )
            owners: list[dict[str, Any]] = result.get("owners", [])
            return owners

        async def _get_hotspot() -> float | None:
            project_id = f"project/{neo4j_slug}"
            async with driver.session() as neo4j_session:
                r = await neo4j_session.run(
                    _QUERY_HOTSPOT_SCORE, project_id=project_id, path=file_path
                )
                record = await r.single()
            if record is None:
                return None
            score: float | None = record["hotspot_score"]
            return score

        async def _get_recent_commits() -> list[dict[str, Any]]:
            result = await _git_log(
                neo4j_slug, path=file_path, n=req.max_recent_commits
            )
            return [
                {
                    "sha": e["sha"],
                    "short": e["short"],
                    "author_name": e["author_name"],
                    "date": e["date"],
                    "subject": e["subject"],
                }
                for e in result.get("entries", [])
            ]

        usages_r, owners_r, hotspot_r, commits_r = await asyncio.gather(
            _get_usages(),
            _get_owners(),
            _get_hotspot(),
            _get_recent_commits(),
            return_exceptions=True,
        )

        rich: dict[str, Any] = {
            "ok": True,
            "requested_qualified_name": req.qualified_name,
            "qualified_name": resolved_qn,
            "project": neo4j_slug,
            "snippet": snippet,
            "definition_location": definition_location,
        }

        if isinstance(usages_r, BaseException):
            rich["usages"] = []
            rich["usages_error"] = str(usages_r)
        else:
            rich["usages"] = usages_r

        if isinstance(owners_r, BaseException):
            rich["owners"] = []
            rich["owners_error"] = str(owners_r)
        else:
            rich["owners"] = owners_r

        if isinstance(hotspot_r, BaseException):
            rich["hotspot_score"] = None
            rich["hotspot_error"] = str(hotspot_r)
        else:
            rich["hotspot_score"] = hotspot_r

        if isinstance(commits_r, BaseException):
            rich["recent_commits"] = []
            rich["recent_commits_error"] = str(commits_r)
        else:
            rich["recent_commits"] = commits_r

        return rich

    @tool_decorator("palace.code.call_hierarchy", _DESC_CALL_HIERARCHY)
    async def palace_code_call_hierarchy(
        qualified_name: str,
        project: str | None = None,
        max_results: int = 50,
        index_store_path: str | None = None,
    ) -> dict[str, Any]:
        from palace_mcp.cache import cache_key, get_cache, hydration_semaphore
        from palace_mcp.code.call_hierarchy import call_hierarchy_tool
        from palace_mcp.mcp_server import get_settings

        settings = get_settings()
        if settings is None:
            handle_tool_error(RuntimeError("Settings not initialised"))
            raise  # unreachable

        try:
            req = CallHierarchyRequest(
                qualified_name=qualified_name,
                project=project,
                max_results=max_results,
                index_store_path=index_store_path,
            )
        except ValidationError as e:
            return {
                "ok": False,
                "error_code": "validation_error",
                "requested_qualified_name": qualified_name,
                "message": str(e),
            }

        key = cache_key(
            qualified_name=req.qualified_name,
            project=req.project or "",
            max_results=req.max_results,
            index_store_path=req.index_store_path or "",
        )
        cache = get_cache()
        if cache is not None:
            cached_value, hit = cache.get(key)
            if hit:
                logger.info(
                    "palace.cache.hit tool=palace.code.call_hierarchy qn=%s",
                    req.qualified_name,
                )
                return cached_value  # type: ignore[no-any-return]

        logger.info(
            "palace.cache.miss tool=palace.code.call_hierarchy qn=%s",
            req.qualified_name,
        )

        async with hydration_semaphore("palace.code.call_hierarchy"):
            result: dict[str, Any] = await asyncio.to_thread(
                call_hierarchy_tool,
                qualified_name=req.qualified_name,
                project=req.project,
                max_results=req.max_results,
                index_store_path=req.index_store_path,
                indexstore_paths=settings.palace_indexstore_paths,
                default_store_path=settings.palace_sourcekit_index_store_path,
                timeout_s=settings.palace_call_hierarchy_timeout_s,
            )

        if cache is not None and result.get("ok"):
            cache.put(key, result)

        return result
