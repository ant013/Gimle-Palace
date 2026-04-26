---
slug: GIM-98-palace-code-test-impact
status: rev4 (hybrid design — default Cypher TESTS edge, opt-in trace_call_path; convergent reviewer findings applied)
branch: feature/GIM-98-palace-code-test-impact
paperclip_issue: 98
predecessor: 1f7c8f2 (develop tip after GIM-97 merge)
date: 2026-04-26
parent_initiative: N+2 Category 1 (USE-BUILT)
sequence_position: 4 of 4 — palace.code.test_impact composite tool
related: GIM-95 (decide), GIM-96 (prime foundation), GIM-97 (cookbooks)
---

# GIM-98 — `palace.code.test_impact` — find tests exercising a symbol

## Goal

Ship a composite MCP tool that, given a Function's `qualified_name`, returns the list of test functions that exercise it. Default path uses a direct Cypher query over `:TESTS` edges (homonym-immune, hop=1 only). Opt-in `include_indirect=True` falls back to `palace.code.trace_call_path` for multi-hop coverage with a documented homonym caveat.

**Use case:** PE about to refactor `register_code_tools` calls
`palace.code.test_impact("repos-gimle.services.palace-mcp.src.palace_mcp.code_router.register_code_tools")`
→ gets list of test functions to focus on. Saves blind running of full pytest suite.

## Sequence

Slice 4 of 4 in N+2 Category 1 (USE-BUILT). Final slice in this category — after this lands, all 4 USE-BUILT tools are shipped.

1. `palace.memory.decide` — GIM-95 ✅ merged
2. `palace.memory.prime` foundation — GIM-96 ✅ merged
3. `palace.memory.prime` 5 cookbooks — GIM-97 ✅ merged
4. **`palace.code.test_impact` — this slice** (final USE-BUILT)

Slice 5 (`palace.code.semantic_search`) is deferred — separate follow-up if pursued.

## Hard dependencies

- N+1a Codebase-Memory MCP (GIM-76) — ✅ landed
- `palace.code.query_graph` (post-GIM-89 fix) — ✅ landed (used for default Cypher path)
- `palace.code.search_graph` (post-GIM-89 fix) — ✅ landed (disambiguation only)
- `palace.code.trace_call_path` (post-GIM-89 fix) — ✅ landed (opt-in path only)

## Non-goals

- Semantic search (NL → tests) — separate slice
- Test runtime / coverage instrumentation — out of scope
- Test outcomes / pass-fail history — out of scope
- Cross-project test queries — out of scope
- Mutation testing or test smell detection — out of scope

## CM contract — pinned by 2026-04-26 live spike

This section pins the **literal request/response shapes** of CM tools we depend on. All shapes verified against:
- Local CM (DeusData v0.6 stdio MCP)
- Docker CM (palace-mcp `palace.code.*` against `http://localhost:8080/mcp` on iMac with `project="repos-gimle"`)

Any future drift breaks Task 6 contract test.

### `palace.code.search_graph`

Both `name_pattern` (matches against `Function.name`) and `qn_pattern` (regex matched against `Function.qualified_name`) parameters exist independently. Spec uses `qn_pattern` for suffix-anchored match (disambiguation step).

**Request:**
```json
{
  "project": "repos-gimle",
  "qn_pattern": ".*module\\.path\\.symbol_name$",
  "label": "Function",
  "limit": 10
}
```

**Response (success):**
```json
{
  "total": 1,
  "results": [
    {
      "name": "register_code_tools",
      "qualified_name": "repos-gimle.services.palace-mcp.src.palace_mcp.code_router.register_code_tools",
      "label": "Function",
      "file_path": "services/palace-mcp/src/palace_mcp/code_router.py",
      "in_degree": 12,
      "out_degree": 2
    }
  ],
  "has_more": false
}
```

**Response (no match):** `{"total": 0, "results": [], "has_more": false}` — graceful, NOT an error.

### `palace.code.query_graph`

Used by **default path** (Cypher TESTS edge query) — no parameter substitution; we build literal Cypher from validated input.

**Request:**
```json
{
  "project": "repos-gimle",
  "query": "MATCH (test)-[:TESTS]->(target) WHERE target.qualified_name = '<exact_qn>' RETURN test.name AS name, test.qualified_name AS qualified_name ORDER BY test.qualified_name LIMIT 51"
}
```

