---
slug: GIM-98-palace-code-test-impact
status: rev2 (5 open questions answered; ready for multi-reviewer adversarial round)
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

Ship a composite MCP tool that, given a Symbol's `qualified_name`, returns the list of test functions that exercise it (transitively call it). Built on top of existing `palace.code.trace_call_path(mode="callers")` — minimal new surface, high practical value for PE/Opus/QA who need targeted test selection.

**Use case:** PE about to refactor `register_code_tools` calls `palace.code.test_impact("repos-gimle.services.palace-mcp.src.palace_mcp.code_router.register_code_tools")` → gets list of 8 test functions to focus on. Saves blind running of full pytest suite.

## Sequence

Slice 4 of 4 in N+2 Category 1 (USE-BUILT). Final slice in this category — after this lands, all 4 USE-BUILT tools are shipped.

1. `palace.memory.decide` — GIM-95 ✅ merged
2. `palace.memory.prime` foundation — GIM-96 ✅ merged
3. `palace.memory.prime` 5 cookbooks — GIM-97 ✅ merged
4. **`palace.code.test_impact` — this slice** (final USE-BUILT)

Slice 5 (`palace.code.semantic_search`) is deferred — not part of this slice's scope. Separate follow-up if pursued.

## Hard dependencies

- N+1a Codebase-Memory MCP (GIM-76) — ✅ landed
- `palace.code.trace_call_path` (post-GIM-89 fix) — ✅ landed
- `palace.code.search_graph` (post-GIM-89 fix) — ✅ landed for filter validation

## Non-goals

- Semantic search (NL → tests) — separate slice
- Test runtime / coverage instrumentation — out of scope (this is static graph analysis)
- Test outcomes / pass-fail history — out of scope (no test result tracking yet)
- Cross-project test queries — out of scope
- Mutation testing or test smell detection — out of scope

## Architecture

### MCP tool signature

```python
@_tool(
    name="palace.code.test_impact",
    description=(
        "Given a Symbol's qualified_name, return the list of test functions that "
        "transitively call it (inbound callers filtered by test-naming pattern). "
        "Composite of palace.code.trace_call_path(mode=callers). "
        "Use to focus pytest invocation on tests exercising a specific symbol "
        "before refactoring or debugging. "
        "Returns up to max_results test entries ranked by hop distance (closer first)."
    ),
)
async def palace_code_test_impact(
    qualified_name: str,
    project: str | None = None,
    max_hops: int = 3,
    max_results: int = 50,
) -> dict[str, Any]:
    """..."""
```

### Algorithm

1. Validate `qualified_name` is non-empty string.
2. Resolve `project` to `repos-<slug>` via existing `_resolve_project_to_group_id` helper (default to `palace_default_group_id` if None).
3. Call `palace.code.trace_call_path(function_name=symbol_short_name, project=resolved_project, mode="callers")` internally — extract callers with their hop distance.
   - **Note:** `trace_call_path` takes a function_name (short) not qualified_name. We need to extract short name from qualified_name OR resolve qualified_name → uuid first.
   - **Strategy:** call `palace.code.search_graph(qn_pattern=qualified_name, project=project, label="Function")` first to verify symbol exists; use its `name` field for trace_call_path.
   - **Ambiguity (Q3 verdict):** if `search_graph` returns >1 match for the qn_pattern, return `ok: false, error_code: ambiguous_qualified_name, message: "...", matches: [{qualified_name, file_path}, ...]`. Caller must refine the qualified_name. Do NOT silently take first match — leads to wrong test list returned.
4. Filter callers by test-naming pattern (defaults below).
5. Sort by hop distance ascending (closer = more direct test).
6. Truncate to `max_results`.
7. Return structured result.

### Test-naming pattern (hardcoded for v1)

A function is considered a test if **any** of:
- `qualified_name` matches regex `\.tests?\.` (i.e., contains `.test.` or `.tests.` segment) — Python convention
- `qualified_name` ends in `.test_<something>` — pytest convention
- `qualified_name` starts with or contains `.test_` (e.g. `.test_<file>`)
- `name` (short symbol name) starts with `test_`
- `file_path` (if available in result) contains `/tests/` or matches `test_*.py`

This handles common test conventions: pytest (`test_*.py` files), Django (`tests/` dirs), generic (`test_<name>` functions).

**Configurable in v2** (out of scope) via Settings: `palace_test_pattern_regex: str = r"^test_|\.tests?\.|/tests/"`.

### Output schema

```json
{
  "ok": true,
  "qualified_name": "<input>",
  "project": "<resolved project>",
  "tests": [
    {
      "qualified_name": "<test fn qn>",
      "name": "<short name>",
      "file_path": "<path>",
      "hop_distance": 1,
      "label": "Function"
    }
  ],
  "total_found": 12,
  "max_hops_used": 3,
  "max_results_truncated": false
}
```

