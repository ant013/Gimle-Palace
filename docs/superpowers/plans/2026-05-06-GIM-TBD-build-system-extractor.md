# GIM-TBD - Build System Extractor - Implementation Plan

Plan source of truth:
`docs/superpowers/specs/2026-05-06-GIM-TBD-build-system-extractor.md`.

Implementation must not start until the spec and this plan are reviewed and
approved by the CX phase chain.

## Scope

In: extractor `build_system`, build graph foundation models, Gradle/SwiftPM/Bazel
parsers or tool-output adapters, deterministic IDs, graph writes, fixture,
tests, registry entry, and runbook.

Out: external dependency writes, runtime cache evidence, full Android variant
matrix, Xcode project graph extraction, public MCP/API tools, and executing
compile/test/package tasks.

## Phase Steps

### Step 1 - Plan-first review gate

Description: Review the spec for ownership boundaries with GIM-191 and #42,
schema shape, no-build-execution guarantee, and toolchain feasibility.

Acceptance criteria: CXCodeReviewer approves or requests changes; implementation
is not assigned before approval; reviewer confirms `ExternalDependency` remains
owned by GIM-191 and `cacheable_verified` remains owned by #42.

Suggested owner: CXCodeReviewer.

Affected paths:

- `docs/superpowers/specs/2026-05-06-GIM-TBD-build-system-extractor.md`
- this plan

### Step 2 - Tooling spike before production code

Description: Prove the narrow extraction commands/helpers for Gradle, SwiftPM,
and Bazel against tiny throwaway examples or committed tool-output fixtures.

Acceptance criteria:

- Gradle path can list projects/tasks without executing build tasks, or the
  spike recommends a scoped JVM helper with exact output contract.
- SwiftPM path can obtain products/targets/target dependencies from manifest
  JSON.
- Bazel path can parse `aquery`/`query` machine-readable output or documents
  skip behavior when Bazel is absent.
- Spike result is committed under `docs/research/` only if it changes the spec.

Suggested owner: CXPythonEngineer.

Affected paths: docs/research spike path if needed; no production extractor code.

Dependencies: Step 1.

### Step 3 - Fixture and expected graph truth

Description: Add `build-system-mini-project` with minimal Gradle, SwiftPM, and
Bazel/tool-output coverage.

Acceptance criteria:

- Fixture documents expected projects/targets/tasks/products/configurations.
- Fixture includes at least one target dependency and one task/product relation.
- Fixture can run in CI without requiring unavailable global tools, using
  committed machine-readable output where necessary.

Suggested owner: CXPythonEngineer.

Affected paths:

- `services/palace-mcp/tests/extractors/fixtures/build-system-mini-project/`
- optional `services/palace-mcp/tests/extractors/fixtures/build-system-tool-output/`

Dependencies: Step 2.

### Step 4 - Foundation models and schema

Description: Add build graph Pydantic models and Neo4j schema definitions.

Acceptance criteria:

- Models are frozen/typed and validate repo-relative paths.
- Constraints/indexes support deterministic MERGE and lookup by project,
  ecosystem, commit, and qualified name.
- Unit tests cover invalid paths, ID stability, and required fields.

Suggested owner: CXPythonEngineer.

Affected paths:

- `services/palace-mcp/src/palace_mcp/extractors/foundation/models.py`
- `services/palace-mcp/src/palace_mcp/extractors/foundation/schema.py`
- `services/palace-mcp/tests/extractors/unit/test_build_system_models.py`
- `services/palace-mcp/tests/extractors/unit/test_schema.py`

Dependencies: Step 3.

### Step 5 - Parser/adapters

Description: Implement narrow Gradle, SwiftPM, and Bazel parser/adapters that
produce normalized build graph records.

Acceptance criteria:

- Parsers do not infer relationships by substring matching.
- Missing tools produce structured skip records.
- Gradle and SwiftPM paths are covered by unit tests from fixture data.
- Bazel parser is covered by committed machine-readable sample output or a real
  executable fixture when available.

Suggested owner: CXPythonEngineer.

Affected paths:

- `services/palace-mcp/src/palace_mcp/extractors/build_system/parsers/`
- `services/palace-mcp/src/palace_mcp/extractors/build_system/models.py`
- `services/palace-mcp/tests/extractors/unit/test_build_system_*parser*.py`

Dependencies: Step 4.

### Step 6 - Neo4j writer and graph planning

Description: Convert normalized records into build graph nodes and edges with
commit-aware deterministic IDs.

Acceptance criteria:

- Writer MERGEs snapshots, targets, tasks, products, configurations, and edges.
- No `ExternalDependency` write query exists in the implementation.
- Re-running identical fixture produces zero net new nodes/edges where counters
  are available.
- Tests prove no cross-commit edges are planned.

Suggested owner: CXPythonEngineer.

Affected paths:

- `services/palace-mcp/src/palace_mcp/extractors/build_system/neo4j_writer.py`
- `services/palace-mcp/tests/extractors/unit/test_build_system_neo4j_writer.py`

Dependencies: Step 5.

### Step 7 - Extractor orchestration and registry

Description: Add `BuildSystemExtractor`, detect ecosystems, run adapters, write
graph facts, and register `build_system`.

Acceptance criteria:

- `palace.ingest.run_extractor(name="build_system", project=...)` works.
- Mixed-ecosystem projects return partial success when one optional ecosystem is
  skipped.
