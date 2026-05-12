# Localization & Accessibility Extractor (#9) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: `superpowers:test-driven-development`. Atomic-handoff discipline mandatory.

**Slice:** Phase 2 §2.2 #9 Localization & Accessibility.
**Spec:** `docs/superpowers/specs/2026-05-07-localization-accessibility-extractor_spec.md`.
**Source branch:** `feature/GIM-275-localization-accessibility-extractor` cut from `origin/develop`.
**Target branch:** `develop`. Squash-merge on APPROVE.
**Team:** Claude (reassigned 2026-05-12). Phase chain: CTO → CodeReviewer (plan-first) → PythonEngineer → CodeReviewer (mechanical) → OpusArchitectReviewer (adversarial) → QAEngineer → CTO merge.

> ~~Blocked-on-E6~~ — E6 gate no longer applies (reassigned from Codex to Claude team 2026-05-12).

---

## Detection approach per rule (C1)

| Rule / Parser | Tooling | Rationale |
|---|---|---|
| 2.2.1 xcstrings parser | `json` (stdlib) | `.xcstrings` is JSON; stdlib sufficient |
| 2.2.2 `Localizable.strings` parser | regex (`re`) | key=value format, well-defined grammar |
| 2.2.3 Android `strings.xml` parser | `xml.etree.ElementTree` (stdlib) | standard XML; no external dep needed |
| Rule 1 `loc.locale_coverage` | Python computation on `:LocaleResource` rows | pure aggregation, no file parsing |
| Rule 2 `loc.hardcoded_swiftui` | semgrep (YAML rules + subprocess) | proven pattern in `error_handling_policy`; AST-aware matching handles Swift syntax |
| Rule 3 `loc.hardcoded_compose` | semgrep (YAML rules + subprocess) | same architecture as rule 2; Kotlin support built-in |
| Rule 4 `loc.hardcoded_uikit` | semgrep (YAML rules + subprocess) | same architecture; UIKit patterns are AST-matchable |
| Rule 5 `a11y.missing_label_swiftui` | semgrep (YAML rules + subprocess) | `.accessibilityLabel(...)` chain detection needs AST awareness |
| Rule 6 `a11y.missing_compose` | semgrep (YAML rules + subprocess) | `Modifier.semantics` chain detection; Compose-only per Slice 2-lite |

Semgrep rules live under `extractors/localization_accessibility/semgrep_rules/<rule_id>.yaml`.
Subprocess runner follows `error_handling_policy` pattern: `semgrep --config <rule>.yaml --json <target_dir>` → parse JSON output → map to `:HardcodedString` / `:A11yMissing` nodes.

## File structure (W3)

