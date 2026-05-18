# Testability / DI Pattern Extractor (#8) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: `superpowers:test-driven-development`. Atomic-handoff discipline mandatory.

**Slice:** Phase 2 §2.2 #8 Testability / DI Pattern.
**Spec:** `docs/superpowers/specs/2026-05-07-testability-di-pattern-extractor_spec.md`.
**Source branch:** `feature/GIM-NN-testability-di-extractor` cut from `origin/develop` **after E6 closes**.
**Target branch:** `develop`. Squash-merge on APPROVE.
**Team:** Codex. Phase chain: CXCTO → CXCodeReviewer (plan-first) → CXPythonEngineer (or PE-2) → CXCodeReviewer (mechanical) → OpusArchitectReviewer (adversarial) → CXQAEngineer → CXCTO merge.

> **Blocked-on-E6**.

---

## Phase 0 — Wait + branch (Board)

### Step 0.1: E6 gate

- [ ] Verify E6 ✅ on develop. If not, queue with `blockedByIssueIds=[<E6 id>]`.

### Step 0.2: Issue + branch

- [ ] Open paperclip issue `Testability/DI Pattern Extractor (#8)`.
- [ ] Body = link to spec + plan; `GIM-NN` placeholder.
- [ ] Reassign CXCTO.

---

## Phase 1 — CXCTO formalisation + plan-first review

### Step 1.1 (CXCTO)

- [ ] Resolve TD-D1..TD-D5.
- [ ] Reassign CXCodeReviewer.

### Step 1.2 (CXCodeReviewer plan-first)

- [ ] Verify each of 7 rules has test+impl+commit.
- [ ] APPROVE → CXPythonEngineer.

---

## Phase 2 — Implementation

### Phase 2.1 — Scaffolding

- [ ] Failing test: `TestabilityDiExtractor` class loads + registers.
- [ ] Implement scaffolding under
      `services/palace-mcp/src/palace_mcp/extractors/testability_di/{__init__,extractor}.py`.
- [ ] Add to `EXTRACTORS` registry.
- [ ] Tests GREEN.
- [ ] Commit: `feat(GIM-NN): testability_di extractor scaffolding`.

### Phase 2.2 — 7 rule TDD passes

For each rule from spec §6 (`di.init_injection`,
`di.property_injection`, `di.framework_bound`, `di.service_locator`,
`mock.style`, `untestable.singleton_access`,
`untestable.direct_clock`):

- [ ] Swift + Kotlin fixtures `tests/extractors/fixtures/testability-di-fixture/<rule>/{good,bad,outlier}/*.{swift,kt}`.
- [ ] Unit test: classifier on each fixture returns expected `:DiPattern`
      / `:UntestableSite` row with correct `severity` + `confidence`.
- [ ] Implement rule classifier under
      `extractors/testability_di/rules/<rule_name>.py`.
- [ ] Tests GREEN.
- [ ] Commit per rule (or squash 7 into one feature commit per CR
      preference).

### Phase 2.3 — Integration: extract() + Neo4j writer

- [ ] Failing integration test (testcontainers Neo4j): extractor on
      multi-rule fixture writes ≥3 `:DiPattern` + ≥1 `:UntestableSite`
      + correct provenance.
- [ ] Implement `extract()` orchestration + `neo4j_writer.py`.
      Use S0.1 unified `:IngestRun` schema.
- [ ] Tests GREEN.
- [ ] Commit: `feat(GIM-NN): testability_di orchestration + writer`.

### Phase 2.4 — `audit_contract()` + template

- [ ] Failing test: `audit_contract()` returns expected `AuditContract`.
- [ ] Failing test: template renders synthetic data correctly.
- [ ] Implement `audit_contract()` per spec §5.
- [ ] Author `services/palace-mcp/src/palace_mcp/audit/templates/testability_di.md`.
- [ ] Add `TestabilityDiAuditList` Pydantic model in
      `audit/models.py`.
- [ ] Tests GREEN.
- [ ] Commit: `feat(GIM-NN): testability_di audit_contract + template`.

### Phase 2.5 — Runbook + CLAUDE.md update

- [ ] `docs/runbooks/testability-di.md` (new).
- [ ] Add entry to `CLAUDE.md` §"Registered extractors".
- [ ] Push branch.
- [ ] Open PR `feat(GIM-NN): testability_di extractor (#8)`.
- [ ] Reassign CXCodeReviewer.

---

## Phase 3 — Review

### Phase 3.1 — Mechanical (CXCodeReviewer)

- [ ] `gh pr checks` green.
- [ ] Pytest output for new tests.
- [ ] All 7 rules covered.
- [ ] No silent scope reduction.
- [ ] APPROVE → OpusArchitectReviewer.

### Phase 3.2 — Adversarial

- [ ] Probe: framework detection covers Hilt + Koin + Dagger + Resolver
      + Swinject correctly?
- [ ] Probe: false-positive rate on `*.shared` (URLSession.shared in
      DI-config file = OK, in business logic = flag)?
- [ ] Probe: `untestable.direct_clock` rule correctly skips test files?
- [ ] Probe: TD-D2 (service-locator severity=high) actually surfaces
      in audit report at expected severity?

---

## Phase 4 — QA evidence (CXQAEngineer)

- [ ] iMac live smoke: `palace.ingest.run_extractor(name="testability_di", project="gimle")` → `:DiPattern` count > 0.
- [ ] Same on `tronkit-swift` (re-ingest first).
- [ ] Cypher: `MATCH (us:UntestableSite) RETURN us.category, count(us)` — distribution check.
- [ ] QA Evidence in PR body.

---

## Phase 5 — Merge (CXCTO)

- [ ] CI green; CR + Opus APPROVE; QA Evidence.
- [ ] Squash-merge.
- [ ] Update `docs/roadmap-archive.md` §2.2 #8 row → ✅ + SHA.
- [ ] iMac deploy.

---

## DoD checklist

- [ ] Scaffolding + 7 rules + integration + audit_contract + runbook
      + CLAUDE.md update — merged.
- [ ] Smoke runs on tronkit-swift + UW-Android produce expected rows.
- [ ] Roadmap updated.

---

## Risks (from spec §9)

R1 framework detection misses custom DI · R2 mock-style conflation
· R3 legitimate-singleton false positives · R4 performance.

---

## Cross-references

- Spec: `2026-05-07-testability-di-pattern-extractor_spec.md`.
- Predecessor: E6.
- Roadmap: `docs/roadmap-archive.md` §2.2 #8.
- Audit-V1 integration: §3 Quality + §4 Security.