If symbol doesn't exist:
```json
{
  "ok": false,
  "error_code": "symbol_not_found",
  "message": "qualified_name '<x>' not found in project '<y>'"
}
```

If `qualified_name` is ambiguous (search_graph returns >1 match):
```json
{
  "ok": false,
  "error_code": "ambiguous_qualified_name",
  "message": "qn_pattern '<x>' matched 3 symbols in project '<y>' — refine to uniquely identify",
  "matches": [
    {"qualified_name": "...", "file_path": "..."},
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
  "tests": [],
  "total_found": 0,
  "max_hops_used": 3,
  "max_results_truncated": false
}
```

### Error model (per GIM-94 / GIM-95 standard)

- Validation errors → envelope `{ok: false, error_code: validation_error, message: ...}`
- Symbol not found → envelope `{ok: false, error_code: symbol_not_found, message: ...}`
- Unknown project → envelope `{ok: false, error_code: unknown_project, message: ...}` (existing handler)
- Infrastructure failures (CM subprocess down, network) → `handle_tool_error(exc)` raise

## Tasks

| # | Task | Owner | Deps |
|---|---|---|---|
| 1 | Pydantic input model `TestImpactRequest` (qualified_name non-empty, max_hops 1..10, max_results 1..200) | PE | — |
| 2 | Implementation in `services/palace-mcp/src/palace_mcp/code/composite/test_impact.py` (new — Q5 verdict: separate `code/composite/` module to keep palace.code.* passthroughs vs composites distinct) | PE | T1 |
| 3 | MCP tool registration `palace.code.test_impact` in new `services/palace-mcp/src/palace_mcp/code/composite/router.py` (Q5 verdict: composites NOT in `code_router.py`; new module called from `mcp_server.py` lifespan) | PE | T2 |
| 4 | Unit tests — mock CM `trace_call_path` + `search_graph`; verify filter regex on diverse callers (test fn + non-test fn mix); empty result handling | PE | T2 |
| 5 | Integration test through real MCP HTTP+SSE (per GIM-91 wire-contract rule) — call against real indexed `repos-gimle` data | PE | T3 |
| 6 | Update `services/palace-mcp/README.md` with usage example | PE | T2 |
| 7 | QA Phase 4.1 — operator runs against a known function (e.g. `register_code_tools`), verifies non-empty test list returned | QA | T1-T6 |

### Task 1 — TestImpactRequest

```python
from pydantic import BaseModel, Field

class TestImpactRequest(BaseModel):
    qualified_name: str = Field(..., min_length=1, max_length=500)
    project: str | None = None
    max_hops: int = Field(3, ge=1, le=10)
    max_results: int = Field(50, ge=1, le=200)
```

### Task 2 — implementation

`services/palace-mcp/src/palace_mcp/code/test_impact.py`:

```python
import re
from typing import Any
from mcp import ClientSession

# Regex to detect test functions by their qualified_name
TEST_PATTERN = re.compile(
    r"\.tests?\.|\.test_|^test_"
)

async def test_impact(
    cm_session: ClientSession,
    qualified_name: str,
    project: str,
    max_hops: int = 3,
    max_results: int = 50,
) -> dict[str, Any]:
    """..."""
    # Step 1: resolve qualified_name → short name via search_graph
    sg = await cm_session.call_tool("search_graph", arguments={
        "qn_pattern": qualified_name,
        "project": project,
        "label": "Function",
    })
    sg_data = _parse_cm_result(sg)
    results = sg_data.get("results", [])
    if not results:
        return {
            "ok": False,
            "error_code": "symbol_not_found",
            "message": f"qualified_name '{qualified_name}' not found in project '{project}'",
        }

    # Q3 verdict: ambiguous match → error, don't silently take first
    if len(results) > 1:
        return {
            "ok": False,
            "error_code": "ambiguous_qualified_name",
            "message": (
                f"qn_pattern '{qualified_name}' matched {len(results)} symbols "
                f"in project '{project}' — refine to uniquely identify"
            ),
            "matches": [
                {"qualified_name": r.get("qualified_name", ""), "file_path": r.get("file_path", "")}
                for r in results[:10]  # cap match list at 10 entries
            ],
        }

    target = results[0]
    short_name = target["name"]

    # Step 2: trace_call_path callers
    tcp = await cm_session.call_tool("trace_call_path", arguments={
        "function_name": short_name,
        "project": project,
        "mode": "callers",
        "max_hops": max_hops,
    })
    tcp_data = _parse_cm_result(tcp)
    callers = tcp_data.get("callers", [])

    # Step 3: filter by test pattern
    test_callers = [
        c for c in callers
        if TEST_PATTERN.search(c.get("qualified_name", "")) or
           c.get("name", "").startswith("test_") or
           "/tests/" in c.get("file_path", "")
    ]

    # Step 4: sort by hop distance ascending
    test_callers.sort(key=lambda c: c.get("hop", 999))

    # Step 5: truncate
    truncated = len(test_callers) > max_results
    test_callers = test_callers[:max_results]

    # Step 6: format output
    return {
        "ok": True,
        "qualified_name": qualified_name,
        "project": project,
        "tests": [
            {
                "qualified_name": c.get("qualified_name", ""),
                "name": c.get("name", ""),
                "file_path": c.get("file_path", ""),
                "hop_distance": c.get("hop", 0),
                "label": c.get("label", "Function"),
            }
            for c in test_callers
        ],
        "total_found": len(test_callers),
        "max_hops_used": max_hops,
        "max_results_truncated": truncated,
    }


def _parse_cm_result(result) -> dict:
    """Parse MCP CallToolResult → dict, handling text/structuredContent variants."""
    # Per GIM-89 fix pattern in code_router.py
    if result.structuredContent:
        return dict(result.structuredContent)
    for block in result.content:
        if hasattr(block, "text"):
            try:
                import json
                return json.loads(block.text)
            except json.JSONDecodeError:
                return {"_raw": block.text}
    return {}
```

