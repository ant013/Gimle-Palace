# GIM-184 - iOS C/C++/Obj-C extractor via scip-clang - Spec

**Status:** Operator-review spec draft, 2026-05-03.
**Issue:** GIM-184 (`e92ed4c3-6b7f-4d72-ab1c-c16bc70ae89e`).
**Branch:** `feature/GIM-184-ios-clang-extractor`.
**Base:** `develop@365c9c42233ad125728f27048101a01e4899d2cf`.
**Plan:** `docs/superpowers/plans/2026-05-03-GIM-184-ios-clang-extractor.md`.
**Predecessor:** GIM-128 Swift extractor is closed and merged.

## Goal

Add `symbol_index_clang`, a palace-mcp symbol extractor for iOS native C, C++, and Objective-C code using Sourcegraph `scip-clang`.

The extractor ingests pre-generated SCIP protobuf files into the existing symbol-index substrate, following the GIM-128 Swift and Java/Kotlin three-phase pattern:

1. `phase1_defs` - definitions and declarations.
2. `phase2_user_uses` - user-code references above the configured importance threshold.
3. `phase3_vendor_uses` - dependency/vendor references.

Objective-C support is a hard smoke gate, not an assumption. `scip-clang` officially documents C, C++, and CUDA support plus JSON compilation database input; it does not promise Objective-C as a first-class language. Therefore GIM-184 must prove `.m` quality on iMac before implementation starts. If `.m` output is missing or low quality, v1 narrows to C/C++ and Objective-C becomes a documented follow-up.

`.mm` files are not a separate product scope. They are treated only as an optional Obj-C/C++ interop probe if the smoke fixture can index them cleanly.

## Background

GIM-128 added the Swift extractor and a custom Swift emitter because no first-party `scip-swift` exists. C/C++ is different: `scip-clang` exists and is mature enough to try before building anything custom. This slice should reuse palace-mcp's existing SCIP parser, `FindScipPath`, Tantivy bridge, checkpointing, circuit-breaker, and extractor registry patterns.

Known scip-clang constraints that shape this spec:

- It expects a JSON compilation database (`compile_commands.json`).
- It should be run from the project root.
- Large projects should start from a small compilation database and diagnostics before full indexing.
- Its symbol strings may contain an empty manager field.
- C++ descriptors may use backtick-escaped names, including operators.

## Assumptions

- The iMac Xcode/clang toolchain is sufficient for C/C++/Obj-C smoke even if it is too old for modern Swift emitter work.
- `scip-clang` can be installed or already exists on iMac without changing palace-mcp's runtime container.
- palace-mcp continues to ingest `.scip` files generated outside the container, consistent with Swift and Java/Kotlin extractor flow.
- Native source coverage is useful even if real UW-iOS itself is mostly Swift; Pods and adjacent iOS native dependencies still need symbol visibility.
- The implementation starts only after the iMac smoke produces evidence for the language set accepted into v1.

## Scope

### In Scope

- Parser support for `scip-clang` symbols, including empty manager fields and backtick-safe descriptor parsing.
- Language model additions for C, C++, and Objective-C.
- Optional `.mm` interop probe only if smoke proves stable output.
- `symbol_index_clang.py` registered in the extractor registry.
- Mixed native fixture containing app-level C/C++/Obj-C files and Pods/vendor native files.
- Unit tests for parser, language detection, qname canonicalization, and vendor/system classification.
- Integration tests proving IngestRun checkpoints and Tantivy search over native occurrences.
- iMac smoke evidence before implementation handoff.

### Out Of Scope

- Swift emitter changes.
- Multi-repo SPM bundle ingest (GIM-182).
- Custom clang emitter.
- Full call graph, data-flow, or macro expansion semantics beyond DEF/DECL/USE occurrences.
- Guaranteed `.mm` interop support.
- Storyboards, xib, Core Data models, asset/resource indexing.
- Production auto-deploy changes.

## Smoke Gates

Phase 1.1 must run before implementation and determines the final v1 language scope.

### Gate A - C

Input: tiny `.c` + `.h` fixture compiled by clang.

Pass:

- `scip-clang` emits a readable SCIP file.
- Parser sees at least one DEF/DECL and one USE in app-level C files.
- Relative paths are project-root relative.

Fail:

