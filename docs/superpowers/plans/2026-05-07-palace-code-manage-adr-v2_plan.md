# `palace.code.manage_adr` Writable v2 (E5) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: `superpowers:test-driven-development`. Atomic-handoff discipline mandatory.

**Slice:** Phase 6 E5 — `palace.code.manage_adr` v2 (writable + graph projection).
**Spec:** `docs/superpowers/specs/2026-05-07-palace-code-manage-adr-v2_spec.md`.
**Source branch:** `feature/GIM-274-palace-code-manage-adr-v2` cut from `origin/develop`.
**Target branch:** `develop`. Squash-merge on APPROVE.
**Team:** Claude. Phase chain: CTO → CodeReviewer (plan-first) → MCPEngineer or PythonEngineer → CR (mechanical) → OpusArchitectReviewer (adversarial) → QAEngineer → CTO merge.

> **Rev4 — scheduling correction** (CTO-E5-C1):
> Single Claude PE is fully occupied on AV1 critical path. E5 starts
> AFTER S2.3 merges (approx. week 15 of 18w envelope). Wall-time:
> ~2-3w. Operator may choose to defer to post-v1 if late-stage AV1
> work crowds the remaining envelope tail. **PE bandwidth check
> mandatory before cutting branch.**

---

## Phase 0 — Prereqs (Board)

### Step 0.1: PE-bandwidth gate (rev4 addition)

**Owner:** Board.

- [ ] Verify AV1 S2.3 (`#7 Error Handling`) is ✅ on develop.
      If not, do NOT cut E5 branch — Claude PE is still occupied.
- [ ] Verify operator confirms E5 schedule slot:
  - **Option A (default)**: E5 starts immediately after S2.3 merges.
    Tail of 18w envelope; ends approx. week 17-18.
  - **Option B**: E5 deferred to post-v1 (after S5 ships). Operator
    decides based on what S4 smoke surfaces.
- [ ] Document chosen option in PR body + paperclip issue.

**Acceptance:** S2.3 merged; option chosen + recorded.

### Step 0.2: Issue + branch

- [ ] Open paperclip issue `palace.code.manage_adr writable v2 (E5)`.
- [ ] Body = link to spec + plan; `GIM-274` placeholder.
- [ ] Reassign CTO.

---

## Phase 1 — CTO formalisation + plan-first review (CodeReviewer)

### Step 1.1 (CTO)

- [ ] Verify spec §3 schema doesn't conflict with existing `:Decision`
      semantics.
- [ ] Resolve AD-D1..AD-D5 (defaults from spec).
- [ ] Reassign CodeReviewer.

### Step 1.2 (CodeReviewer plan-first)

- [ ] Verify each tool mode has test+impl+commit step below.
- [ ] Verify idempotency contract is testable (same `body_hash`
      check).
- [ ] APPROVE → MCPEngineer (or PythonEngineer per CTO assignment).

---

## Phase 2 — Implementation

### Phase 2.1 — Schema + base classes

#### Step 2.1.1: Failing tests (schema)

**Files:**
- `services/palace-mcp/tests/adr/unit/test_adr_schema.py` (new).

- [ ] Test: `AdrDocument` Pydantic model serialises/deserialises.
- [ ] Test: `AdrSection` Pydantic model with `body_hash` derives
      from body content (SHA-256).
- [ ] Test: schema migration applies new constraints + indices
      idempotently.
- [ ] All RED initially.

#### Step 2.1.2: Implement models + schema + router skeleton

**Files:**
- `services/palace-mcp/src/palace_mcp/adr/__init__.py` (new).
- `services/palace-mcp/src/palace_mcp/adr/models.py` (new).
- `services/palace-mcp/src/palace_mcp/adr/schema.py` (new) —
  `ensure_adr_schema()`: Cypher constraints + indices, idempotent.
- `services/palace-mcp/src/palace_mcp/adr/router.py` (new) —
  `register_adr_tools(tool_decorator)` skeleton (modes wired in
  subsequent phases).
- `services/palace-mcp/src/palace_mcp/mcp_server.py` — import and call
  `register_adr_tools(_tool)` alongside existing `register_code_*` calls.
  Call `ensure_adr_schema(driver)` in server lifespan (AD-D8).
- `services/palace-mcp/src/palace_mcp/code_router.py` — remove
  `"manage_adr"` from `_DISABLED_CM_TOOLS` dict (AD-D7).
- `docs/postulates/` — create directory (W1; can be empty initially,
  `.gitkeep` file to ensure git tracks it).

- [ ] Implement Pydantic models per spec §4.
- [ ] Implement schema migration with `CALL { … } IN TRANSACTIONS`
      and `IF NOT EXISTS` clauses.
