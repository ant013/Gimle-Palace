# `palace.code.manage_adr` Writable v2 (E5) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: `superpowers:test-driven-development`. Atomic-handoff discipline mandatory.

**Slice:** Phase 6 E5 — `palace.code.manage_adr` v2 (writable + graph projection).
**Spec:** `docs/superpowers/specs/2026-05-07-palace-code-manage-adr-v2_spec.md`.
**Source branch:** `feature/GIM-NN-palace-code-manage-adr-v2` cut from `origin/develop`.
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
- [ ] Body = link to spec + plan; `GIM-NN` placeholder.
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
- `services/palace-mcp/tests/code/unit/test_adr_schema.py` (new).

- [ ] Test: `AdrDocument` Pydantic model serialises/deserialises.
- [ ] Test: `AdrSection` Pydantic model with `body_hash` derives
      from body content (SHA-256).
- [ ] Test: schema migration applies new constraints + indices
      idempotently.
- [ ] All RED initially.

#### Step 2.1.2: Implement models + migration

**Files:**
- `services/palace-mcp/src/palace_mcp/adr/models.py` (new).
- `services/palace-mcp/src/palace_mcp/adr/schema.py` (new) —
  Cypher constraints + indices, idempotent.
- Schema bootstrap call wired into existing
  `extractors/foundation/schema.py::ensure_custom_schema()` or sibling.

- [ ] Implement Pydantic models per spec §4.
- [ ] Implement schema migration with `CALL { … } IN TRANSACTIONS`
      and `IF NOT EXISTS` clauses.
- [ ] Tests GREEN.

#### Step 2.1.3: Commit

- [ ] Commit: `feat(GIM-NN): manage_adr v2 schema + Pydantic models`.

---

### Phase 2.2 — `read` mode (existing v1 → keep working)

#### Step 2.2.1: Backwards-compat regression test

- [ ] Test: `manage_adr(mode="read", slug="<existing-adr>")` returns
      same shape as v1 (markdown body + section list).

#### Step 2.2.2: Adjust v1 read to project graph

**Files:**
- `services/palace-mcp/src/palace_mcp/code_router.py` — branch on
  `mode` parameter.
- `services/palace-mcp/src/palace_mcp/adr/reader.py` (new) —
  factor v1 read out into module.

- [ ] Read continues to use file as source of truth.
- [ ] Side-effect: `read` triggers idempotent graph projection (file
      → `:AdrDocument` + `:AdrSection`).
- [ ] Tests GREEN; v1 regression test still passes.

#### Step 2.2.3: Commit

- [ ] Commit: `refactor(GIM-NN): manage_adr read mode projects to graph`.

---

### Phase 2.3 — `write` mode (NEW)

#### Step 2.3.1: Failing tests

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
- `services/palace-mcp/src/palace_mcp/code_router.py` — wire `mode="write"`.

- [ ] Validate inputs (Pydantic at MCP boundary).
- [ ] File-level `flock` on `docs/postulates/<slug>.md`.
- [ ] Read existing file → parse 6 sections → splice in new body
      for target section → write back.
- [ ] In same transaction (driver-level): upsert `:AdrSection`.
- [ ] Tests GREEN.

#### Step 2.3.3: Commit

- [ ] Commit: `feat(GIM-NN): manage_adr write mode (idempotent section upsert)`.

---

### Phase 2.4 — `supersede` mode (NEW)

#### Step 2.4.1: Failing tests

- [ ] Test: `supersede(old_slug="a", new_slug="b", reason="...")`:
  - Old `:AdrDocument.status = "superseded"`.
  - New `:AdrDocument.status = "active"` (creates new if missing).
  - Edge `(:AdrDocument {slug:"a"})-[:SUPERSEDED_BY {reason, ts}]->(:AdrDocument {slug:"b"})`.
- [ ] Test: superseding already-superseded ADR → idempotent.
- [ ] Test: file-side: old file gets a header banner
      `**SUPERSEDED by <new>** — <reason>`.
- [ ] All RED.

#### Step 2.4.2: Implement supersede

**Files:** `services/palace-mcp/src/palace_mcp/adr/supersede.py` (new).

- [ ] Same flock + file edit + graph update transactional pattern.
- [ ] Tests GREEN.

#### Step 2.4.3: Commit

- [ ] Commit: `feat(GIM-NN): manage_adr supersede mode`.

---

### Phase 2.5 — `query` mode (existing v1 → graph-augmented)

#### Step 2.5.1: Failing tests

- [ ] Test: `query(keyword="X")` returns ADRs whose section
      `body_excerpt` contains "X".
- [ ] Test: `query(section_filter="ARCHITECTURE")` returns only
      ARCHITECTURE sections across all ADRs.
- [ ] Test: `query(project_filter="gimle-*")` returns project-prefixed
      slugs.
- [ ] Test: query against empty graph returns empty list (not error).

#### Step 2.5.2: Implement query

**Files:** `services/palace-mcp/src/palace_mcp/adr/query.py` (new).

- [ ] Use Cypher with `body_excerpt` text search; for full-text use
      Tantivy bridge if existing.
- [ ] Tests GREEN.

#### Step 2.5.3: Commit

- [ ] Commit: `feat(GIM-NN): manage_adr query mode (graph-augmented)`.

---

### Phase 2.6 — `:Decision` bridge (post-spec AD-D5: manual)

#### Step 2.6.1: Failing test

- [ ] Test: `manage_adr(mode="write", ..., decision_id="<uuid>")`
      creates `(:Decision {id})-[:CITED_BY]->(:AdrDocument {slug})`
      edge.
- [ ] Test: writing without `decision_id` does NOT create edge.

#### Step 2.6.2: Implement bridge

**Files:** `services/palace-mcp/src/palace_mcp/adr/decision_bridge.py` (new).

- [ ] Conditional edge creation when `decision_id` present.
- [ ] Tests GREEN.

#### Step 2.6.3: Commit

- [ ] Commit: `feat(GIM-NN): manage_adr decision bridge (CITED_BY)`.

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
- [ ] Open PR `feat(GIM-NN): palace.code.manage_adr writable v2 (E5)`.
- [ ] Reassign CodeReviewer.

---

## Phase 3 — Review

### Phase 3.1 — Mechanical (CodeReviewer)

- [ ] `gh pr checks` green; pytest output for new tests.
- [ ] Verify v1 backwards-compat — `read` mode unchanged shape.
- [ ] Verify all 4 modes covered + bridge.
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

## Risks (from spec §8)

R1 file/graph drift · R2 section name typos · R3 concurrent writes
· R4 git tracking churn.

---

## Cross-references

- Spec: `2026-05-07-palace-code-manage-adr-v2_spec.md`.
- Predecessor (v1): existing manage_adr in `code_router.py`.
- Sibling: GIM-95 `palace.memory.decide` write tool.
- Roadmap: `docs/roadmap-archive.md` §"Phase 6" E5 row.
- Memory: `reference_cm_adr_postulate_pattern.md` — 6-section format.
- Audit-V1 integration: post-v1 — `:CITED_BY` edges as decision
  provenance in §1 Architecture.
