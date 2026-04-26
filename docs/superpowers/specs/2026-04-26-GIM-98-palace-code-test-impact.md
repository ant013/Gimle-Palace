---
slug: GIM-98-palace-code-test-impact
status: rev3 (live CM contract spike against docker, multi-hop is_test confirmed, design simplified)
branch: feature/GIM-98-palace-code-test-impact
paperclip_issue: TBD
predecessor: 1f7c8f2 (develop tip after GIM-97 merge)
date: 2026-04-26
parent_initiative: N+2 Category 1 (USE-BUILT)
sequence_position: 4 of 4 — palace.code.test_impact composite tool
related: GIM-95 (decide), GIM-96 (prime foundation), GIM-97 (cookbooks)
---

# GIM-98 — `palace.code.test_impact` — find tests exercising a symbol

## Goal

Ship a composite MCP tool that, given a Symbol's `qualified_name`, returns the list of test functions that exercise it (transitively call it). Built on top of existing `palace.code.trace_call_path` (with `include_tests=True`) — minimal new surface, high practical value for PE/Opus/QA who need targeted test selection.

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
- `palace.code.trace_call_path` (post-GIM-89 fix) — ✅ landed
- `palace.code.search_graph` (post-GIM-89 fix) — ✅ landed for symbol disambiguation

## Non-goals

- Semantic search (NL → tests) — separate slice
- Test runtime / coverage instrumentation — out of scope (this is static graph analysis)
- Test outcomes / pass-fail history — out of scope
- Cross-project test queries — out of scope
- Mutation testing or test smell detection — out of scope

## CM contract — pinned by 2026-04-26 live spike

This section pins the **literal request/response shapes** of the two CM tools we depend on. All shapes verified directly via:
- Local CM (DeusData v0.6 stdio MCP)
- Docker CM (palace-mcp `palace.code.*` against `http://localhost:8080/mcp` with `project="repos-gimle"`)

Any future drift breaks our contract test (Task 5).

### `palace.code.search_graph`

**Request:**
```json
{
  "project": "repos-gimle",
  "qn_pattern": ".*module\\.path\\.symbol_name$",
  "label": "Function",
  "limit": 2
}
```

Notes:
- `qn_pattern` is a regex matched against `Function.qualified_name`
- `label` filters node type — pass `"Function"` to exclude `Class`, `Method`, `Section`, etc.
- `limit` caps result count

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

**Response (no match):** `{"total": 0, "results": [], "has_more": false}` (graceful, NOT an error).

### `palace.code.trace_call_path`

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
- `function_name` accepts the **short symbol name only** — not `qualified_name`. (Confirmed via spike: full QN returns `"function not found"`.)
- `direction`: `"inbound"` | `"outbound"` | `"both"`
- `depth`: traversal depth in the call graph (NOT `max_hops`)
- `include_tests`: when `true`, test functions are included in `callers`, each marked with `is_test: true`. When `false` (default), test functions are excluded entirely.

**Response (success):**
```json
{
  "function": "register_code_tools",
  "direction": "inbound",
  "callers": [
    {
      "name": "test_decorator_receives_all_names",
      "qualified_name": "repos-gimle.services.palace-mcp.tests.test_code_router.TestToolRegistration.test_decorator_receives_all_names",
      "hop": 1,
      "is_test": true
    },
    {
      "name": "_cli",
      "qualified_name": "repos-gimle..github.scripts.paperclip_signal._cli",
      "hop": 2
    }
  ]
}
```

Notes:
- Hop field is `hop` (integer, NOT `hop_distance`)
- `is_test: true` is set by CM for any test-marked function at any hop. Non-test callers have **no `is_test` key** (use `c.get("is_test")` for falsy default)
- Empty call graph: `{"function": "...", "direction": "inbound", "callers": []}`

**Response (function not in index):** envelope `{"error": "function not found"}` — surfaces as `result.isError=True` from MCP SDK.

### Project slug