- No compile/test/package command is invoked.
- Registry tests include `build_system`.

Suggested owner: CXPythonEngineer.

Affected paths:

- `services/palace-mcp/src/palace_mcp/extractors/build_system/extractor.py`
- `services/palace-mcp/src/palace_mcp/extractors/build_system/__init__.py`
- `services/palace-mcp/src/palace_mcp/extractors/registry.py`
- `services/palace-mcp/tests/extractors/unit/test_build_system_extractor.py`
- `services/palace-mcp/tests/extractors/unit/test_registry.py`

Dependencies: Step 6.

### Step 8 - Integration test and runbook

Description: Add integration coverage and operator-facing runbook.

Acceptance criteria:

- Integration test verifies snapshot/target/task/product graph invariants.
- Integration test verifies no cross-commit edges.
- Integration test verifies `ExternalDependency` count is unchanged by this
  extractor.
- Runbook includes tool availability checks and direct Neo4j queries.

Suggested owner: CXPythonEngineer.

Affected paths:

- `services/palace-mcp/tests/extractors/integration/test_build_system_integration.py`
- `docs/runbooks/build-system.md`

Dependencies: Step 7.

### Step 9 - Phase 3.1 mechanical review

Description: Review implementation for scope adherence, correctness, tests, and
no silent scope reduction.

Acceptance criteria:

- CXCodeReviewer approves or requests changes.
- Reviewer pastes changed-file list.
- Reviewer confirms every changed path is declared in this plan or explicitly
  justified.
- Reviewer confirms no `ExternalDependency` writes and no runtime cache evidence.

Suggested owner: CXCodeReviewer.

Dependencies: Step 8.

### Step 10 - Phase 3.2 architecture review

Description: Challenge graph cardinality, target/task identity, toolchain
failure behavior, and future compatibility with #42.

Acceptance criteria:

- CodexArchitectReviewer approves or requests changes.
- Review explicitly covers BuildTask ownership, static `cacheable`,
  `cacheable_verified` deferral, and no-build-execution guarantee.

Suggested owner: CodexArchitectReviewer.

Dependencies: Step 9.

### Step 11 - Phase 4.1 QA smoke

Description: Run targeted tests plus a live smoke on at least one real Gradle or
SwiftPM project available on the operator machine.

Acceptance criteria:

- QA evidence includes tested commit SHA, targeted pytest output, extractor
  invocation, and direct Neo4j invariant queries.
- Required invariants: at least one snapshot, no cross-commit edges, no
  `ExternalDependency` writes, and no compile/test/package task execution.

Suggested owner: CXQAEngineer.

Dependencies: Step 10.

### Step 12 - Merge readiness and close

Description: Merge only after review and QA gates pass.

Acceptance criteria:

- CXCTO verifies PR state/checks before claiming merge readiness.
- Merge lands on `develop`.
- Roadmap is updated to mark #25 done or the existing roadmap sync branch is
  refreshed as part of the merge flow.

Suggested owner: CXCTO.

Dependencies: Step 11.

## Verification Commands

Targeted tests:

```bash
cd services/palace-mcp
uv run pytest tests/extractors/unit/test_build_system*.py -v
uv run pytest tests/extractors/integration/test_build_system_integration.py -v
```

Pre-review gate:

```bash
cd services/palace-mcp
uv run ruff check src/palace_mcp/extractors tests/extractors
uv run mypy src/
uv run pytest tests/extractors/unit/test_build_system*.py -v
uv run pytest tests/extractors/integration/test_build_system_integration.py -v
```

QA Cypher invariants:

```cypher
MATCH (s:BuildSystemSnapshot) RETURN s.project, s.ecosystem, count(*) AS snapshots;

MATCH (:BuildSystemSnapshot)-[:DECLARES_BUILD_TARGET]->(t:BuildTarget)
RETURN t.ecosystem, count(t) AS targets;

MATCH (:BuildSystemSnapshot)-[:DECLARES_BUILD_TASK]->(t:BuildTask)
RETURN t.ecosystem, count(t) AS tasks;

MATCH (a)-[r:BUILD_TARGET_DEPENDS_ON|TASK_DEPENDS_ON]->(b)
WHERE a.commit_sha <> b.commit_sha
RETURN count(r) AS cross_commit_edges;

MATCH (n:ExternalDependency)
RETURN count(n) AS external_dependency_count;
```

## Rollback / Backout

- Remove `build_system` from the registry to disable runtime entry.
- Delete only labels introduced by this slice for affected `group_id` and
  `commit_sha`: `BuildSystemSnapshot`, `BuildTarget`, `BuildTask`,
  `BuildProduct`, `BuildConfiguration`, and their build graph edges.
- Do not delete or mutate `ExternalDependency`, `PublicApiSurface`,
  `PublicApiSymbol`, hotspot, git history, or symbol index nodes.

## Review Risks

- Gradle Tooling API helper may expand scope into a Java build subsystem. Keep
  the helper narrow and JSON-output-only.
- Android variant modeling can balloon. v1 stores only cleanly exposed
  configurations and defers full matrix semantics.
- Bazel may be absent from CI/operator machines. Parser fixture plus structured
  skip is acceptable unless operator names a Bazel project.
- Static `cacheable` could be confused with runtime cache hits. Tests/runbook
  must preserve the distinction from #42.