**Response:**
```json
{
  "columns": ["name", "qualified_name"],
  "rows": [
    ["test_decorator_receives_all_names", "repos-gimle...test_code_router.TestToolRegistration.test_decorator_receives_all_names"]
  ],
  "total": 1
}
```

Quirks discovered during spike:
- Multi-column return is reliable for `RETURN x AS a, y AS b` form (tested with 2 columns OK)
- **Aggregation queries (`count(*)`, `labels()[0]`) return broken output** — avoid in our queries
- Empty match → `{"columns": [...], "rows": [], "total": 0}` (graceful)

### `palace.code.trace_call_path`

Used by **opt-in path** when `include_indirect=True`.

**Request:**
```json
{
  "project": "repos-gimle",
  "function_name": "register_code_tools",
  "direction": "inbound",
  "depth": 3,
  "include_tests": true
}
```

Notes:
- `function_name` accepts the **short symbol name only** — full QN returns `"function not found"` (verified via spike).
- `direction`: `"inbound"` | `"outbound"` | `"both"`
- `depth`: traversal depth (NOT `max_hops`)
- `include_tests=true`: test functions appear in `callers`, marked with `is_test: true`. When `false`, tests are excluded.

**Response (success):**
```json
{
  "function": "register_code_tools",
  "direction": "inbound",
  "callers": [
    {
      "name": "test_x",
      "qualified_name": "repos-gimle...test_x",
      "hop": 1,
      "is_test": true
    },
    {
      "name": "_cli",
      "qualified_name": "repos-gimle...._cli",
      "hop": 2
    }
  ]
}
```

Notes:
- Hop field is `hop` (integer)
- `is_test: true` marker present at any hop where CM classifies caller as a test (verified up to hop=2 in spike)
- Non-test callers have **no `is_test` key** at all (use `c.get("is_test")` for falsy default)
- ⚠ `function_name` accepts only short name — homonym risk: traces callers of EVERY symbol in graph with that short name (see Algorithm Step 4b for caveat)

**Known limitation (homonym):** If `function_name="decide"` matches multiple distinct functions in the graph, `trace_call_path` returns callers of all of them — there is no `qualified_name` parameter for disambiguation. The default path (Cypher TESTS edge with exact `qualified_name = '...'` match) is homonym-immune. Opt-in path inherits the limitation; output flags `disambiguation_caveat: "trace uses short-name; collisions possible"` when `include_indirect=True`.

### Project slug

Live spike confirmed docker CM uses path-based slug: **`repos-gimle`** (from bind-mount `/repos/gimle`). Local CM uses different slug — irrelevant for the docker-deployed tool.

## Architecture

### MCP tool signature

```python
@_tool(
    name="palace.code.test_impact",
    description=(
        "Given a Function's qualified_name, return tests that exercise it. "
        "Default: direct :TESTS edge query (hop=1, homonym-immune). "
        "include_indirect=True: trace_call_path inbound + is_test filter "
        "(multi-hop, but homonym caveat applies). "
        "Use to focus pytest invocation on tests exercising a specific symbol "
        "before refactoring or debugging."
    ),
)
async def palace_code_test_impact(
    qualified_name: str,
    project: str | None = None,
    include_indirect: bool = False,
    max_hops: int = 3,
    max_results: int = 50,
) -> dict[str, Any]:
    ...
```

### Algorithm

1. **Validate** input via Pydantic `TestImpactRequest`. Tighter qualified_name regex (no leading digit/hyphen). Reject empty `qualified_name`, out-of-range `max_hops` (1..5) / `max_results` (1..200).
2. **Resolve project**: if `project is None`, default to `Settings.cm_default_project` (env-overridable; defaults to `"repos-gimle"`).
3. **Capture session reference once**: `session = code_router.get_cm_session()` (single read; if None → `handle_tool_error`). Pass `session` (local) into helpers — TOCTOU-immune.
4. **Disambiguate** via `search_graph(qn_pattern=f".*{re.escape(qualified_name)}$", label="Function", limit=10, project=…)`.
   - 0 results → `error_code="symbol_not_found"`.
   - >1 results → `error_code="ambiguous_qualified_name"` envelope. `matches: [...]` includes ALL up-to-10 results; if `has_more=True`, append `"matched at least 10 symbols (showing 10)"` to message; otherwise exact count.
   - 1 result → extract `name` (short, opt-in path only) and `qualified_name` (canonical).