- [ ] Schema bootstrap in server lifespan, NOT extractor pipeline (AD-D8).
- [ ] Native `@mcp.tool` registration, NOT CM subprocess passthrough (AD-D7).
- [ ] Tests GREEN.

#### Step 2.1.3: Commit

- [ ] Commit: `feat(GIM-274): manage_adr v2 schema + Pydantic models`.

---

### Phase 2.2 — `read` mode (NEW — no v1 exists)

> **Note:** v1 `manage_adr` was DISABLED (`_DISABLED_CM_TOOLS` in
> `code_router.py:151`). `read` is a new implementation, not a refactor.
> There is no backwards-compat regression test.

#### Step 2.2.1: Failing tests

**Files:**
- `services/palace-mcp/tests/adr/unit/test_adr_reader.py` (new).

- [ ] Test: `read(slug="test-adr")` reads file from
      `docs/postulates/test-adr.md`, returns markdown body + section list.
- [ ] Test: `read(slug="nonexistent")` returns error envelope
      `error_code="adr_not_found"`.
- [ ] Test: `read` side-effect: idempotent graph projection (file
      → `:AdrDocument` + `:AdrSection` nodes).
- [ ] All RED.

#### Step 2.2.2: Implement reader

**Files:**
- `services/palace-mcp/src/palace_mcp/adr/reader.py` (new).

- [ ] Read uses file as source of truth (AD-D1: file canonical).
- [ ] Side-effect: `read` triggers idempotent graph projection (file
      → `:AdrDocument` + `:AdrSection`).
- [ ] Tests GREEN.

#### Step 2.2.3: Commit

- [ ] Commit: `feat(GIM-274): manage_adr read mode (file-to-graph projection)`.

---

### Phase 2.3 — `write` mode (NEW)

#### Step 2.3.1: Failing tests

**Files:**
- `services/palace-mcp/tests/adr/unit/test_adr_writer.py` (new).

- [ ] Test: `write(slug="x", section="PURPOSE", body="...")` creates
      file under `docs/postulates/x.md` with proper structure.
- [ ] Test: same `write(...)` twice = idempotent (same `body_hash`,
      no file mtime change).
- [ ] Test: `write(...)` updates `:AdrSection` row; `:AdrDocument.updated_at`
      reflects new time.
- [ ] Test: `write` with invalid section name → error envelope
      `error_code="invalid_section"`.
- [ ] All RED.

#### Step 2.3.2: Implement writer

**Files:**
- `services/palace-mcp/src/palace_mcp/adr/writer.py` (new).
- `services/palace-mcp/src/palace_mcp/adr/router.py` — wire `mode="write"`.

- [ ] Validate inputs (Pydantic at MCP boundary).
- [ ] File-level advisory lock via `fcntl.flock` (AD-D9; stdlib `fcntl`
      module, no third-party `filelock` package).
- [ ] Read existing file → parse 6 sections → splice in new body
      for target section → write back.
- [ ] In same transaction (driver-level): upsert `:AdrSection`.
- [ ] Tests GREEN.

#### Step 2.3.3: Commit

- [ ] Commit: `feat(GIM-274): manage_adr write mode (idempotent section upsert)`.

---

### Phase 2.4 — `supersede` mode (NEW)

#### Step 2.4.1: Failing tests

**Files:**
- `services/palace-mcp/tests/adr/unit/test_adr_supersede.py` (new).

- [ ] Test: `supersede(old_slug="a", new_slug="b", reason="...")`:
  - Old `:AdrDocument.status = "superseded"`.
  - New `:AdrDocument.status = "active"` (creates new if missing).
  - Edge `(:AdrDocument {slug:"a"})-[:SUPERSEDED_BY {reason, ts}]->(:AdrDocument {slug:"b"})`.
- [ ] Test: superseding already-superseded ADR → idempotent.
- [ ] Test: file-side: old file gets a header banner
      `**SUPERSEDED by <new>** — <reason>`.
- [ ] All RED.

#### Step 2.4.2: Implement supersede

**Files:**
- `services/palace-mcp/src/palace_mcp/adr/supersede.py` (new).
- `services/palace-mcp/src/palace_mcp/adr/router.py` — wire `mode="supersede"`.

- [ ] Same `fcntl.flock` + file edit + graph update transactional pattern.
- [ ] Tests GREEN.

#### Step 2.4.3: Commit

- [ ] Commit: `feat(GIM-274): manage_adr supersede mode`.

---

### Phase 2.5 — `query` mode (existing v1 → graph-augmented)

#### Step 2.5.1: Failing tests

**Files:**
- `services/palace-mcp/tests/adr/unit/test_adr_query.py` (new).

- [ ] Test: `query(keyword="X")` returns ADRs whose section
      `body_excerpt` contains "X".
- [ ] Test: `query(section_filter="ARCHITECTURE")` returns only
      ARCHITECTURE sections across all ADRs.