Live spike confirmed docker CM uses path-based slug: **`repos-gimle`** (from bind-mount `/repos/gimle`). The `project` param of every `palace.code.*` call must use this exact string. Local CM uses different slug (`Users-ant013-Android-Gimle-Palace`) — irrelevant for the docker-deployed tool but useful when reproducing spike findings.

## Architecture

### MCP tool signature

```python
@_tool(
    name="palace.code.test_impact",
    description=(
        "Given a Function's qualified_name, return the list of test functions "
        "that transitively call it (inbound + is_test=true filter). "
        "Built on palace.code.trace_call_path(include_tests=True). "
        "Use to focus pytest invocation on tests exercising a specific symbol "
        "before refactoring or debugging. "
        "Returns up to max_results test entries ranked by hop ascending (closer first)."
    ),
)
async def palace_code_test_impact(
    qualified_name: str,
    project: str | None = None,
    max_hops: int = 3,
    max_results: int = 50,
) -> dict[str, Any]:
    ...
```

### Algorithm (4 steps)

1. **Validate** input via Pydantic `TestImpactRequest`. Reject empty `qualified_name`, out-of-range `max_hops` (1..5) / `max_results` (1..200), and `qualified_name` containing chars outside `[A-Za-z0-9._-]`.
2. **Resolve project**: if `project is None`, default to the CM project slug for this stack (currently `"repos-gimle"` — from `Settings.cm_default_project` env var, defaulting to `"repos-gimle"` if unset).
3. **Disambiguate**: call `palace.code.search_graph(qn_pattern=f".*{re.escape(qualified_name)}$", label="Function", limit=2, project=…)`.
   - 0 results → envelope `error_code="symbol_not_found"`.
   - >1 results → envelope `error_code="ambiguous_qualified_name"` with `matches: [{qualified_name, file_path}, ...]`. Caller refines.
   - 1 result → extract `name` (short) and `qualified_name` (echo back resolved).
4. **Trace**: call `palace.code.trace_call_path(function_name=short_name, direction="inbound", depth=max_hops, include_tests=True, project=…)`. From the returned `callers`:
   - Filter: `[c for c in callers if c.get("is_test")]` — only test functions.
   - `total_found = len(filtered)` — **before** truncation.
   - Sort: `key=lambda c: c["hop"]` — ascending.
   - `truncated = total_found > max_results`.
   - `tests = filtered[:max_results]`.
5. **Return** structured result.

### Output schema

```json
{
  "ok": true,
  "qualified_name": "repos-gimle.services.palace-mcp.src.palace_mcp.code_router.register_code_tools",
  "project": "repos-gimle",
  "tests": [
    {
      "name": "test_decorator_receives_all_names",
      "qualified_name": "repos-gimle.services.palace-mcp.tests.test_code_router.TestToolRegistration.test_decorator_receives_all_names",
      "hop": 1
    }
  ],
  "total_found": 12,
  "max_hops_used": 3,
  "truncated": false
}
```

Notes on output fields:
- `qualified_name` echoes the **resolved** QN from search_graph (canonical), even if caller passed a suffix
- `hop` (NOT `hop_distance`) — matches CM's native field
- `total_found` is computed BEFORE truncation — accurate count of testers found in the graph
- `truncated` (NOT `max_results_truncated`) — boolean flag

If symbol doesn't exist:
```json
{
  "ok": false,
  "error_code": "symbol_not_found",
  "message": "qualified_name '<x>' not found in project '<y>' (no Function node matches suffix)"
}
```

If ambiguous:
```json
{
  "ok": false,
  "error_code": "ambiguous_qualified_name",
  "message": "qn_pattern '<x>' matched 2 symbols in project '<y>' — refine to uniquely identify",
  "matches": [
    {"qualified_name": "...", "file_path": "..."},
    {"qualified_name": "...", "file_path": "..."}
  ]
}
```