5. **Branch on `include_indirect`:**

   **5a. Default path (`include_indirect=False`) — Cypher TESTS edge:**
   ```python
   cypher = (
       f"MATCH (test)-[:TESTS]->(target) "
       f"WHERE target.qualified_name = '{resolved_qn}' "
       f"RETURN test.name AS name, test.qualified_name AS qualified_name "
       f"ORDER BY test.qualified_name "
       f"LIMIT {max_results + 1}"
   )
   result = await session.call_tool("query_graph", {"project": project, "query": cypher})
   ```
   - Single Cypher, `qualified_name = '...'` exact match → no homonym risk
   - `total_found` = `len(rows)` if not truncated else `max_results + 1` (a "≥" lower bound)
   - All hop=1 implicitly (TESTS edge is direct relationship)

   **5b. Opt-in path (`include_indirect=True`) — trace_call_path:**
   ```python
   tcp = await session.call_tool("trace_call_path", {
       "project": project,
       "function_name": short_name,
       "direction": "inbound",
       "depth": max_hops,
       "include_tests": True,
   })
   tests = [c for c in tcp["callers"] if c.get("is_test")]
   total_found = len(tests)  # before truncation
   tests.sort(key=lambda c: c["hop"])  # ascending; KeyError on contract drift = good
   ```
   - Output **must** include `disambiguation_caveat: "trace uses short-name; collisions possible"` to make the limitation visible to the caller.

6. **Truncate**: `truncated = total_found > max_results`; `tests = tests[:max_results]`.
7. **Return** structured result with `requested_qualified_name` (input echo) and `qualified_name` (resolved canonical).

### Output schema

```json
{
  "ok": true,
  "requested_qualified_name": "<input from caller>",
  "qualified_name": "<canonical resolved QN>",
  "project": "repos-gimle",
  "method": "tests_edge",
  "tests": [
    {
      "name": "test_decorator_receives_all_names",
      "qualified_name": "repos-gimle...TestToolRegistration.test_decorator_receives_all_names",
      "hop": 1
    }
  ],
  "total_found": 12,
  "max_hops_used": null,
  "truncated": false
}
```

When `include_indirect=True`:
```json
{
  "ok": true,
  "requested_qualified_name": "register_code_tools",
  "qualified_name": "repos-gimle...code_router.register_code_tools",
  "project": "repos-gimle",
  "method": "trace_call_path",
  "disambiguation_caveat": "trace uses short-name; collisions possible",
  "tests": [
    {"name": "test_x", "qualified_name": "...", "hop": 1},
    {"name": "test_y", "qualified_name": "...", "hop": 2}
  ],
  "total_found": 7,
  "max_hops_used": 3,
  "truncated": false
}
```

Field notes:
- `requested_qualified_name`: exact input echo (observability — analytics, debugging)
- `qualified_name`: canonical resolved (what we actually queried)
- `method`: `"tests_edge"` | `"trace_call_path"` — which path produced the result
- `max_hops_used`: integer when method is `trace_call_path`; `null` when method is `tests_edge`
- `disambiguation_caveat`: present **only** in opt-in path output

If symbol doesn't exist:
```json
{
  "ok": false,
  "error_code": "symbol_not_found",
  "requested_qualified_name": "<input>",
  "message": "qualified_name '<x>' not found in project '<y>' (no Function node matches suffix)"
}
```

If ambiguous (real CM `total` echoed):
```json
{
  "ok": false,
  "error_code": "ambiguous_qualified_name",
  "requested_qualified_name": "<input>",
  "message": "qn_pattern matched 7 symbols in project 'repos-gimle' — refine to uniquely identify",
  "matches": [
    {"qualified_name": "...", "file_path": "..."},
    ...
  ]
}
```

If no tests exercise the symbol (NOT an error):
```json
{
  "ok": true,
  "requested_qualified_name": "<input>",
  "qualified_name": "<resolved>",
  "project": "repos-gimle",
  "method": "tests_edge",
  "tests": [],
  "total_found": 0,
  "max_hops_used": null,
  "truncated": false
}
```

### Error model

- Validation errors → envelope `{"ok": false, "error_code": "validation_error", "message": ...}`
- Symbol not found → envelope `{"ok": false, "error_code": "symbol_not_found", ...}`
- Ambiguous QN → envelope `{"ok": false, "error_code": "ambiguous_qualified_name", "matches": [...]}`
- Unknown project → envelope `{"ok": false, "error_code": "unknown_project", ...}` (CM-side error surfaced)
- Infrastructure failures (CM session None, transport error, unexpected exception) → `handle_tool_error(exc)` raises (verified `NoReturn` per `services/palace-mcp/src/palace_mcp/errors.py:108`)

