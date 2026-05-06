---
slug: build-system-extractor
status: proposed (rev1)
branch: feature/GIM-TBD-build-system-extractor
paperclip_issue: TBD
authoring_team: CX/Codex spec gate; CX/Codex implements end-to-end after approval
predecessor: 0a9c236 (origin/develop, post #102)
date: 2026-05-06
roadmap_item: "Phase 2 #25 Build System Extractor"
plan: docs/superpowers/plans/2026-05-06-GIM-TBD-build-system-extractor.md
---

# GIM-TBD - Build System Extractor (Phase 2 #25)

## 1. Context

Roadmap reference: `docs/roadmap.md` §2.1 item #25 "Build System Extractor" -
CX team, deterministic, tool stack `Gradle Tooling API + SwiftPM
PackageDescription + Bazel aquery`. Status before this slice: 📦.

The current `origin/develop` already contains the adjacent extractor work that
must not be duplicated:

- GIM-190 `public_api_surface` writes exported API facts.
- GIM-191 `dependency_surface` writes `:ExternalDependency` and
  `(:Project)-[:DEPENDS_ON]->(:ExternalDependency)`.
- GIM-192 `cross_module_contract` writes module-to-module public API
  consumption snapshots.
- GIM-193 `dead_symbol_binary_surface` writes dead-symbol and binary-surface
  facts.
- GIM-195 `hotspot` writes complexity/churn hotspot facts.

This slice adds the missing build graph substrate: build targets, tasks,
products, configurations, and target-to-target build dependencies. It is
separate from GIM-191 dependency surface. GIM-191 answers "which external
packages does this project declare/resolve?" GIM-TBD answers "which build
targets/tasks/configurations exist, how are they wired, and which outputs do
they produce?"

Research basis:

- `docs/research/extractor-library/report.md` §8 lists #25 Build System as a
  deterministic foundational N+2 slice for build DAG queries.
- `docs/research/extractor-library/report.md` §6.3 states that #25 and #42 must
  stay separate: #25 owns static `:BuildTask` node creation and static
  `cacheable`; #42 later annotates runtime `cacheable_verified`.
- Official Gradle Tooling API docs describe querying project hierarchy,
  dependencies, source directories, and tasks without hand-parsing all Gradle
  DSL.
- Official Swift PackageDescription docs define packages, products, targets,
  target dependencies, resources, and settings as the manifest-level source of
  truth.
- Official Bazel `aquery` docs define action graph queries over the configured
  target graph and machine-readable output modes.

Reference links checked during spec authoring:

- Gradle Tooling API:
  <https://docs.gradle.org/current/userguide/tooling_api.html>
- Swift PackageDescription:
  <https://docs.swift.org/package-manager/PackageDescription/PackageDescription.html>
- Bazel `aquery`:
  <https://bazel.build/versions/9.0.0/query/aquery>

## 2. Goal

Implement extractor `build_system` that creates commit-aware build graph facts
for Gradle, SwiftPM, and Bazel projects without executing full project builds.

The extractor should let operators and future extractors answer:

- what modules/targets/tasks/products exist in a project at a commit;
- which build targets depend on other build targets;
- which tasks/actions produce which outputs;
- which configurations/flavors/variants are visible to the build system;
- which static tasks are cacheable or non-cacheable before #42 adds runtime
  cache evidence.

## 3. Assumptions

- Phase 1 symbol index and existing Phase 2 extractors are available but are not
  required for `build_system` to run.
- `dependency_surface` may already have written `:ExternalDependency` nodes, but
  this extractor must not create or mutate those nodes in v1.
- Build graph extraction may configure a Gradle/SwiftPM/Bazel project, but must
  not execute compile/test/package tasks.
- SwiftPM extraction can use SwiftPM's manifest evaluation JSON output as the
  practical representation of `PackageDescription`; v1 should not parse
  arbitrary Swift manifest syntax with regex.
- Bazel support is optional per project: if no Bazel workspace markers are
  present, the Bazel parser is skipped with metrics, not an error.
- Some UW repos may not use Bazel. A no-Bazel result is acceptable when Gradle
  and/or SwiftPM facts are present.
- If a required external tool is absent, the extractor records a structured
  skip reason for that ecosystem and returns partial stats rather than failing
  the entire run, unless the selected project contains only that ecosystem.

## 4. Scope

### In Scope

1. New extractor identity: `build_system`.
2. New package:
   `services/palace-mcp/src/palace_mcp/extractors/build_system/`.
3. New foundation models for build graph storage:
   - `BuildSystemSnapshot`
   - `BuildTarget`
   - `BuildTask`
   - `BuildProduct`
   - `BuildConfiguration`
4. New graph edges:
   - `(Project)-[:HAS_BUILD_SNAPSHOT]->(BuildSystemSnapshot)`
   - `(BuildSystemSnapshot)-[:DECLARES_BUILD_TARGET]->(BuildTarget)`
   - `(BuildSystemSnapshot)-[:DECLARES_BUILD_TASK]->(BuildTask)`
   - `(BuildSystemSnapshot)-[:DECLARES_BUILD_PRODUCT]->(BuildProduct)`
   - `(BuildSystemSnapshot)-[:DECLARES_BUILD_CONFIGURATION]->(BuildConfiguration)`
   - `(BuildTarget)-[:BUILD_TARGET_DEPENDS_ON]->(BuildTarget)`
   - `(BuildTask)-[:TASK_DEPENDS_ON]->(BuildTask)`
   - `(BuildTask)-[:PRODUCES_BUILD_PRODUCT]->(BuildProduct)`
5. Gradle extractor path:
   - detect `settings.gradle`, `settings.gradle.kts`, `build.gradle`,
     `build.gradle.kts`, and `gradlew`;
   - query build/project/task model via a narrow Tooling API helper;
   - capture project path, task path, group, description, project ownership,
     static cacheability when available, and dependencies when exposed by the
     helper;
   - avoid running compile/test/package tasks.
6. SwiftPM extractor path:
   - detect `Package.swift`;
   - evaluate manifest through SwiftPM JSON output;
   - capture package name, products, targets, target dependencies, resources,
     and build settings where available;
   - avoid package build/test execution.
7. Bazel extractor path:
   - detect `MODULE.bazel`, `WORKSPACE`, `WORKSPACE.bazel`, or `BUILD(.bazel)`;
   - use `bazel query`/`bazel aquery` machine-readable output when `bazel` is
     available;
   - capture configured target/action/task-like facts, mnemonics, inputs,
     outputs, and action owner labels;
   - treat missing Bazel as a structured skip.
8. Commit-aware, deterministic IDs using `group_id`, `project`, ecosystem,
   target/task/product/configuration key, `commit_sha`, and `schema_version`.
9. Unit tests for model validation, ID stability, parser normalization, skip
   reasons, and graph planning.
10. Integration test with a fixture containing at least:
    - one minimal Gradle multi-project build;
    - one minimal SwiftPM package with product and multiple targets;
    - one minimal Bazel workspace if Bazel is available in CI, otherwise a
      committed parser fixture from JSON/proto output and a skip-path test.
11. Runbook at `docs/runbooks/build-system.md` with direct Neo4j inspection
    queries and tool availability notes.
12. Registry entry in `extractors/registry.py`.

### Out Of Scope

- Creating or mutating `:ExternalDependency` nodes. That remains GIM-191.
- Runtime cache-hit evidence, Develocity/Bazel BEP ingestion, or
  `cacheable_verified`. That remains #42 Build Reproducibility.
- Full Gradle variant attribute matrix if Tooling API does not expose it
  cleanly in v1.
- Android-specific APK/AAB packaging output analysis.
- Xcode project/workspace build graph extraction outside SwiftPM.
- Executing project builds, tests, package tasks, or code generation tasks.
- Public MCP/API query surface. v1 uses extractor stats, tests, runbook queries,
  and direct Neo4j smoke.
- Automatic bundle iteration. Operator can run per project/member.

## 5. Data Model

### `BuildSystemSnapshot`

One project/ecosystem snapshot at one commit.

- `id`
- `group_id`
- `project`
- `ecosystem`: `gradle`, `swiftpm`, or `bazel`
- `commit_sha`
- `root_path`
- `tool_name`
- `tool_version`
- `schema_version`
- `target_count`
- `task_count`
- `product_count`
- `configuration_count`
- `skip_reasons`

### `BuildTarget`

Build-level target/module identity. Examples: Gradle project `:shared`,
SwiftPM target `WalletCore`, Bazel label `//app:app`.

- `id`
- `group_id`
- `project`
- `ecosystem`
- `commit_sha`
- `name`
- `qualified_name`
- `target_kind`
- `module_path`
- `source_roots`
- `resource_roots`
- `schema_version`

### `BuildTask`

Task or action-like build operation.

- `id`
- `group_id`
- `project`
- `ecosystem`
- `commit_sha`
- `name`
- `qualified_name`
- `owner_target_id`
- `task_kind`
- `group_name`
- `description`
- `cacheable`
- `inputs_sample`
- `outputs_sample`
- `schema_version`

`cacheable` is static only. #42 may later add `cacheable_verified` from runtime
evidence.

### `BuildProduct`

Build output declared by the build system.

- `id`
- `group_id`
- `project`
- `ecosystem`
- `commit_sha`
- `name`
- `product_kind`
- `path`
- `owner_target_id`
- `schema_version`

### `BuildConfiguration`

Configuration/variant/flavor/platform/build-setting record.

- `id`
- `group_id`
- `project`
- `ecosystem`
- `commit_sha`
- `name`
- `configuration_kind`
- `owner_target_id`
- `attributes`
- `schema_version`

## 6. Matching And Identity Rules

1. All nodes are commit-aware. No build graph edge may cross commit boundaries.
2. IDs must be deterministic across identical fixture runs.
3. Repo-relative paths use POSIX separators and must not be absolute.
4. Same label/path from different ecosystems is not deduplicated.
5. Gradle project paths (`:`, `:app`, `:shared`) and task paths
   (`:app:assembleDebug`) are canonical keys.
6. SwiftPM package/target/product names are canonical keys within the package
   root.
7. Bazel labels are canonical keys and must preserve repository/package/target
   identity.
8. If parser output cannot determine a relationship exactly, skip the edge with
   a metric. Do not infer target/task dependencies from name substrings.

## 7. Affected Areas After Approval

Expected implementation paths:

- `services/palace-mcp/src/palace_mcp/extractors/build_system/`
- `services/palace-mcp/src/palace_mcp/extractors/registry.py`
- `services/palace-mcp/src/palace_mcp/extractors/foundation/models.py`
- `services/palace-mcp/src/palace_mcp/extractors/foundation/schema.py`
- `services/palace-mcp/tests/extractors/unit/test_build_system*.py`
- `services/palace-mcp/tests/extractors/integration/test_build_system_integration.py`
- `services/palace-mcp/tests/extractors/fixtures/build-system-mini-project/`
- `docs/runbooks/build-system.md`

Potential helper paths if the approved implementation needs subprocess
fixtures or a JVM helper:

- `services/palace-mcp/src/palace_mcp/extractors/build_system/tooling/`
- `services/palace-mcp/tests/extractors/fixtures/build-system-tool-output/`

Implementation must avoid edits to `dependency_surface` unless a tiny shared
manifest-walk helper is explicitly approved during review.

## 8. Acceptance Criteria

1. `build_system` is registered and runnable through the existing extractor
   runner.
2. Minimal fixture creates at least one `BuildSystemSnapshot`.
3. Gradle fixture creates multiple `BuildTarget` nodes and `BuildTask` nodes.
4. SwiftPM fixture creates `BuildTarget` and `BuildProduct` nodes with target
   dependency edges.
5. Bazel fixture path either creates action/target facts from committed
   machine-readable output or proves structured skip behavior when Bazel is not
   available.
6. Snapshot/target/task/product/configuration IDs are deterministic across two
   identical fixture runs.
7. No `ExternalDependency` nodes are created or mutated by this extractor.
8. No compile/test/package task is executed during extraction.
9. No build graph edge crosses commit boundaries.
10. Missing external tools produce structured skip metrics and partial success
    when other ecosystems are present.
11. Runbook includes Neo4j queries for snapshots, targets, tasks, products,
    dependency edges, no external-dependency writes, and no cross-commit edges.
12. Targeted unit/integration tests and lint/typecheck pass.

## 9. Verification Plan

Targeted tests after implementation:

```bash
cd services/palace-mcp
uv run pytest tests/extractors/unit/test_build_system*.py -v
uv run pytest tests/extractors/integration/test_build_system_integration.py -v
```

Pre-review implementation gate:

```bash
cd services/palace-mcp
uv run ruff check src/palace_mcp/extractors tests/extractors
uv run mypy src/
uv run pytest tests/extractors/unit/test_build_system*.py -v
uv run pytest tests/extractors/integration/test_build_system_integration.py -v
```

QA graph invariants should include:

```cypher
MATCH (s:BuildSystemSnapshot) RETURN s.ecosystem, count(s) AS snapshots;

MATCH (s:BuildSystemSnapshot)-[:DECLARES_BUILD_TARGET]->(t:BuildTarget)
RETURN s.ecosystem, count(t) AS targets;

MATCH (task:BuildTask)-[:PRODUCES_BUILD_PRODUCT]->(product:BuildProduct)
RETURN count(*) AS task_products;

MATCH (a)-[r:BUILD_TARGET_DEPENDS_ON|TASK_DEPENDS_ON]->(b)
WHERE a.commit_sha <> b.commit_sha
RETURN count(r) AS cross_commit_edges;

MATCH (n:ExternalDependency)
RETURN count(n) AS external_dependency_count_after_build_system;
```

## 10. Open Questions

1. Should Gradle extraction require a small JVM helper in this repository, or
   should it invoke a checked-in init script/build action via the existing
   wrapper? The implementation plan treats this as Step 2 spike before code.
2. Should Bazel v1 be pure fixture/parser support until a real Bazel project is
   present, or should CI install/use Bazel for an executable integration test?
3. How much Gradle variant/flavor detail is required for the first UW query?
   v1 should reject broad Android variant modeling unless the operator names a
   concrete query.
4. Should `BuildTarget` later link to source `:Module` nodes if/when module
   ownership facts exist? v1 stores build targets independently and avoids
   guessing.

## 11. Followups

- #42 Build Reproducibility: annotate `BuildTask.cacheable_verified` and
  runtime cache-hit evidence.
- Android variant matrix expansion if product flavor/build type queries become
  first-class.
- Xcode `.xcodeproj` / `.xcworkspace` graph extraction if UW-iOS build questions
  require it.
- External dependency join from `BuildTarget` to GIM-191 `ExternalDependency`
  once a concrete query needs target-level dependency answers.
