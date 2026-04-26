---
slug: GIM-95-palace-memory-decide
spec: docs/superpowers/specs/2026-04-26-GIM-96-palace-memory-decide.md (rev2, commit 604a283)
branch: feature/GIM-96-palace-memory-decide
predecessor: 9c87fb9 (develop tip after GIM-94 merge)
date: 2026-04-26
owner: PythonEngineer (Tasks 1–7), QAEngineer (Task 8)
reviewers: CodeReviewer (Phase 3.1), OpusArchitectReviewer (Phase 3.2)
---

# Plan — GIM-95 `palace.memory.decide`

Write-side MCP tool for `:Decision` nodes. 8 tasks, all on `feature/GIM-96-palace-memory-decide`.

## Codebase context (verified at 604a283)

- **`_tool()` wrapper**: `mcp_server.py:148–154` — `_registered_tool_names` list + Pattern #21 dedup via `assert_unique_tool_names`.
- **Globals**: `mcp_server.py:72–88` — `_driver`, `_graphiti`, `_settings`, `_default_group_id`.
- **`save_entity_node`**: `graphiti_runtime.py:67–71` — calls `generate_name_embedding` then `node.save(g.driver)`.
- **`resolve_group_ids`**: `memory/projects.py:42–67` — handles `None` / `str` / `list[str]` / `"*"`. Raises `UnknownProjectError` for unknown slug. NOTE: spec says `_resolve_project_to_group_id` — actual function is `resolve_group_ids(tx, project, default_group_id=...)` and runs inside a transaction.
- **`_WHITELIST["Decision"]`**: `memory/filters.py:~60` — currently has `"author"` and `"status"` entries. Must be REPLACED (not just extended) because spec schema drops `author`/`status` fields and adds `slice_ref`/`decision_maker_claimed`/`decision_kind`/`tags_any`.
- **`make_decision` factory**: `graphiti_schema/entities.py:154–184` — exists but uses `text`/`status` schema that differs from spec's `body`/`slice_ref`/`decision_maker_claimed` schema. Do NOT use this factory; construct `EntityNode` directly per spec. The factory can be updated in a followup.
- **Error pattern**: `errors.py:108–115` — `handle_tool_error(exc)` raises `RuntimeError` with recovery hint. Existing tools use `"error"` key in envelope; this tool uses `"error_code"` per spec (backfill existing tools in followup).
- **Lookup error handling**: `mcp_server.py:196–214` — `UnknownProjectError` caught → envelope `{ok: false, error: "unknown_project"}`.
- **`resolve_group_ids` needs a transaction**: It runs inside `session.execute_read(tx)`. The decide tool needs `_driver` to get a session for project resolution, then `_graphiti` for `save_entity_node`. Both globals needed.

## Task 1 — Pydantic model `DecideRequest` + filter whitelist

**Owner**: PythonEngineer
**Dependencies**: none
**Affected files**:
- NEW: `services/palace-mcp/src/palace_mcp/memory/decide_models.py`
- EDIT: `services/palace-mcp/src/palace_mcp/memory/filters.py` — replace `_WHITELIST["Decision"]`

**What to do**:

1. Create `decide_models.py` with `DecideRequest` Pydantic model per spec § Validation rules. Fields:
   - `title: str` (1..200)
   - `body: str` (1..2000)
   - `slice_ref: str` (regex pattern `^GIM-\d+$|^N\+\d+[a-z]*(\.\d+)?$|^operator-decision-\d{8}$`)
   - `decision_maker_claimed: str` (field_validator against `VALID_DECISION_MAKERS` set)
   - `project: str | None = None`
   - `decision_kind: str | None` (max_length=80)
   - `tags: list[str] | None` (max_length=16 — this is Pydantic v2 `max_length` on the list itself)
   - `evidence_ref: list[str] | None` (max_length=32)
   - `confidence: float = 1.0` (ge=0.0, le=1.0)
   - Export `SLICE_REF_PATTERN` and `VALID_DECISION_MAKERS` as module-level constants.

2. In `filters.py`, REPLACE `_WHITELIST["Decision"]` (currently `{"author": ..., "status": ...}`) with:
   ```python
   "Decision": {
       "name": "n.name = $name",
       "name_pattern": "n.name CONTAINS $name_pattern",
       "slice_ref": "n.slice_ref = $slice_ref",
       "decision_maker_claimed": "n.decision_maker_claimed = $decision_maker_claimed",
       "decision_kind": "n.decision_kind = $decision_kind",
       "tags_any": "ANY(t IN n.tags WHERE t IN $tags_any)",
   },
   ```