## Tasks

| # | Task | Owner | Deps |
|---|---|---|---|
| 1 | Pydantic input model `TestImpactRequest` (tightened qualified_name regex, max_hops 1..5, max_results 1..200, `include_indirect: bool = False`) | PE | — |
| 2 | Implementation in `services/palace-mcp/src/palace_mcp/code_composite.py` (single new file alongside `code_router.py` — flat structure until 2nd composite ships) | PE | T1 |
| 3 | Add `get_cm_session()` accessor to `code_router.py`; extract `parse_cm_result` helper from `_forward` to module-level util reused by `code_composite.py` | PE | — |
| 4 | MCP tool registration via `register_code_composite_tools(_tool, default_project)` in `code_composite.py`; wired in `mcp_server.py` lifespan after `register_code_tools` | PE | T2, T3 |
| 5 | Unit tests covering both paths — mock `_cm_session.call_tool`; happy path each path, all error envelopes, truncation, sort stability, homonym caveat presence | PE | T2 |
| 6 | Integration test through real MCP HTTP+SSE (per GIM-91): default + opt-in paths, ambiguity, not-found | PE | T4 |
| 7 | CM contract test pinning literal `search_graph`, `query_graph`, `trace_call_path` shapes — fail loudly if CM lib version drifts | PE | T4 |
| 8 | Update `services/palace-mcp/README.md` with usage example (both paths) | PE | T2 |
| 9 | QA Phase 4.1 — operator runs against known function on iMac docker stack, both paths | QA | T1-T8 |

### Task 1 — TestImpactRequest

```python
import re
from pydantic import BaseModel, Field, field_validator

# Python qualified name shape: identifier components joined by '.', allowing
# slug-style component names (e.g. "palace-mcp"). Reject leading digit/hyphen
# at component boundaries.
_QN_RE = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_-]*(\.[A-Za-z_][A-Za-z0-9_-]*)*$"
)


class TestImpactRequest(BaseModel):
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
```

### Task 2 — implementation

`services/palace-mcp/src/palace_mcp/code_composite.py` (new, single file, sibling of `code_router.py`):

```python
"""palace.code.* composite (orchestrated) tools.

Distinct from code_router.py which only exposes raw passthroughs to CM.
Composites here build their behaviour on top of multiple CM calls.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any, Protocol

from mcp import ClientSession
from pydantic import BaseModel, Field, ValidationError, field_validator

from palace_mcp import code_router
from palace_mcp.errors import handle_tool_error


_QN_RE = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_-]*(\.[A-Za-z_][A-Za-z0-9_-]*)*$"
)


class TestImpactRequest(BaseModel):
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


async def _test_impact_tests_edge(
    session: ClientSession,
    requested_qn: str,
    resolved_qn: str,
    project: str,
    max_results: int,
) -> dict[str, Any]:
    """Default path — direct Cypher over :TESTS edge."""
    cypher = (
        f"MATCH (test)-[:TESTS]->(target) "
        f"WHERE target.qualified_name = '{resolved_qn}' "
        f"RETURN test.name AS name, test.qualified_name AS qualified_name "
        f"ORDER BY test.qualified_name "
        f"LIMIT {max_results + 1}"
    )
    raw = await session.call_tool(
        "query_graph",
        arguments={"project": project, "query": cypher},
    )
    data = code_router.parse_cm_result(raw)
    rows = data.get("rows", [])
    truncated = len(rows) > max_results
    rows = rows[:max_results]
    tests = [{"name": r[0], "qualified_name": r[1], "hop": 1} for r in rows]
    total_found = len(rows) + (1 if truncated else 0)  # lower-bound when truncated
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


async def _resolve_qn(
    session: ClientSession, qualified_name: str, project: str
) -> tuple[str, str] | dict[str, Any]:
    """Disambiguate qualified_name → (short_name, resolved_qn).

    Returns dict envelope for symbol_not_found / ambiguous_qualified_name.
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
        count_phrase = (
            f"at least {len(results)}" if has_more else f"{total}"
        )
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
        # H3 fix — capture session once into local; immune to concurrent stop_cm
        session = code_router.get_cm_session()
        if session is None:
            handle_tool_error(
                RuntimeError("CM subprocess not started — set CODEBASE_MEMORY_MCP_BINARY")
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
```

