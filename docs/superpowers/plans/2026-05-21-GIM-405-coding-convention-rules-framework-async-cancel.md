# GIM-405 - Coding Convention Rules Framework + async_cancel Seed Intent

Plan for [GIM-405](/GIM/issues/GIM-405). Source of truth is the issue body and spec reference `docs/superpowers/specs/2026-05-19-uw-discovery-readiness-roadmap-rev2.md` section M3.D. The referenced roadmap file is not present in this checkout, so implementation must not add requirements beyond this plan and the issue thread without CTO review.

## Scope

- In: refactor `coding_convention` into a small rule plugin framework, migrate existing syntactic rules without regression, add the first behavioral intent rule `async_cancel`, prove graph output on `uw-ios`, and document the extension pattern for M3.D.1-3.
- Out: public MCP tools, audit renderer redesign, broad graph schema changes, semgrep/tree-sitter runtime provisioning, full interprocedural cancellation correctness, and implementation of later intents.

## CTO Decision

Use a deterministic Python plugin/rules framework with a source-window semantic rule for `async_cancel`, optionally consuming existing SCIP/Tantivy occurrence evidence only where it is already produced by the ingest pipeline. Do not add semgrep or tree-sitter as a new runtime dependency in this slice.

Reason: the current extractor is a Python source scanner with stable Neo4j writer/tests, and prior coding-convention scope deliberately deferred unverified external runtimes. `async_cancel` needs semantic intent, but M3.D.0 can prove the plugin seam and first behavior rule with explicit Swift concurrency patterns, source positions, and operator spotcheck before taking on a heavier parser/data-flow engine.

The `async_cancel` seed rule should classify module-level style choices from concrete Swift evidence:

- `structured_propagation`: `withTaskCancellationHandler`, `Task.checkCancellation()`, `try Task.sleep`, `async throws` cancellation propagation.
- `cooperative_polling`: `Task.isCancelled`, `Task.currentPriority`/loop checks paired with early return or throw.
- `manual_task_handle`: stored `Task` handles with `.cancel()` lifecycle cleanup.
- `missing_or_unclear`: only when enough async/task samples exist but cancellation evidence is absent.

## Phase Steps

### Step 1 - Plan-first review gate

**Description:** Validate this plan before implementation starts, especially the chosen non-semgrep approach and the `async_cancel` evidence taxonomy.
**Acceptance criteria:** CXCodeReviewer explicitly APPROVES or requests changes; reviewer confirms each acceptance criterion from [GIM-405](/GIM/issues/GIM-405) maps to a test, graph query, or QA/operator action; implementation is not assigned before approval.
**Suggested owner:** CXCodeReviewer.
**Affected paths:** this plan, [GIM-405](/GIM/issues/GIM-405) thread.
**Dependencies:** GIM-404 done.

### Step 2 - Freeze current extractor behavior with regression tests

**Description:** Add or extend tests around current `collect_conventions()` output before moving code into rules.
**Acceptance criteria:** Tests assert the existing migrated kinds still produce the same `ConventionFinding.kind`, dominant choice, sample suppression, and violation behavior for `naming.type_class`, `naming.test_class`, `naming.module_protocol`, `structural.adt_pattern`, `structural.error_modeling`, `idiom.collection_init`, and `idiom.computed_vs_property`.
**Suggested owner:** CXPythonEngineer.
**Affected paths:** `services/palace-mcp/tests/extractors/unit/test_coding_convention_extractor.py`, related fixtures.
**Dependencies:** Step 1.

### Step 3 - Introduce the minimal rule interface and registry

**Description:** Add a narrow extension contract for convention rules.
**Acceptance criteria:** `ConventionRule` exposes `kind` and `collect(module, rel_path, text) -> list[ConventionSignal]`; registry discovery returns a deterministic ordered rule list; tests prove duplicate `kind` values fail fast and all built-in rules load.
**Suggested owner:** CXPythonEngineer.
**Affected paths:** `services/palace-mcp/src/palace_mcp/extractors/coding_convention/rules/_base.py`, `services/palace-mcp/src/palace_mcp/extractors/coding_convention/rules/__init__.py`, `services/palace-mcp/tests/extractors/unit/test_coding_convention_rules.py`.
**Dependencies:** Step 2.

### Step 4 - Move existing syntactic rules into plugins

**Description:** Split existing regex classifiers from `extractor.py` into focused rule modules while preserving output shape.
**Acceptance criteria:** `collect_conventions()` iterates the rule registry instead of calling a monolithic `_extract_signals()`; Step 2 tests stay green; no Neo4j writer or audit contract behavior changes.
**Suggested owner:** CXPythonEngineer.
**Affected paths:** `services/palace-mcp/src/palace_mcp/extractors/coding_convention/extractor.py`, `services/palace-mcp/src/palace_mcp/extractors/coding_convention/rules/*.py`.
**Dependencies:** Step 3.

### Step 5 - Add `async_cancel` unit fixture and failing tests

**Description:** Create a compact Swift fixture with at least three modules and mixed cancellation styles.
**Acceptance criteria:** Tests fail first and cover `structured_propagation`, `cooperative_polling`, `manual_task_handle`, and absence/unclear cases; expected output includes `kind="async_cancel"` and module-level dominant choices.
**Suggested owner:** CXPythonEngineer.
**Affected paths:** `services/palace-mcp/tests/extractors/fixtures/coding-convention-async-cancel/`, `services/palace-mcp/tests/extractors/unit/test_coding_convention_async_cancel.py`.
**Dependencies:** Step 4.

### Step 6 - Implement `rules/async_cancel.py`

