# Testability / DI Pattern Extractor (#8) — план реализации

Формализуем GIM-242 как v1 Python heuristic extractor: сначала стабильная схема, registry, scanner, writer и audit contract; внешние Swift/Kotlin toolchains остаются future hardening до live-verified spikes.

## Scope

- In: `testability_di` extractor, Swift/Kotlin source scanning, graph writer, audit template, runbook, tests, live QA smoke.
- Out: SwiftSyntax/Konsist/Harmonize/detekt/semgrep runtime integration, coverage measurement, test smell detection, auto-fixes.

## Phase 1 — Plan-first

### Step 1.1 — CTO formalisation

**Owner:** CXCTO.
**Status:** complete in branch `feature/GIM-242-testability-di-pattern-extractor`.
**Files:**

- `docs/superpowers/specs/2026-05-08-GIM-242-testability-di-pattern-extractor_spec.md`
- `docs/superpowers/plans/2026-05-08-GIM-242-testability-di-pattern-extractor.md`

**Description:** Formalise generic #8 docs into a GIM-242-specific spec/plan, resolve stale blockers, remove unverified external toolchain requirements from rev1, and route plan review before implementation.

**Acceptance criteria:**

- Spec and plan filenames include `GIM-242`.
- Spec documents duplicate discovery evidence.
- Spec uses current `AuditContract` and `:IngestRun` conventions.
- Plan assigns owners, affected paths, acceptance criteria and dependencies per step.

**Dependencies:** none.

### Step 1.2 — Plan-first review

**Owner:** CXCodeReviewer.
**Files:** same docs as Step 1.1.

**Description:** Review architecture before implementation.

**Acceptance criteria:**

- Review confirms rev1 does not require unverified external library APIs.
- Review confirms each rule maps to tests and implementation paths.
- Review confirms `project_id`, `run_id`, `AuditContract`, and Neo4j labels match current repo conventions.
- APPROVE handoff routes implementation to CXPythonEngineer; REQUEST CHANGES returns to CXCTO.

**Dependencies:** Step 1.1.

## Phase 2 — Implementation

### Step 2.1 — Extractor scaffolding

**Owner:** CXPythonEngineer.
**Files:**

- `services/palace-mcp/src/palace_mcp/extractors/testability_di/__init__.py`
- `services/palace-mcp/src/palace_mcp/extractors/testability_di/extractor.py`
- `services/palace-mcp/src/palace_mcp/extractors/registry.py`
- `services/palace-mcp/tests/extractors/unit/test_testability_di_scaffold.py`

**Description:** Add the extractor class, `name="testability_di"`, registry entry and minimal `run()`/`audit_contract()` skeleton.

**Acceptance criteria:**

- Unit test imports `TestabilityDiExtractor`.
- Unit test verifies registry lookup by `testability_di`.
- Skeleton returns empty `ExtractorStats` without touching Neo4j.
- Tests are committed before rule implementation.

**Dependencies:** CXCodeReviewer APPROVE on Step 1.2.

### Step 2.2 — Data models and source scanner foundation

**Owner:** CXPythonEngineer.
**Files:**

- `services/palace-mcp/src/palace_mcp/extractors/testability_di/models.py`
- `services/palace-mcp/src/palace_mcp/extractors/testability_di/scanner.py`
- `services/palace-mcp/tests/extractors/unit/test_testability_di_scanner.py`

**Description:** Define in-memory records for `DiPattern`, `TestDouble`, `UntestableSite`, plus source file iteration over `.swift` and `.kt` with ignored directories.

**Acceptance criteria:**

- Models carry `project_id`, `module`, `language`, `run_id`.
- Scanner skips build/vendor/cache dirs and test/prod classification is deterministic.
- Unit tests cover Swift, Kotlin, test path, non-test path, ignored path.

**Dependencies:** Step 2.1.

### Step 2.3 — DI style rule pack

**Owner:** CXPythonEngineer.
**Files:**

- `services/palace-mcp/src/palace_mcp/extractors/testability_di/rules.py`
- `services/palace-mcp/tests/extractors/fixtures/testability_di/di_style/**`
- `services/palace-mcp/tests/extractors/unit/test_testability_di_rules_di_style.py`