### Task 3 — code_router.py additions

Add to existing `code_router.py`:

```python
def get_cm_session() -> ClientSession | None:
    """Public accessor — returns current CM session, None if not started.

    Use from composite tools to read the session at invocation time
    (avoids None-at-import-time of direct imports).
    """
    return _cm_session


def parse_cm_result(result: Any) -> dict[str, Any]:
    """Parse MCP CallToolResult → dict; replaces inline logic in _forward.

    Public so composite tools (code_composite.py) can reuse the same
    result-extraction semantics without duplicating the pattern.
    """
    if result.structuredContent is not None:
        return dict(result.structuredContent)
    for block in result.content:
        if isinstance(block, TextContent):
            try:
                parsed = json.loads(block.text)
                return parsed if isinstance(parsed, dict) else {"_raw": parsed}
            except json.JSONDecodeError:
                return {"_raw": block.text}
    return {}
```

Refactor `_forward` to use `parse_cm_result` (no behaviour change).

### Task 4 — registration wiring

In `mcp_server.py`, alongside existing `register_code_tools`:

```python
from palace_mcp.code_composite import register_code_composite_tools

register_code_tools(_tool, mcp)
register_code_composite_tools(_tool, default_project=settings.cm_default_project)
```

`Settings.cm_default_project: str = "repos-gimle"` — added to `palace_mcp/config.py` (env override `PALACE_CM_DEFAULT_PROJECT`).

**Schema strategy decision:** composite tools use FastMCP's **closed schema** (Pydantic-derived from typed signature) — distinct from passthroughs which use the open `_OpenArgs` schema for flat-arg propagation (GIM-89 requirement). Composites have a fixed contract owned by us; closed schema is correct for v1. Documented in `code_composite.py` module docstring. If a future composite needs open-schema, opt-in by passing `mcp_instance` and patching as in `code_router._patch_tool_open_schema`.

### Task 5 — unit tests

`tests/test_code_composite.py`:

Default-path branches:
1. **validation_error** — `qualified_name=""`, `qualified_name="0bad"`, `qualified_name="bad name"`, `max_hops=10`, `max_results=0`
2. **symbol_not_found** — search_graph returns `{"results": []}` → envelope; verify `requested_qualified_name` echoed
3. **ambiguous (count exact)** — search_graph returns 3 results, `has_more=False` → message says "matched 3 symbols"
4. **ambiguous (count lower-bound)** — search_graph returns 10 results, `has_more=True` → message says "at least 10"
5. **happy path tests_edge** — search_graph returns 1 match; query_graph returns 3 rows → tests array has 3 entries with `hop: 1`, `method: "tests_edge"`, no `disambiguation_caveat`
6. **truncation tests_edge** — query_graph returns `max_results + 1` rows → `truncated: true`, `total_found = max_results + 1` (lower-bound)
7. **empty result tests_edge** — query_graph returns `{"rows": []}` → `tests: []`, `total_found: 0`, `ok: true`
8. **resolved QN echo** — caller passes short suffix, search_graph resolves to long QN → output `qualified_name` is the long one, `requested_qualified_name` is the short suffix

Opt-in path branches:
9. **happy path trace_call_path** — search resolves; trace returns mixed (test + non-test) callers at hop 1 + 2 → tests filtered to is_test only, sorted by hop, `method: "trace_call_path"`, `disambiguation_caveat` present, `max_hops_used: 3`
10. **trace path empty** — trace returns `{"callers": []}` → `tests: []`, `caveat` still present (always set when method=trace)
11. **truncation trace path** — 7 testers, max_results=3 → truncated, `total_found: 7` (exact, computed before truncation)
12. **infrastructure failure** — `_cm_session` is None → `handle_tool_error` raises (pytest.raises)

Mock pattern (uses DI accessor — F9 Python-pro fix):

