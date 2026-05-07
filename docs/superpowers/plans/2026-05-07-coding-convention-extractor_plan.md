# Coding Convention Extractor (#6) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: `superpowers:test-driven-development`. Atomic-handoff discipline mandatory.

**Slice:** Phase 2 §2.2 #6 Coding Convention Extractor.
**Spec:** `docs/superpowers/specs/2026-05-07-coding-convention-extractor_spec.md`.
**Source branch:** `feature/GIM-NN-coding-convention-extractor` cut from `origin/develop` **after E6 closes**.
**Target branch:** `develop`. Squash-merge on APPROVE.
**Team:** Codex. Phase chain: CXCTO → CXCodeReviewer (plan-first) → CXPythonEngineer (or PE-2 from E6) → CXCodeReviewer (mechanical) → OpusArchitectReviewer (adversarial; cross-team OK for adversarial pass) → CXQAEngineer → CXCTO merge.

> **Blocked-on-E6**: this plan can be drafted now, but team-chain
> execution starts only after E6 (CX hire of BlockchainEng + SecAud +
> PE-2) closes. Until then, the slice sits in CXCTO queue with
> `status=blocked, blockedByIssueIds=[<E6 issue id>]`.

---

## Phase 0 — Wait for E6 + branch (Board)

### Step 0.1: Block until E6 lands

**Owner:** Board.

- [ ] Verify `docs/roadmap.md` E6 row = ✅ + merge SHA.
- [ ] Verify 3 new agents listed in
      `GET /api/companies/<id>/agents` per E6 acceptance.
- [ ] If E6 not yet merged: pause; create issue with
      `blockedByIssueIds=[<E6 issue id>]`. Re-check daily.

**Acceptance:** E6 ✅; new CX agents available.

### Step 0.2: Resolve issue + branch

**Owner:** Board.

- [ ] Open paperclip issue `Coding Convention Extractor (#6)`.
- [ ] Body = link to spec + this plan; `GIM-NN` placeholders.
- [ ] Reassign to CXCTO for Phase 1 formalisation.

**Acceptance:** issue exists; CXCTO is assignee.

---

## Phase 1 — CXCTO formalisation + plan-first review (CXCodeReviewer)

### Step 1.1: CXCTO formalisation

**Owner:** CXCTO.

- [ ] Verify spec §3 detection strategy is consistent with existing
      Phase 1 symbol-index outputs (Swift + Kotlin).
- [ ] Resolve decision points CC-D1..CC-D5 with operator (or default).
- [ ] Verify §6 initial rule set is concrete enough to test (each rule
      maps to ≥1 unit-test fixture file).
- [ ] Reassign to CXCodeReviewer.

### Step 1.2: Plan-first review

**Owner:** CXCodeReviewer.

- [ ] Verify each rule in §6 has a test+impl+commit step in Phase 2
      below.
- [ ] Verify acceptance criteria measurable (sample counts, severity
      thresholds).
- [ ] Per `feedback_anti_rubber_stamp.md`: full review with evidence.
- [ ] APPROVE → CXPythonEngineer (or PE-2 if assigned by CXCTO).

**Acceptance:** APPROVE; assignee = CXPythonEngineer/PE-2.

---

## Phase 2 — Implementation (CXPythonEngineer / PE-2)

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

- [ ] Commit: `feat(GIM-NN): coding_convention extractor scaffolding`.

---

### Phase 2.2 — Rule implementations (one TDD pass per rule from §6)

For each of the 8 rules in spec §6:

#### Step 2.2.X.1: Failing tests

- [ ] Add Swift fixture under
      `tests/extractors/fixtures/coding-convention-fixture/swift/<rule>/{good,bad,outlier}/*.swift`.
- [ ] Add Kotlin fixture under
      `tests/extractors/fixtures/coding-convention-fixture/kotlin/<rule>/{good,bad,outlier}/*.kt`.
- [ ] Unit test: classifier on each fixture returns expected
      `:Convention` row + `:ConventionViolation` rows.
- [ ] RED.

#### Step 2.2.X.2: Rule classifier

**Files:**
- `extractors/coding_convention/rules/<rule_name>.py` (one per rule).
- For Swift: SwiftSyntax visitor invoked via subprocess (or direct
  Python binding if available).
- For Kotlin: Konsist DSL invoked via subprocess (Kotlin script
  dispatched from Python).
- For semgrep-portable rules: YAML rule file under
  `extractors/coding_convention/rules/semgrep/<rule_name>.yaml`.

- [ ] Implement rule classifier.
- [ ] Tests GREEN.

#### Step 2.2.X.3: Commit

- [ ] Commit: `feat(GIM-NN): coding_convention rule <rule_name>`.

**Total**: 8 × 3 steps = ~24 small commits or 8 squashable feature
commits depending on team-chain preference.