If no tests exercise the symbol (empty result is NOT an error):
```json
{
  "ok": true,
  "qualified_name": "...",
  "project": "...",
  "tests": [],
  "total_found": 0,
  "max_hops_used": 3,
  "truncated": false
}
```

### Error model (per GIM-94 / GIM-95 standard)

- Validation errors → envelope `{"ok": false, "error_code": "validation_error", "message": ...}`
- Symbol not found → envelope `{"ok": false, "error_code": "symbol_not_found", ...}`
- Ambiguous QN → envelope `{"ok": false, "error_code": "ambiguous_qualified_name", "matches": [...]}`
- Unknown project → envelope `{"ok": false, "error_code": "unknown_project", ...}` (CM-side error surfaced as envelope)
- Infrastructure failures (CM session None, network down, MCP transport error) → `handle_tool_error(exc)` raises (FastMCP `isError=true`)

## Tasks

| # | Task | Owner | Deps |
|---|---|---|---|
| 1 | Pydantic input model `TestImpactRequest` (qualified_name regex + length, max_hops 1..5, max_results 1..200) | PE | — |
| 2 | Implementation in `services/palace-mcp/src/palace_mcp/code/composite/test_impact.py` (new module — Q5 verdict: composites separate from passthroughs) | PE | T1 |
| 3 | MCP tool registration via new `services/palace-mcp/src/palace_mcp/code/composite/router.py`, wired in `mcp_server.py` lifespan alongside existing `register_code_tools` | PE | T2 |
| 4 | Unit tests — mock `_cm_session.call_tool`; verify all 4 algorithm branches (no_match, ambiguous, no_tests, ok with mixed callers); truncation; sort | PE | T2 |
| 5 | Integration test through real MCP HTTP+SSE (per GIM-91 wire-contract rule) — call against real indexed `repos-gimle` data; pin both happy path and ambiguity behaviour | PE | T3 |
| 6 | CM contract test — separate test pinning the **literal** request/response shape of `palace.code.search_graph` and `palace.code.trace_call_path` we depend on, so version drift in CM lib breaks CI loudly | PE | T3 |
| 7 | Update `services/palace-mcp/README.md` with usage example | PE | T2 |
| 8 | QA Phase 4.1 — operator runs against a known function on iMac docker stack | QA | T1-T7 |

### Task 1 — TestImpactRequest

```python
import re
from pydantic import BaseModel, Field, field_validator

_QN_RE = re.compile(r"^[A-Za-z0-9._\-]+$")


class TestImpactRequest(BaseModel):
    qualified_name: str = Field(..., min_length=1, max_length=500)
    project: str | None = None
    max_hops: int = Field(3, ge=1, le=5)
    max_results: int = Field(50, ge=1, le=200)

    @field_validator("qualified_name")
    @classmethod
    def _qn_charset(cls, v: str) -> str:
        if not _QN_RE.match(v):
            raise ValueError(
                "qualified_name must match [A-Za-z0-9._-]+ "
                "(no spaces, quotes, or special chars)"
            )
        return v
```

Charset restriction prevents Cypher/regex injection at the search_graph step (we embed `qualified_name` into a regex pattern). Real Python qualified names never contain chars outside this set.

### Task 2 — implementation

`services/palace-mcp/src/palace_mcp/code/composite/test_impact.py`:

```python
"""palace.code.test_impact — composite tool finding tests exercising a Symbol.

Built on palace.code.trace_call_path with include_tests=True; relies on CM's
native is_test marking (does NOT re-implement test detection via path regex).
"""
from __future__ import annotations

import json
import re
from typing import Any

from mcp import ClientSession


async def test_impact(
    cm_session: ClientSession,
    qualified_name: str,
    project: str,
    max_hops: int,
    max_results: int,
) -> dict[str, Any]:
    # Step 1: disambiguate via search_graph
    sg = await cm_session.call_tool(
        "search_graph",
        arguments={
            "project": project,
            "qn_pattern": f".*{re.escape(qualified_name)}$",
            "label": "Function",
            "limit": 2,
        },
    )
    sg_data = _parse_cm_result(sg)
    results = sg_data.get("results", [])
    if not results:
        return {
            "ok": False,
            "error_code": "symbol_not_found",
            "message": (
                f"qualified_name '{qualified_name}' not found in project "
                f"'{project}' (no Function node matches suffix)"
            ),
        }
    if len(results) > 1:
        return {
            "ok": False,
            "error_code": "ambiguous_qualified_name",
            "message": (
                f"qn_pattern matched {len(results)} symbols in project "
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
    short_name = target["name"]
    resolved_qn = target["qualified_name"]

    # Step 2: trace inbound, with tests included
    tcp = await cm_session.call_tool(
        "trace_call_path",
        arguments={
            "project": project,
            "function_name": short_name,
            "direction": "inbound",
            "depth": max_hops,
            "include_tests": True,
        },
    )
    tcp_data = _parse_cm_result(tcp)
    callers = tcp_data.get("callers", [])

    # Step 3: keep only is_test=true; sort by hop ascending; truncate
    tests = [c for c in callers if c.get("is_test")]
    total_found = len(tests)
    tests.sort(key=lambda c: c.get("hop", 999))
    truncated = total_found > max_results
    tests = tests[:max_results]

    return {
        "ok": True,
        "qualified_name": resolved_qn,
        "project": project,
        "tests": [
            {
                "name": c.get("name", ""),
                "qualified_name": c.get("qualified_name", ""),
                "hop": c.get("hop", 0),
            }
            for c in tests
        ],
        "total_found": total_found,
        "max_hops_used": max_hops,
        "truncated": truncated,
    }


def _parse_cm_result(result: Any) -> dict[str, Any]:
    """Parse MCP CallToolResult → dict (per GIM-89 pattern in code_router._forward)."""
    if result.structuredContent is not None:
        return dict(result.structuredContent)
    for block in getattr(result, "content", []):
        text = getattr(block, "text", None)
        if text is None:
            continue
        try:
            parsed = json.loads(text)
            return parsed if isinstance(parsed, dict) else {"_raw": parsed}
        except json.JSONDecodeError:
            return {"_raw": text}
    return {}
```

### Task 3 — registration

`services/palace-mcp/src/palace_mcp/code/composite/router.py` (new):

```python
"""palace.code.* composite tool registration.

Composites (e.g., test_impact) live here, distinct from raw passthroughs in
code_router.py. Both share the same _cm_session via late binding (lookup at
call time, not import time — avoids circular-init issues).
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import ValidationError

from palace_mcp import code_router  # imported as MODULE for late _cm_session lookup
from palace_mcp.code.composite.test_impact import test_impact
from palace_mcp.code.composite.models import TestImpactRequest
from palace_mcp.errors import handle_tool_error


def register_code_composite_tools(
    tool_decorator: Callable[[str, str], Callable[..., Any]],
    default_project: str,
) -> None:
    @tool_decorator("palace.code.test_impact", _DESC)
    async def palace_code_test_impact(
        qualified_name: str,
        project: str | None = None,
        max_hops: int = 3,
        max_results: int = 50,
    ) -> dict[str, Any]:
        # Late binding — read _cm_session attribute at call time, not import
        if code_router._cm_session is None:
            handle_tool_error(
                RuntimeError("CM subprocess not started — set CODEBASE_MEMORY_MCP_BINARY")
            )  # raises (handle_tool_error never returns)

        try:
            req = TestImpactRequest(
                qualified_name=qualified_name,
                project=project,
                max_hops=max_hops,
                max_results=max_results,
            )
        except ValidationError as e:
            return {
                "ok": False,
                "error_code": "validation_error",
                "message": str(e),
            }

        resolved_project = req.project or default_project

        try:
            return await test_impact(
                cm_session=code_router._cm_session,
                qualified_name=req.qualified_name,
                project=resolved_project,
                max_hops=req.max_hops,
                max_results=req.max_results,
            )
        except Exception as e:
            handle_tool_error(e)  # raises


_DESC = (
    "Given a Function's qualified_name, return tests transitively calling it. "
    "Composite over palace.code.trace_call_path(include_tests=True)."
)
```

