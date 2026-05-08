# Audit-V1 S2.2 — Architecture Layer extractor — Implementation Plan

**Issue:** GIM-243
**Spec:** `docs/superpowers/specs/2026-05-08-GIM-243-arch-layer-extractor_spec.md`
**Branch:** `feature/GIM-243-arch-layer-extractor`
**Target:** `develop`
**Source sprint:** `docs/superpowers/sprints/B-audit-extractors.md` §S2.2
**Predecessor:** GIM-239 merged to `develop` at `700a17a65e1187425da162981a50adafe03a5c28`

---

## Phase 1.1 — CTO formalisation

### Step 1.1.1: Verify S2.2 against current develop

**Owner:** CXCTO
**Affected paths:** `docs/superpowers/sprints/B-audit-extractors.md`,
`docs/superpowers/specs/2026-05-08-GIM-243-arch-layer-extractor_spec.md`,
this plan.
**Dependencies:** GIM-239 merged.

Description:

- Check `origin/develop` after GIM-239.
- Confirm current `AuditContract` shape.
- Confirm `dependency_surface` owns `(:Project)-[:DEPENDS_ON]->(:ExternalDependency)`.
- Resolve sprint ambiguity around module dependencies and external tooling.

Acceptance criteria:

- Spec cites current `AuditContract` fields.
- Plan forbids reusing `:DEPENDS_ON` for module edges.
- Plan has explicit external-tooling spike gate.
- Issue is handed to CXCodeReviewer for plan-first review.

## Phase 1.2 — Plan-first review

### Step 1.2.1: Review architecture and acceptance criteria

**Owner:** CXCodeReviewer
**Affected paths:** spec and plan only.
**Dependencies:** Step 1.1.1.

Description:

- Review spec/plan before implementation.
- Verify no unsupported external API commitments.
- Verify changed graph semantics do not collide with existing
  `dependency_surface`.
- Verify each implementation step has measurable acceptance criteria.

Acceptance criteria:

- Paperclip comment says APPROVE or REQUEST CHANGES.
- If approved, issue is reassigned to CXPythonEngineer for Phase 2.
- If changes are requested, comments cite exact spec/plan lines.

## Phase 2 — Implementation

### Step 2.1: Scaffold `arch_layer` package and models

**Owner:** CXPythonEngineer
**Affected paths:**

- `services/palace-mcp/src/palace_mcp/extractors/arch_layer/__init__.py`
- `services/palace-mcp/src/palace_mcp/extractors/arch_layer/models.py`
- `services/palace-mcp/tests/extractors/unit/test_arch_layer_models.py`

**Dependencies:** Phase 1.2 APPROVE.

Description:

- Add Pydantic models for modules, layers, rules, module dependencies,
  import evidence, parser warnings and violations.
- Keep model fields aligned with spec §7.

Acceptance criteria:

- Model tests cover valid and invalid severities, missing identifiers,
  duplicate key components and frozen model behavior.
- No registry changes yet.

### Step 2.2: Add rule loader

**Owner:** CXPythonEngineer
**Affected paths:**

- `services/palace-mcp/src/palace_mcp/extractors/arch_layer/rules.py`
- `services/palace-mcp/tests/extractors/unit/test_arch_layer_rules.py`
- `services/palace-mcp/tests/extractors/fixtures/arch-layer-mini-project/.palace/architecture-rules.yaml`

**Dependencies:** Step 2.1.

Description:

- Load `.palace/architecture-rules.yaml`, then `docs/architecture-rules.yaml`.
- Support no-file, valid-file, invalid-YAML and unknown-rule-kind cases.
- Do not add external tooling dependencies.

Acceptance criteria:

- No rule file returns an empty ruleset and `rules_declared=false`.
- Invalid YAML raises extractor config error.
- Unknown rule kinds are warnings, not crashes.
- Valid fixture returns expected layers and rules.

### Step 2.3: Add SwiftPM and Gradle parsers

**Owner:** CXPythonEngineer
**Affected paths:**

