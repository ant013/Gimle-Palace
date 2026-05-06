---
slug: build-system-extractor
status: proposed (rev2.1)
branch: feature/GIM-TBD-build-system-extractor
paperclip_issue: TBD
authoring_team: CX/Codex spec gate; CX/Codex implements end-to-end after approval
predecessor: 0a9c236 (origin/develop, post #102)
date: 2026-05-06
roadmap_item: "Phase 2 #25 Build System Extractor"
plan: docs/superpowers/plans/2026-05-06-GIM-TBD-build-system-extractor.md
rev2_changes: |
  Addressed read-only audit blockers before implementation:
  - build identity is now one snapshot per detected build root per ecosystem per commit;
    build_root_path/build_root_id are part of all child node IDs.
  - graph ownership now has explicit BuildTarget ownership edges for tasks,
    products, and configurations.
  - "no build execution" is narrowed to "no build task/action execution";
    configuration/manifest/analysis phases are allowed only under security controls.
  - added sandbox/security constraints for untrusted build metadata evaluation.
  - schema ownership is extractor-local via BaseExtractor.constraints/indexes.
  - missing tools are structured skip records, not extractor failures, unless
    policy explicitly escalates a single detected ecosystem with no extractable facts.
rev2_1_changes: |
  - structured skips persist as zero-count BuildSystemSnapshot records, not logs only.
  - schema_version is explicitly excluded from stable node IDs; it remains a property.
  - Bazel root discovery now requires nearest enclosing MODULE.bazel/WORKSPACE(.bazel);
    BUILD(.bazel)-only candidates persist a skip snapshot instead of becoming roots.
  - Step 2 tooling + security spike output is a hard approval gate before any
    production extractor code.
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
for Gradle, SwiftPM, and Bazel projects without executing compile/test/package
build tasks or Bazel execution actions. The extractor may run controlled build
configuration, SwiftPM manifest evaluation, and Bazel analysis/query phases
because those are the source-of-truth interfaces for build metadata.

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
- Build graph extraction may configure a Gradle/SwiftPM/Bazel project, evaluate
  Swift manifests, and run Bazel query/analysis phases, but must not execute
  compile/test/package tasks, code generation tasks, or Bazel execution
  actions.
- SwiftPM extraction can use SwiftPM's manifest evaluation JSON output as the
  practical representation of `PackageDescription`; v1 should not parse
  arbitrary Swift manifest syntax with regex.
- Bazel support is optional per project: if no Bazel workspace markers are
  present, the Bazel parser is skipped with metrics, not an error.
- Some UW repos may not use Bazel. A no-Bazel result is acceptable when Gradle
  and/or SwiftPM facts are present.
- If a required external tool is absent or the security preflight fails, the
  extractor records a structured skip reason for that ecosystem and returns
  partial stats rather than failing the entire run. A full extractor failure is
  allowed only when the project has exactly one detected ecosystem and the
  approved policy says that ecosystem is mandatory.
- Structured skip reasons must be persisted in graph state. Logs alone are not
  acceptable because `ExtractorStats` and runner `IngestRun` records currently
  expose only aggregate counts/errors/success.

## 4. Scope

### In Scope

1. New extractor identity: `build_system`.
2. New package:
   `services/palace-mcp/src/palace_mcp/extractors/build_system/`.
3. New extractor-local models for build graph storage:
   - `BuildSystemSnapshot`
   - `BuildTarget`
   - `BuildTask`
   - `BuildProduct`
   - `BuildConfiguration`
4. New graph edges:
   - `(Project)-[:HAS_BUILD_SNAPSHOT]->(BuildSystemSnapshot)`
   - `(BuildSystemSnapshot)-[:DECLARES_BUILD_TARGET]->(BuildTarget)`
   - `(BuildTarget)-[:OWNS_BUILD_TASK]->(BuildTask)`
   - `(BuildTarget)-[:DECLARES_BUILD_PRODUCT]->(BuildProduct)`
   - `(BuildTarget)-[:HAS_BUILD_CONFIGURATION]->(BuildConfiguration)`
   - `(BuildTarget)-[:BUILD_TARGET_DEPENDS_ON]->(BuildTarget)`
   - `(BuildTask)-[:TASK_DEPENDS_ON]->(BuildTask)`
   - `(BuildTask)-[:PRODUCES_BUILD_PRODUCT]->(BuildProduct)`
5. Gradle extractor path:
   - detect `settings.gradle`, `settings.gradle.kts`, `build.gradle`,
     `build.gradle.kts`, and `gradlew`;
   - query build/project/task model via a trusted narrow Tooling API helper;
   - capture project path, task path, group, description, project ownership,
     static cacheability when available, and dependencies when exposed by the
     helper;
   - do not execute host repo `gradlew` or allow wrapper downloads.
6. SwiftPM extractor path:
   - detect `Package.swift`;
   - evaluate manifest through `swift package dump-package --type json
     --package-path <root>`;
   - capture package name, products, targets, target dependencies, resources,
     and build settings where available;
   - avoid package build/test execution.
7. Bazel extractor path:
   - discover Bazel build roots by nearest enclosing `MODULE.bazel`,
     `WORKSPACE`, or `WORKSPACE.bazel`;
   - treat `BUILD` / `BUILD.bazel` files as package markers, not workspace
     roots; if no enclosing workspace marker exists, persist a structured skip
     snapshot with `bazel_workspace_root_unresolved`;
   - use `bazel query` and `bazel aquery --output=jsonproto` when `bazel` is
     available; textproto is an allowed fallback only when JSON proto is not
     available for the installed Bazel version;
   - capture configured target/action/task-like facts, mnemonics, inputs,
     outputs, and action owner labels;
   - treat missing Bazel as a structured skip.
8. One `BuildSystemSnapshot` per detected build root per ecosystem per commit.
9. Commit-aware, deterministic IDs using `group_id`, `project`, ecosystem,
   `build_root_path`, target/task/product/configuration key, and `commit_sha`.
   `schema_version` is not part of primary IDs.
10. Unit tests for model validation, ID stability, parser normalization, skip
   reasons, and graph planning.
11. Integration test with a fixture containing at least:
    - one minimal Gradle multi-project build;
    - one minimal SwiftPM package with product and multiple targets;
    - one minimal Bazel workspace if Bazel is available in CI, otherwise a
      committed parser fixture from JSON/proto output and a skip-path test.
12. Runbook at `docs/runbooks/build-system.md` with direct Neo4j inspection
    queries and tool availability notes.
13. Registry entry in `extractors/registry.py`.

### Out Of Scope

- Creating or mutating `:ExternalDependency` nodes. That remains GIM-191.
- Runtime cache-hit evidence, Develocity/Bazel BEP ingestion, or
  `cacheable_verified`. That remains #42 Build Reproducibility.
- Full Gradle variant attribute matrix if Tooling API does not expose it
  cleanly in v1.
- Android-specific APK/AAB packaging output analysis.
- Xcode project/workspace build graph extraction outside SwiftPM.
- Executing project builds, tests, package tasks, code generation tasks, or
  Bazel action execution.
- Persisting raw stdout/stderr, raw Bazel command lines, environment variables,
  secrets, or unbounded tool output.
- Public MCP/API query surface. v1 uses extractor stats, tests, runbook queries,
  and direct Neo4j smoke.
- Automatic bundle iteration. Operator can run per project/member.

## 5. Security Constraints

Build metadata extraction evaluates untrusted repo-controlled code or build
configuration. v1 must fail closed at the ecosystem level unless these controls
are true:

1. Tool execution is sandbox-only. The implementation must have an explicit
   sandbox preflight; if the sandbox cannot be asserted, the ecosystem is
   skipped with `build_system_unsandboxed`.
2. Do not execute host repo `gradlew` or allow repo wrapper downloads. Gradle
   extraction uses a trusted helper/tooling runtime shipped or pinned by Gimle.
3. Do not allow network access or automatic dependency/tool downloads during
   extraction. Any required helper must already exist in the runtime image or be
   preinstalled by an approved setup step.
4. Use a sanitized environment based on the `palace_mcp.git.command` pattern:
   minimal `PATH`, no inherited secrets, fixed `HOME`, no terminal prompts, and
   no user shell startup.
5. All subprocesses must have timeout, bounded stdout/stderr capture,
   process-group kill, and cleanup for child daemons. Gradle daemon cleanup is
   required when the helper starts a daemon.
6. Raw stdout/stderr is never persisted. Logs include only structured event
   names, sanitized tool version, duration, bounded counts, and redacted error
   categories.
7. Tool output samples are bounded and sanitized. Absolute host paths, env var
   values, command-line secrets, and raw Bazel command lines are redacted before
   models or logs see them.
8. Hostile fixtures must cover env leak attempts, hanging configuration,
   wrapper download attempts, absolute path emission, Bazel command-line
   leakage, timeout, and cancellation cleanup.

## 6. Tool Output Contracts

Implementation must define versioned parser contracts before graph writing:

- **Gradle v1:** trusted JVM helper JSON contract. Required fields: root path,
  Gradle version, projects, tasks, task owner project, static cacheable flag
  when available, and explicit task dependencies when available. Host repo
  wrapper execution is forbidden.
- **SwiftPM v1:** JSON from
  `swift package dump-package --type json --package-path <root>`. Required
  fields: package name, tools version if available, products, targets, target
  dependencies, resources, and settings when present.
- **Bazel v1:** `bazel query` target labels plus
  `bazel aquery --output=jsonproto` actions. `--output=textproto` may be
  parsed only as a fallback. Persisted facts must not include raw command lines;
  intermediate action inputs/outputs stay as bounded `inputs_sample` and
  `outputs_sample` on `BuildTask`.

The Step 2 tooling + security spike must produce reviewer-approved output
contracts and sandbox/preflight proof before Step 3 or any production extractor
code starts.

## 7. Data Model

### `BuildSystemSnapshot`

One detected build root, or detected-but-skipped build candidate, for one
project/ecosystem at one commit. A mono-repo with three independent Swift
packages creates three SwiftPM snapshots, not one project-wide SwiftPM
snapshot.

- `id`
- `group_id`
- `project`
- `ecosystem`: `gradle`, `swiftpm`, or `bazel`
- `commit_sha`
- `build_root_path`: repo-relative POSIX path
- `build_root_id`: stable hash of `group_id`, `project`, `ecosystem`,
  `build_root_path`, and `commit_sha`
- `snapshot_state`: `extracted` or `skipped`
- `tool_name`
- `tool_version`
- `schema_version`
- `target_count`
- `task_count`
- `product_count`
- `configuration_count`
- `skip_reasons`

For detected-but-skipped build roots/candidates, write a zero-count snapshot
with `snapshot_state="skipped"`, `target_count=0`, `task_count=0`,
`product_count=0`, `configuration_count=0`, and non-empty `skip_reasons`.
This is the persistence target for missing tools, unsandboxed execution,
security preflight failures, unsupported tool output, and Bazel package markers
without an enclosing workspace root.

### `BuildTarget`

Build-level target/module identity. Examples: Gradle project `:shared`,
SwiftPM target `WalletCore`, Bazel label `//app:app`.

- `id`
- `group_id`
- `project`
- `ecosystem`
- `commit_sha`
- `build_root_path`
- `build_root_id`
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
- `build_root_path`
- `build_root_id`
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
evidence. `inputs_sample` and `outputs_sample` are bounded sanitized samples,
not complete artifact inventories.

### `BuildProduct`

Top-level product/output declared by the build system. Examples: SwiftPM
product, Gradle archive/product-like declared output, or Bazel requested target
output when it is a top-level deliverable. Bazel intermediate action outputs are
not `BuildProduct` nodes in v1; they remain bounded sanitized samples on
`BuildTask`.

- `id`
- `group_id`
- `project`
- `ecosystem`
- `commit_sha`
- `build_root_path`
- `build_root_id`
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
- `build_root_path`
- `build_root_id`
- `name`
- `configuration_kind`
- `owner_target_id`
- `attributes`
- `schema_version`

## 8. Matching And Identity Rules

1. All nodes are commit-aware. No build graph edge may cross commit boundaries.
2. IDs must be deterministic across identical fixture runs.
3. `schema_version` is deliberately excluded from stable node IDs. It remains a
   property for parser/schema interpretation. Future migrations that require ID
   forking must make that a new explicit spec decision.
4. Repo-relative paths use POSIX separators and must not be absolute.
5. Same label/path from different ecosystems is not deduplicated.
6. Same target/task name from two build roots in the same repo is not
   deduplicated. `build_root_path` is part of every child node ID.
7. Gradle project paths (`:`, `:app`, `:shared`) and task paths
   (`:app:assembleDebug`) are canonical keys.
8. SwiftPM package/target/product names are canonical keys within the package
   root.
9. Bazel labels are canonical keys and must preserve repository/package/target
   identity.
10. If parser output cannot determine a relationship exactly, skip the edge with
   a metric. Do not infer target/task dependencies from name substrings.
11. Build schema constraints/indexes are extractor-local via
    `BaseExtractor.constraints` and `BaseExtractor.indexes`. Do not add Build*
    constraints to `foundation/schema.py` unless a later reviewer explicitly
    approves a shared global schema need.

## 9. Affected Areas After Approval

Expected implementation paths:

- `services/palace-mcp/src/palace_mcp/extractors/build_system/`
- `services/palace-mcp/src/palace_mcp/extractors/registry.py`
- `services/palace-mcp/tests/extractors/unit/test_build_system*.py`
- `services/palace-mcp/tests/extractors/integration/test_build_system_integration.py`
- `services/palace-mcp/tests/extractors/fixtures/build-system-mini-project/`
- `docs/runbooks/build-system.md`

Potential helper paths if the approved implementation needs subprocess
fixtures or a JVM helper:

- `services/palace-mcp/src/palace_mcp/extractors/build_system/tooling/`
- `services/palace-mcp/tests/extractors/fixtures/build-system-tool-output/`
- `docs/research/2026-05-06-build-system-tooling-security-spike/`

Implementation must avoid edits to `dependency_surface` unless a tiny shared
manifest-walk helper is explicitly approved during review.
Implementation must avoid edits to `foundation/schema.py` unless reviewer
approval changes the schema ownership decision.

## 10. Acceptance Criteria

1. `build_system` is registered and runnable through the existing extractor
   runner.
2. Minimal fixture creates one `BuildSystemSnapshot` per detected build root per
   ecosystem per commit.
3. Gradle fixture creates multiple `BuildTarget` nodes and `BuildTask` nodes.
4. SwiftPM fixture creates `BuildTarget` and `BuildProduct` nodes with target
   dependency edges.
5. Bazel fixture path either creates action/target facts from committed
   machine-readable output or proves structured skip behavior when Bazel is not
   available.
6. Snapshot/target/task/product/configuration IDs are deterministic across two
   identical fixture runs.
7. No `ExternalDependency` nodes are created or mutated by this extractor.
8. No compile/test/package task, codegen task, or Bazel execution action is
   executed during extraction.
9. No build graph edge crosses commit boundaries.
10. Missing external tools produce structured skip metrics and partial success
    when other ecosystems are present; each detected-but-skipped build
    root/candidate has a persisted zero-count `BuildSystemSnapshot`.
11. Bazel `BUILD` / `BUILD.bazel` package markers without an enclosing
    `MODULE.bazel` / `WORKSPACE(.bazel)` produce
    `bazel_workspace_root_unresolved` skip snapshots.
12. Security fixtures cover env leak, hanging config, wrapper download attempt,
    absolute path emission, Bazel command-line leakage, timeout, and cleanup.
13. Schema constraints/indexes are declared extractor-local, not in global
    `foundation/schema.py`.
14. Runbook includes Neo4j queries for snapshots, targets, tasks, products,
    dependency edges, no external-dependency writes, and no cross-commit edges.
15. Targeted unit/integration tests and lint/typecheck pass.

## 11. Verification Plan

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

MATCH (s:BuildSystemSnapshot {snapshot_state: 'skipped'})
RETURN s.ecosystem, s.build_root_path, s.skip_reasons;

MATCH (s:BuildSystemSnapshot)-[:DECLARES_BUILD_TARGET]->(t:BuildTarget)
RETURN s.ecosystem, count(t) AS targets;

MATCH (target:BuildTarget)-[:OWNS_BUILD_TASK]->(task:BuildTask)
RETURN count(*) AS target_tasks;

MATCH (target:BuildTarget)-[:DECLARES_BUILD_PRODUCT]->(product:BuildProduct)
RETURN count(*) AS target_products;

MATCH (task:BuildTask)-[:PRODUCES_BUILD_PRODUCT]->(product:BuildProduct)
RETURN count(*) AS task_products;

MATCH (a)-[r:BUILD_TARGET_DEPENDS_ON|TASK_DEPENDS_ON]->(b)
WHERE a.commit_sha <> b.commit_sha
RETURN count(r) AS cross_commit_edges;

MATCH (n:ExternalDependency)
RETURN count(n) AS external_dependency_count_after_build_system;
```

## 12. Open Questions

1. Should Gradle extraction require a small JVM helper in this repository, or
   should it invoke a checked-in init script/build action via a trusted Gradle
   runtime? Host repo wrapper execution is disallowed either way. The
   implementation plan treats this as Step 2 spike before code.
2. Should Bazel v1 be pure fixture/parser support until a real Bazel project is
   present, or should CI install/use Bazel for an executable integration test?
3. How much Gradle variant/flavor detail is required for the first UW query?
   v1 should reject broad Android variant modeling unless the operator names a
   concrete query.
4. Should `BuildTarget` later link to source `:Module` nodes if/when module
   ownership facts exist? v1 stores build targets independently and avoids
   guessing.

## 13. Followups

- #42 Build Reproducibility: annotate `BuildTask.cacheable_verified` and
  runtime cache-hit evidence.
- Android variant matrix expansion if product flavor/build type queries become
  first-class.
- Xcode `.xcodeproj` / `.xcworkspace` graph extraction if UW-iOS build questions
  require it.
- External dependency join from `BuildTarget` to GIM-191 `ExternalDependency`
  once a concrete query needs target-level dependency answers.
