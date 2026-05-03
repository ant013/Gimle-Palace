# GIM-184 - iOS C/C++/Obj-C extractor via scip-clang - Plan

**Status:** Operator-review draft, 2026-05-03.
**Issue:** GIM-184 (`e92ed4c3-6b7f-4d72-ab1c-c16bc70ae89e`).
**Branch:** `feature/GIM-184-ios-clang-extractor`.
**Base:** `develop@365c9c42233ad125728f27048101a01e4899d2cf`.
**Predecessor:** GIM-128 Swift extractor is closed and merged; this plan reuses its SCIP parser, extractor, fixture, and Tantivy patterns.

## Goal

Ship `symbol_index_clang`, a palace-mcp extractor for iOS native C, C++, Objective-C, and Objective-C++ code using `scip-clang`.

This slice must cover both app-level native files (`.c`, `.cc`, `.cpp`, `.h`, `.hpp`, `.m`, `.mm`) and native vendor code under Pods/third-party paths. First smoke should run on the iMac before deeper implementation, because Obj-C/C++ indexing should not require the newer Swift/Xcode setup that blocked Swift.

## Assumptions

- `scip-clang` can run on the iMac host with the installed Xcode/clang toolchain, or can be installed there without changing the palace-mcp container image.
- `scip-clang` consumes a compilation database; the spike chooses the least-fragile way to generate `compile_commands.json` for Xcode projects.
- palace-mcp continues to ingest pre-generated `.scip` files inside the container, matching Swift/Java/Kotlin flow.
- C, C++, Obj-C, and Obj-C++ must remain separate languages in Tantivy metadata where SCIP or extension fallback can distinguish them.

## Scope

### In

- Add SCIP parser language support for C, C++, Obj-C, Obj-C++ documents.
- Add `symbol_index_clang.py` following the GIM-128 three-phase extractor shape: defs/decls, user uses, vendor uses.
- Add a mixed native fixture with app-level and Pods/vendor native sources.
- Add parser and extractor tests for scip-clang quirks: empty manager, backtick names, headers, mixed languages, and vendor classification.
- Add iMac-first smoke evidence for `scip-clang` on a tiny native project before implementation handoff.

### Out

- Swift emitter changes.
- Multi-repo SPM bundle ingest; that remains GIM-182.
- Custom clang emitter; v1 uses `scip-clang`.
- Full semantic call graph/data-flow beyond DEF/DECL/USE occurrences.
- Production deploy automation changes.

## Affected Areas

- `services/palace-mcp/src/palace_mcp/extractors/foundation/models.py`
- `services/palace-mcp/src/palace_mcp/extractors/scip_parser.py`
- `services/palace-mcp/src/palace_mcp/extractors/symbol_index_clang.py`
- `services/palace-mcp/src/palace_mcp/extractors/registry.py`
- `services/palace-mcp/tests/extractors/unit/`
- `services/palace-mcp/tests/extractors/integration/`
- `services/palace-mcp/tests/extractors/fixtures/uw-ios-clang-mini-project/`
- `docker-compose.yml` / `.env.example` only if a new SCIP path setting or mount is required.

## Acceptance Criteria

- `symbol_index_clang` is registered and runnable through the existing extractor runner.
- Parser handles valid `scip-clang` symbols with empty manager fields and backtick-escaped descriptor names.
- Tantivy occurrence documents preserve distinct language values for C, C++, Obj-C, and Obj-C++ where detectable.
- Fixture ingest writes non-zero phase checkpoints for `phase1_defs`, `phase2_user_uses`, and `phase3_vendor_uses`.
- App-level native and Pods/vendor native files are both represented in fixture assertions.
- Headers are indexed without duplicate-path explosions; duplicate header observations are documented if `scip-clang` emits them.
- iMac smoke evidence includes tool versions, compilation database generation, SCIP generation, and a minimal parse/role count.
- Local test evidence is posted before handoff to QA manager.

## Action Items

- [ ] Formalize this draft into the GIM-184 spec after operator review, including the exact `scip-clang` install/version decision.
- [ ] Run the first smoke on iMac: verify `xcodebuild -version`, `clang --version`, `scip-clang --version`, create a tiny `.m/.mm/.cpp/.h` project, generate `compile_commands.json`, emit `index.scip`, and inspect role/language counts.
- [ ] Choose and document the Xcode compilation database path: prefer the simplest reproducible flow that works on iMac; fall back to a committed mini fixture if real UW-iOS compilation database generation is too noisy for v1.
- [ ] Extend `Language` and `scip_parser` for C, C++, Obj-C, and Obj-C++ with extension fallback for `.c`, `.h`, `.hpp`, `.hh`, `.cc`, `.cpp`, `.cxx`, `.m`, and `.mm`.
- [ ] Add parser tests for scip-clang empty-manager symbols, C++ backtick/operator descriptors, mixed-language documents, and ambiguous headers.
- [ ] Implement `symbol_index_clang.py` by adapting the Swift/Java extractor shape and adding native vendor classification for `Pods/`, `Carthage/`, `SourcePackages/`, `third_party/`, generated build folders, and system SDK paths.
- [ ] Add `uw-ios-clang-mini-project` fixture with app-level C/Obj-C/Obj-C++ and Pods/vendor native files, plus `REGEN.md` and pre-generated `scip/index.scip`.
- [ ] Add unit tests for extractor batching, language tagging, vendor routing, and importance filtering.
- [ ] Add an integration test with Neo4j IngestRun checkpoints and Tantivy queries proving app/native and vendor occurrences are searchable.
- [ ] Run local MacBook tests after implementation: targeted unit tests, targeted integration tests, then the palace-mcp extractor slice.
- [ ] Post smoke and test evidence to GIM-184, then hand off via the standard Paperclip phase chain.

## Verification Plan

Initial iMac smoke:

```bash
xcodebuild -version
clang --version
scip-clang --version
# Generate compile_commands.json for the native mini project.
# Run scip-clang against it and write scip/index.scip.
# Parse index.scip with palace_mcp.extractors.scip_parser and print role/language counts.
```

Local MacBook tests after implementation:

```bash
uv run pytest services/palace-mcp/tests/extractors/unit/test_scip_parser*.py
uv run pytest services/palace-mcp/tests/extractors/unit/test_symbol_index_clang.py
uv run pytest services/palace-mcp/tests/extractors/integration/test_symbol_index_clang_integration.py
```

Full-ish extractor slice before handoff:

```bash
uv run ruff check services/palace-mcp/src/palace_mcp/extractors services/palace-mcp/tests/extractors
uv run mypy services/palace-mcp/src
uv run pytest services/palace-mcp/tests/extractors
```

## Risks

- **Compilation database generation is the likely blocker.** Mitigation: prove the iMac mini-project path first, before writing extractor code.
- **Header duplication can inflate occurrence counts.** Mitigation: add fixture assertions and document whether v1 deduplicates or accepts scip-clang output as-is.
- **Obj-C vs Obj-C++ language tagging may depend on document language quality.** Mitigation: use `doc.language` when present and extension fallback otherwise.
- **Real UW-iOS may currently be mostly Swift.** Mitigation: fixture must still cover app-level native and Pods/vendor native; real-source smoke can use any UW-adjacent native dependency available on iMac.

## Open Questions

- Which exact `scip-clang` distribution/version should be pinned for iMac and CI documentation?
- Should v1 add a dedicated `PALACE_SCIP_CLANG_PATH` setting, or reuse the generic SCIP path resolver keyed by project slug?
- Should real UW-iOS native smoke be a merge gate for GIM-184, or a follow-up if the mini fixture proves the extractor contract?
