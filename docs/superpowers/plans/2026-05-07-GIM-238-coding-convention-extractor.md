# Coding Convention Extractor (#6) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: `superpowers:test-driven-development`. Atomic-handoff discipline mandatory.

**Slice:** Phase 2 §2.2 #6 Coding Convention Extractor.
**Spec:** `docs/superpowers/specs/2026-05-07-GIM-238-coding-convention-extractor_spec.md`.
**Source branch:** `feature/GIM-238-coding-convention-extractor` cut from `origin/develop` at `e2f9a09`.
**Target branch:** `develop`. Squash-merge on APPROVE.
**Team:** Codex. Phase chain: CXCTO → CXCodeReviewer (plan-first) → CXPythonEngineer → CXCodeReviewer (mechanical) → CodexArchitectReviewer (adversarial) → CXQAEngineer → CXCTO merge.

> **GIM-238 formalisation note (2026-05-08):** E6 is closed via
> GIM-229 / PR #116 (`e2f9a09`). The rev5 operator decision says this
> slice no longer depends on the newly hired forward-looking roles; the
> first implementation handoff is to CXPythonEngineer after plan-first
> review.

---

## Phase 0 — Resolved prerequisites + branch (Board/CXCTO)

### Step 0.1: Verify E6 landed

**Owner:** Board / CXCTO.

- [x] Verify E6 merge SHA: GIM-229 / PR #116 squash merge `e2f9a09`.
- [x] Verify this slice is unblocked by rev5 operator decision; no
      forward-looking new-hire dependency remains for #6.

**Acceptance:** E6 ✅; no hiring blocker remains for #6.

### Step 0.2: Resolve issue + branch

**Owner:** Board.

- [x] Open paperclip issue `GIM-238 Coding Convention Extractor (#6)`.
- [x] Body = link to spec + this plan.
- [x] Create branch `feature/GIM-238-coding-convention-extractor`
      from `origin/develop` at `e2f9a09`.
- [x] Reassign to CXCTO for Phase 1 formalisation.

**Acceptance:** issue exists; CXCTO is assignee.

---

## Phase 1 — CXCTO formalisation + plan-first review (CXCodeReviewer)

### Step 1.1: CXCTO formalisation

**Owner:** CXCTO.

- [x] Verify spec §3 detection strategy is consistent with existing
      Phase 1 symbol-index outputs (Swift + Kotlin).
- [x] Resolve decision points CC-D1..CC-D5 with operator (or default).
- [x] Verify §6 initial rule set is concrete enough to test (each rule
      maps to ≥1 unit-test fixture file).
- [x] Resolve CC-D1..CC-D5 by default: both Swift+Kotlin, Harmonize
      aid for SwiftSyntax, Konsist primary for Kotlin, semgrep for
      portable cross-language patterns, 10% outlier threshold with
      `min_sample_count=5`.
- [ ] Reassign to CXCodeReviewer.

### Step 1.2: Plan-first review

**Owner:** CXCodeReviewer.

- [ ] Verify each rule in §6 has a test+impl+commit step in Phase 2
      below.
- [ ] Verify acceptance criteria measurable (sample counts, severity
      thresholds).
- [ ] Per `feedback_anti_rubber_stamp.md`: full review with evidence.
- [ ] APPROVE → CXPythonEngineer.

**Acceptance:** APPROVE; assignee = CXPythonEngineer.

---

## Phase 2 — Implementation (CXPythonEngineer)

### Phase 2.1 — Foundation: extractor scaffolding

#### Step 2.1.1: Failing scaffolding test

**Owner:** CXPythonEngineer.
**Files:** `services/palace-mcp/tests/extractors/unit/test_coding_convention_scaffold.py` (new).

- [ ] Test: `from palace_mcp.extractors.coding_convention import CodingConventionExtractor` returns class.
- [ ] Test: `CodingConventionExtractor().name == "coding_convention"`.
- [ ] Test: extractor is registered in `EXTRACTORS` dict.
- [ ] All RED.

#### Step 2.1.2: Scaffolding implementation

**Owner:** CXPythonEngineer.
**Files:**
- `services/palace-mcp/src/palace_mcp/extractors/coding_convention/__init__.py` (new).
- `services/palace-mcp/src/palace_mcp/extractors/coding_convention/extractor.py` (new — class skeleton).
- `services/palace-mcp/src/palace_mcp/extractors/registry.py` — add `coding_convention` entry.

- [ ] Class extends `BaseExtractor` (post-S1.3 with `audit_contract()` slot).
- [ ] `name = "coding_convention"`, `description`, `constraints`,
      `indexes` per S0.1 schema.
- [ ] `extract()` placeholder returns empty stats.
- [ ] Tests GREEN.

#### Step 2.1.3: Commit

- [ ] Commit: `feat(GIM-238): coding_convention extractor scaffolding`.