```python
def test_happy_path_tests_edge(monkeypatch):
    fake_session = AsyncMock()
    fake_session.call_tool = AsyncMock(side_effect=[
        _make_result({  # search_graph response
            "total": 1, "has_more": False,
            "results": [{"name": "decide", "qualified_name": "...decide", "file_path": "..."}],
        }),
        _make_result({  # query_graph response
            "columns": ["name", "qualified_name"],
            "rows": [
                ["test_a", "...test_a"],
                ["test_b", "...test_b"],
            ],
            "total": 2,
        }),
    ])
    # Patch via the public accessor (DI-style) — no module-attr reach-through
    monkeypatch.setattr(
        "palace_mcp.code_router.get_cm_session", lambda: fake_session
    )
    ...
```

### Task 6 — integration test

`tests/integration/test_palace_code_test_impact_wire.py`:

```python
async def test_test_impact_default_path(mcp_url):
    async with streamablehttp_client(mcp_url) as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()
            result = await s.call_tool("palace.code.test_impact", arguments={
                "qualified_name": "register_code_tools",
                "project": "repos-gimle",
            })
            payload = json.loads(result.content[0].text)
            assert payload["ok"] is True
            assert payload["method"] == "tests_edge"
            assert payload["max_hops_used"] is None
            assert "disambiguation_caveat" not in payload
            assert payload["tests"], "register_code_tools is exercised by tests"
            for t in payload["tests"]:
                assert "test" in t["qualified_name"].lower(), (
                    f"non-test in tests_edge result: {t['qualified_name']}"
                )
                assert t["hop"] == 1


async def test_test_impact_opt_in_indirect(mcp_url):
    async with streamablehttp_client(mcp_url) as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()
            result = await s.call_tool("palace.code.test_impact", arguments={
                "qualified_name": "register_code_tools",
                "project": "repos-gimle",
                "include_indirect": True,
                "max_hops": 3,
            })
            payload = json.loads(result.content[0].text)
            assert payload["ok"] is True
            assert payload["method"] == "trace_call_path"
            assert payload["disambiguation_caveat"] == "trace uses short-name; collisions possible"
            assert payload["max_hops_used"] == 3


async def test_test_impact_not_found(mcp_url):
    async with streamablehttp_client(mcp_url) as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()
            result = await s.call_tool("palace.code.test_impact", arguments={
                "qualified_name": "nonexistent_function_xyz_abc",
                "project": "repos-gimle",
            })
            payload = json.loads(result.content[0].text)
            assert payload["ok"] is False
            assert payload["error_code"] == "symbol_not_found"
            assert payload["requested_qualified_name"] == "nonexistent_function_xyz_abc"


async def test_test_impact_validation(mcp_url):
    async with streamablehttp_client(mcp_url) as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()
            result = await s.call_tool("palace.code.test_impact", arguments={
                "qualified_name": "bad name with spaces",
                "project": "repos-gimle",
            })
            payload = json.loads(result.content[0].text)
            assert payload["ok"] is False
            assert payload["error_code"] == "validation_error"
```

### Task 7 — CM contract test

`tests/code_composite/test_cm_contract.py`:

```python
async def test_search_graph_qn_pattern_works(cm_session):
    """qn_pattern must match Function.qualified_name as regex."""
    result = await cm_session.call_tool("search_graph", {
        "project": "repos-gimle",
        "qn_pattern": ".*\\.register_code_tools$",
        "label": "Function",
        "limit": 5,
    })
    data = parse_cm_result(result)
    assert data["results"], "register_code_tools must be in repos-gimle index"
    first = data["results"][0]
    for k in ("name", "qualified_name", "label", "file_path"):
        assert k in first, f"CM contract drift: missing {k} in search_graph result"
    assert first["qualified_name"].endswith(".register_code_tools")


async def test_trace_call_path_marks_tests(cm_session):
    """is_test=true must be set on test callers (semantic anchor, not just structure)."""
    result = await cm_session.call_tool("trace_call_path", {
        "project": "repos-gimle",
        "function_name": "register_code_tools",
        "direction": "inbound",
        "depth": 2,
        "include_tests": True,
    })
    data = parse_cm_result(result)
    assert "callers" in data
    test_callers = [c for c in data["callers"] if c.get("is_test")]
    assert test_callers, "register_code_tools is tested → ≥1 is_test caller expected"
    for c in test_callers:
        assert isinstance(c["hop"], int) and c["hop"] >= 1
        assert c["qualified_name"].lower().count("test") >= 1
    # Anchor: at least one non-test caller has NO is_test key (not False)
    non_test = [c for c in data["callers"] if not c.get("is_test")]
    if non_test:
        assert "is_test" not in non_test[0], (
            "CM marker convention drift: non-test callers should not have is_test key"
        )


async def test_query_graph_tests_edge_match(cm_session):
    """:TESTS edge with exact qualified_name match returns hop-1 testers."""
    cypher = (
        "MATCH (test)-[:TESTS]->(target) "
        "WHERE target.qualified_name CONTAINS 'register_code_tools' "
        "RETURN test.name AS name, test.qualified_name AS qn LIMIT 5"
    )
    result = await cm_session.call_tool("query_graph", {
        "project": "repos-gimle", "query": cypher,
    })
    data = parse_cm_result(result)
    assert "rows" in data and "columns" in data
    assert data["rows"], "TESTS edge must exist for register_code_tools"
```

