# GIM-756 Plan: Schema Linking Fix + ScopeTaggedWriter

## Goal

Make extractor Neo4j writes multi-tenant safe by introducing one scoped node-write chokepoint, deploying a database-side guard, migrating legacy `path` usage toward `file_path`, and proving that the known broken extractors write `group_id` consistently.

## Assumptions

- `ExtractorRunContext.group_id` is the canonical tenant scope passed from the runner into extractors.
- The issue body is authoritative for G0b because the referenced sprint spec path is not present in this checkout or `origin/develop`.
- This slice targets the 11 extractor families named in GIM-756; unrelated extractor cleanup is out of scope.
- Neo4j trigger deployment belongs with palace-mcp container/init infrastructure, not ad hoc production mutation.

## Acceptance Criteria

- `ScopeTaggedWriter` exists at `services/palace-mcp/src/palace_mcp/extractors/foundation/scope_tagging.py` with label allowlisting, required `group_id`, default group support, `path` to `file_path` aliasing, and `remove_legacy_path`.
- Unit tests cover at least: missing group rejection, label rejection, path alias dual-write, and legacy path removal.
- Neo4j init deploys the APOC `require_group_id` trigger while allowing `Bundle`, `Project`, `IngestRun`, and `IngestCheckpoint`.
- The 11 named extractor families write scoped nodes through `ScopeTaggedWriter`, including shared SCIP symbol index paths.
- A guard test enumerates extractor write paths and fails when a new extractor creates Neo4j nodes without the wrapper or explicit exemption.
- Migration script supports dry run, step 1 copy, step 3 cleanup, and rollback snapshot flow.
- Audit-V1 reads tolerate both `file_path` and legacy `path` during the deprecation window.
- Integration evidence shows bitcoin-core and evm-kit ingest counts remain tenant-isolated, Audit-V1 regression passes, and G0e dry-run reaches at least 13/15 testable extractors.

## Steps

1. Foundation writer and unit tests
   - Owner: `CXPythonEngineer`
   - Affected paths:
     - `services/palace-mcp/src/palace_mcp/extractors/foundation/scope_tagging.py`
     - `services/palace-mcp/tests/extractors/unit/test_scope_tagging.py`
   - Details:
     - Add `ALLOWED_LABELS` as a closed frozenset for the labels used by the G0b extractor set.
     - Implement `ScopeTaggedWriter.write_node(tx, label, props, *, group_id)` with constructor default group fallback.
     - Normalize `path` into `file_path`; keep dual-write by default; remove `path` when `remove_legacy_path=True`.
   - Check:
     - `uv run pytest services/palace-mcp/tests/extractors/unit/test_scope_tagging.py`

2. Refactor shared symbol index and SCIP writes
   - Owner: `CXPythonEngineer`
   - Depends on: Step 1
   - Affected paths:
     - `services/palace-mcp/src/palace_mcp/extractors/scip_parser.py`
     - `services/palace-mcp/src/palace_mcp/extractors/symbol_index_swift.py`
     - `services/palace-mcp/src/palace_mcp/extractors/symbol_index_python.py`
     - `services/palace-mcp/src/palace_mcp/extractors/symbol_index_typescript.py`
     - `services/palace-mcp/src/palace_mcp/extractors/symbol_index_java.py`
     - `services/palace-mcp/src/palace_mcp/extractors/symbol_index_solidity.py`
     - `services/palace-mcp/src/palace_mcp/extractors/symbol_index_clang.py`
     - matching unit/integration tests under `services/palace-mcp/tests/extractors/`
   - Details:
     - Prefer the smallest shared change in `scip_parser.py` if symbol node construction is centralized there.
     - Do not duplicate wrapper setup in each language extractor if one shared parser/writer path covers all symbol index extractors.
   - Check:
     - `uv run pytest services/palace-mcp/tests/extractors/unit/test_scip_parser*.py services/palace-mcp/tests/extractors/unit/test_symbol_index_*.py`