---

### Phase 2.2 — Rule implementations (one TDD pass per rule from §6)

For each of the 7 rules in spec §6:

#### Step 2.2.X.1: Failing tests

- [ ] Add Swift fixture under
      `services/palace-mcp/tests/extractors/fixtures/coding-convention-fixture/swift/<rule>/{good,bad,outlier}/*.swift`.
- [ ] Add Kotlin fixture under
      `services/palace-mcp/tests/extractors/fixtures/coding-convention-fixture/kotlin/<rule>/{good,bad,outlier}/*.kt`.
- [ ] Unit test: classifier on each fixture returns expected
      `:Convention` row + `:ConventionViolation` rows.
- [ ] RED.

#### Step 2.2.X.2: Rule classifier

**Files:**
- `services/palace-mcp/src/palace_mcp/extractors/coding_convention/rules/<rule_name>.py` (one per rule).
- For Swift: SwiftSyntax visitor invoked via subprocess (or direct
  Python binding if available).
- For Kotlin: Konsist DSL invoked via subprocess (Kotlin script
  dispatched from Python).
- For semgrep-portable rules: YAML rule file under
  `services/palace-mcp/src/palace_mcp/extractors/coding_convention/rules/semgrep/<rule_name>.yaml`.

- [ ] Implement rule classifier.
- [ ] Tests GREEN.

#### Step 2.2.X.3: Commit

- [ ] Commit: `feat(GIM-238): coding_convention rule <rule_name>`.

**Total**: 7 × 3 steps = ~21 small commits or 7 squashable feature
commits depending on team-chain preference.

---

### Phase 2.3 — Integration: extract() orchestration + Neo4j writer

#### Step 2.3.1: Failing integration test

**Files:** `services/palace-mcp/tests/extractors/integration/test_coding_convention_e2e.py` (new).

- [ ] Real Neo4j (testcontainers or compose-reuse).
- [ ] Run extractor on `services/palace-mcp/tests/extractors/fixtures/coding-convention-fixture/` (multi-rule fixture).
- [ ] Assert: `:Convention` count ≥ 5; `:ConventionViolation` count ≥ 3.
- [ ] Assert: every node has `run_id` referencing a successful
      `:IngestRun`.
- [ ] RED.

#### Step 2.3.2: extract() orchestration

**Files:**
- `services/palace-mcp/src/palace_mcp/extractors/coding_convention/extractor.py::extract()`.
- `services/palace-mcp/src/palace_mcp/extractors/coding_convention/neo4j_writer.py` (new).

- [ ] `extract()` iterates rules → collects findings → batches Neo4j writes.
- [ ] Use `palace_mcp.extractors.foundation.checkpoint.create_ingest_run(driver, run_id=..., project=..., extractor_name="coding_convention")`.
- [ ] Use `palace_mcp.extractors.foundation.checkpoint.finalize_ingest_run(...)`
      on success/failure; do not duplicate `:IngestRun` lifecycle Cypher.
- [ ] Tests GREEN.

#### Step 2.3.3: Commit

- [ ] Commit: `feat(GIM-238): coding_convention extract() orchestration + neo4j writer`.

---

### Phase 2.4 — `audit_contract()` + template

#### Step 2.4.1: Failing test

- [ ] Test: `extractor.audit_contract()` returns
      `AuditContract(extractor_name="coding_convention",
      template_name="coding_convention.md", query=...,
      severity_column="outlier_ratio", severity_mapper=...)`.
- [ ] Test: rendering template with synthetic data produces
      expected markdown structure (sections, severity sort).

#### Step 2.4.2: Implement `audit_contract()` + template

**Files:**
- `services/palace-mcp/src/palace_mcp/extractors/coding_convention/extractor.py::audit_contract()`.
- `services/palace-mcp/src/palace_mcp/audit/templates/coding_convention.md` (new).
- No `response_model` / `ConventionAuditList` addition unless the audit
  platform first grows explicit support for typed response models in
  `palace_mcp.audit.contracts.AuditContract`.

- [ ] Tests GREEN.

#### Step 2.4.3: Commit

- [ ] Commit: `feat(GIM-238): coding_convention audit_contract + template`.

---

### Phase 2.5 — Runbook + extractor docs

#### Step 2.5.1: Author runbook

**Files:** `docs/runbooks/coding-convention.md` (new).

- [ ] Document: how to run, expected outputs, how to interpret outliers
      / violations, how to add a rule.

#### Step 2.5.2: Update CLAUDE.md extractor catalogue

- [ ] Add `coding_convention` entry to `CLAUDE.md` §"Registered
      extractors" with its team affinity (Codex), language coverage
      (Swift + Kotlin), and rule count (7).

#### Step 2.5.3: Commit + push