| File | Purpose |
|---|---|
| `extractors/localization_accessibility/__init__.py` | Package init |
| `extractors/localization_accessibility/extractor.py` | `LocalizationAccessibilityExtractor(BaseExtractor)` |
| `extractors/localization_accessibility/parsers/__init__.py` | Parser package init |
| `extractors/localization_accessibility/parsers/xcstrings.py` | `.xcstrings` JSON parser |
| `extractors/localization_accessibility/parsers/localizable_strings.py` | `Localizable.strings` key=value parser |
| `extractors/localization_accessibility/parsers/android_strings.py` | `res/values-XX/strings.xml` parser |
| `extractors/localization_accessibility/parsers/coverage.py` | Rule 1: locale coverage computation |
| `extractors/localization_accessibility/semgrep_rules/loc_hardcoded_swiftui.yaml` | Semgrep rule: SwiftUI hardcoded strings |
| `extractors/localization_accessibility/semgrep_rules/loc_hardcoded_compose.yaml` | Semgrep rule: Compose hardcoded strings |
| `extractors/localization_accessibility/semgrep_rules/loc_hardcoded_uikit.yaml` | Semgrep rule: UIKit hardcoded strings |
| `extractors/localization_accessibility/semgrep_rules/a11y_missing_label_swiftui.yaml` | Semgrep rule: SwiftUI a11y missing |
| `extractors/localization_accessibility/semgrep_rules/a11y_missing_compose.yaml` | Semgrep rule: Compose a11y missing |
| `extractors/localization_accessibility/rules/__init__.py` | Rules package init |
| `extractors/localization_accessibility/rules/semgrep_runner.py` | Shared semgrep subprocess + JSON mapper |
| `extractors/localization_accessibility/rules/allowlist.py` | Allowlist loader + matcher |
| `extractors/localization_accessibility/neo4j_writer.py` | Neo4j write logic |
| `tests/extractors/unit/test_localization_accessibility.py` | Unit tests (parsers + rules) |
| `tests/extractors/integration/test_localization_accessibility_integration.py` | Integration tests (Neo4j) |
| `tests/extractors/fixtures/loc-a11y-fixture/` | Fixture root |
| `tests/extractors/fixtures/loc-a11y-fixture/xcstrings/` | Synthetic `.xcstrings` |
| `tests/extractors/fixtures/loc-a11y-fixture/localizable-strings/` | Synthetic `Localizable.strings` per locale |
| `tests/extractors/fixtures/loc-a11y-fixture/android-strings/` | Synthetic `res/values-XX/strings.xml` |
| `tests/extractors/fixtures/loc-a11y-fixture/hardcoded-swiftui/{good,bad}/` | Rule 2 fixtures |
| `tests/extractors/fixtures/loc-a11y-fixture/hardcoded-compose/{good,bad}/` | Rule 3 fixtures |
| `tests/extractors/fixtures/loc-a11y-fixture/hardcoded-uikit/{good,bad}/` | Rule 4 fixtures |
| `tests/extractors/fixtures/loc-a11y-fixture/a11y-missing-swiftui/{good,bad}/` | Rule 5 fixtures |
| `tests/extractors/fixtures/loc-a11y-fixture/a11y-missing-compose/{good,bad}/` | Rule 6 fixtures |
| `audit/templates/localization_accessibility.md` | Audit report template |
| `docs/runbooks/localization-accessibility.md` | Operator runbook |

Estimated: ~28 new files.

---

## Phase 0 — Wait + branch (Board)

### Step 0.1 (E6 gate)

- [x] ~~Verify E6~~ — E6 gate no longer applies (team reassigned).

### Step 0.2 (Issue + branch)

- [x] Paperclip issue GIM-275 opened.
- [x] Branch `feature/GIM-275-localization-accessibility-extractor` created.

---

## Phase 1 — CTO formalisation + plan-first review

### Step 1.1 (CTO)

- [x] Resolved LA-D1..LA-D5 (see spec §7a).
- [x] Reassigned CodeReviewer.

### Step 1.2 (CodeReviewer plan-first)

- [ ] Verify each of 6 rules has test+impl+commit.
- [ ] Verify allowlist mechanism (LA-D4) is implementable.
- [ ] APPROVE → PythonEngineer.

---

## Phase 2 — Implementation

### Phase 2.1 — Scaffolding

- [ ] Failing test: `LocalizationAccessibilityExtractor` class loads + registers.
- [ ] Implement under
      `extractors/localization_accessibility/{__init__,extractor}.py`.
- [ ] Add to `EXTRACTORS` registry.
- [ ] Tests GREEN.
- [ ] Commit: `feat(GIM-275): localization_accessibility scaffolding`.

### Phase 2.2 — Locale resource parsers

#### 2.2.1 — iOS xcstrings parser

- [ ] Failing test: synthetic `.xcstrings` JSON → expected
      `:LocaleResource` rows.
- [ ] Implement `extractors/localization_accessibility/parsers/xcstrings.py`.
      Uses `json` (stdlib) to parse `.xcstrings` catalog format.
- [ ] Tests GREEN.
- [ ] Commit.

#### 2.2.2 — iOS legacy `Localizable.strings` parser