---

### Phase 2.3 — Integration: extract() orchestration + Neo4j writer

#### Step 2.3.1: Failing integration test

**Files:** `tests/extractors/integration/test_coding_convention_e2e.py` (new).

- [ ] Real Neo4j (testcontainers or compose-reuse).
- [ ] Run extractor on `tests/extractors/fixtures/coding-convention-fixture/` (multi-rule fixture).
- [ ] Assert: `:Convention` count ≥ 5; `:ConventionViolation` count ≥ 3.
- [ ] Assert: every node has `run_id` referencing a successful
      `:IngestRun`.
- [ ] RED.

#### Step 2.3.2: extract() orchestration

**Files:**
- `extractors/coding_convention/extractor.py::extract()`.
- `extractors/coding_convention/neo4j_writer.py` (new).

- [ ] `extract()` iterates rules → collects findings → batches Neo4j writes.
- [ ] Use `extractors/cypher.py::create_ingest_run()` (post-S0.1
      unified schema).
- [ ] Tests GREEN.

#### Step 2.3.3: Commit

- [ ] Commit: `feat(GIM-NN): coding_convention extract() orchestration + neo4j writer`.

---

### Phase 2.4 — `audit_contract()` + template

#### Step 2.4.1: Failing test

- [ ] Test: `extractor.audit_contract()` returns
      `AuditContract(query=..., response_model=ConventionAuditList,
      template_path=Path("audit/templates/coding_convention.md"))`.
- [ ] Test: rendering template with synthetic data produces
      expected markdown structure (sections, severity sort).

#### Step 2.4.2: Implement `audit_contract()` + template

**Files:**
- `extractors/coding_convention/extractor.py::audit_contract()`.
- `services/palace-mcp/src/palace_mcp/audit/templates/coding_convention.md` (new).
- `services/palace-mcp/src/palace_mcp/audit/models.py` — add
  `ConventionAuditList` Pydantic model.

- [ ] Tests GREEN.

#### Step 2.4.3: Commit

- [ ] Commit: `feat(GIM-NN): coding_convention audit_contract + template`.

---

### Phase 2.5 — Runbook + extractor docs

#### Step 2.5.1: Author runbook

**Files:** `docs/runbooks/coding-convention.md` (new).

- [ ] Document: how to run, expected outputs, how to interpret outliers
      / violations, how to add a rule.

#### Step 2.5.2: Update CLAUDE.md extractor catalogue

- [ ] Add `coding_convention` entry to `CLAUDE.md` §"Registered
      extractors" with its team affinity (Codex), language coverage
      (Swift + Kotlin), and rule count (8).

#### Step 2.5.3: Commit + push

- [ ] Commit: `docs(GIM-NN): coding_convention runbook + CLAUDE.md catalogue entry`.
- [ ] Push branch.
- [ ] Open PR `feat(GIM-NN): coding_convention extractor (#6)`.
- [ ] PR body: closes GIM-NN; commit list mapping → 8 rules + scaffolding + integration; QA Evidence placeholder.
- [ ] Reassign to CXCodeReviewer.

**Acceptance:** PR open; CI runs.

---

## Phase 3 — Review

### Phase 3.1 — Mechanical review (CXCodeReviewer)

- [ ] Paste `gh pr checks` — required CI green
      (lint, typecheck, test, docker-build, qa-evidence-present).
- [ ] Paste full pytest output for new tests.
- [ ] Verify all 8 rules have tests + implementation + commit.
- [ ] Verify scope matches spec §6 (no silent additions or omissions per
      `feedback_silent_scope_reduction.md`).
- [ ] APPROVE on paperclip + GitHub. Reassign to OpusArchitectReviewer.

**Acceptance:** APPROVE.

### Phase 3.2 — Adversarial review (OpusArchitectReviewer or CXCodeReviewer-2)

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

- [ ] Verify CI green; CR + Opus APPROVE; QA Evidence present.
- [ ] Squash-merge.
- [ ] Update `docs/roadmap-archive.md` §2.2 #6 row: deferred →
      ✅ + merge SHA.
- [ ] iMac deploy: `bash paperclips/scripts/imac-deploy.sh`.

**Acceptance:** #6 ✅; iMac runs `palace.ingest.run_extractor(name="coding_convention", ...)` against live data.

---

## Definition-of-Done checklist

- [ ] Scaffolding + 8 rules + integration + audit_contract +
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

- Spec: `2026-05-07-coding-convention-extractor_spec.md`.
- Roadmap: `docs/roadmap-archive.md` §2.2 #6.
- Predecessor: E6 (`2026-05-07-cx-team-hire-blockchain-security-pyorch_*.md`).
- Audit-V1 integration: feeds §2 Architecture / §3 Quality of report.
- Atomic-handoff: `paperclips/fragments/profiles/handoff.md`.