Header constant `LAST_VERIFIED_CM_VERSION = "<commit sha of CM lib at spike date>"` documents the contract pin date.

### Task 8 — README example

```markdown
### palace.code.test_impact

Find tests exercising a Function (composite tool).

```
# Default — direct :TESTS edge query (hop=1, exact, fast)
palace.code.test_impact(
  qualified_name="repos-gimle.services.palace-mcp.src.palace_mcp.code_router.register_code_tools",
  project="repos-gimle",
)

# Opt-in — multi-hop via trace_call_path (homonym caveat applies)
palace.code.test_impact(
  qualified_name="register_code_tools",
  include_indirect=True,
  max_hops=3,
)
```

Use to focus pytest before refactoring.
```

### Task 9 — QA Phase 4.1 live smoke

Operator-driven on iMac:

1. `docker compose --profile review up -d --build --wait`
2. Auth-path probe per GIM-94 Step 5
3. **Default path happy:** `palace.code.test_impact(qualified_name="register_code_tools", project="repos-gimle")` → `ok: true, method: "tests_edge", tests: [...]` with ≥1 entry, all `hop: 1`, no caveat
4. **Opt-in path happy:** same call with `include_indirect: true, max_hops: 3` → `ok: true, method: "trace_call_path", disambiguation_caveat` present
5. **Ambiguous (deterministic):** pre-flight `palace.code.search_graph(name_pattern="...", limit=20)` to find a known-ambiguous suffix in the indexed graph; use that → `error_code: ambiguous_qualified_name, matches: [≥2]`
6. **Not found:** `qualified_name="nonexistent_function_xyz_abc"` → `error_code: symbol_not_found`
7. **Validation:** `qualified_name="bad name with spaces"` → `error_code: validation_error`
8. Verify integration tests (Task 6) + contract tests (Task 7) pass in pytest run on iMac
9. Restore production checkout to develop (per worktree-discipline.md)

## Acceptance

1. Tool callable via real MCP HTTP+SSE; default path returns `ok: true, method: "tests_edge", tests: [...]` for known-tested symbol
2. `include_indirect=true` returns `ok: true, method: "trace_call_path", disambiguation_caveat: ...`
3. Empty result is NOT an error — `ok: true, total_found: 0`
4. Symbol not found → envelope `error_code: symbol_not_found`, `requested_qualified_name` echoed
5. Ambiguous QN → envelope `error_code: ambiguous_qualified_name, matches: [...]` with ALL up-to-10 results
6. Validation errors → envelope `error_code: validation_error`
7. Infrastructure errors raise via `handle_tool_error` (FastMCP `isError=true`); explicit `raise` after the call satisfies ruff RET503
8. Default path uses Cypher TESTS edge with **exact** `qualified_name = '...'` match — no homonym risk
9. Opt-in path tags result with `disambiguation_caveat` to make the limitation visible
10. `requested_qualified_name` field present in every response (success + error envelopes)
11. `total_found` in opt-in path computed BEFORE truncation; in default path is lower-bound when truncated
12. CM contract test (Task 7) pins `qn_pattern`, `is_test` marker convention, and TESTS edge — fails loudly on drift
13. `code_router.get_cm_session()` accessor + `parse_cm_result` utility extracted; `_forward` uses the same `parse_cm_result`
14. Pattern #21 dedup-aware registration via `_ToolDecorator` Protocol — `palace.code.test_impact` appears in `tools/list` exactly once
15. TOCTOU-safe — session captured once; concurrent `stop_cm_subprocess` cannot null it mid-call

## Out of scope (defer)