### Task 3 — MCP tool registration (in NEW module per Q5 verdict)

Per Q5: composite tools live in `services/palace-mcp/src/palace_mcp/code/composite/router.py` (NEW), NOT in `code_router.py` (passthroughs only). Pattern:

```python
# services/palace-mcp/src/palace_mcp/code/composite/router.py

from collections.abc import Callable
from typing import Any

from palace_mcp.code.composite.test_impact import test_impact, TestImpactRequest

def register_code_composite_tools(
    tool_decorator: Callable[[str, str], Callable[..., Any]],
) -> None:
    """Register palace.code.* composite (non-passthrough) tools.

    Composites internally call CM via _cm_session (set by code_router's
    lifespan) but expose orchestrated logic — distinct from raw passthroughs.
    """
    from palace_mcp.code_router import _cm_session  # share session

    @tool_decorator("palace.code.test_impact", "...")
    async def palace_code_test_impact(
        qualified_name: str,
        project: str | None = None,
        max_hops: int = 3,
        max_results: int = 50,
    ) -> dict[str, Any]:
        # ... full body per implementation below
```

Then in `mcp_server.py`, alongside `register_code_tools(_tool)`:

```python
from palace_mcp.code.composite.router import register_code_composite_tools
register_code_tools(_tool)            # existing passthroughs
register_code_composite_tools(_tool)  # new composites
```

Body per implementation block:

@_tool(
    name="palace.code.test_impact",
    description="...",
)
async def palace_code_test_impact(
    qualified_name: str,
    project: str | None = None,
    max_hops: int = 3,
    max_results: int = 50,
) -> dict[str, Any]:
    if _cm_session is None:
        handle_tool_error(DriverUnavailableError("CM subprocess not started"))

    try:
        req = TestImpactRequest(
            qualified_name=qualified_name,
            project=project,
            max_hops=max_hops,
            max_results=max_results,
        )
    except ValidationError as e:
        return {"ok": False, "error_code": "validation_error", "message": str(e)}

    resolved_project = req.project or _resolve_default_cm_project()

    try:
        return await test_impact(
            cm_session=_cm_session,
            qualified_name=req.qualified_name,
            project=resolved_project,
            max_hops=req.max_hops,
            max_results=req.max_results,
        )
    except Exception as e:
        handle_tool_error(e)
```

Note: `test_impact` is NOT a passthrough — it's a composite. Therefore it lives outside the `_register_passthrough` loop and is registered explicitly.

### Task 4 — unit tests

`tests/code/test_test_impact_unit.py`:

- Mock `cm_session.call_tool` for both `search_graph` and `trace_call_path`
- Mixed callers (test functions + non-test functions) → only test callers returned
- Empty callers → empty `tests` array, `ok: true` (NOT error)
- Symbol not found in `search_graph` → envelope `error_code: symbol_not_found`
- Infrastructure failure (CM session None / call_tool raises) → handle_tool_error
- Validation: max_hops out of range → envelope `error_code: validation_error`
- Truncation: max_results=2 + 5 callers → returns 2 + `max_results_truncated: true`
- Filter: test patterns vs non-test patterns
  - `repos-gimle.tests.test_foo.test_bar` → matched as test
  - `repos-gimle.src.module.helper` → NOT a test
  - `repos-gimle.tests.unit.helper` → matched (`.tests.`)
  - file_path `services/palace-mcp/tests/test_foo.py` → matched (`/tests/`)

### Task 5 — integration test through real MCP

Per `paperclip-shared-fragments/fragments/compliance-enforcement.md` MCP wire-contract rule (GIM-91):

```python
# tests/integration/test_palace_code_test_impact_wire.py
async def test_test_impact_via_streamablehttp():
    async with streamablehttp_client("http://localhost:8080/mcp") as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()
            result = await s.call_tool("palace.code.test_impact", arguments={
                "qualified_name": "repos-gimle.services.palace-mcp.src.palace_mcp.code_router.register_code_tools",
                "project": "repos-gimle",
            })
            payload = json.loads(result.content[0].text)
            assert payload["ok"] is True
            # register_code_tools is exercised by tests/test_code_router.py
            # so we expect at least 1 test caller
            assert len(payload["tests"]) >= 1
            assert all("test" in t["qualified_name"].lower() for t in payload["tests"])