Wired in `mcp_server.py`:

```python
from palace_mcp.code.composite.router import register_code_composite_tools

register_code_tools(_tool, mcp)                                              # existing passthroughs
register_code_composite_tools(_tool, default_project=settings.cm_default_project)  # NEW composites
```

`Settings.cm_default_project: str = "repos-gimle"` — added to `palace_mcp/config.py` (with env override `PALACE_CM_DEFAULT_PROJECT`).

**Note on `handle_tool_error` semantics:** `handle_tool_error` **always raises**, never returns. Calls like `handle_tool_error(e)` should be the last statement in their branch. We don't add `return` after them — mypy will warn if reachable code follows.

### Task 4 — unit tests

`tests/code/composite/test_test_impact_unit.py`:

Branches to cover:
1. `validation_error` — `qualified_name=""`, `qualified_name` with spaces, `max_hops=10`, `max_results=0`
2. `symbol_not_found` — search_graph returns `{"results": []}`
3. `ambiguous_qualified_name` — search_graph returns 2 results; verify `matches` field is populated with both
4. **Happy path with mixed callers** — trace_call_path returns:
   - `{name: "test_x", qualified_name: "...test_x", hop: 1, is_test: true}` (kept)
   - `{name: "_internal_helper", qualified_name: "...helper", hop: 1}` (no is_test → dropped)
   - `{name: "test_y", qualified_name: "...test_y", hop: 2, is_test: true}` (kept)
   Verify `tests` has 2 entries, sorted by hop, `total_found: 2`.
5. **Truncation** — 5 testers + `max_results=2` → returns 2, `total_found: 5`, `truncated: true`.
6. **Empty result is not error** — trace_call_path returns `{"callers": []}` → `ok: true, tests: [], total_found: 0`.
7. **Resolved QN echoed** — search_graph returns long QN, function called with shorter suffix; output echoes the **full** QN from search_graph.
8. **Infrastructure failure** — `_cm_session` is None → `handle_tool_error` raises (use pytest.raises).

Mock pattern (avoid Python-pro F1 trap):

```python
def test_happy_path(monkeypatch):
    fake_session = AsyncMock()
    fake_session.call_tool = AsyncMock(side_effect=[
        _make_result({"results": [{"name": "decide", "qualified_name": "...decide", "file_path": "..."}], "has_more": False}),
        _make_result({"function": "decide", "direction": "inbound", "callers": [
            {"name": "test_x", "qualified_name": "...test_x", "hop": 1, "is_test": True},
            {"name": "_helper", "qualified_name": "...helper", "hop": 1},
        ]}),
    ])
    # Patch the module attribute (NOT a name binding):
    from palace_mcp import code_router
    monkeypatch.setattr(code_router, "_cm_session", fake_session)
    ...
```

### Task 5 — integration test through real MCP

Per `paperclip-shared-fragments/fragments/compliance-enforcement.md` MCP wire-contract rule (GIM-91):

```python
# tests/integration/test_palace_code_test_impact_wire.py

async def test_test_impact_via_streamablehttp(mcp_url):
    """End-to-end through real MCP HTTP+SSE against indexed repos-gimle."""
    async with streamablehttp_client(mcp_url) as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()
            result = await s.call_tool("palace.code.test_impact", arguments={
                "qualified_name": "register_code_tools",
                "project": "repos-gimle",
            })
            payload = json.loads(result.content[0].text)
            assert payload["ok"] is True
            # register_code_tools is exercised by tests/test_code_router.py
            # so non-empty test list is expected
            assert len(payload["tests"]) >= 1
            assert all(
                t.get("qualified_name", "").lower().count("test") >= 1
                for t in payload["tests"]
            )
            # All testers must have hop in valid range
            assert all(1 <= t["hop"] <= 3 for t in payload["tests"])
```

