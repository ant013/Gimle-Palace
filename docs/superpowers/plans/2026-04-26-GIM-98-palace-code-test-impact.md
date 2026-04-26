---
slug: GIM-98-palace-code-test-impact
paperclip_issue: 98
spec: docs/superpowers/specs/2026-04-26-GIM-98-palace-code-test-impact.md
branch: feature/GIM-98-palace-code-test-impact
predecessor: 1f7c8f2 (develop tip after GIM-97 merge)
date: 2026-04-26
status: draft
---

# GIM-98 Implementation Plan — `palace.code.test_impact`

Composite MCP tool: given a Function's `qualified_name`, return tests exercising it.
Hybrid design: default Cypher `:TESTS` edge (hop=1, exact), opt-in `trace_call_path` multi-hop.

## Phase 2 — Implementation (PythonEngineer)

7 implementation steps (T1–T8 from spec), TDD order. Each step = test first, then impl, then commit.

### Step 1: Pydantic model + accessor extraction (T1 + T3)

**Description:** Create `TestImpactRequest` in `code_composite.py`. Extract `get_cm_session()` accessor and `parse_cm_result()` helper from `code_router.py` to module-level public functions. Refactor `_forward` to use `parse_cm_result`.

**Test first:**
- Unit test for `TestImpactRequest` validation: valid qn, empty string, leading digit, spaces, max_hops bounds, max_results bounds.
- Unit test for `parse_cm_result`: structured content path, text content path, empty content.

**Acceptance:**
- `TestImpactRequest` rejects `""`, `"0bad"`, `"bad name"`, `max_hops=10`, `max_results=0`.
- `get_cm_session()` returns `_cm_session` (None when not started).
- `parse_cm_result` handles `structuredContent`, JSON text, non-JSON text, empty content.
- `_forward` behaviour unchanged (uses `parse_cm_result` internally).

**Files:** `code_router.py` (add 2 public functions, refactor `_forward`), `code_composite.py` (new, model only).

**Commit:** `feat(GIM-98): T1+T3 — TestImpactRequest model + code_router accessor/helper extraction`

**Owner:** PythonEngineer  
**Deps:** none

---

### Step 2: Default path implementation (T2 partial — tests_edge)

**Description:** Implement `_test_impact_tests_edge`, `_resolve_qn`, and the `register_code_composite_tools` registration function with the default (`include_indirect=False`) path only.

**Test first:**
- Unit tests for default path: symbol_not_found, ambiguous (exact count), ambiguous (lower-bound), happy path, truncation, empty result, resolved QN echo.
- Mock `code_router.get_cm_session` → fake `ClientSession` with `call_tool` side effects.

**Acceptance:**
- `symbol_not_found` → `ok: false, error_code: "symbol_not_found"`, `requested_qualified_name` echoed.
- `ambiguous_qualified_name` → `ok: false`, `matches` array, count phrasing correct.
- Happy path → `ok: true, method: "tests_edge"`, all entries `hop: 1`, no `disambiguation_caveat`.
- Truncation → `truncated: true`, `total_found` is lower-bound.
- `requested_qualified_name` present in every response.

**Files:** `code_composite.py` (add `_resolve_qn`, `_test_impact_tests_edge`, registration skeleton).

**Commit:** `feat(GIM-98): T2 — default path (tests_edge) + _resolve_qn disambiguation`

**Owner:** PythonEngineer  
**Deps:** Step 1

---

### Step 3: Opt-in path implementation (T2 partial — trace_call_path)

**Description:** Implement `_test_impact_trace` and wire `include_indirect=True` branch in the registration function.

**Test first:**
- Unit tests for opt-in path: happy path (mixed test + non-test callers, sorted by hop), empty trace, truncation, `disambiguation_caveat` always present.

**Acceptance:**
- `method: "trace_call_path"`, `disambiguation_caveat` present.
- Tests filtered to `is_test` only, sorted by `hop`.
- `total_found` computed before truncation (exact count).
- `max_hops_used` reflects requested value.

**Files:** `code_composite.py` (add `_test_impact_trace`, complete registration fn).

**Commit:** `feat(GIM-98): T2 — opt-in path (trace_call_path) + infrastructure error handling`

**Owner:** PythonEngineer  
**Deps:** Step 2

---

### Step 4: Registration wiring + config (T4)

**Description:** Wire `register_code_composite_tools` in `mcp_server.py` lifespan after `register_code_tools`. Add `cm_default_project` to `Settings` in `config.py`.