```

Test target chosen because it's a known-tested function in our own repo; should always have non-empty result.

### Task 6 — README example

```markdown
### palace.code.test_impact

Find tests exercising a symbol (composite of trace_call_path callers + test pattern filter).

    palace.code.test_impact(
      qualified_name="repos-gimle.services.palace-mcp.src.palace_mcp.code_router.register_code_tools",
      project="repos-gimle",
    )

Returns up to 50 test functions ranked by hop distance. Use to focus pytest before refactoring.
```

### Task 7 — QA Phase 4.1 live smoke

Operator-driven on iMac:

1. `docker compose --profile review up -d --build --wait` (per deploy-checklist GIM-94)
2. Auth-path probe per GIM-94
3. Call `palace.code.test_impact(qualified_name="repos-gimle.services.palace-mcp.src.palace_mcp.code_router.register_code_tools", project="repos-gimle")` via MCP
4. Expect: `ok: true, tests: [...]` with at least 1 entry containing `test_` in qualified_name
5. Negative test: `palace.code.test_impact(qualified_name="repos-gimle.nonexistent.symbol", project="repos-gimle")` → expect `ok: false, error_code: symbol_not_found`
6. Verify integration test (Task 5) passes in pytest run
7. Restore production checkout to develop (per worktree-discipline.md)

## Acceptance

1. Tool callable via real MCP HTTP+SSE; returns `ok: true` + `tests` list for known symbols
2. Empty result (`tests: []`) is NOT an error — returns `ok: true, total_found: 0`
3. Symbol not found → envelope with `error_code: symbol_not_found`
4. Validation errors (max_hops out of range, qualified_name empty) → envelope with `error_code: validation_error`
5. Infrastructure errors (CM session None, network) raise via `handle_tool_error` (FastMCP `isError=true`)
6. Test pattern filter correctly excludes non-test callers
7. Tests sorted by hop distance ascending (closest test first)
8. Truncation works at max_results boundary; `max_results_truncated: true` flag set
9. Pattern #21 dedup-aware registration — `palace.code.test_impact` appears in `tools/list` exactly once
10. All MCP wire-contract test rule criteria met (per GIM-91)

## Out of scope (defer)

- Configurable test pattern regex via Settings — v1 hardcoded
- Test outcome / coverage data — separate slice if pursued
- Reverse direction (`tests covered by this test`) — semantic_search is a better fit
- Cross-project queries — defer until federation work
- `palace.code.semantic_search` — separate slice (Slice 5 candidate)

## Decisions recorded (rev2)

5 open questions from rev1 review answered by operator (2026-04-26):

| Q | Topic | Verdict | Rationale |
|---|---|---|---|
| 1 | Test pattern source | Hardcoded regex (NOT Settings field) | One Python project for now; Settings field deferred until non-Python project arrives |
| 2 | `max_hops` default | 3 (NOT 5) | Balance between coverage + noise. Caller can override per-call |
| 3 | Ambiguous qualified_name | Return `error_code: ambiguous_qualified_name` with `matches: [...]` | Don't silently take first match — leads to wrong test list returned. Force caller to refine |
| 4 | `hop_distance` in output | Keep | Useful for ranking (direct vs nested test); ~10 bytes per entry is negligible |
| 5 | Composite tool location | NEW `services/palace-mcp/src/palace_mcp/code/composite/` module | Keeps `code_router.py` as 100% passthrough (clean separation). Future composites (e.g., palace.code.semantic_search) land here too |

## Open questions

All 5 questions from rev1 answered. Spec ready for multi-reviewer adversarial round before paperclip Phase 1.1.

## References

- `services/palace-mcp/src/palace_mcp/code_router.py` — palace.code.* registration pattern (post-GIM-89 fix)
- `services/palace-mcp/src/palace_mcp/mcp_server.py:139-` — `_tool()` decorator (Pattern #21)
- CM `search_graph` schema — supports `qn_pattern` filter
- CM `trace_call_path` schema — supports `mode="callers" | "callees" | "both"`
- Memory `reference_paperclip_pr_body_literal_newlines` — gh pr create --body-file pattern
- GIM-91 — MCP wire-contract test rule
- GIM-94 — error model split standard