- C is not indexable on iMac. Stop and return to operator; do not implement.

### Gate B - C++

Input: tiny `.cpp` or `.cc` + `.hpp` fixture with a class/function and one operator or overloaded function when feasible.

Pass:

- `scip-clang` emits DEF/DECL and USE occurrences.
- Backtick/operator descriptors parse without qname corruption.

Fail:

- v1 may still proceed as C-only only if operator explicitly accepts. Default is stop and revise.

### Gate C - Objective-C

Input: tiny `.m` + `.h` fixture with an `@interface`, method definition, and call site.

Pass:

- `scip-clang` emits usable Objective-C symbols and references.
- Language is `objective-c` from document metadata or a safe `.m` extension fallback.
- Method identity is stable enough for Tantivy `search_by_symbol`.

Fail:

- v1 scope becomes C/C++ only.
- Spec and plan must document "Objective-C follow-up" before team handoff.

### Optional Probe - `.mm`

Input: tiny `.mm` file calling both Objective-C and C++ code.

Pass:

- Document as supported interop smoke evidence.

Fail:

- No v1 scope impact. `.mm` remains out of scope.

## Compilation Database Decision

Implementation cannot start until Phase 1.1 records the chosen iMac compilation database path.

Try candidates in this order:

1. **Manual mini fixture compdb** for smoke:
   - Commit a tiny native fixture.
   - Generate `compile_commands.json` directly for `.c`, `.cpp`, and `.m` commands.
   - This proves `scip-clang` and parser behavior without Xcode project noise.
2. **Bear around xcodebuild** for Xcode/Pods:
   - Run from project root.
   - Candidate command:
     `bear -- xcodebuild -workspace <Workspace>.xcworkspace -scheme <Scheme> -configuration Debug -sdk iphonesimulator build`
   - Use only if Bear works on iMac and captures clang invocations.
3. **Xcode build log extraction fallback**:
   - Capture `xcodebuild` clang commands and generate a reduced `compile_commands.json`.
   - Accept only if deterministic enough to document in `REGEN.md`.
4. **No Xcode compdb fallback**:
   - v1 ships the committed mini fixture and generic extractor only.
   - Real UW-iOS/Pads smoke becomes a follow-up issue.

`scip-clang` must be run from the project root with the selected compilation database. Full-project indexing must not be attempted before a reduced compdb produces clean diagnostics.

## Canonical qname Rule

The current parser applies GIM-105 Variant B:

`<scheme> <manager> <package-name> <version> <descriptors...>` -> `<package-name> <descriptors...>`

`scip-clang` may emit empty manager and placeholder package/version fields, e.g. `scip-clang  . . util/Formatter#toString().`.

For GIM-184 v1:

- Empty manager is valid and must not make parsing fail.
- Package placeholder `.` is accepted as project-local package.
- Canonical qname for project-local scip-clang symbols remains `. <descriptor-chain>` unless Phase 1.1 smoke proves a better stable package token is emitted by the installed `scip-clang`.
- If the team changes this rule, it must update `symbol_id_for` expectations and parser tests in the same PR.

Required tests:

- Empty manager qname.
- `.` package/version placeholder.
- Backtick-escaped descriptor with embedded spaces.
- C++ operator descriptor.

## Language Detection Policy

Language detection order:

1. SCIP `document.language` wins when present.
2. Safe extension fallback:
   - `.c` -> C
   - `.cc`, `.cpp`, `.cxx` -> C++
   - `.m` -> Objective-C, only if Gate C passes
   - `.mm` -> UNKNOWN unless optional probe passes and spec is revised
3. Header fallback:
   - `.h`, `.hh`, `.hpp`, `.hxx` must not be blindly assigned.
   - If SCIP document language is absent, classify header language as UNKNOWN unless the implementation has translation-unit context from the compilation database and tests prove it.

This avoids treating the same `.h` as C, C++, or Objective-C based only on extension.

## System And Vendor Policy

System SDK headers must not flood `phase1_defs`.

Rules:

- Exclude system SDK and toolchain paths entirely before phase selection:
  - `/Applications/Xcode.app/`
  - `/Library/Developer/`
  - SDK roots under Xcode platform directories
  - compiler builtin include paths