**Description:** Add the first behavioral rule using deterministic Swift source evidence windows.
**Acceptance criteria:** Rule emits `ConventionSignal` with stable file/line evidence and meaningful messages; low-sample modules are suppressed by existing aggregation; no new external runtime dependency is added; Step 5 tests pass.
**Suggested owner:** CXPythonEngineer.
**Affected paths:** `services/palace-mcp/src/palace_mcp/extractors/coding_convention/rules/async_cancel.py`.
**Dependencies:** Step 5.

### Step 7 - Preserve graph write and audit contract compatibility

**Description:** Ensure the framework refactor still writes the existing `:Convention` and `:ConventionViolation` schema.
**Acceptance criteria:** Unit writer tests continue to pass; integration test asserts the expected kind set includes `async_cancel` plus the migrated syntactic kinds; audit query returns `async_cancel` rows without template/query changes beyond kind data.
**Suggested owner:** CXPythonEngineer.
**Affected paths:** `services/palace-mcp/tests/extractors/unit/test_coding_convention_neo4j_writer.py`, `services/palace-mcp/tests/extractors/integration/test_coding_convention_e2e.py`, optional audit test updates.
**Dependencies:** Step 6.

### Step 8 - Run targeted verification

**Description:** Run only the tests that prove the refactor, new rule, and writer path.
**Acceptance criteria:** Paste exact output for:

```bash
cd services/palace-mcp
uv run pytest tests/extractors/unit/test_coding_convention*.py tests/extractors/coding_convention/test_finding_includes_source_context.py -v
uv run pytest tests/extractors/integration/test_coding_convention_e2e.py -m integration -v
uv run ruff check src/palace_mcp/extractors/coding_convention tests/extractors/unit/test_coding_convention*.py tests/extractors/integration/test_coding_convention_e2e.py
uv run mypy src/palace_mcp/extractors/coding_convention
```

**Suggested owner:** CXPythonEngineer.
**Affected paths:** test output / PR evidence.
**Dependencies:** Step 7.

### Step 9 - Open PR and hand off to mechanical review

**Description:** Push `feature/GIM-405-m3d0-rules-framework` and open a PR to `develop`.
**Acceptance criteria:** PR body links this plan, lists changed files, includes QA Evidence placeholder, and maps each [GIM-405](/GIM/issues/GIM-405) acceptance criterion to tests or live smoke.
**Suggested owner:** CXPythonEngineer.
**Affected paths:** GitHub PR, [GIM-405](/GIM/issues/GIM-405) thread.
**Dependencies:** Step 8.

### Step 10 - Mechanical review

**Description:** Review implementation for plan adherence, regression coverage, and CI readiness.
**Acceptance criteria:** CXCodeReviewer posts compliance checklist with local command evidence, `gh pr checks`, changed-file scope check against this plan, and explicit confirmation that existing syntactic rule outputs did not regress.
**Suggested owner:** CXCodeReviewer.
**Affected paths:** PR diff and evidence.
**Dependencies:** Step 9.

### Step 11 - Adversarial architecture review

**Description:** Challenge whether the plugin interface is minimal, whether `async_cancel` overclaims semantic certainty, and whether later M3.D intents can extend the pattern without new framework churn.
**Acceptance criteria:** CodexArchitectReviewer APPROVES or requests changes; review explicitly covers rule discovery determinism, duplicate-kind handling, evidence quality, low-sample behavior, and no unverified parser/runtime dependency.
**Suggested owner:** CodexArchitectReviewer.
**Affected paths:** PR diff, this plan.
**Dependencies:** Step 10.

### Step 12 - QA and operator-graded spotcheck

**Description:** Run live extractor smoke on `uw-ios` and collect operator spotcheck evidence.
**Acceptance criteria:** CXQAEngineer evidence includes tested head SHA, extractor invocation, direct Neo4j queries proving `:Convention {kind: "async_cancel"}` exists, at least three modules have dominant `async_cancel`, and existing syntactic convention kinds still exist after re-ingest. Operator picks five modules and confirms dominant `async_cancel` matches reality; this operator result is quoted or linked before merge.
**Suggested owner:** CXQAEngineer plus operator for spotcheck only.
**Affected paths:** PR QA Evidence, [GIM-405](/GIM/issues/GIM-405) thread.
**Dependencies:** Step 11.

### Step 13 - Merge gate

**Description:** Merge only after review and QA/operator gates pass.
**Acceptance criteria:** CXCTO verifies latest CR APPROVE and QA PASS cite the same head SHA, `gh pr checks <PR>` exits 0 with no pending required checks, no conflict markers exist, and the PR body references this plan.
**Suggested owner:** CXCTO.
**Affected paths:** PR to `develop`, [GIM-405](/GIM/issues/GIM-405).
**Dependencies:** Step 12.

## Acceptance Mapping

- `async_cancel` `:Convention` nodes on `uw-ios`: Steps 6, 7, 12.
- At least three modules with dominant `async_cancel`: Steps 5, 6, 12.
- Operator-graded five-module spotcheck: Step 12.
- Existing syntactic rules produce correct nodes: Steps 2, 4, 7, 12.
- Clear extension pattern for M3.D.1-3: Steps 3, 4, 11.
- Tests cover framework loading and `async_cancel`: Steps 3, 5, 6, 8.

## Risks

- Source-window heuristics may under-detect cancellation semantics. Mitigation: mark confidence as `heuristic`, require operator spotcheck, and keep the rule taxonomy conservative.
- Missing roadmap file may hide extra constraints. Mitigation: plan-first reviewer must compare this plan to any available issue-thread or branch copy before approval.
- Refactor could silently drop existing convention kinds. Mitigation: freeze kind-level regression tests before moving code.
