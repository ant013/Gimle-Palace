# GIM-1690 Plan: incremental symbol_index_swift Neo4j layer

Grounded in `origin/develop` at `236d9c265c3e75c7e8e169f516eab9442440ef74`.
Authoritative spec: `docs/superpowers/specs/2026-06-20-incremental-update-orchestration.md`
Phase 1 and sections 1, 1.1, 1.2, 2, 5, and 6.

## Goal

Make `symbol_index_swift` update Neo4j file-scoped when
`PALACE_INCREMENTAL_INGEST` is enabled and the changed ratio is below the
existing full-reprocess threshold, while preserving prune/dead-code correctness.

## Assumptions

- Implementation branch: `feature/GIM-1690-incremental-symbol-index-swift-neo4j`
  cut from `origin/develop`; PR targets `develop`.
- Review lane is codex-only: `CXCodeReviewer` -> `CodexArchitectReviewer` ->
  `CXQAEngineer` -> `CXCTO`.
- No implementation starts until this plan passes plan-first review.
- Full reprocess behavior remains the fallback for initial runs, unchanged runs,
  truncated/unsafe change detection, and `changed_ratio >= 0.8`.
- `group_id` is the isolation boundary for every Neo4j write, bump, prune, and
  stale-delete query.

## Acceptance Criteria

- AC-1: Incremental Neo4j symbol writes process only changed plus added source
  files; unchanged files are not re-MERGEd, and SCIP symbol-info iteration is
  filtered before `seen_qnames` is built.
- AC-2: B1-a liveness bump updates still-live, unchanged symbols for the current
  `group_id` with `CALL { ... } IN TRANSACTIONS OF 10000`, and schema ensures an
  index on `(:Symbol group_id, last_seen_in_run_id)`.
- AC-3: Removed files are soft-deleted/deprecated without deprecating unchanged
  files.
- AC-4: B6 stamps `last_seen_in_run_id` on `REFERENCES`, `CONFORMS_TO`,
  `EXTENDS`, and `EXTENSION_OF`, then deletes stale relationships scoped to
  changed-source files.
- AC-5: `dead_code` graph loading ignores soft-deleted and `:Deprecated`
  symbols and does not traverse relationships from/to those symbols.
- AC-6: `prune_swift_symbols` threshold denominator excludes `:Deprecated`
  nodes.
- AC-7: P1-TC-01 through P1-TC-14 and prune threshold boundary tests are mapped
  to concrete tests and pass locally before the PR is handed to review.

## Work Plan

1. [ ] Establish TDD baseline and branch hygiene.
   - Owner: `CXPythonEngineer`.
   - Files: `services/palace-mcp/tests/extractors/integration/test_symbol_index_swift_integration.py`,
     `services/palace-mcp/tests/extractors/unit/test_symbol_index_swift.py`,
     `services/palace-mcp/tests/extractors/unit/test_symbol_node_writer.py`,
     `services/palace-mcp/tests/extractors/prune_swift_symbols/test_cypher.py`,
     `services/palace-mcp/tests/extractors/unit/test_dead_code_swift_contract.py`.
   - Acceptance: existing incremental integration test is rewritten to expect
     file-scoped Neo4j writes rather than the current full `nodes_written == 6`
     behavior; new failing tests cover B1, B6, dead_code filter, prune
     denominator, and unsafe fallback cases before implementation changes.
   - Verification: targeted pytest initially fails for the new assertions, then
     passes after later steps.

2. [ ] Derive the authoritative incremental change set.
   - Owner: `CXPythonEngineer`.
   - Files: `services/palace-mcp/src/palace_mcp/extractors/symbol_index_swift.py`
     and related unit tests.
   - Acceptance: `selected_paths` for incremental Neo4j is `changed + added`
     source paths from git/body-hash state intersected with SCIP paths; removed
     paths are tracked separately; SCIP-only generated/vendor/doc paths and
     truncated detection fall back to full instead of silently no-oping.
   - Verification: P1-TC-10, P1-TC-11, and P1-TC-12 pass in
     `test_symbol_index_swift.py`.

