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
from collections.abc import Callable
from typing import Any, Protocol

from mcp import ClientSession
from pydantic import BaseModel, Field, ValidationError, field_validator

from palace_mcp import code_router
from palace_mcp.errors import handle_tool_error


logger = logging.getLogger(__name__)

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
    session: ClientSession, qualified_name: str, project: str
) -> tuple[str, str] | dict[str, Any]:
    """Disambiguate qualified_name → (short_name, resolved_qn).

    Returns error envelope dict for symbol_not_found / ambiguous_qualified_name.
    """
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


_QUERY_INGEST_RUN = """
MATCH (r:IngestRun {project: $project, extractor_name: $extractor_name})
WHERE r.success = true
RETURN r.run_id AS run_id, r.success AS success, r.error_code AS error_code
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

        from palace_mcp.extractors.foundation.identifiers import symbol_id_for
        from palace_mcp.extractors.foundation.tantivy_bridge import TantivyBridge
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

        # State B: never-indexed — check for a successful IngestRun
        ingest_run = await _query_ingest_run_for_project(
            driver, resolved_project, "symbol_index_python"
        )
        if ingest_run is None:
            return {
                "ok": True,
                "occurrences": [],
                "total_found": 0,
                "warning": "project_not_indexed",
                "action_required": (
                    f"Run palace.ingest.run_extractor('symbol_index_python', "
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
        truncated = len(raw_results) > req.max_results
        raw_results = raw_results[: req.max_results]

        occurrences: list[dict[str, Any]] = [
            {
                "file_path": r["file_path"],
                "line": r["line"],
                "col_start": r["col_start"],
                "col_end": r["col_end"],
                "kind": r["kind"],
                "qualified_name": r.get("symbol_qualified_name", resolved_qn),
            }
            for r in raw_results
        ]

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