- [ ] Failing test: synthetic `Localizable.strings` per locale → expected rows.
- [ ] Implement `extractors/localization_accessibility/parsers/localizable_strings.py`.
      Uses regex to parse `"key" = "value";` format.
- [ ] Tests GREEN.
- [ ] Commit.

> **W1 scope note:** `.stringsdict` (Apple plural rules — XML plist format) is **deferred to v2**. Plural rules require a separate parser and contribute only to coverage counts, not to hard-coded / a11y detection. Low ROI for v1.

#### 2.2.3 — Android `strings.xml` parser

- [ ] Failing test: synthetic `res/values-XX/strings.xml` per locale → expected rows.
- [ ] Implement `extractors/localization_accessibility/parsers/android_strings.py`.
      Uses `xml.etree.ElementTree` (stdlib).
- [ ] Tests GREEN.
- [ ] Commit.

#### 2.2.4 — Locale coverage computation (rule 1: `loc.locale_coverage`)

- [ ] Failing test: 3 synthetic locales (`en`=100 keys, `ru`=80 keys, `es`=60 keys)
      → coverage computed as `en`=100%, `ru`=80%, `es`=60% relative to base locale `en`.
- [ ] Implement `extractors/localization_accessibility/parsers/coverage.py`.
      Pure Python computation on `:LocaleResource` rows after parsers run.
- [ ] Tests GREEN.
- [ ] Commit: `feat(GIM-275): loc.locale_coverage computation`.

### Phase 2.3 — Hard-coded string detectors (rules 2-4)

Detection approach: **semgrep custom YAML rules** (subprocess runner, JSON output → `:HardcodedString` mapping). Shared runner in `rules/semgrep_runner.py`.

For each of `loc.hardcoded_swiftui`, `loc.hardcoded_compose`,
`loc.hardcoded_uikit`:

- [ ] Semgrep YAML rule under `semgrep_rules/<rule_id>.yaml`.
- [ ] Fixture under
      `tests/extractors/fixtures/loc-a11y-fixture/<rule>/{good,bad}/*.{swift,kt}`.
      **N1:** `hardcoded-swiftui/good/` MUST include a `Text(verbatim:)` case
      (spec §9 R2 — deliberately NOT flagged).
- [ ] Unit test: runner on each fixture returns expected
      `:HardcodedString` rows with correct severity + context.
- [ ] Tests GREEN.
- [ ] Commit per rule.

### Phase 2.4 — A11y missing detectors (rules 5-6)

Detection approach: **semgrep custom YAML rules** (same runner as Phase 2.3).

> **Slice 2-lite narrowing (W2):** Rule 6 `a11y.missing_compose` covers Compose `Modifier.semantics` detection **only**. View XML `android:contentDescription` / `android:labelFor` checks are **deferred** — no YAML rule, no fixture, no test for View XML in this slice.

For each of `a11y.missing_label_swiftui`, `a11y.missing_compose`:

- [ ] Semgrep YAML rule under `semgrep_rules/<rule_id>.yaml`.
- [ ] Fixture per rule under `tests/extractors/fixtures/loc-a11y-fixture/`.
- [ ] Unit test: runner returns expected `:A11yMissing` rows.
- [ ] Tests GREEN.
- [ ] Commit per rule.

### Phase 2.5 — Allowlist mechanism (LA-D4)

- [ ] Failing test: extractor reads `<project>/.gimle/loc-allowlist.txt`
      (one literal per line) and skips matching strings during
      hard-coded detection.
- [ ] Implement allowlist loader in `rules/allowlist.py`.
- [ ] Tests GREEN.
- [ ] Commit: `feat(GIM-275): loc-a11y allowlist support`.

### Phase 2.6 — extract() orchestration + Neo4j writer

- [ ] Failing integration test (testcontainers Neo4j): extractor on
      multi-locale + multi-rule fixture writes ≥2 `:LocaleResource`
      + ≥3 `:HardcodedString` + ≥2 `:A11yMissing` + correct provenance.