- [ ] Test: `query(project_filter="gimle-*")` returns project-prefixed
      slugs.
- [ ] Test: query against empty graph returns empty list (not error).

#### Step 2.5.2: Implement query

**Files:**
- `services/palace-mcp/src/palace_mcp/adr/query.py` (new).
- `services/palace-mcp/src/palace_mcp/adr/router.py` — wire `mode="query"`.

- [ ] Cypher-only text search via `body_excerpt CONTAINS` / `STARTS WITH`
      (AD-D6: no Tantivy — ADR corpus is tens of documents, Cypher sufficient).
- [ ] Tests GREEN.

#### Step 2.5.3: Commit

- [ ] Commit: `feat(GIM-274): manage_adr query mode (graph-augmented)`.

---

### Phase 2.6 — `:Decision` bridge (post-spec AD-D5: manual)

#### Step 2.6.1: Failing test

**Files:**
- `services/palace-mcp/tests/adr/unit/test_adr_decision_bridge.py` (new).

- [ ] Test: `manage_adr(mode="write", slug="x", section="PURPOSE",
      body="...", decision_id="<uuid>")` creates
      `(:Decision {id})-[:CITED_BY]->(:AdrDocument {slug})` edge.
      (`decision_id` param is in spec §5 signature — AD-D5: manual bridge.)
- [ ] Test: writing without `decision_id` does NOT create edge.
- [ ] Test: `decision_id` referencing non-existent `:Decision` →
      error envelope `error_code="decision_not_found"` (no orphan edge).

#### Step 2.6.2: Implement bridge

**Files:**
- `services/palace-mcp/src/palace_mcp/adr/decision_bridge.py` (new).
- `services/palace-mcp/src/palace_mcp/adr/writer.py` — call bridge
  conditionally when `decision_id` present.

- [ ] Conditional edge creation when `decision_id` present.
- [ ] Validate `:Decision` exists before creating edge.
- [ ] Tests GREEN.

#### Step 2.6.3: Commit

- [ ] Commit: `feat(GIM-274): manage_adr decision bridge (CITED_BY)`.

---

### Phase 2.8 — MCP wire tests (`streamablehttp_client`)

> Per GIM-182 rule: any `@mcp.tool` must have real MCP HTTP coverage.
> Pattern: `tests/integration/test_palace_memory_decide_wire.py`.

#### Step 2.8.1: Wire test file

**Files:**
- `services/palace-mcp/tests/integration/test_manage_adr_wire.py` (new).

- [ ] Test: `palace.code.manage_adr` appears in `tools/list`.
- [ ] Test: `read` mode — valid slug succeeds, `payload["ok"] is True`.
- [ ] Test: `read` mode — nonexistent slug fails, `error_code="adr_not_found"`.
- [ ] Test: `write` mode — valid args succeed, `payload["ok"] is True`.
- [ ] Test: `write` mode — invalid section fails, exact `error_code`.
- [ ] Test: `supersede` mode — valid args succeed.
- [ ] Test: `supersede` mode — nonexistent old slug fails.
- [ ] Test: `query` mode — valid args succeed (empty result = ok, not error).
- [ ] Test: `write` with `decision_id` — valid Decision succeeds.
- [ ] Test: `write` with `decision_id` — nonexistent Decision fails,
      `error_code="decision_not_found"`.
- [ ] No tautological assertions.
- [ ] All GREEN (run after all unit/integration tests pass).

#### Step 2.8.2: Commit

- [ ] Commit: `test(GIM-274): manage_adr MCP wire tests (streamablehttp_client)`.

---

### Phase 2.7 — Runbook + CLAUDE.md update

- [ ] `docs/runbooks/manage-adr-v2.md` (new):
  - Tool surface (4 modes) with examples.
  - File-vs-graph drift handling (manual edits + `sync` subcommand).
  - Decision bridge usage.
  - 6-section format reminder.
- [ ] Update `CLAUDE.md` to reference manage_adr v2 (replace v1 entry
      if exists; otherwise add new entry).
- [ ] Push branch.
- [ ] Open PR `feat(GIM-274): palace.code.manage_adr writable v2 (E5)`.
- [ ] Reassign CodeReviewer.

---

## Phase 3 — Review

### Phase 3.1 — Mechanical (CodeReviewer)

- [ ] `gh pr checks` green; pytest output for new tests.
- [ ] Verify `manage_adr` removed from `_DISABLED_CM_TOOLS` (AD-D7).
- [ ] Verify all 4 modes covered + bridge + wire tests.
- [ ] File count matches File Structure table (N1).
- [ ] APPROVE → OpusArchitectReviewer.

### Phase 3.2 — Adversarial (Opus)

- [ ] Probe: file/graph drift recovery — manually edit a file,
      run `read`, verify graph re-projects.