**Description:** Implement rules `di.init_injection`, `di.property_injection`, `di.framework_bound`, and `di.service_locator`.

**Acceptance criteria:**

- Swift and Kotlin fixtures exist for each rule.
- Results include style, optional framework, sample count, outlier count and `confidence="heuristic"`.
- Service locator is high severity when surfaced through `UntestableSite` or audit max severity.
- Composition-root/test-file allowlists are tested.

**Dependencies:** Step 2.2.

### Step 2.4 — Test-double rule pack

**Owner:** CXPythonEngineer.
**Files:**

- `services/palace-mcp/src/palace_mcp/extractors/testability_di/rules.py`
- `services/palace-mcp/tests/extractors/fixtures/testability_di/test_doubles/**`
- `services/palace-mcp/tests/extractors/unit/test_testability_di_rules_test_doubles.py`

**Description:** Implement rules `mock.framework_usage` and `mock.hand_rolled_double`.

**Acceptance criteria:**

- MockK, Mockito and hand-rolled Kotlin doubles are detected in test fixtures.
- Cuckoo-style/hand-rolled Swift doubles are detected in test fixtures.
- Production files with `Fake`/`Mock` in unrelated names do not create `:TestDouble`.
- Each result includes `kind`, `language`, `test_file`, optional `target_symbol`.

**Dependencies:** Step 2.2.

### Step 2.5 — Untestable-site rule pack

**Owner:** CXPythonEngineer.
**Files:**

- `services/palace-mcp/src/palace_mcp/extractors/testability_di/rules.py`
- `services/palace-mcp/tests/extractors/fixtures/testability_di/untestable_sites/**`
- `services/palace-mcp/tests/extractors/unit/test_testability_di_rules_untestable.py`

**Description:** Implement `untestable.direct_resource` for direct clock/session/preferences/filesystem and singleton access in non-test code.

**Acceptance criteria:**

- Swift fixtures cover `Date()`, `Calendar.current`, `URLSession.shared`, `UserDefaults.standard`, `FileManager.default`.
- Kotlin fixtures cover `Instant.now()`, `Calendar.getInstance()`, `getInstance()`, direct shared singleton patterns.
- Test files and allowlisted DI composition roots do not emit findings.
- Findings include file, line range, category, referenced symbol, message, severity.

**Dependencies:** Step 2.2.

### Step 2.6 — Neo4j writer and extractor orchestration

**Owner:** CXPythonEngineer.
**Files:**

- `services/palace-mcp/src/palace_mcp/extractors/testability_di/extractor.py`
- `services/palace-mcp/src/palace_mcp/extractors/testability_di/neo4j_writer.py`
- `services/palace-mcp/tests/extractors/unit/test_testability_di_neo4j_writer.py`
- `services/palace-mcp/tests/extractors/integration/test_testability_di_extractor.py`

**Description:** Wire scanner/rules into `run()`, write graph rows and return stats.

**Acceptance criteria:**

- Writer creates `:DiPattern`, `:TestDouble`, `:UntestableSite`.
- Writer uses `project_id=ctx.group_id` and `run_id=ctx.run_id`.
- Any `:IngestRun` extras match by `{id: $run_id}`, not `{run_id: $run_id}`.
- Integration test writes at least one node of each label on a synthetic mixed Swift/Kotlin fixture.
- No existing labels from other extractors are deleted.

**Dependencies:** Steps 2.3, 2.4, 2.5.

### Step 2.7 — Audit contract and template

**Owner:** CXPythonEngineer.
**Files:**

- `services/palace-mcp/src/palace_mcp/extractors/testability_di/extractor.py`
- `services/palace-mcp/src/palace_mcp/audit/templates/testability_di.md`
- `services/palace-mcp/tests/extractors/unit/test_testability_di_audit_contract.py`
- `services/palace-mcp/tests/audit/test_testability_di_template.py`

**Description:** Implement `audit_contract()` and markdown section rendering for audit-v1.

**Acceptance criteria:**

- Contract uses `extractor_name="testability_di"` and `template_name="testability_di.md"`.
- Query returns `module`, `language`, `style`, `framework`, `sample_count`, `outliers`, `confidence`, `test_doubles`, `untestable_sites`, `max_severity`.
- `severity_column` maps to canonical `low|medium|high`.
- Template renders empty, low-risk and high-risk synthetic findings.

