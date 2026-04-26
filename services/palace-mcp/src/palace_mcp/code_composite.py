"""palace.code.* composite (orchestrated) tools.

Distinct from code_router.py which only exposes raw passthroughs to CM.
Composites here build their behaviour on top of multiple CM calls.

Schema strategy: composite tools use FastMCP's closed schema (Pydantic-derived
from typed signature) — distinct from passthroughs which use open _OpenArgs
schema for flat-arg propagation (GIM-89). Composites have a fixed contract
owned by us; closed schema is correct for v1.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any, Protocol

from mcp import ClientSession
from pydantic import BaseModel, Field, ValidationError, field_validator

from palace_mcp import code_router
from palace_mcp.errors import handle_tool_error


_QN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*(\.[A-Za-z_][A-Za-z0-9_-]*)*$")


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
        return {"ok": False, "error_code": "cm_error", "requested_qualified_name": qualified_name, "message": f"CM error from search_graph: {cm_msg}"}
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
        return {"ok": False, "error_code": "cm_error", "requested_qualified_name": requested_qn, "message": f"CM error from query_graph: {cm_msg}"}
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
        return {"ok": False, "error_code": "cm_error", "requested_qualified_name": requested_qn, "message": f"CM error from trace_call_path: {cm_msg}"}
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

        resolved_project = req.project or default_project

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