- `services/palace-mcp/src/palace_mcp/extractors/arch_layer/parsers/spm.py`
- `services/palace-mcp/src/palace_mcp/extractors/arch_layer/parsers/gradle.py`
- `services/palace-mcp/tests/extractors/unit/test_arch_layer_parser_spm.py`
- `services/palace-mcp/tests/extractors/unit/test_arch_layer_parser_gradle.py`
- `services/palace-mcp/tests/extractors/fixtures/arch-layer-mini-project/`

**Dependencies:** Step 2.1.

Description:

- Parse SwiftPM target names and internal target dependencies from
  `Package.swift`.
- Parse Gradle module includes and `project(":x")` dependencies from
  `settings.gradle.kts` and `build.gradle.kts`.
- Record parser warnings for unsupported constructs.

Acceptance criteria:

- Swift fixture yields expected module count and internal dependency edges.
- Gradle fixture yields expected module count and dependency scopes.
- Unsupported manifest constructs produce warnings and no guessed edges.
- Tests do not invoke Swift, Gradle or network.

### Step 2.4: Add import scanner and rule evaluator

**Owner:** CXPythonEngineer
**Affected paths:**

- `services/palace-mcp/src/palace_mcp/extractors/arch_layer/imports.py`
- `services/palace-mcp/src/palace_mcp/extractors/arch_layer/evaluator.py`
- `services/palace-mcp/tests/extractors/unit/test_arch_layer_imports.py`
- `services/palace-mcp/tests/extractors/unit/test_arch_layer_evaluator.py`

**Dependencies:** Steps 2.2 and 2.3.

Description:

- Scan Swift/Kotlin/Java imports using conservative text parsing.
- Evaluate `forbidden_dependency`, `forbidden_module_glob_dependency`,
  `no_circular_module_deps`, `manifest_dep_actually_used` and
  `ast_dep_not_declared`.
- Include evidence text and source file/line when available.

Acceptance criteria:

- One good and one bad fixture per rule kind.
- Ambiguous import-to-module mapping produces warning, not violation.
- Cycle detection emits deterministic results.
- Severity defaults match spec §9.

### Step 2.5: Add Neo4j writer and schema bootstrap

**Owner:** CXPythonEngineer
**Affected paths:**

- `services/palace-mcp/src/palace_mcp/extractors/arch_layer/neo4j_writer.py`
- `services/palace-mcp/tests/extractors/integration/test_arch_layer_integration.py`

**Dependencies:** Steps 2.1 through 2.4.

Description:

- Create constraints/indexes from spec §7.
- Write `:Module`, `:Layer`, `:ArchRule`, `:ArchViolation`,
  `:IN_LAYER`, `:MODULE_DEPENDS_ON`, `:VIOLATES_RULE`.
- Keep `:DEPENDS_ON` untouched.

Acceptance criteria:

- Integration test writes expected nodes and edges.
- Second run is idempotent and creates zero duplicates.
- A query against existing `:DEPENDS_ON` still only sees
  `Project -> ExternalDependency` edges.
- Constraints are safe to run repeatedly.

### Step 2.6: Implement extractor, registry and audit contract

**Owner:** CXPythonEngineer
**Affected paths:**

- `services/palace-mcp/src/palace_mcp/extractors/arch_layer/extractor.py`
- `services/palace-mcp/src/palace_mcp/extractors/registry.py`
- `services/palace-mcp/tests/extractors/unit/test_registry.py`
- `services/palace-mcp/tests/extractors/unit/test_arch_layer_extractor.py`

**Dependencies:** Step 2.5.

Description:

- Compose rule loader, parsers, import scanner, evaluator and writer.
- Register `arch_layer`.
- Return current-form `AuditContract`.
- Return meaningful `ExtractorStats`.

Acceptance criteria:

- `EXTRACTORS["arch_layer"]` exists.
- `audit_contract().template_name == "arch_layer.md"`.
- Contract query uses `$project_id`.
- No-manifest and no-rule-file cases return controlled stats and warnings.

### Step 2.7: Add audit template and runbook

**Owner:** CXPythonEngineer
**Affected paths:**

- `services/palace-mcp/src/palace_mcp/audit/templates/arch_layer.md`
- `services/palace-mcp/tests/audit/unit/test_templates.py`
- `docs/runbooks/arch-layer.md`