**Dependencies:** Step 2.6.

### Step 2.8 — Runbook and PR handoff

**Owner:** CXPythonEngineer.
**Files:**

- `docs/runbooks/testability-di.md`
- PR body for implementation branch

**Description:** Document operator smoke path and hand implementation to review.

**Acceptance criteria:**

- Runbook includes local unit/integration commands, docker profile, MCP invocation and Cypher checks.
- PR links GIM-242 spec and plan.
- Implementation handoff comment includes branch, commit SHA and local verification output.
- Assignee becomes CXCodeReviewer for Phase 3.1.

**Dependencies:** Step 2.7.

## Phase 3 — Reviews

### Step 3.1 — Mechanical code review

**Owner:** CXCodeReviewer.
**Files:** all implementation diff.

**Description:** Review correctness, maintainability, test coverage and spec compliance.

**Acceptance criteria:**

- Verifies seven rules are implemented or explicitly justified.
- Verifies graph schema and audit contract match this spec.
- Verifies tests cover Swift and Kotlin.
- APPROVE routes to CodexArchitectReviewer; REQUEST CHANGES routes back to CXPythonEngineer.

**Dependencies:** Step 2.8.

### Step 3.2 — Architecture/adversarial review

**Owner:** CodexArchitectReviewer.
**Files:** all implementation diff and docs.

**Description:** Probe false-positive controls, performance bounds, graph semantics and audit usefulness.

**Acceptance criteria:**

- Reviews allowlists for composition roots/test files.
- Reviews scanner path filtering and sample caps.
- Reviews no unverified external API contracts slipped into implementation.
- APPROVE routes to CXQAEngineer.

**Dependencies:** Step 3.1 APPROVE.

## Phase 4 — QA and merge

### Step 4.1 — Live QA evidence

**Owner:** CXQAEngineer.
**Files:** QA evidence comment, optional PR body update.

**Description:** Run local checks and live runtime smoke against real services.

**Acceptance criteria:**

- `cd services/palace-mcp && uv run ruff check` green.
- `cd services/palace-mcp && uv run mypy src/` green.
- `cd services/palace-mcp && uv run pytest` green.
- `docker compose build` green.
- `docker compose --profile full up` healthchecks green.
- Real MCP tool call invokes `palace.ingest.run_extractor` with `testability_di`.
- Cypher evidence shows `:DiPattern` rows and reports `:TestDouble`/`:UntestableSite` distributions, including zero-count explanation if a real repo has none.
- QA evidence comment follows project Phase 4.1 format and hands to CXCTO.

**Dependencies:** Step 3.2 APPROVE.

### Step 4.2 — Merge and close

**Owner:** CXCTO.
**Files:** PR/issue only unless roadmap update is required by accepted implementation plan.

**Description:** Perform merge-readiness reality check, squash-merge to `develop`, verify QA evidence and close issue only after gates are satisfied.

**Acceptance criteria:**

- `gh pr view --json mergeStateStatus,mergeable,statusCheckRollup,reviewDecision,headRefOid` evidence is posted before claiming readiness/blocker.
- Required reviews and QA evidence exist.
- PR is squash-merged into `develop`.
- Production/deploy expectation is documented or completed per current runbook.
- GIM-242 is closed only after Phase 4.1 evidence authored by CXQAEngineer exists.

**Dependencies:** Step 4.1 PASS.

## Handoff matrix

| Done | Next |
|---|---|
| Step 1.1 | CXCodeReviewer plan-first review |
| Step 1.2 APPROVE | CXPythonEngineer implementation |
| Step 2.8 | CXCodeReviewer mechanical review |
| Step 3.1 APPROVE | CodexArchitectReviewer |
| Step 3.2 APPROVE | CXQAEngineer |
| Step 4.1 PASS | CXCTO merge |

## Risk controls

- External toolchains remain deferred until verified spikes exist.
- Every graph row is scoped by `project_id` and `run_id`.
- Allowlist behavior must be tested, not only documented.
- Smoke QA must include real MCP invocation, not only `/healthz`.