- [ ] Probe: concurrent `write` calls — flock works correctly?
- [ ] Probe: supersede chain — A→B→C, what happens to B (still
      "superseded" or downgraded)?
- [ ] Probe: query against very large ADR corpus (>100 documents)
      — Cypher latency acceptable?
- [ ] Probe: `decision_id` references non-existent Decision —
      error envelope clear, no orphan edge?

---

## Phase 4 — QA evidence (QAEngineer on iMac)

- [ ] iMac live: bring up palace-mcp.
- [ ] Live MCP call:
  - `manage_adr(mode="read", slug="<existing>")` → markdown + sections.
  - `manage_adr(mode="write", slug="test-e5-smoke", section="PURPOSE", body="smoke")` → idempotent.
  - `manage_adr(mode="supersede", old_slug="<old>", new_slug="<new>", reason="smoke")` → graph edge.
  - `manage_adr(mode="query", keyword="smoke")` → finds the test ADR.
- [ ] Cypher: `MATCH (d:AdrDocument)-[:HAS_SECTION]->(s:AdrSection) RETURN d.slug, count(s)` — populated.
- [ ] Verify file `docs/postulates/test-e5-smoke.md` created on iMac
      filesystem.
- [ ] Cleanup: delete test ADR file + graph rows.
- [ ] QA Evidence in PR body.

---

## Phase 5 — Merge (CTO)

- [ ] CI green; CR + Opus APPROVE; QA Evidence.
- [ ] Squash-merge.
- [ ] Update `docs/roadmap-archive.md` §"Phase 6" E5 row → ✅ + SHA.
- [ ] iMac deploy.

---

## DoD checklist

- [ ] Schema + 4 tool modes (read, write, supersede, query) +
      decision bridge + runbook + CLAUDE.md update — merged.
- [ ] Smoke runs all 4 modes successfully on iMac.
- [ ] Roadmap E5 row → ✅.

---

## File Structure (N1)

| File | Type | Phase |
|------|------|-------|
| `services/palace-mcp/src/palace_mcp/adr/__init__.py` | new | 2.1 |
| `services/palace-mcp/src/palace_mcp/adr/models.py` | new | 2.1 |
| `services/palace-mcp/src/palace_mcp/adr/schema.py` | new | 2.1 |
| `services/palace-mcp/src/palace_mcp/adr/router.py` | new | 2.1–2.5 |
| `services/palace-mcp/src/palace_mcp/adr/reader.py` | new | 2.2 |
| `services/palace-mcp/src/palace_mcp/adr/writer.py` | new | 2.3 |
| `services/palace-mcp/src/palace_mcp/adr/supersede.py` | new | 2.4 |
| `services/palace-mcp/src/palace_mcp/adr/query.py` | new | 2.5 |
| `services/palace-mcp/src/palace_mcp/adr/decision_bridge.py` | new | 2.6 |
| `services/palace-mcp/src/palace_mcp/code_router.py` | modify | 2.1 (remove from `_DISABLED_CM_TOOLS`) |
| `services/palace-mcp/src/palace_mcp/mcp_server.py` | modify | 2.1 (import + register + lifespan) |
| `services/palace-mcp/tests/adr/unit/test_adr_schema.py` | new | 2.1 |
| `services/palace-mcp/tests/adr/unit/test_adr_reader.py` | new | 2.2 |
| `services/palace-mcp/tests/adr/unit/test_adr_writer.py` | new | 2.3 |
| `services/palace-mcp/tests/adr/unit/test_adr_supersede.py` | new | 2.4 |
| `services/palace-mcp/tests/adr/unit/test_adr_query.py` | new | 2.5 |
| `services/palace-mcp/tests/adr/unit/test_adr_decision_bridge.py` | new | 2.6 |
| `services/palace-mcp/tests/integration/test_manage_adr_wire.py` | new | 2.8 |
| `docs/postulates/.gitkeep` | new | 2.1 |
| `docs/runbooks/manage-adr-v2.md` | new | 2.7 |

**Total:** 18 new files, 2 modified files.

---

## Risks (from spec §8)

R1 file/graph drift · R2 section name typos · R3 concurrent writes
· R4 git tracking churn.

---

## Cross-references

- Spec: `2026-05-07-palace-code-manage-adr-v2_spec.md`.
- Predecessor: `manage_adr` DISABLED in `code_router.py:151`
  (`_DISABLED_CM_TOOLS`). No functioning v1.
- Sibling: GIM-95 `palace.memory.decide` write tool.
- Roadmap: `docs/roadmap-archive.md` §"Phase 6" E5 row.
- Memory: `reference_cm_adr_postulate_pattern.md` — 6-section format.
- Audit-V1 integration: post-v1 — `:CITED_BY` edges as decision
  provenance in §1 Architecture.