- [ ] Implement `extract()` orchestration + `neo4j_writer.py`.
      Use existing `BaseExtractor` + `create_ingest_run` pattern.
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
- [ ] Open PR `feat(GIM-275): localization_accessibility extractor (#9)`.
- [ ] Reassign CodeReviewer.

---

## Phase 3 — Review

### Phase 3.1 — Mechanical (CodeReviewer)

- [ ] `gh pr checks` green; pytest output for new tests.
- [ ] Verify all 6 rules covered.
- [ ] Verify allowlist mechanism works.
- [ ] Verify file list matches File Structure table above.
- [ ] APPROVE → OpusArchitectReviewer.

### Phase 3.2 — Adversarial

- [ ] Probe: `Text(verbatim:)` correctly NOT flagged (per spec §9 R2)?
- [ ] Probe: A11y rule on test files correctly skipped (LA-D3)?
- [ ] Probe: locale coverage with mixed `.xcstrings` + legacy
      `.strings` files in same project — sane aggregation?
- [ ] Probe: very long literal strings (e.g., legal text) handled
      correctly (truncated to 100 chars per spec)?

---

## Phase 4 — QA evidence (QAEngineer on iMac)

### 4.1 — Android smoke (`uw-android`)

- [ ] iMac live: bring up palace-mcp.
- [ ] Live MCP call: `palace.ingest.run_extractor(name="localization_accessibility", project="uw-android")`.
- [ ] Cypher: `MATCH (lr:LocaleResource {project_id: $p}) RETURN lr.locale, lr.key_count` — locale matrix populated.
- [ ] Cypher: `MATCH (h:HardcodedString {project_id: $p, severity: "high"}) RETURN count(h)` — non-zero count expected.

### 4.2 — iOS smoke (`uw-ios-mini` fixture or `uw-ios`)

- [ ] Live MCP call: `palace.ingest.run_extractor(name="localization_accessibility", project="uw-ios-mini")`.
      (If `uw-ios-mini` lacks `.strings`/`.xcstrings` files, use `uw-ios` or add synthetic loc fixture to `uw-ios-mini`.)
- [ ] Cypher: `MATCH (lr:LocaleResource {project_id: $p, surface: "ios"}) RETURN lr.locale, lr.key_count`.
- [ ] Cypher: `MATCH (a:A11yMissing {project_id: $p, surface: "ios"}) RETURN count(a)` — validates iOS rules fire.

### 4.3 — QA evidence

- [ ] QA Evidence in PR body with SHA, Cypher outputs from 4.1 + 4.2.

---

## Phase 5 — Merge (CTO)

- [ ] CI green; CR + Opus APPROVE; QA Evidence.
- [ ] Squash-merge.
- [ ] Update `docs/roadmap-archive.md` §2.2 #9 row → ✅ + SHA.
- [ ] iMac deploy.

---

## DoD checklist

- [ ] Scaffolding + 3 locale parsers + 1 coverage computation + 5
      semgrep rule classifiers + allowlist + extract + audit_contract
      + template + runbook + CLAUDE.md update — merged.
- [ ] Smoke run on UW-Android produces expected locale coverage matrix.
- [ ] Smoke run on iOS target (`uw-ios-mini` or `uw-ios`) validates iOS rules.
- [ ] Roadmap updated.

---

## Risks (from spec §9)

R1 false positives · R2 `Text(verbatim:)` · R3 custom Compose DSL ·
R4 locale-resource churn.

---

## Cross-references

- Spec: `2026-05-07-localization-accessibility-extractor_spec.md`.
- ~~Predecessor: E6~~ — no longer applies.
- Roadmap: `docs/roadmap-archive.md` §2.2 #9.
- Audit-V1 integration: §3 Quality (and potential §11 future
  sub-section if locale/a11y becomes a first-class report section).
