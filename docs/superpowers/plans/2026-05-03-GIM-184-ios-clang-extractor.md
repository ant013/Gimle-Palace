# GIM-184 - iOS C/C++/Obj-C extractor via scip-clang - Plan

**Status:** Operator-review draft, 2026-05-03.
**Issue:** GIM-184 (`e92ed4c3-6b7f-4d72-ab1c-c16bc70ae89e`).
**Branch:** `feature/GIM-184-ios-clang-extractor`.
**Base:** `develop@365c9c42233ad125728f27048101a01e4899d2cf`.
**Spec:** `docs/superpowers/specs/2026-05-03-GIM-184-ios-clang-extractor.md`.
**Predecessor:** GIM-128 Swift extractor is closed and merged; this plan reuses its SCIP parser, extractor, fixture, and Tantivy patterns.

## Goal

Ship `symbol_index_clang`, a palace-mcp extractor for iOS native C, C++, and Objective-C code using `scip-clang`.

This slice must cover both app-level native files (`.c`, `.cc`, `.cpp`, `.h`, `.hpp`, `.m`) and native vendor code under Pods/third-party paths. First smoke must run on the iMac before deeper implementation, because Obj-C/C++ indexing should not require the newer Swift/Xcode setup that blocked Swift. `.mm` is an optional interop probe only, not a v1 promise.

## Assumptions

- `scip-clang` can run on the iMac host with the installed Xcode/clang toolchain, or can be installed there without changing the palace-mcp container image.
- `scip-clang` consumes a JSON compilation database; Phase 1.1 must record the exact iMac path for generating or committing `compile_commands.json`.
- palace-mcp continues to ingest pre-generated `.scip` files inside the container, matching Swift/Java/Kotlin flow.
- C, C++, and Obj-C must remain separate languages in Tantivy metadata where SCIP document language or safe extension fallback can distinguish them.

## Scope

### In

- Add SCIP parser language support for C, C++, and Obj-C documents.
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
- Parser handles valid `scip-clang` symbols with empty manager fields, package/version placeholders, and backtick-escaped descriptor names.
- Tantivy occurrence documents preserve distinct language values for C, C++, and Obj-C where smoke proves detection is safe.
- Objective-C is included in v1 only if `.m` smoke passes; otherwise v1 narrows to C/C++ and Obj-C becomes a follow-up.
- `.h` files are never blindly assigned to C/C++/Obj-C without SCIP document language or translation-unit context.
- System SDK/toolchain headers are excluded before phase selection so they cannot inflate `phase1_defs`.
- Fixture ingest writes non-zero phase checkpoints for `phase1_defs`, `phase2_user_uses`, and `phase3_vendor_uses`.
- App-level native and Pods/vendor native files are both represented in fixture assertions.
- Headers are indexed without duplicate-path explosions; duplicate header observations are documented if `scip-clang` emits them.
- iMac smoke evidence includes tool versions, compilation database generation, SCIP generation, and a minimal parse/role count.
- Local test evidence is posted before handoff to QA manager.

## Action Items

- [ ] Review and approve the GIM-184 spec, including the `scip-clang` install/version decision and final smoke-gated language scope.
- [ ] Run the first smoke on iMac: verify `xcodebuild -version`, `clang --version`, `scip-clang --version`, create tiny `.c/.cpp/.m/.h` projects, generate `compile_commands.json`, emit `index.scip`, and inspect role/language counts. Probe `.mm` only as optional interop evidence.
- [ ] Choose and document the compilation database path: manual mini fixture compdb first, then Bear around `xcodebuild`, then deterministic xcodebuild-log extraction, then fixture-only fallback.
- [ ] Extend `Language` and `scip_parser` for C, C++, and Obj-C with safe extension fallback for `.c`, `.cc`, `.cpp`, `.cxx`, and `.m`; keep headers UNKNOWN unless document language or TU context proves otherwise.
- [ ] Add parser tests for scip-clang empty-manager symbols, `.` package/version placeholders, C++ backtick/operator descriptors, mixed-language documents, ambiguous headers, and app/vendor same-descriptor collision behavior.
- [ ] Implement `symbol_index_clang.py` by adapting the Swift/Java extractor shape, excluding system SDK/toolchain paths before phase selection, and classifying `Pods/`, `Carthage/`, `SourcePackages/`, `third_party/`, and `Vendor/` as vendor.
- [ ] Wire fixture `.scip` files through `palace_scip_index_paths`; do not add a runtime `scip_path` runner override in v1.
- [ ] Add `uw-ios-clang-mini-project` fixture with app-level C/C++/Obj-C and Pods/vendor native files, plus `REGEN.md` and pre-generated `scip/index.scip`.
- [ ] Add unit tests for extractor batching, parser/extractor language tagging, path normalization, vendor routing, system SDK exclusion, and importance filtering.
- [ ] Add an integration test with Neo4j IngestRun checkpoints and Tantivy `search_by_symbol_id_async(symbol_id_for(qname))` queries proving app/native and vendor occurrences are searchable.
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
cd services/palace-mcp
uv run pytest tests/extractors/unit/test_scip_parser*.py
uv run pytest tests/extractors/unit/test_symbol_index_clang.py
uv run pytest tests/extractors/integration/test_symbol_index_clang_integration.py
```

Full-ish extractor slice before handoff:

```bash
cd services/palace-mcp
uv run ruff check src/palace_mcp/extractors tests/extractors
uv run mypy src
uv run pytest tests/extractors
```

## Risks

- **Compilation database generation is the likely blocker.** Mitigation: prove the iMac mini-project path first, before writing extractor code.
- **Header duplication can inflate occurrence counts.** Mitigation: add fixture assertions and document whether v1 deduplicates or accepts scip-clang output as-is.
- **Obj-C may not be first-class in `scip-clang`.** Mitigation: `.m` smoke is a hard gate; failed Obj-C smoke narrows v1 to C/C++.
- **Header language is ambiguous.** Mitigation: `doc.language` wins; otherwise `.h/.hh/.hpp/.hxx` stays UNKNOWN unless compile-command/TU context is proven.
- **SDK/system headers can explode phase1.** Mitigation: exclude system SDK/toolchain paths before phase selection.
- **Real UW-iOS may currently be mostly Swift.** Mitigation: fixture must still cover app-level native and Pods/vendor native; real-source smoke can use any UW-adjacent native dependency available on iMac.

## Open Questions

- Which exact `scip-clang` distribution/version should be pinned for iMac and CI documentation?
- Should v1 add a dedicated `PALACE_SCIP_CLANG_PATH` setting, or reuse the generic SCIP path resolver keyed by project slug?
- Should vendor DEF/DECL occurrences be routed to a dedicated future phase, or excluded in v1?
