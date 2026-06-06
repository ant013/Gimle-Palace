"""palace.code.* composite (orchestrated) tools.

Distinct from code_router.py which only exposes raw passthroughs to CM.
Composites here build their behaviour on top of multiple CM calls.

Schema strategy: composite tools use FastMCP's closed schema (Pydantic-derived
from typed signature) — distinct from passthroughs which use open _OpenArgs
schema for flat-arg propagation (GIM-89). Composites have a fixed contract
owned by us; closed schema is correct for v1.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Hashable
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from mcp import ClientSession
from mcp.server.fastmcp import Context
from pydantic import BaseModel, Field, ValidationError, field_validator

from palace_mcp import code_router
from palace_mcp.errors import handle_tool_error
from palace_mcp.extractors.foundation.identifiers import symbol_id_for
from palace_mcp.extractors.foundation.tantivy_bridge import TantivyBridge
from palace_mcp.extractors.scip_parser import decode_scip_short_name
from palace_mcp.memory.bundle import bundle_status


logger = logging.getLogger(__name__)


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


def _slug_to_cm_project(value: str) -> str:
    """Translate operator-facing project slug to CM-internal project name.

    palace-mcp public API uses operator slugs (e.g. ``gimle``). The codebase-
    memory-mcp sidecar derives project names from mount paths
    (``/repos/gimle`` → ``repos-gimle``) and refuses calls keyed on the
    operator slug. Translate at the boundary before any CM call.

    Idempotent on already-translated names: ``repos-gimle`` passes through
    unchanged. Assumes the standard ``/repos/<slug>`` mount convention from
    docker-compose.yml.
    """
    if value.startswith("repos-"):
        return value
    return f"repos-{value}"


def _cm_project_to_slug(value: str) -> str:
    """Inverse of :func:`_slug_to_cm_project`. Strip the ``repos-`` prefix.

    The current default ``palace_cm_default_project='repos-gimle'`` is in
    CM-form, but Neo4j-side queries (e.g. ``IngestRun.project``) store the
    operator slug. Apply this before any Neo4j read in code_composite so
    explicit-slug and default-fallback paths agree.

    Idempotent on plain slugs.
    """
    return value.removeprefix("repos-")


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
        if _QN_RE.match(v) or v.startswith("scip-") or "%3" in v:
            return v
        if not _QN_RE.match(v):
            raise ValueError(
                "qualified_name must be a dotted identifier, short name, or SCIP symbol"
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
    driver: Any | None = None,
    max_candidates: int = 15,
) -> tuple[str, str] | dict[str, Any]:
    """Disambiguate qualified_name → (short_name, resolved_qn).

    Returns error envelope dict for symbol_not_found / ambiguous_qualified_name.
    """
    short_name = decode_scip_short_name(qualified_name)
    can_try_short_name = (
        driver is not None
        and _needs_human_resolution(qualified_name)
        and bool(short_name)
    )

    if session is None:
        if can_try_short_name:
            return await _resolve_short_name(
                driver,
                requested_qualified_name=qualified_name,
                short_name=short_name,
                project=project,
                max_candidates=max_candidates,
            )
        return {
            "ok": False,
            "error_code": "cm_error",
            "requested_qualified_name": qualified_name,
            "message": "CM session not available for exact qualified_name resolution",
        }

    raw = await session.call_tool(
        "search_graph",
        arguments={
            "project": project,
            "qn_pattern": f".*{re.escape(qualified_name)}$",
            "label": "Function",
            "limit": 10,
        },
    )
    if raw.isError:
        if can_try_short_name:
            return await _resolve_short_name(
                driver,
                requested_qualified_name=qualified_name,
                short_name=short_name,
                project=project,
                max_candidates=max_candidates,
            )
        cm_msg = code_router.parse_cm_result(raw).get("_raw", "")
        return {
            "ok": False,
            "error_code": "cm_error",
            "requested_qualified_name": qualified_name,
            "message": f"CM error from search_graph: {cm_msg}",
        }
    data = code_router.parse_cm_result(raw)
    results = data.get("results", [])
    total = data.get("total", len(results))
    has_more = data.get("has_more", False)

    if not results:
        if can_try_short_name:
            return await _resolve_short_name(
                driver,
                requested_qualified_name=qualified_name,
                short_name=short_name,
                project=project,
                max_candidates=max_candidates,
            )
        return {
            "ok": False,
            "error_code": "symbol_not_found",
            "requested_qualified_name": qualified_name,
            "message": (
                f"qualified_name '{qualified_name}' not found in project "
                f"'{project}' (no Function node matches suffix)"
            ),
        }
    if len(results) > 1:
        count_phrase = f"at least {len(results)}" if has_more else f"{total}"
        return {
            "ok": False,
            "error_code": "ambiguous_qualified_name",
            "requested_qualified_name": qualified_name,
            "terminal": True,
            "message": (
                f"qn_pattern matched {count_phrase} symbols in project "
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
    max_candidates: int = Field(15, ge=1, le=50)


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

_QUERY_SYMBOL_BY_SHORT_NAME = """
MATCH (s:Symbol {group_id: $group_id, short_name: $short_name})
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