3. [ ] Scope symbol/shadow node refresh to changed and added files.
   - Owner: `CXPythonEngineer`.
   - Files: `services/palace-mcp/src/palace_mcp/extractors/symbol_index_swift.py`,
     `services/palace-mcp/src/palace_mcp/extractors/foundation/symbol_node_writer.py`.
   - Acceptance: `_refresh_graph_state` accepts an explicit changed-path scope;
     definition occurrence collection, shadow rows, symbol batches, and
     `seen_qnames` are built only from scoped SCIP data during incremental runs.
     Full runs keep current all-file behavior.
   - Verification: P1-TC-01, P1-TC-02, P1-TC-03, P1-TC-06, and P1-TC-09 pass in
     `test_symbol_index_swift_integration.py`; unit tests assert unchanged-file
     symbol infos are not passed to `write_symbol_nodes`.

4. [ ] Implement B1-a unchanged-symbol liveness bump and schema index.
   - Owner: `CXPythonEngineer`.
   - Files: `services/palace-mcp/src/palace_mcp/extractors/foundation/symbol_node_writer.py`,
     `services/palace-mcp/src/palace_mcp/extractors/foundation/schema.py`,
     affected schema tests.
   - Acceptance: after scoped symbol writes, a grouped, batched query sets
     `last_seen_in_run_id = $run_id` for live `:Symbol` nodes not just written,
     with `s.deleted_at IS NULL`, `NOT s:Deprecated`, and `s.group_id = $group_id`.
     Schema ensures `(group_id, last_seen_in_run_id)` lookup support.
   - Verification: P1-TC-01 and P1-TC-08 pass against real Neo4j; unit tests
     assert the B1 query contains `IN TRANSACTIONS`, `group_id`, `deleted_at IS
     NULL`, `NOT s:Deprecated`, and excludes just-written qualified names.

5. [ ] Handle removed files without global symbol soft-delete.
   - Owner: `CXPythonEngineer`.
   - Files: `services/palace-mcp/src/palace_mcp/extractors/symbol_index_swift.py`,
     `services/palace-mcp/src/palace_mcp/extractors/foundation/symbol_node_writer.py`,
     integration tests.
   - Acceptance: incremental runs soft-delete/deprecate symbols and `:File`
     nodes for removed paths only; zero-symbol files receive file liveness so
     prune does not remove them on the next run.
   - Verification: P1-TC-04, P1-TC-05, P1-TC-07, and P1-TC-14 pass in
     `test_symbol_index_swift_integration.py`.

6. [ ] Implement B6 relationship liveness and stale-delete.
   - Owner: `CXPythonEngineer`.
   - Files: `services/palace-mcp/src/palace_mcp/extractors/foundation/symbol_node_writer.py`,
     relationship writer tests, `test_symbol_index_swift_integration.py`.
   - Acceptance: all four `REFERENCES`-family MERGEs stamp
     `last_seen_in_run_id`; after changed-file relationship writes, stale
     relationships whose source file is in the changed set and whose run id is
     not current are deleted. The delete is `group_id` scoped through endpoint
     symbols.
   - Verification: P1-TC-13 passes against real Neo4j; unit tests assert each
     relationship query sets `last_seen_in_run_id` and stale-delete only targets
     `REFERENCES|CONFORMS_TO|EXTENDS|EXTENSION_OF`.

7. [ ] Fix dead_code loader and prune denominator correctness.
   - Owner: `CXPythonEngineer`.
   - Files: `services/palace-mcp/src/palace_mcp/extractors/dead_code/graph_loader.py`,
     `services/palace-mcp/src/palace_mcp/extractors/prune_swift_symbols/cypher.py`,
     `services/palace-mcp/tests/extractors/unit/test_dead_code_swift_contract.py`,
     `services/palace-mcp/tests/extractors/prune_swift_symbols/test_cypher.py`.
   - Acceptance: `_LOAD_SYMBOLS` and `_LOAD_EDGES` filter out `deleted_at IS NOT
     NULL` and `:Deprecated` symbols; prune `overall_total` excludes
     `:Deprecated`.
   - Verification: dead_code unit tests prove filtered symbols/edges are absent;
     T-B1 proves stale ratio `0.50` proceeds, T-B2 proves `0.51` aborts.