### Task 6 — CM contract test

`tests/code/composite/test_cm_contract.py` — pins the literal request/response shape we depend on. If CM lib version shifts and renames/removes fields, this test fails loudly:

```python
async def test_search_graph_response_has_required_fields(cm_session):
    result = await cm_session.call_tool("search_graph", {
        "project": "repos-gimle",
        "name_pattern": "register_code_tools",
        "label": "Function",
        "limit": 1,
    })
    data = _parse_cm_result(result)
    assert "total" in data
    assert "results" in data
    if data["results"]:
        first = data["results"][0]
        for k in ("name", "qualified_name", "label", "file_path"):
            assert k in first, f"CM contract drift: missing {k}"


async def test_trace_call_path_callers_have_required_fields(cm_session):
    result = await cm_session.call_tool("trace_call_path", {
        "project": "repos-gimle",
        "function_name": "register_code_tools",
        "direction": "inbound",
        "depth": 2,
        "include_tests": True,
    })
    data = _parse_cm_result(result)
    assert "callers" in data
    if data["callers"]:
        for c in data["callers"]:
            assert "name" in c
            assert "qualified_name" in c
            assert "hop" in c
            assert isinstance(c["hop"], int)
        test_callers = [c for c in data["callers"] if c.get("is_test")]
        # Anchor: register_code_tools is tested → at least 1 test caller exists
        assert len(test_callers) >= 1
```

### Task 7 — README example

```markdown
### palace.code.test_impact

Find tests transitively calling a symbol (composite over `trace_call_path` + CM `is_test` filter).

```
palace.code.test_impact(
  qualified_name="repos-gimle.services.palace-mcp.src.palace_mcp.code_router.register_code_tools",
  project="repos-gimle",
  max_hops=3,
  max_results=50,
)
```

Returns up to `max_results` tests ranked by `hop` ascending. Use to focus pytest before refactoring.
```

### Task 8 — QA Phase 4.1 live smoke

Operator-driven on iMac:

1. `docker compose --profile review up -d --build --wait` (per deploy-checklist GIM-94)
2. Auth-path probe per GIM-94 Step 5
3. **Happy path:** call `palace.code.test_impact(qualified_name="register_code_tools", project="repos-gimle")` via MCP → expect `ok: true, tests: [...]` with ≥1 entry and all entries having `qualified_name` containing `test`
4. **Ambiguous case:** call with `qualified_name="main"` (likely many `main` functions in graph) → expect `ok: false, error_code: ambiguous_qualified_name, matches: [...]` with ≥2 entries
5. **Not found:** `qualified_name="nonexistent_function_xyz_abc"` → expect `ok: false, error_code: symbol_not_found`
6. **Validation:** `qualified_name="bad name with spaces"` → expect `ok: false, error_code: validation_error`
7. Verify integration test (Task 5) + contract test (Task 6) pass in pytest run on iMac
8. Restore production checkout to develop (per worktree-discipline.md)

## Acceptance

1. Tool callable via real MCP HTTP+SSE; returns `ok: true` + non-empty `tests` for known-tested symbol
2. Empty result (`tests: []`) is NOT an error — returns `ok: true, total_found: 0`
3. Symbol not found → envelope with `error_code: symbol_not_found`
4. Ambiguous QN → envelope with `error_code: ambiguous_qualified_name` and `matches: [...]`
5. Validation errors (max_hops out of range, qualified_name empty/charset) → envelope with `error_code: validation_error`
6. Infrastructure errors (CM session None, network) raise via `handle_tool_error` (FastMCP `isError=true`)
7. Tests sorted by `hop` ascending (closest first)
8. `total_found` reflects count BEFORE truncation (not after)
9. Truncation works at `max_results` boundary; `truncated: true` flag set when applicable
10. CM contract test (Task 6) anchors the literal field names we depend on
11. Pattern #21 dedup-aware registration — `palace.code.test_impact` appears in `tools/list` exactly once
12. Resolved `qualified_name` echoed back even when caller passes a suffix