- Keep in-repo vendor/native dependency paths as vendor:
  - `Pods/`
  - `Carthage/`
  - `SourcePackages/`
  - `third_party/`
  - `Vendor/`
- Vendor USE occurrences go to `phase3_vendor_uses`.
- Vendor DEF/DECL occurrences must not enter user `phase1_defs`; either route them to a vendor-def path or exclude them from v1. The implementation must make this explicit in tests.

Default v1 choice: exclude system SDK entirely; include Pods/third-party as vendor.

## Affected Files

- `services/palace-mcp/src/palace_mcp/extractors/foundation/models.py`
- `services/palace-mcp/src/palace_mcp/extractors/scip_parser.py`
- `services/palace-mcp/src/palace_mcp/extractors/symbol_index_clang.py`
- `services/palace-mcp/src/palace_mcp/extractors/registry.py`
- `services/palace-mcp/tests/extractors/unit/test_scip_parser*.py`
- `services/palace-mcp/tests/extractors/unit/test_symbol_index_clang.py`
- `services/palace-mcp/tests/extractors/integration/test_symbol_index_clang_integration.py`
- `services/palace-mcp/tests/extractors/fixtures/uw-ios-clang-mini-project/`
- `docker-compose.yml` / `.env.example` only if new SCIP path wiring is required.

## Acceptance Criteria

- Phase 1.1 smoke evidence is posted to GIM-184 before implementation assignment.
- Final v1 language scope is explicitly set after smoke: either C/C++/Obj-C or narrowed C/C++.
- `symbol_index_clang` is registered and runnable through the extractor runner.
- Parser handles `scip-clang` empty-manager symbols and backtick descriptors without qname corruption.
- Language metadata follows the detection policy above; `.h` is not blindly classified.
- System SDK/toolchain headers do not inflate `phase1_defs`.
- App-level native and Pods/vendor native fixture files are both represented.
- Fixture ingest writes expected checkpoints for phases enabled by the final scope.
- Tantivy search can find at least one native symbol definition and one reference by `symbol_qualified_name`.
- Tests run from `services/palace-mcp` and pass for the targeted extractor slice.

## Verification Plan

### iMac Smoke

Run on iMac before implementation:

```bash
xcodebuild -version
clang --version
scip-clang --version
cd <native-mini-project-root>
cat compile_commands.json
scip-clang --compdb-path compile_commands.json --index-file scip/index.scip
```

Then parse role/language counts through palace-mcp:

```bash
cd services/palace-mcp
uv run python - <<'PY'
from collections import Counter
from palace_mcp.extractors.scip_parser import iter_scip_occurrences, parse_scip_file

idx = parse_scip_file("tests/extractors/fixtures/uw-ios-clang-mini-project/scip/index.scip")
occs = list(iter_scip_occurrences(idx, commit_sha="smoke", ingest_run_id="smoke"))
print("count", len(occs))
print("kind", Counter(o.kind.value for o in occs))
print("language", Counter(o.language.value for o in occs))
print("paths", sorted({o.file_path for o in occs})[:20])
PY
```

### Local MacBook Tests

Run after implementation:

```bash
cd services/palace-mcp
uv run pytest tests/extractors/unit/test_scip_parser_qname.py
uv run pytest tests/extractors/unit/test_scip_parser_language.py
uv run pytest tests/extractors/unit/test_symbol_index_clang.py
uv run pytest tests/extractors/integration/test_symbol_index_clang_integration.py
```

Before handoff:

```bash
cd services/palace-mcp
uv run ruff check src/palace_mcp/extractors tests/extractors
uv run mypy src
uv run pytest tests/extractors
```

## Risks

- Objective-C may not be usable through `scip-clang`; the smoke gate must narrow scope instead of hiding this.
- Xcode compilation database generation may be the largest unknown; manual fixture compdb is required as the first controlled step.
- Header documents may be ambiguous; default UNKNOWN is safer than incorrect language labels.
- SDK/system headers may produce too much data; they are excluded by default.
- Real UW-iOS native surface may live mostly in dependencies; fixture coverage is still required even if real-source smoke is deferred.

## Open Questions

- Which exact `scip-clang` version/source is pinned for iMac?
- Does the installed `scip-clang` emit useful `document.language` for `.m` files?
- Should vendor DEF/DECL occurrences be routed to a dedicated future phase, or excluded in v1?