3. Refactor remaining broken extractor writers
   - Owner: `CXPythonEngineer`
   - Depends on: Step 1
   - Affected paths:
     - `services/palace-mcp/src/palace_mcp/extractors/git_history/neo4j_writer.py`
     - `services/palace-mcp/src/palace_mcp/extractors/code_ownership/neo4j_writer.py`
     - `services/palace-mcp/src/palace_mcp/extractors/coding_convention/neo4j_writer.py`
     - `services/palace-mcp/src/palace_mcp/extractors/error_handling_policy/extractor.py`
     - `services/palace-mcp/src/palace_mcp/extractors/testability_di/neo4j_writer.py`
     - `services/palace-mcp/src/palace_mcp/extractors/arch_layer/neo4j_writer.py`
     - `services/palace-mcp/src/palace_mcp/extractors/crypto_domain_model/extractor.py`
     - `services/palace-mcp/src/palace_mcp/extractors/hotspot/neo4j_writer.py`
     - `services/palace-mcp/src/palace_mcp/extractors/localization_accessibility/neo4j_writer.py`
     - `services/palace-mcp/src/palace_mcp/extractors/dependency_surface/neo4j_writer.py`
   - Details:
     - Preserve existing node identities and relationship write semantics.
     - Pass `ctx.group_id` through writer entry points instead of deriving scope from `project_id`.
   - Check:
     - Run the focused unit/integration tests for each touched extractor directory.

4. Add extractor write-path guard
   - Owner: `CXPythonEngineer`
   - Depends on: Steps 2-3
   - Affected paths:
     - `services/palace-mcp/tests/extractors/unit/test_scope_tagging_coverage.py`
   - Details:
     - Enumerate extractor source files that issue node-creating Cypher.
     - Fail if a non-exempt extractor writer creates nodes without `ScopeTaggedWriter`.
     - Keep explicit exemptions only for non-project labels allowed by GIM-756.
   - Check:
     - `uv run pytest services/palace-mcp/tests/extractors/unit/test_scope_tagging_coverage.py`

5. Neo4j trigger deployment
   - Owner: `CXInfraEngineer`
   - Depends on: Step 1
   - Affected paths:
     - palace-mcp Neo4j/container init files discovered by implementation
     - integration tests for schema/init if present
   - Details:
     - Add APOC `require_group_id` trigger from GIM-756.
     - Make deployment idempotent for repeated container starts.
     - Confirm the trigger rejects a created project-scoped node missing `group_id`.
   - Check:
     - Focused Neo4j init/schema test or a documented container smoke that creates one allowed node and one rejected node.

6. Migration and dual-read compatibility
   - Owner: `CXPythonEngineer`
   - Depends on: Step 1
   - Affected paths:
     - `paperclips/scripts/migrate_path_to_file_path.sh`
     - Audit-V1 fetch/query code that reads file paths
     - tests for migration command rendering and dual-read behavior
   - Details:
     - Implement `--dry-run`, `--apply-step-1`, `--apply-step-3`, and `--rollback-snapshot`.
     - Use `apoc.periodic.iterate` with 1000-row batches over `Symbol|File|Function|Module`.
     - Backport reads to `coalesce(n.file_path, n.path)` during the 30-day dual-read window.
   - Check:
     - Script dry-run test or shell test plus focused Audit-V1 query/fetcher tests.

7. Tenant isolation and regression verification
   - Owner: `CXQAEngineer`
   - Depends on: Steps 2-6
   - Affected paths:
     - integration tests or smoke scripts under `services/palace-mcp/tests/` and `paperclips/scripts/tests/`
   - Details:
     - Ingest bitcoin-core and evm-kit in the same Neo4j instance.
     - Compare `MATCH (n:Function {group_id:"project/bitcoin-core"}) RETURN count(n)` against the single-kit bitcoin-core count.
     - Re-run bitcoin-core full ingest and G0e verification matrix dry-run.
     - Run Audit-V1 e2e regression suite.
   - Check:
     - QA evidence comment includes exact commands and output summaries for tenant isolation, G0e dry-run >=13/15, and Audit-V1 regression.

## Review Gates

- Phase 1.2: `CXCodeReviewer` validates this plan before implementation starts.
- Phase 3.1: `CXCodeReviewer` performs mechanical review with `uv run ruff check`, `uv run mypy src/`, focused/full pytest evidence as appropriate, and `gh pr checks`.
- Phase 3.2: `CodexArchitectReviewer` performs adversarial review focused on defense-in-depth, schema compatibility, and migration safety.
- Phase 4.1: `CXQAEngineer` performs live smoke and posts concrete evidence.
- Phase 4.2: `CXCTO` merges only after CR approval, architect review resolution, QA PASS, and green required checks.

## Branch and PR

- Branch: `feature/GIM-756-schema-linking-scope-tagged-writer`
- PR target: `develop`
- PR body must reference this plan file and include a `## QA Evidence` block.