## Out of scope (defer)

- Configurable `is_test` detection — v1 trusts CM's marking entirely
- Test outcome / coverage data — separate slice if pursued
- Reverse direction (`tests covered by this test`) — semantic_search is a better fit
- Cross-project queries — defer until federation
- `palace.code.semantic_search` — separate slice (Slice 5 candidate)
- Multiple resolution strategies (e.g., fuzzy match, name-only fallback) — v1 demands canonical QN suffix

## Decisions recorded (rev3)

Spike-driven design changes from rev2 (live CM contract verified 2026-04-26):

| # | rev2 → rev3 change | Driver |
|---|---|---|
| D1 | Removed hardcoded test-pattern regex (`\.tests?\.|...`) | Live spike: CM marks `is_test: true` on test functions at any hop. Trust CM's signal — no need to re-implement detection |
| D2 | `mode="callers"` → `direction="inbound"` | Live spike: `trace_call_path` parameter is `direction`, not `mode` |
| D3 | `max_hops` parameter passed to CM → `depth` | Live spike: CM parameter is `depth`, not `max_hops` |
| D4 | Output field `hop_distance` → `hop` | CM native field is `hop` — match upstream |
| D5 | Output field `max_results_truncated` → `truncated` | API-designer review F2: shorter, idiomatic |
| D6 | `total_found` computed BEFORE truncation | API-designer F1 / Python-pro F5 — rev2 returned post-truncation count, miscount bug |
| D7 | Added `qualified_name` charset validator | Python-pro & API-designer: prevent regex injection at `search_graph` step |
| D8 | `_cm_session` import as module attribute (`code_router._cm_session`), not name binding | Python-pro F1: avoids None-at-import-time circular trap |
| D9 | `max_hops` upper bound 5 (was 10) | Spike: `is_test` marking works on multi-hop, but graph noise dominates beyond depth 4 — 5 keeps signal/noise sane |
| D10 | Added Task 6 (CM contract test) | Architect F2-style: pin literal request/response shape; future CM lib drift breaks CI loudly |
| D11 | Removed invented helpers `_resolve_default_cm_project` / `_resolve_project_to_group_id` | Architect F3: doesn't exist. Use plain `Settings.cm_default_project` (env-overridable) |
| D12 | Slug `repos-gimle` (not `gimle`) | Live spike: docker CM available_projects = ["repos-gimle"] |

Q1-Q5 verdicts from rev1 review (unchanged):

| Q | Topic | Verdict |
|---|---|---|
| 1 | Test detection source | **CHANGED in rev3:** delegate to CM `is_test` (was hardcoded regex) |
| 2 | `max_hops` default | 3 (kept) — supports multi-hop now that we know it works |
| 3 | Ambiguous qualified_name | Return envelope with `matches: [...]`. Don't silently take first |
| 4 | `hop` in output | Keep — useful for ranking |
| 5 | Composite tool location | NEW `palace_mcp/code/composite/` module — keeps passthroughs vs composites separate |

## Open questions

None remaining. Spec ready for paperclip Phase 1.1 (CTO formalize → CR plan-first review → PE implement).

## References

- `services/palace-mcp/src/palace_mcp/code_router.py` — palace.code.* passthrough pattern (post-GIM-89)
- `services/palace-mcp/tests/code_graph/test_code_graph_integration.py` — passes through real CM subprocess; pins `trace_call_path` parameter names
- `services/palace-mcp/src/palace_mcp/mcp_server.py:139-` — `_tool()` decorator (Pattern #21)
- Live spike report (this session, 2026-04-26): probe paths in `/tmp/gim98_docker_smoke{,2,3}.sh`
- GIM-91 — MCP wire-contract test rule
- GIM-94 — error model split standard + Phase 4.2 CTO-only rule
- GIM-89 — `_OpenArgs` schema for flat-arg passthrough