- [ ] Commit: `docs(GIM-238): coding_convention runbook + CLAUDE.md catalogue entry`.
- [ ] Push branch.
- [ ] Open PR `feat(GIM-238): coding_convention extractor (#6)`.
- [ ] PR body: closes GIM-238; commit list mapping → 7 rules + scaffolding + integration; QA Evidence placeholder.
- [ ] Reassign to CXCodeReviewer.

**Acceptance:** PR open; CI runs.

---

## Phase 3 — Review

### Phase 3.1 — Mechanical review (CXCodeReviewer)

- [ ] Paste `gh pr checks` — required CI green
      (lint, typecheck, test, docker-build, qa-evidence-present).
- [ ] Paste exact local validation output from `services/palace-mcp`:
      `uv run ruff check src/palace_mcp/extractors/coding_convention src/palace_mcp/extractors/registry.py tests/extractors/unit/test_coding_convention_*.py tests/extractors/integration/test_coding_convention_e2e.py`
- [ ] Paste exact local validation output from `services/palace-mcp`:
      `uv run mypy src/palace_mcp/extractors/coding_convention src/palace_mcp/extractors/registry.py`
- [ ] Paste exact local validation output from `services/palace-mcp`:
      `uv run pytest tests/extractors/unit/test_coding_convention_*.py tests/extractors/unit/test_registry.py -v`
- [ ] Paste exact env-gated integration output from `services/palace-mcp`:
      `uv run pytest tests/extractors/integration/test_coding_convention_e2e.py -m integration -v`
- [ ] Verify all 7 rules have tests + implementation + commit.
- [ ] Verify scope matches spec §6 (no silent additions or omissions per
      `feedback_silent_scope_reduction.md`).
- [ ] APPROVE on paperclip + GitHub. Reassign to CodexArchitectReviewer.

**Acceptance:** APPROVE.

### Phase 3.2 — Adversarial review (CodexArchitectReviewer)

- [ ] Probe: does each rule classifier handle edge cases (empty
      module, file with no top-level types, file with mixed
      Swift+ObjC headers)?
- [ ] Probe: outlier threshold (CC-D5 default 10%) — sane on small
      modules?
- [ ] Probe: heuristic findings clearly distinguished from certain
      ones in the report?
- [ ] Probe: cross-language rules (semgrep) actually fire on both
      Swift and Kotlin fixtures?

**Acceptance:** APPROVE / NUDGE / BLOCK.

---

## Phase 4 — QA evidence (CXQAEngineer on iMac)

### Step 4.1: Live smoke

- [ ] SSH iMac.
- [ ] FF-pull develop. Pull PR branch into temp worktree.
- [ ] Build palace-mcp.
- [ ] Live MCP call: `palace.ingest.run_extractor(name="coding_convention", project="gimle")`.
- [ ] Verify `:Convention` count ≥ 1 and ≥ 1 module covered.
- [ ] Live MCP call same on `tronkit-swift` (after re-ingesting Swift
      Kit in test mode).
- [ ] Cypher: `MATCH (c:Convention) WHERE c.run_id IS NOT NULL RETURN count(c)` > 0.

### Step 4.2: QA Evidence

- [ ] Edit PR body `## QA Evidence`. Cite SHA + 3 live commands +
      output excerpts + affirmation.
- [ ] Reassign to CXCTO.

**Acceptance:** Evidence satisfies `qa-evidence-present` CI.

---

## Phase 5 — Merge (CXCTO)

- [ ] Verify CI green; CXCodeReviewer + CodexArchitectReviewer APPROVE; QA Evidence present.
- [ ] Squash-merge.
- [ ] Update `docs/roadmap-archive.md` §2.2 #6 row: deferred →
      ✅ + merge SHA.
- [ ] iMac deploy: `bash paperclips/scripts/imac-deploy.sh`.

**Acceptance:** #6 ✅; iMac runs `palace.ingest.run_extractor(name="coding_convention", ...)` against live data.

---

## Definition-of-Done checklist

- [ ] Scaffolding + 7 rules + integration + audit_contract +
      runbook + CLAUDE.md update — all merged.
- [ ] Smoke run on tronkit-swift + UW-Android produces expected
      `:Convention` rows.
- [ ] Roadmap row updated.

---

## Risks (from spec §9)

R1 false positives · R2 SwiftSyntax/Konsist version drift · R3
module detection · R4 performance.

---

## Cross-references

- Spec: `2026-05-07-GIM-238-coding-convention-extractor_spec.md`.
- Roadmap: `docs/roadmap-archive.md` §2.2 #6.
- Predecessor: E6 (`2026-05-07-cx-team-hire-blockchain-security-pyorch_*.md`).
- Audit-V1 integration: feeds §2 Architecture / §3 Quality of report.
- Atomic-handoff: `paperclips/fragments/profiles/handoff.md`.