- `include_indirect=True` post-filter to confirm calls reach `resolved_qn` (eliminates homonym in opt-in path) — adds Cypher round-trip; defer until users hit collision
- Configurable `is_test` detection — v1 trusts CM's marking
- Test outcome / coverage data — separate slice
- Reverse direction (tests covered by this test) — semantic_search fits better
- Cross-project queries — defer until federation
- `palace.code.semantic_search` — Slice 5 candidate
- Refactor `code_composite.py` into a package — wait for 2nd composite

## Decisions recorded (rev4)

Rev3 → rev4 changes driven by 2-reviewer adversarial round (Architect + Python-pro):

| # | Change | Driver |
|---|---|---|
| D13 | Hybrid algorithm: default Cypher TESTS edge, opt-in `include_indirect=True` for trace_call_path | Architect F5 — short-name homonym in `trace_call_path` is silent correctness bug. Default safe; opt-in with caveat |
| D14 | Output `method: "tests_edge"`/"trace_call_path" + `disambiguation_caveat` (only when method=trace) | Make limitation visible in response, not buried in spec |
| D15 | `requested_qualified_name` field added to all responses | Architect F10 — observability win, free |
| D16 | search_graph `limit=2` → `limit=10`; ambiguous message echoes real CM `total` (or "at least N" when has_more) | Architect F4 — limit=2 truncates context with misleading count |
| D17 | TOCTOU fix — capture `code_router.get_cm_session()` once into local; pass to helpers | Python-pro F1 — module global re-read between guard and use was racey |
| D18 | New `get_cm_session()` accessor + `parse_cm_result` shared utility on `code_router.py` | Architect F3 (cleaner late-binding) + Python-pro F4 (de-dup `_parse_cm_result`) |
| D19 | `code/composite/` directory → flat `code_composite.py` (single file) | Architect F7 — premature package for one tool; flatten until 2nd composite |
| D20 | Tighter qualified_name regex `^[A-Za-z_][...]*(\.[...]*)*$` | Python-pro F3 — accepts only valid Python dotted names |
| D21 | `_ToolDecorator` Protocol for `tool_decorator` parameter | Python-pro F5 — Pattern #21 dedup needs identity, not just shape |
| D22 | `c["hop"]` (no `.get(default)`) — KeyError on contract drift = fail-loud | Python-pro F6 — defensive default contradicts contract |
| D23 | Explicit `raise` after `handle_tool_error(e)` to satisfy ruff RET503 | Python-pro F2 — ruff RET503 may flag implicit None return |
| D24 | Composite tool uses FastMCP closed schema (typed signature); decision documented in code | Architect F2 — explicit, contrasted with passthrough's open schema |
| D25 | Task 7 contract test pins semantic anchors (is_test marker present on test caller; absent key on non-test) | Architect F6 — structural-only assertions don't catch convention drift |
| D26 | Task 6 contract test uses `qn_pattern` (was `name_pattern` in rev3 — internal contradiction) | Python-pro F7 — direct internal consistency fix |
| D27 | Phase 4.1 ambiguity smoke uses pre-flight `search_graph` to find deterministic ambiguous suffix | Architect F8 — `qualified_name="main"` was probabilistic; replace with discovery step |

Decisions kept from rev3:
- D2 (`direction`/`depth`/`hop`/`is_test` field names)
- D6 (`total_found` before truncation in opt-in path)
- D7 (charset validator)
- D9 (`max_hops` upper bound 5)
- D11 (no invented helpers)
- D12 (slug `repos-gimle`)

## Open questions

None remaining. Spec ready for paperclip Phase 1.1.

## References

- `services/palace-mcp/src/palace_mcp/code_router.py` — palace.code.* passthrough pattern (post-GIM-89); rev4 adds `get_cm_session()` accessor + `parse_cm_result` helper
- `services/palace-mcp/src/palace_mcp/errors.py:108` — `handle_tool_error: NoReturn` signature confirmed
- `services/palace-mcp/src/palace_mcp/config.py:23` — existing Settings pattern; rev4 adds `cm_default_project`
- `services/palace-mcp/tests/code_graph/test_code_graph_integration.py` — pins CM passthrough wire contract (existing)
- Live spike report (this session, 2026-04-26): `/tmp/gim98_docker_smoke{,2,3}.sh` produced literal request/response shapes
- GIM-91 — MCP wire-contract test rule
- GIM-94 — error model split standard + Phase 4.2 CTO-only rule
- GIM-89 — `_OpenArgs` schema for flat-arg passthrough (passthrough vs composite distinction)