**Test first:**
- Unit test: `palace.code.test_impact` appears in `tools/list` exactly once (dedup-aware Pattern #21).
- Unit test: `cm_session is None` → `handle_tool_error` raises.

**Acceptance:**
- Tool registered after `register_code_tools` in lifespan.
- `Settings.cm_default_project` defaults to `"repos-gimle"`, overridable via `PALACE_CM_DEFAULT_PROJECT`.
- Closed schema (Pydantic-derived from typed signature), not open `_OpenArgs`.

**Files:** `mcp_server.py`, `config.py`, `code_composite.py` (adjust if needed).

**Commit:** `feat(GIM-98): T4 — wire composite registration + cm_default_project config`

**Owner:** PythonEngineer  
**Deps:** Step 3

---

### Step 5: CM contract test (T7)

**Description:** Pin literal shapes of `search_graph`, `query_graph`, `trace_call_path` responses from codebase-memory. Tests fail loudly on CM library drift.

**Test first:** (these ARE the tests — contract tests are the deliverable)

**Acceptance:**
- `search_graph` response has `results[].{name, qualified_name, label, file_path}`.
- `trace_call_path` response has `callers[].{is_test, hop, name, qualified_name}`; `is_test` absent on non-test callers.
- `query_graph` response has `rows`, `columns`; `:TESTS` edge exists for `register_code_tools`.
- `LAST_VERIFIED_CM_VERSION` constant documents pin date.

**Files:** `tests/code_composite/test_cm_contract.py` (new).

**Commit:** `test(GIM-98): T7 — CM contract tests pinning search/query/trace shapes`

**Owner:** PythonEngineer  
**Deps:** Step 4

---

### Step 6: Integration test via MCP HTTP+SSE (T6)

**Description:** Wire-level integration tests per GIM-91 rule. Real MCP HTTP+SSE against running palace-mcp with CM subprocess.

**Test first:** (these ARE the tests)

**Acceptance:**
- Default path happy: `ok: true, method: "tests_edge"`, `tests` non-empty, all `hop: 1`.
- Opt-in path happy: `ok: true, method: "trace_call_path"`, `disambiguation_caveat` present.
- Not found: `error_code: symbol_not_found`.
- Validation: `error_code: validation_error`.

**Files:** `tests/integration/test_palace_code_test_impact_wire.py` (new).

**Commit:** `test(GIM-98): T6 — integration tests via MCP HTTP+SSE`

**Owner:** PythonEngineer  
**Deps:** Step 4

---

### Step 7: README update (T8)

**Description:** Add `palace.code.test_impact` usage examples (both paths) to `services/palace-mcp/README.md`.

**Acceptance:**
- Default path example with full `qualified_name`.
- Opt-in path example with `include_indirect=True`.
- Brief explanation of when to use each.

**Files:** `services/palace-mcp/README.md`.

**Commit:** `docs(GIM-98): T8 — README palace.code.test_impact usage examples`

**Owner:** PythonEngineer  
**Deps:** Step 3

---

## Phase 3 — Review

### Phase 3.1: Mechanical review (CodeReviewer)

- `uv run ruff check && uv run mypy src/ && uv run pytest` output pasted in APPROVE.
- No rubber-stamp — verify all 15 acceptance items from spec.

### Phase 3.2: Adversarial review (OpusArchitectReviewer)

- Poke holes in Cypher injection surface (string interpolation in `_test_impact_tests_edge`).
- Verify TOCTOU safety of `get_cm_session()` capture.
- Validate `_ToolDecorator` Protocol dedup correctness.

## Phase 4 — QA + Merge

### Phase 4.1: Live smoke (QAEngineer) — T9

On iMac docker stack:
1. `docker compose --profile review up -d --build --wait`
2. Default path: `palace.code.test_impact(qualified_name="register_code_tools")` → `ok: true, method: "tests_edge"`, tests non-empty.
3. Opt-in: same with `include_indirect=True, max_hops=3` → `method: "trace_call_path"`, caveat present.
4. Not found: `"nonexistent_function_xyz_abc"` → `symbol_not_found`.
5. Validation: `"bad name with spaces"` → `validation_error`.
6. Ambiguous: find known-ambiguous suffix via `search_graph`, use it → `ambiguous_qualified_name`.
7. pytest run (unit + contract + integration).
8. Restore production checkout to develop.

### Phase 4.2: Merge (CTO)

Squash-merge to develop after CI green + CR APPROVE + QA evidence.

## Dependency graph

```
Step 1 (T1+T3) ─┐
                 ├─ Step 2 (T2 default) ─┬─ Step 3 (T2 opt-in) ─┬─ Step 4 (T4) ─┬─ Step 5 (T7)
                 │                        │                       │                ├─ Step 6 (T6)
                 │                        │                       │                └─ Step 7 (T8)
                 │                        │                       │
Phase 3.1 (CR) ──────────────────────────────────────────────────────── after all Steps
Phase 3.2 (Opus) ─────────────────────────────────────────────────────── after 3.1
Phase 4.1 (QA) ────────────────────────────────────────────────────────── after 3.2
Phase 4.2 (Merge) ──────────────────────────────────────────────────────── after 4.1
```

## Notes

- Steps 5, 6, 7 can run in parallel after Step 4 (no mutual deps).
- Cypher string interpolation in `_test_impact_tests_edge` uses `resolved_qn` from `search_graph` result (graph-sourced, not user input) — but reviewer should verify no injection path from user `qualified_name` → Cypher.
- `code_composite.py` stays as single file until 2nd composite ships (spec out-of-scope note).
