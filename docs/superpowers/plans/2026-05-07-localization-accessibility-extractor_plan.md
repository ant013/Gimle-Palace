# Localization & Accessibility Extractor (#9) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: `superpowers:test-driven-development`. Atomic-handoff discipline mandatory.

**Slice:** Phase 2 §2.2 #9 Localization & Accessibility.
**Spec:** `docs/superpowers/specs/2026-05-07-localization-accessibility-extractor_spec.md`.
**Source branch:** `feature/GIM-NN-localization-accessibility-extractor` cut from `origin/develop` **after E6 closes**.
**Target branch:** `develop`. Squash-merge on APPROVE.
**Team:** Codex. Phase chain: CXCTO → CXCodeReviewer (plan-first) → CXPythonEngineer (or PE-2) → CXCodeReviewer (mechanical) → OpusArchitectReviewer (adversarial) → CXQAEngineer → CXCTO merge.

> **Blocked-on-E6**.

---

## Phase 0 — Wait + branch (Board)

### Step 0.1 (E6 gate)

- [ ] Verify E6 ✅. If not, queue with `blockedByIssueIds=[<E6 id>]`.

### Step 0.2 (Issue + branch)

- [ ] Open paperclip issue `Localization & Accessibility Extractor (#9)`.
- [ ] Body = link to spec + plan; `GIM-NN` placeholder.
- [ ] Reassign CXCTO.

---

## Phase 1 — CXCTO formalisation + plan-first review

### Step 1.1 (CXCTO)

- [ ] Resolve LA-D1..LA-D5 (defaults from spec).
- [ ] Reassign CXCodeReviewer.

### Step 1.2 (CXCodeReviewer plan-first)

- [ ] Verify each of 6 rules has test+impl+commit.
- [ ] Verify allowlist mechanism (LA-D4) is implementable.
- [ ] APPROVE → CXPythonEngineer.

---

## Phase 2 — Implementation

### Phase 2.1 — Scaffolding

- [ ] Failing test: `LocalizationAccessibilityExtractor` class loads + registers.
- [ ] Implement under
      `extractors/localization_accessibility/{__init__,extractor}.py`.
- [ ] Add to `EXTRACTORS` registry.
- [ ] Tests GREEN.
- [ ] Commit: `feat(GIM-NN): localization_accessibility scaffolding`.

### Phase 2.2 — Locale resource parsers

#### 2.2.1 — iOS xcstrings parser

- [ ] Failing test: synthetic `.xcstrings` JSON → expected
      `:LocaleResource` rows.
- [ ] Implement `extractors/localization_accessibility/parsers/xcstrings.py`.
- [ ] Tests GREEN.
- [ ] Commit.

#### 2.2.2 — iOS legacy `Localizable.strings` parser

- [ ] Failing test: synthetic `Localizable.strings` per locale → expected rows.
- [ ] Implement `extractors/localization_accessibility/parsers/strings_dict.py`.
- [ ] Tests GREEN.
- [ ] Commit.

#### 2.2.3 — Android `strings.xml` parser

- [ ] Failing test: synthetic `res/values-XX/strings.xml` per locale → expected rows.
- [ ] Implement `extractors/localization_accessibility/parsers/android_strings.py`.
- [ ] Tests GREEN.
- [ ] Commit.

### Phase 2.3 — Hard-coded string detectors (rules 2-4)

For each of `loc.hardcoded_swiftui`, `loc.hardcoded_compose`,
`loc.hardcoded_uikit`:

- [ ] Fixture under
      `tests/extractors/fixtures/loc-a11y-fixture/<rule>/{good,bad}/*.{swift,kt,xml}`.
- [ ] Unit test: classifier on each fixture returns expected
      `:HardcodedString` rows with correct severity + context.
- [ ] Implement classifier under
      `extractors/localization_accessibility/rules/<rule_name>.py`.
- [ ] Tests GREEN.
- [ ] Commit per rule.

### Phase 2.4 — A11y missing detectors (rules 5-6)

For each of `a11y.missing_label_swiftui`, `a11y.missing_compose`:

- [ ] Fixture per rule.
- [ ] Unit test: classifier returns expected `:A11yMissing` rows.
- [ ] Implement classifier.
- [ ] Tests GREEN.
- [ ] Commit per rule.

### Phase 2.5 — Allowlist mechanism (LA-D4)

- [ ] Failing test: extractor reads `<project>/.gimle/loc-allowlist.txt`
      (one literal per line) and skips matching strings during
      hard-coded detection.