async def _query_symbol_candidates(
    driver: Any,
    query: str,
    **params: Any,
) -> list[dict[str, Any]]:
    async with driver.session() as session:
        result = await session.run(query, **params)
        rows = [dict(row) async for row in result]
    return _dedup_items(
        [row for row in rows if row.get("qualified_name")],
        key=lambda row: row["qualified_name"],
    )


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


def _short_name_candidates(row: dict[str, Any]) -> list[str]:
    qualified_name = str(row.get("qualified_name") or "")
    terminal_name = qualified_name.rsplit(".", 1)[-1] if "." in qualified_name else ""
    return [
        str(row.get("short_name") or ""),
        str(row.get("name") or ""),
        str(row.get("symbol") or ""),
        terminal_name,
        decode_scip_short_name(qualified_name),
    ]


def _filter_short_name_rows(
    rows: list[dict[str, Any]],
    short_name: str,
) -> list[dict[str, Any]]:
    folded_short_name = short_name.lower()
    matched: list[dict[str, Any]] = []
    for row in rows:
        candidates = [
            candidate for candidate in _short_name_candidates(row) if candidate
        ]
        resolved_short_name = next(
            (
                candidate
                for candidate in candidates
                if candidate.lower() == folded_short_name
            ),
            "",
        )
        if not resolved_short_name:
            continue
        matched.append(
            {
                **row,
                "name": row.get("name") or row.get("symbol") or resolved_short_name,
                "short_name": row.get("short_name") or resolved_short_name,
            }
        )
    return _dedup_items(matched, key=lambda row: row["qualified_name"])


def _ambiguous_name_envelope(
    *,
    requested_qualified_name: str,
    requested_short_name: str,
    project: str,
    rows: list[dict[str, Any]],
    max_candidates: int,
) -> dict[str, Any]:
    truncated = len(rows) > max_candidates
    matches = rows[:max_candidates]
    count_phrase = f"at least {max_candidates + 1}" if truncated else f"{len(matches)}"
    return {
        "ok": False,
        "error_code": "ambiguous_name",
        "requested_qualified_name": requested_qualified_name,
        "requested_short_name": requested_short_name,
        "terminal": True,
        "message": (
            f"short name '{requested_short_name}' matched {count_phrase} symbols "
            f"in project '{project}' — refine to uniquely identify"
        ),
        "matches": [
            {
                "qualified_name": row.get("qualified_name", ""),
                "file_path": row.get("file_path", ""),
            }
            for row in matches
        ],
    }


