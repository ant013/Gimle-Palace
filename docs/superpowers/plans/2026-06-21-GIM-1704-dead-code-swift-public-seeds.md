# GIM-1704 Plan: dead_code Swift public seeds

Grounded in `origin/develop` at `80df1e1ad0e30793b834df3de4001f3d811f354c`.
Authoritative parent context: `docs/superpowers/specs/2026-06-20-incremental-update-orchestration.md`
section `1.2 dead_code liveness filter` and GIM-1702 Board evidence from
2026-06-21T12:57:09Z.

## Goal

Populate Swift symbol visibility data in the `:Symbol` records written by
`symbol_index_swift`, so `dead_code.seeds.identify_public_seeds` receives a
non-empty public/open root set on real `uw-ios-app` after re-indexing.

## Assumptions

- Implementation branch: `feature/GIM-1704-dead-code-swift-access-modifier`
  cut from `origin/develop`; PR targets `develop`.
- Scope is limited to Swift visibility/public-seed persistence and the tests
  proving dead_code consumes that data. Do not implement incremental dead_code.
- Current SCIP `SymbolInformation` has no explicit access/visibility field.
  The implementer should use a first-class IndexStoreDB visibility/access field
  if one is available; otherwise derive access from source declaration text at
  SCIP definition locations. That fallback is acceptable only if tests prove the
  persisted `access_modifier` drives `identify_public_seeds`.
- Existing dead_code liveness filters are present on `origin/develop`; this
  plan does not reopen that work.
- Review lane is codex-only: `CXCodeReviewer` ->
  `CodexArchitectReviewer` -> `CXQAEngineer` -> `CXCTO`.

## Acceptance Criteria

- AC-1: `symbol_index_swift` writes `access_modifier` values for Swift
  `:Symbol` rows when the declaration is `public` or `open`.
- AC-2: internal/private/fileprivate/package declarations remain non-public
  seeds by storing either `""` or their exact non-public modifier; the behavior
  must be explicit in tests.
- AC-3: `dead_code.seeds.identify_public_seeds` returns public/open Swift
  symbols after the SCIP-to-`:Symbol` row path, not only from hand-built
  `SymbolGraph` fixtures.
- AC-4: full dead_code no longer reaches the all-dead failure mode solely
  because public seed discovery is empty.
- AC-5: Board/QA receive concrete real-Neo4j verification commands for
  `uw-ios-app` re-indexing and seed-count validation.

## Work Plan

1. [ ] Confirm the visibility substrate and keep the implementation surgical.
   - Owner: `CXPythonEngineer`.
   - Files: `services/palace-mcp/scip_emit_swift/Sources/PalaceSwiftScipEmitCore/IndexStoreReader.swift`,
     `services/palace-mcp/scip_emit_swift/Sources/PalaceSwiftScipEmitCore/ScipEmitter.swift`,
     `services/palace-mcp/src/palace_mcp/extractors/scip_parser.py`.
   - Acceptance: there is a single documented source for Swift access data:
     either IndexStoreDB metadata emitted into SCIP-compatible data already
     available to Python, or a minimal Python-side source-line parser keyed by
     DEF file/line.
   - Verification: targeted unit test fails before the change for a public
     Swift fixture symbol whose `access_modifier` is currently `""`.

2. [ ] Persist Swift access into `:Symbol` rows.
   - Owner: `CXPythonEngineer`.
   - Files: `services/palace-mcp/src/palace_mcp/extractors/scip_parser.py`,
     `services/palace-mcp/src/palace_mcp/extractors/foundation/symbol_node_writer.py`.
   - Acceptance: `ScipSymbolInfo` and `build_symbol_node_rows` carry an
     `access_modifier` field, and `_MERGE_SYMBOLS` sets
     `s.access_modifier = r.access_modifier` instead of overwriting it with
     `""`.
   - Verification: `uv run pytest tests/extractors/unit/test_symbol_index_swift.py -k access_modifier`.

3. [ ] Prove dead_code seed selection consumes the persisted field.
   - Owner: `CXPythonEngineer`.
   - Files: `services/palace-mcp/tests/extractors/unit/test_dead_code_swift_contract.py`,
     `services/palace-mcp/tests/extractors/fixtures/scip_factory.py` if the
     existing fixture needs public/open/internal declarations.
   - Acceptance: the contract test round-trips Swift SCIP data through
     `iter_scip_symbol_infos` -> `build_symbol_node_rows` -> `_row_to_symbol`
     and asserts `identify_public_seeds` contains public/open symbols and
     excludes internal/private symbols.
   - Verification: `uv run pytest tests/extractors/unit/test_dead_code_swift_contract.py`.

4. [ ] Prove full dead_code no longer degenerates when public seeds exist.
   - Owner: `CXPythonEngineer`.
   - Files: `services/palace-mcp/tests/extractors/unit/test_dead_code_swift_contract.py`
     or the narrowest existing dead_code unit test file.
   - Acceptance: a fixture with one public/open entry symbol and one unreachable
     internal helper produces a non-empty seed set and does not classify the
     public/open entry as dead solely due to empty seed discovery.
   - Verification: targeted dead_code pytest from step 3 or the new narrow test.

5. [ ] Leave real-Neo4j Board/QA verification instructions.
   - Owner: `CXPythonEngineer`.
   - Files: PR body and/or a short note in this plan if the exact commands
     change during implementation.
   - Acceptance: instructions include re-running `symbol_index_swift` for
     `uw-ios-app`, counting non-empty `access_modifier` values, invoking
     `identify_public_seeds` or an equivalent dead_code path, and running full
     dead_code to confirm seed discovery is non-empty.
   - Verification: PR `## QA Evidence` contains the commands and expected
     invariants for `CXQAEngineer`.

## Verification

From `services/palace-mcp`:

- `uv run ruff check`
- `uv run ruff format --check`
- `uv run mypy src/`
- `uv run pytest tests/extractors/unit/test_symbol_index_swift.py -k access_modifier`
- `uv run pytest tests/extractors/unit/test_dead_code_swift_contract.py`

Board/QA real-Neo4j check after merge candidate deploy:

1. Re-run `symbol_index_swift` for `uw-ios-app`.
2. Query `MATCH (s:Symbol {group_id: <uw-ios-app group>}) WHERE coalesce(s.access_modifier, '') <> '' RETURN s.access_modifier, count(*)`.
3. Run the dead_code public-seed path and assert seed count is greater than 0.
4. Run full `dead_code` and assert the result is not the all-symbols-dead
   failure mode caused by empty seed discovery.

## Risks

- Standard SCIP does not model Swift access modifiers. If no IndexStoreDB
  visibility field is available, the source-line parser must stay deliberately
  narrow: declaration-leading `open`/`public` should be enough to unblock seeds,
  while unsupported syntax should fail closed as non-public.
- If implementation broadens into dynamic dispatch flags or incremental
  dead_code scheduling, the PR is out of scope for this prerequisite.
- Real `uw-ios-app` seed count can remain zero if the production SCIP/fixture
  contains no declaration text or no definition locations for public/open
  symbols; that is a blocker for Board, not a reason to mark all symbols alive.