- [ ] Implement allowlist loader.
- [ ] Tests GREEN.
- [ ] Commit: `feat(GIM-NN): loc-a11y allowlist support`.

### Phase 2.6 — extract() orchestration + Neo4j writer

- [ ] Failing integration test (testcontainers Neo4j): extractor on
      multi-locale + multi-rule fixture writes ≥2 `:LocaleResource`
      + ≥3 `:HardcodedString` + ≥2 `:A11yMissing` + correct provenance.
- [ ] Implement `extract()` orchestration + `neo4j_writer.py`.
      Use S0.1 unified `:IngestRun` schema.
- [ ] Tests GREEN.
- [ ] Commit.

### Phase 2.7 — `audit_contract()` + template

- [ ] Failing test: `audit_contract()` returns expected.
- [ ] Failing test: template renders synthetic data with locale
      coverage matrix.
- [ ] Implement `audit_contract()` per spec §5.
- [ ] Author `audit/templates/localization_accessibility.md` with:
  - Locale coverage matrix (one row per locale × column for key
    count + coverage %).
  - Top hard-coded strings (severity-grouped).
  - Top a11y misses (severity-grouped).
- [ ] Add `LocAuditList` Pydantic model.
- [ ] Tests GREEN.
- [ ] Commit.

### Phase 2.8 — Runbook + CLAUDE.md update

- [ ] `docs/runbooks/localization-accessibility.md` (new):
  - How to run, expected outputs.
  - How to write `.gimle/loc-allowlist.txt`.
  - Common false-positive patterns and how to suppress.
- [ ] Add `localization_accessibility` row to `CLAUDE.md` §"Registered
      extractors".
- [ ] Push branch.
- [ ] Open PR `feat(GIM-NN): localization_accessibility extractor (#9)`.
- [ ] Reassign CXCodeReviewer.

---

## Phase 3 — Review

### Phase 3.1 — Mechanical (CXCodeReviewer)

- [ ] `gh pr checks` green; pytest output for new tests.
- [ ] Verify all 6 rules covered.
- [ ] Verify allowlist mechanism works.
- [ ] APPROVE → OpusArchitectReviewer.

### Phase 3.2 — Adversarial

- [ ] Probe: `Text(verbatim:)` correctly NOT flagged (per spec §9 R2)?
- [ ] Probe: A11y rule on test files correctly skipped (LA-D3)?
- [ ] Probe: locale coverage with mixed `.xcstrings` + legacy
      `.strings` files in same project — sane aggregation?
- [ ] Probe: very long literal strings (e.g., legal text) handled
      correctly (truncated to 100 chars per spec)?

---

## Phase 4 — QA evidence (CXQAEngineer on iMac)

- [ ] iMac live: bring up palace-mcp.
- [ ] Live MCP call: `palace.ingest.run_extractor(name="localization_accessibility", project="uw-android")`.
- [ ] Cypher: `MATCH (lr:LocaleResource) RETURN lr.locale, lr.key_count` — locale matrix populated.
- [ ] Cypher: `MATCH (h:HardcodedString {severity: "high"}) RETURN count(h)` — non-zero count expected on UW-Android.
- [ ] Cypher: `MATCH (a:A11yMissing {severity: "high"}) RETURN count(a)` — non-zero expected.
- [ ] QA Evidence in PR body.

---

## Phase 5 — Merge (CXCTO)

- [ ] CI green; CR + Opus APPROVE; QA Evidence.
- [ ] Squash-merge.
- [ ] Update `docs/roadmap-archive.md` §2.2 #9 row → ✅ + SHA.
- [ ] iMac deploy.

---

## DoD checklist

- [ ] Scaffolding + 3 locale parsers + 5 rule classifiers + allowlist
      + extract + audit_contract + template + runbook + CLAUDE.md
      update — merged.
- [ ] Smoke run on UW-Android produces expected coverage matrix.
- [ ] Roadmap updated.

---

## Risks (from spec §9)

R1 false positives · R2 `Text(verbatim:)` · R3 custom Compose DSL ·
R4 locale-resource churn.

---

## Cross-references

- Spec: `2026-05-07-localization-accessibility-extractor_spec.md`.
- Predecessor: E6.
- Roadmap: `docs/roadmap-archive.md` §2.2 #9.
- Audit-V1 integration: §3 Quality (and potential §11 future
  sub-section if locale/a11y becomes a first-class report section).