**Dependencies:** Step 2.6.

Description:

- Add template with module DAG summary, severity-grouped violations,
  parser warnings, provenance and clean/no-rules messages.
- Add runbook for rule file authoring, ingest order, smoke and troubleshooting.

Acceptance criteria:

- Template golden tests pass.
- Runbook names the default rule file locations.
- Runbook explains that `dependency_surface` is optional context, not a
  prerequisite for `arch_layer`.

### Step 2.8: Local implementation validation and PR

**Owner:** CXPythonEngineer
**Affected paths:** implementation files from Phase 2.
**Dependencies:** Steps 2.1 through 2.7.

Description:

- Run targeted unit and integration tests for `arch_layer`.
- Run registry/audit template tests touched by this slice.
- Push the branch and open/update PR into `develop`.

Acceptance criteria:

- Targeted tests are green or failures are documented with exact blocker.
- PR includes spec + plan links.
- Paperclip handoff includes branch, commit SHA and test evidence.

## Phase 3.1 — Mechanical code review

### Step 3.1.1: Review implementation against plan

**Owner:** CXCodeReviewer
**Affected paths:** all files changed by Phase 2.
**Dependencies:** Phase 2 handoff.

Description:

- Verify changed files are within declared scope.
- Verify graph schema does not reuse `:DEPENDS_ON` for module edges.
- Verify no external tooling dependency was added without spike.
- Verify tests cover all V1 rule kinds and idempotent writes.

Acceptance criteria:

- APPROVE or REQUEST CHANGES in Paperclip and GitHub.
- Any requested changes cite exact file/line and plan/spec requirement.

## Phase 3.2 — Architect adversarial review

### Step 3.2.1: Review architecture risk

**Owner:** CodexArchitectReviewer
**Affected paths:** implementation and docs.
**Dependencies:** Phase 3.1 APPROVE.

Description:

- Check graph contract compatibility with Audit-V1 S1 and GIM-239.
- Check false-positive controls for import evidence.
- Check no-rule-file behavior and report semantics.

Acceptance criteria:

- APPROVE or REQUEST CHANGES.
- If approved, issue is reassigned to CXQAEngineer.

## Phase 4.1 — QA live smoke

### Step 4.1.1: Run required QA evidence

**Owner:** CXQAEngineer
**Affected paths:** runtime only; no implementation changes unless returned.
**Dependencies:** Phase 3.2 APPROVE.

Description:

- Run required quality gates from project instructions.
- Run live smoke on `tronkit-swift`.
- Verify a real MCP/tool path or ingest CLI path, not only unit tests.
- Restore production checkout per checkout discipline.

Acceptance criteria:

- QA PASS comment includes commit SHA, container health, extractor run output,
  `:Module` count > 1, report evidence, and production checkout restoration.
- If failed, issue returns to implementer with exact failing command/output.

## Phase 4.2 — CTO merge and queue propagation

### Step 4.2.1: Merge readiness and close/handoff

**Owner:** CXCTO
**Affected paths:** Paperclip/GitHub only.
**Dependencies:** Phase 4.1 QA PASS by CXQAEngineer.

Description:

- Run mandatory merge-readiness reality check.
- Squash-merge to `develop` if checks/reviews allow.
- Confirm merge SHA.
- Propagate Audit-V1 queue to S2.3 if unblocked.

Acceptance criteria:

- `gh pr view --json mergeStateStatus,mergeable,statusCheckRollup,reviewDecision,headRefOid`
  output is posted before claiming merge readiness/blocker.
- PR merged to `develop`.
- Issue closed only after QA evidence exists and merge/deploy state is documented.
- S2.3 is unblocked or Board is told exactly what remains blocked.

## External tooling gate

Implementation may not add `modules-graph-assert`, ArchUnit, tree-sitter or a
new Gradle/SwiftPM parser dependency in this issue unless a fresh
`docs/research/<tool>-arch-layer-spike/` artifact is added first and reviewed
by CXCodeReviewer. Default plan uses conservative Python parsing only.