**Acceptance criteria**:
- `DecideRequest(title="x", body="y", slice_ref="GIM-1", decision_maker_claimed="cto")` validates OK
- `DecideRequest(title="", ...)` raises `ValidationError`
- `DecideRequest(..., slice_ref="bad")` raises `ValidationError`
- `DecideRequest(..., decision_maker_claimed="hacker")` raises `ValidationError`
- `DecideRequest(..., confidence=1.5)` raises `ValidationError`
- `DecideRequest(..., tags=["a"]*17)` raises `ValidationError`
- `resolve_filters("Decision", {"slice_ref": "GIM-96"})` returns correct WHERE clause
- `resolve_filters("Decision", {"author": "x"})` returns `author` in unknown list (old key removed)

**Commit**: `feat(GIM-95): Task 1 — DecideRequest model + Decision filter whitelist`

---

## Task 2 — `decide()` implementation

**Owner**: PythonEngineer
**Dependencies**: Task 1
**Affected files**:
- NEW: `services/palace-mcp/src/palace_mcp/memory/decide.py`

**What to do**:

1. Create `decide.py` with `async def decide(req, *, g, group_id) -> dict[str, Any]`.
2. Construct `EntityNode(name=req.title, group_id=group_id, labels=["Decision"], attributes={...})` with ALL spec attributes: `body`, `slice_ref`, `decision_maker_claimed`, `decision_kind`, `provenance="asserted"`, `confidence`, `decided_at` (UTC ISO8601), `extractor="palace.memory.decide@0.1"`, `extractor_version="0.1"`, `attestation="none"`, `tags` (default `[]`), `evidence_ref` (default `[]`).
3. Call `save_entity_node(g, node)` — this handles embedding + persist. Let infra exceptions propagate.
4. Return success envelope: `{ok: True, uuid, name, slice_ref, decision_maker_claimed, decided_at, name_embedding_dim}`.

**Important**: Do NOT use `make_decision` factory from `graphiti_schema/entities.py` — it has a different field schema (`text`/`status` vs `body`/`slice_ref`). Construct `EntityNode` directly.

**Important**: `group_id` resolution happens in the MCP wrapper (Task 3), not here. This function receives the resolved `group_id` string.

**Acceptance criteria**:
- Given valid `DecideRequest` + mock Graphiti, returns `{ok: True, uuid: ..., name_embedding_dim: 1024}`
- `EntityNode` constructed with `labels=["Decision"]`
- All 12 attribute keys present in `node.attributes`
- `save_entity_node` called exactly once
- Embedder/Neo4j exceptions propagate (not caught)

**Commit**: `feat(GIM-95): Task 2 — decide() implementation`

---

## Task 3 — MCP tool registration with split error model

**Owner**: PythonEngineer
**Dependencies**: Tasks 1, 2
**Affected files**:
- EDIT: `services/palace-mcp/src/palace_mcp/mcp_server.py`

**What to do**:

1. Import `DecideRequest` from `decide_models`, `decide` from `decide`, `ValidationError` from `pydantic`.
2. Register `palace.memory.decide` via `@_tool(name=..., description=...)` per spec § MCP tool signature.
3. Error handling (split model):
   - `_graphiti is None` → `handle_tool_error(DriverUnavailableError("graphiti not initialized"))` (infra path)
   - Pydantic `ValidationError` → catch → return `{"ok": False, "error_code": "validation_error", "message": str(e)}` (envelope)
   - Project resolution: need `_driver` for a session → `resolve_group_ids(tx, project, default_group_id=_default_group_id)`. `UnknownProjectError` → return `{"ok": False, "error_code": "unknown_project", "message": str(e)}` (envelope). NOTE: use `"error_code"` not `"error"` per spec decision.
   - `decide()` call: `EmbedderUnavailableError` / `DriverUnavailableError` / generic Exception → `handle_tool_error(exc)` (infra path)
4. Project resolution detail: `resolve_group_ids` requires a Neo4j transaction. Pattern from `palace_memory_lookup`:
   ```python
   async with _driver.session() as session:
       group_ids = await session.execute_read(
           lambda tx: resolve_group_ids(tx, project, default_group_id=_default_group_id)
       )
   group_id = group_ids[0]  # decide always resolves to exactly one
   ```
   If `project is None`, skip the session — use `_default_group_id` directly.