async def _resolve_short_name(
    driver: Any,
    *,
    requested_qualified_name: str,
    short_name: str,
    project: str,
    max_candidates: int,
) -> tuple[str, str] | dict[str, Any]:
    group_id = f"project/{project}"
    query_limit = max_candidates + 1
    queries = (
        (
            _QUERY_SYMBOL_BY_SHORT_NAME,
            {"group_id": group_id, "short_name": short_name, "limit": query_limit},
        ),
        (
            _QUERY_SYMBOL_BY_SHORT_NAME_FOLD,
            {"group_id": group_id, "short_name": short_name, "limit": query_limit},
        ),
        (
            _QUERY_SYMBOL_BY_SHORT_NAME_REGEX,
            {
                "group_id": group_id,
                "pattern": rf"(?i){re.escape(short_name)}.*",
                "limit": query_limit,
            },
        ),
        (
            _QUERY_SYMBOL_BY_SCIP_SHORT_NAME,
            {
                "group_id": group_id,
                "pattern": rf"(?i).*[0-9]+{re.escape(short_name)}[VCPOAES].*",
                "limit": query_limit,
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
        if not rows:
            continue
        if len(rows) > 1:
            return _ambiguous_name_envelope(
                requested_qualified_name=requested_qualified_name,
                requested_short_name=short_name,
                project=project,
                rows=rows,
                max_candidates=max_candidates,
            )
        row = rows[0]
        return row.get("short_name", short_name) or short_name, row["qualified_name"]

    return {
        "ok": False,
        "error_code": "symbol_not_found",
        "requested_qualified_name": requested_qualified_name,
        "message": f"short name '{short_name}' not found in project '{project}'",
    }


def _disambiguation_session_key(ctx: Context[Any, Any, Any] | None) -> str:
    if ctx is None:
        return "session:unknown"
    try:
        client_id = ctx.client_id
    except ValueError:
        client_id = None
    if client_id:
        return f"client:{client_id}"
    try:
        return f"session:{id(ctx.session)}"
    except ValueError:
        return "session:unknown"


def _apply_disambiguation_guard(
    disambig: dict[str, Any],
    *,
    ctx: Context[Any, Any, Any] | None,
    project: str,
) -> dict[str, Any]:
    from palace_mcp.mcp_server import (
        record_ambiguous_name_attempt,
        reset_ambiguous_name_attempts,
    )

    session_key = _disambiguation_session_key(ctx)
    if disambig.get("error_code") != "ambiguous_name":
        reset_ambiguous_name_attempts(session_key, project)
        return disambig
    if record_ambiguous_name_attempt(session_key, project):
        return {
            "ok": False,
            "error_code": "disambiguation_loop_detected",
            "requested_qualified_name": disambig.get("requested_qualified_name", ""),
            "terminal": True,
            "message": (
                f"Repeated ambiguous short-name lookups in project '{project}' "
                "detected. Retry with a full qualified_name."
            ),
        }
    return disambig


def _reset_disambiguation_guard(
    ctx: Context[Any, Any, Any] | None, project: str
) -> None:
    from palace_mcp.mcp_server import reset_ambiguous_name_attempts

    reset_ambiguous_name_attempts(_disambiguation_session_key(ctx), project)


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
        ctx: Context[Any, Any, Any] | None = None,
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

        resolved_project = _slug_to_cm_project(req.project or default_project)
        from palace_mcp.mcp_server import get_driver

        driver = get_driver()

        try:
            disambig = await _resolve_qn(
                session,
                req.qualified_name,
                resolved_project,
                driver=driver,
            )
        except Exception as e:
            handle_tool_error(e)
            raise  # unreachable; satisfies ruff RET503

        if isinstance(disambig, dict):
            return _apply_disambiguation_guard(
                disambig, ctx=ctx, project=_cm_project_to_slug(resolved_project)
            )
        short_name, resolved_qn = disambig
        _reset_disambiguation_guard(ctx, _cm_project_to_slug(resolved_project))
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
        max_candidates: int = 15,
        ctx: Context[Any, Any, Any] | None = None,
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
                max_candidates=max_candidates,
            )
        except ValidationError as e:
            return {
                "ok": False,
                "error_code": "validation_error",
                "requested_qualified_name": qualified_name,
                "message": str(e),
            }

        # default_project is in CM-form ('repos-gimle'); Neo4j IngestRun.project
        # stores the operator slug ('gimle'). Reverse-translate so the default-
        # fallback path matches what palace.ingest.run_extractor wrote.
        resolved_project = _cm_project_to_slug(req.project or default_project)

        # §5.2: resolve slug kind FIRST — bundle vs project vs none
        resolution = await _resolve_slug(driver, resolved_project)

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
            try:
                async with TantivyBridge(
                    tantivy_path, heap_size_mb=settings.palace_tantivy_heap_mb
                ) as bridge:
                    raw = await bridge.search_by_symbol_id_async(
                        sym_id, limit=req.max_results + 1
                    )
                occurrences_bundle = _dedup_items(
                    [
                        _decode_tantivy_occurrence(
                            r,
                            fallback_qualified_name=req.qualified_name,
                        )
                        for r in raw
                    ],
                    key=lambda occurrence: (
                        occurrence["qualified_name"],
                        occurrence["file_path"],
                        occurrence["line"],
                        occurrence["col_start"],
                        occurrence["col_end"],
                    ),
                )
                occurrences_bundle = occurrences_bundle[: req.max_results]
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
                "total_found": len(occurrences_bundle),
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
            try:
                disambig = await _resolve_qn(
                    cm_session,
                    req.qualified_name,
                    resolved_project,
                    driver=driver,
                    max_candidates=req.max_candidates,
                )
                if isinstance(disambig, dict):
                    if disambig.get("error_code") == "cm_error":
                        # CM is connected but search_graph failed (project not in CM graph).
                        # Fall back to literal QN instead of surfacing a CM infrastructure error.
                        resolved_qn = req.qualified_name
                    else:
                        return _apply_disambiguation_guard(
                            disambig, ctx=ctx, project=resolved_project
                        )
                else:
                    _short_name, resolved_qn = disambig
                _reset_disambiguation_guard(ctx, resolved_project)
            except Exception:
                logger.debug(
                    "CM symbol resolution failed for %s, using literal",
                    req.qualified_name,
                    exc_info=True,
                )
                resolved_qn = req.qualified_name  # fall back to literal
                _reset_disambiguation_guard(ctx, resolved_project)

        # Query Tantivy for occurrences
        sym_id = symbol_id_for(resolved_qn)
        tantivy_path = Path(settings.palace_tantivy_index_path)
        async with TantivyBridge(
            tantivy_path, heap_size_mb=settings.palace_tantivy_heap_mb
        ) as bridge:
            raw_results = await bridge.search_by_symbol_id_async(
                sym_id, limit=req.max_results + 1
            )
        occurrences: list[dict[str, Any]] = [
            _decode_tantivy_occurrence(
                r,
                fallback_qualified_name=resolved_qn,
            )
            for r in raw_results
        ]
        occurrences = _dedup_items(
            occurrences,
            key=lambda occurrence: (
                occurrence["qualified_name"],
                occurrence["file_path"],
                occurrence["line"],
                occurrence["col_start"],
                occurrence["col_end"],
            ),
        )
        truncated = len(occurrences) > req.max_results
        occurrences = occurrences[: req.max_results]

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
