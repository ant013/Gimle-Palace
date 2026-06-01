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
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from mcp import ClientSession
from pydantic import BaseModel, Field, ValidationError, field_validator

from palace_mcp import code_router
from palace_mcp.errors import handle_tool_error
from palace_mcp.extractors.foundation.identifiers import symbol_id_for
from palace_mcp.extractors.foundation.tantivy_bridge import TantivyBridge
from palace_mcp.memory.bundle import bundle_status


logger = logging.getLogger(__name__)

_SHORT_NAME_LABELS = ("Function", "Method", "Class")


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
    session: ClientSession,
    qualified_name: str,
    project: str,
    *,
    label: str | None = "Function",
) -> tuple[str, str] | dict[str, Any]:
    """Disambiguate qualified_name → (short_name, resolved_qn).

    Returns error envelope dict for symbol_not_found / ambiguous_qualified_name.
    Pass label=None to search all symbol types (Functions, Classes, Methods).
    """
    _sg_args: dict[str, Any] = {
        "project": project,
        "qn_pattern": f".*{re.escape(qualified_name)}$",
        "limit": 10,
    }
    if label is not None:
        _sg_args["label"] = label
    raw = await session.call_tool("search_graph", arguments=_sg_args)
    if raw.isError:
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
    match_source = "qn_pattern"

    if not results:
        fallback = await _resolve_short_name(session, qualified_name, project)
        if isinstance(fallback, dict):
            return fallback
        if not fallback:
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
        results = fallback
        total = len(results)
        has_more = False
        match_source = "short-name search"
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


async def _resolve_short_name(
    session: ClientSession,
    qualified_name: str,
    project: str,
) -> list[dict[str, Any]] | dict[str, Any]:
    safe_name = _escape_cypher_string(qualified_name)
    label_filter = " OR ".join(f"s:{label}" for label in _SHORT_NAME_LABELS)
    cypher = (
        "MATCH (s) "
        f"WHERE ({label_filter}) "
        f"AND toLower(s.name) = toLower('{safe_name}') "
        "RETURN s.name AS name, s.qualified_name AS qualified_name, "
        "coalesce(s.file_path, '') AS file_path "
        "ORDER BY s.qualified_name "
        "LIMIT 10"
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
            "requested_qualified_name": qualified_name,
            "message": f"CM error from query_graph: {cm_msg}",
        }
    data = code_router.parse_cm_result(raw)
    rows = data.get("rows", [])
    return [
        {
            "name": row[0],
            "qualified_name": row[1],
            "file_path": row[2] if len(row) > 2 else "",
        }
        for row in rows
        if len(row) >= 2
    ]


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
    total_found = len(tests)
    tests.sort(key=lambda c: c["hop"])  # KeyError on contract drift = fail loud
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


_DESC_SNIPPET_RICH = (
    "Rich context card for a symbol: source snippet, definition location, "
    "usages, code owners, hotspot score, and recent commits. "
    "Single call replaces get_code_snippet + find_references + find_owners + "
    "find_hotspots + git.log."
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
        if session is None:
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

        try:
            disambig = await _resolve_qn(session, req.qualified_name, resolved_project)
        except Exception as e:
            handle_tool_error(e)
            raise  # unreachable; satisfies ruff RET503

        if isinstance(disambig, dict):
            return disambig
        short_name, resolved_qn = disambig

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
                occurrences_bundle = _decode_unique_occurrences(
                    raw,
                    fallback_qualified_name=req.qualified_name,
                    symbol_id=sym_id,
                )[: req.max_results]
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
        if cm_session is not None:
            try:
                disambig = await _resolve_qn(
                    cm_session, req.qualified_name, resolved_project
                )
                if isinstance(disambig, dict):
                    if disambig.get("error_code") == "cm_error":
                        # CM is connected but search_graph failed (project not in CM graph).
                        # Fall back to literal QN instead of surfacing a CM infrastructure error.
                        resolved_qn = req.qualified_name
                    else:
                        return disambig  # symbol_not_found or ambiguous_qualified_name
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
            raw_results = await bridge.search_by_symbol_id_async(
                sym_id, limit=req.max_results + 1
            )
        occurrences = _decode_unique_occurrences(
            raw_results,
            fallback_qualified_name=resolved_qn,
            symbol_id=sym_id,
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

        # CM uses repos-<slug>; Neo4j IngestRun.project and find_owners use plain slug
        cm_project = _slug_to_cm_project(req.project or default_project)
        neo4j_slug = _cm_project_to_slug(req.project or default_project)

        # Step 1: Resolve qualified_name — all symbol types (F1 fix: label=None)
        try:
            disambig = await _resolve_qn(
                session, req.qualified_name, cm_project, label=None
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