**Acceptance criteria**:
- `palace.memory.decide` appears in `tools/list` exactly once (Pattern #21)
- `build_mcp_asgi_app()` does not crash (existing dedup test still passes)
- Valid call → `{ok: True, ...}`
- Bad input → `{ok: False, error_code: "validation_error", ...}` (NOT `isError`)
- Unknown project → `{ok: False, error_code: "unknown_project", ...}` (NOT `isError`)
- Graphiti down → `RuntimeError` via `handle_tool_error` → FastMCP `isError=True`

**Commit**: `feat(GIM-95): Task 3 — palace.memory.decide MCP registration`

---

## Task 4 — Unit tests

**Owner**: PythonEngineer
**Dependencies**: Tasks 1, 2, 3
**Affected files**:
- NEW: `services/palace-mcp/tests/memory/test_decide_models.py`
- NEW: `services/palace-mcp/tests/memory/test_decide.py`

**What to do**:

### 4a — Model validation tests (`test_decide_models.py`)
- Valid minimal input → OK
- Valid full input (all optional fields) → OK
- `title=""` → `ValidationError`
- `title` > 200 chars → `ValidationError`
- `body=""` → `ValidationError`
- `body` > 2000 chars → `ValidationError`
- `slice_ref="bad-format"` → `ValidationError`
- `slice_ref="GIM-123"` → OK
- `slice_ref="N+2a"` → OK
- `slice_ref="N+1a.1"` → OK
- `slice_ref="operator-decision-20260426"` → OK
- `decision_maker_claimed="hacker"` → `ValidationError`
- Each valid maker in `VALID_DECISION_MAKERS` → OK
- `confidence=1.5` → `ValidationError`
- `confidence=-0.1` → `ValidationError`
- `tags=["a"]*17` → `ValidationError`
- `tags=["a"]*16` → OK
- `evidence_ref=["x"]*33` → `ValidationError`
- `decision_kind` > 80 chars → `ValidationError`

### 4b — decide() function tests (`test_decide.py`)
- Happy path: mock `save_entity_node` → returns `{ok: True}` with correct fields
- Verify `EntityNode` constructed with `labels=["Decision"]`, all 12 attribute keys
- `save_entity_node` raises generic Exception → propagates (not caught)
- Verify `decided_at` is ISO8601 UTC
- Verify defaults: `tags=[]`, `evidence_ref=[]`, `provenance="asserted"`, `attestation="none"`

### 4c — Filter whitelist test (extends existing `test_filters.py`)
- `resolve_filters("Decision", {"slice_ref": "GIM-96"})` → correct clause + params
- `resolve_filters("Decision", {"tags_any": ["foo"]})` → correct `ANY(...)` clause
- `resolve_filters("Decision", {"author": "x"})` → `author` in unknown list (old key gone)

**Acceptance criteria**:
- All tests pass: `uv run pytest tests/memory/test_decide_models.py tests/memory/test_decide.py -v`
- Coverage ≥ 90% on `decide.py` + `decide_models.py`
- Existing `test_filters.py` still passes

**Commit**: `test(GIM-95): Task 4 — unit tests for decide models + function + filters`

---

## Task 5 — MCP wire-contract integration test

**Owner**: PythonEngineer
**Dependencies**: Task 3
**Affected files**:
- NEW: `services/palace-mcp/tests/integration/test_palace_memory_decide_wire.py`

**What to do**:

Per GIM-91 wire-contract rule, test through real MCP HTTP+SSE transport.

1. Use `streamablehttp_client("http://localhost:8080/mcp")` pattern from `tests/integration/test_mcp_wire_pattern.py`.
2. Call `palace.memory.decide` with valid input → assert `{ok: True, uuid: ..., slice_ref: ...}`.
3. Call with invalid `decision_maker_claimed="hacker"` → assert `{ok: False, error_code: "validation_error"}` (envelope, NOT `isError`).
4. Mark with `@pytest.mark.integration` — requires running palace-mcp container.

**Acceptance criteria**:
- Test passes against running palace-mcp with Neo4j + embedder
- Valid call returns `ok: True` with UUID
- Invalid call returns envelope (not tool error)
- Uses real MCP transport, not direct function call

**Commit**: `test(GIM-95): Task 5 — wire-contract integration test`

---

## Task 6 — Round-trip integration test (decide → lookup)

**Owner**: PythonEngineer
**Dependencies**: Tasks 1, 3, 5
**Affected files**:
- NEW: `services/palace-mcp/tests/integration/test_decide_lookup_roundtrip.py`

**What to do**:

1. Write via `palace.memory.decide` (unique `slice_ref` per test run to avoid collisions).
2. Read back via `palace.memory.lookup(entity_type="Decision", filters={"slice_ref": "<unique>"})`.
3. Assert the returned item has matching `uuid`, `decision_maker_claimed`, `confidence`, `extractor`, `attestation`.

**Critical**: This test validates that Task 1's filter whitelist update works. Without `slice_ref` in `_WHITELIST["Decision"]`, the filter is logged + ignored and lookup returns ALL Decision nodes — the test would pass vacuously if not asserting on the specific UUID.

**Acceptance criteria**:
- Write returns `{ok: True, uuid: ...}`
- Lookup with `slice_ref` filter returns exactly the written node (match on UUID)
- Properties include `attestation: "none"`, `extractor: "palace.memory.decide@0.1"`
- Test fails if `_WHITELIST["Decision"]` doesn't include `slice_ref` (guard assertion)

**Commit**: `test(GIM-95): Task 6 — decide→lookup round-trip integration test`

---

## Task 7 — README update

**Owner**: PythonEngineer
**Dependencies**: Task 2
**Affected files**:
- EDIT: `services/palace-mcp/README.md`

**What to do**:

Add usage example for `palace.memory.decide` + read-back via lookup:

```
palace.memory.decide(
  title="Adopt edge-based supersession model",
  body="Decision nodes use (:Decision)-[:SUPERSEDES]->(:Decision) edges...",
  slice_ref="GIM-96",
  decision_maker_claimed="cto",
  decision_kind="design",
  tags=["architecture","graphiti"],
  confidence=0.9,
)
# Read back:
palace.memory.lookup(entity_type="Decision", filters={"slice_ref": "GIM-96"})
```

**Acceptance criteria**:
- README has working example call + read-back
- No broken markdown

**Commit**: `docs(GIM-95): Task 7 — README example for palace.memory.decide`

---

## Task 8 — QA Phase 4.1 live smoke

**Owner**: QAEngineer
**Dependencies**: Tasks 1–7 merged to feature branch
**Affected files**: none (evidence in paperclip comment)

**What to do** (per spec § Task 8):

1. Deploy feature branch on iMac (`docker compose --profile review up -d --build`)
2. Record real Decision: `palace.memory.decide(title="Adopt palace.memory.decide as Slice 1 of N+2 Cat 1", body="...", slice_ref="GIM-95", decision_maker_claimed="operator", decision_kind="board-ratification", tags=["n+2","category-1","enabler"])`
3. Expect `{ok: true, uuid: "..."}`
4. Read back: `palace.memory.lookup(entity_type="Decision", filters={"slice_ref": "GIM-95"})` — expect match
5. `palace.memory.health` — `entity_counts.Decision >= 1`
6. Trigger validation error: `decision_maker_claimed="hacker"` → envelope `error_code: validation_error`
7. Trigger infra error: stop graphiti container, call decide → FastMCP `isError=true`
8. Paste all outputs in QA evidence comment
9. Restore production checkout to `develop` after testing

**Acceptance criteria**:
- All 7 smoke steps produce expected output
- Evidence comment posted by QAEngineer (not implementer)
- Production checkout restored to develop

---

## Execution order

```
T1 (model + filters) ──→ T2 (decide impl) ──→ T3 (MCP reg) ──→ T4 (unit tests)
                                                  │                    │
                                                  ├──→ T5 (wire test)  │
                                                  │                    │
                                                  └──→ T6 (roundtrip) ←┘
T2 ──→ T7 (README)

T1–T7 all green ──→ T8 (QA smoke)
```

Tasks 5, 6, and 7 can run in parallel after Task 3 (with Task 4 also being parallelizable with 5/6).

## Phase sequence

| Phase | Agent | Action |
|---|---|---|
| 1.1 Formalize | CTO | Write this plan, push, reassign to CR |
| 1.2 Plan-first review | CodeReviewer | Validate tasks, flag gaps, APPROVE → reassign to PE |
| 2 Implement | PythonEngineer | TDD through Tasks 1–7, push frequently |
| 3.1 Mechanical review | CodeReviewer | `ruff check && mypy src/ && pytest` output in APPROVE |
| 3.2 Adversarial review | OpusArchitectReviewer | Poke holes; findings addressed before Phase 4 |
| 4.1 Live smoke | QAEngineer | Task 8 evidence on iMac |
| 4.2 Merge | CTO | Squash-merge to develop, then chain-trigger GIM-96 |