8. [ ] Final verification and PR handoff.
   - Owner: `CXPythonEngineer`.
   - Acceptance: PR body references this plan and includes a `## QA Evidence`
     placeholder for the later QA phase; no scope outside the listed files unless
     explicitly justified in the PR.
   - Verification from `services/palace-mcp`:
     - `uv run ruff check`
     - `uv run ruff format --check`
     - `uv run mypy src/`
     - `uv run pytest tests/extractors/unit/test_symbol_index_swift.py tests/extractors/unit/test_symbol_node_writer.py tests/extractors/unit/test_dead_code_swift_contract.py tests/extractors/prune_swift_symbols/test_cypher.py tests/extractors/integration/test_symbol_index_swift_integration.py`
     - `gh pr checks <PR>`

## Test Mapping

| Spec case | Test file | Required assertion |
|---|---|---|
| P1-TC-01 edit 1 file | `tests/extractors/integration/test_symbol_index_swift_integration.py` | unchanged symbols are not `:Deprecated` after prune |
| P1-TC-02 changed props updated | same | changed symbol `file_path`, line/doc key, and `last_seen_in_run_id` reflect run 2 |
| P1-TC-03 add file | same | new symbols appear and deprecated count is zero |
| P1-TC-04 delete file | same | removed file symbols and `:File` are deprecated; others stay live |
| P1-TC-05 git rename | same | old path deprecated, new path live, no duplicate qualified names |
| P1-TC-06 symbol moved | same | same qualified name updates to the new `file_path` |
| P1-TC-07 zero-symbol file | same | `:File.last_seen_in_run_id` is bumped for changed zero-symbol file |
| P1-TC-08 cross-project isolation | same | project A incremental run does not bump project B symbols |
| P1-TC-09 idempotency | same | same incremental run repeated produces zero net graph delta |
| P1-TC-10 changed ratio >= 0.8 | `tests/extractors/unit/test_symbol_index_swift.py` | full reprocess path is selected |
| P1-TC-11 SCIP-only generated/vendor doc | same | unsafe SCIP-only path triggers full fallback |
| P1-TC-12 detect_changes truncated | same | truncated/unsafe change set triggers full fallback |
| P1-TC-13 B6 edge hygiene | `tests/extractors/integration/test_symbol_index_swift_integration.py` plus `tests/extractors/unit/test_symbol_node_writer.py` | removed reference edge is deleted and no stale relationship remains |
| P1-TC-14 Tantivy/Neo4j consistency | `tests/extractors/integration/test_symbol_index_swift_integration.py` | removed-file path is absent from Tantivy and deprecated in Neo4j |
| T-B1/T-B2 prune boundaries | `tests/extractors/prune_swift_symbols/test_cypher.py` and `test_extractor.py` | 0.50 proceeds; 0.51 aborts |

## Handoff Sequence

1. CXCTO sends this plan to `CXCodeReviewer` for plan-first review.
2. If approved, `CXCodeReviewer` assigns implementation to the codex-side
   implementer for one PR from `feature/GIM-1690-incremental-symbol-index-swift-neo4j`.
3. Implementer opens the PR to `develop` and hands back to `CXCodeReviewer`
   with commit SHA, PR link, and exact command output.
4. Mechanical review hands to `CodexArchitectReviewer`, then to `CXQAEngineer`,
   then back to `CXCTO` for merge only after green CI and QA PASS.

## Risks

- A scoped Neo4j write without B1-a makes prune deprecate unchanged symbols; do
  not merge steps 2-3 without step 4.
- A scoped write without B6 stale-delete leaves stale `REFERENCES`-family edges
  and can create false-live dead_code results.
- `dead_code` schedule changes are out of scope for this issue; only the loader
  correctness filter ships here.
- If real Neo4j integration fixtures become too slow, reduce fixture size rather
  than replacing P1-TC-01, 04, 08, 13, or 14 with mocked-only tests.
