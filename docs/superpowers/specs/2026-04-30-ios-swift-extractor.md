> ⚠ **DEPRECATED 2026-05-01 — Superseded by [rev3](2026-04-30-ios-swift-extractor-rev3.md).** Phase 1.0 spike found SwiftSCIPIndex (community) unviable on Xcode 26: 0 symbols returned even on real UW-ios DerivedData (34245 records), and output format is non-canonical SQLite/JSON, not Sourcegraph SCIP protobuf. Operator approved pivot to **custom Swift emitter** (Option C) on 2026-05-01. See [Phase 1.0 spike findings](../../research/2026-05-01-swift-indexstore-spike.md) for evidence. This rev2 file is retained for historical context only.

# Slice 3 — iOS Swift extractor (`symbol_index_swift`)

**Status:** SUPERSEDED — Board draft (rev2, 2026-04-30); SwiftSCIPIndex approach failed Phase 1.0 spike, replaced by rev3.
**Revision history:**
- rev1 (2026-04-30) — initial draft from operator brainstorm Q1-Q5
- rev2 (2026-04-30) — operator review surfaced 7 issues; fixes: parser support claim corrected (parser is NOT lang-agnostic for Swift today — `_SCIP_LANGUAGE_MAP` lacks swift, `.swift` extension fallback absent); "максимум эффективности" mandate softened (Apple compile-time codegen visibility is Phase 1.0 unknown, not assumed); SwiftSCIPIndex risk re-balanced (Apple IndexStoreDB stable, but **community converter unproven** — biggest unknown); Xcode CLI-only assumption removed (full Xcode.app likely required for iOS Simulator builds — Phase 1.0 verifies); `~80 LOC copy-paste` revised to ~200-300 LOC across multiple files; AC#7 live-smoke threshold replaced from `nodes_written > 5000` to substantive criteria (named UW-ios symbols, language distribution, non-vendor DEF/USE, cross-file refs, low UNKNOWN); minor wording cleanups (removed "1:N ratio as Slice 1" leftover marketing); explicit gating: iMac toolchain setup may run parallel BUT successful real-project smoke is hard merge gate (no fabrication path).
**Predecessor merge:** `6492561` (GIM-127 Android scip-java validation merged 2026-04-30; spec rev3 pin policy and rev2 review-fix patterns inform this spec)
**Related:** GIM-127 Slice 1 Android (sibling pattern), GIM-126 find_references lang-agnostic fix (pending merge — affects AC#7 evidence script), GIM-105 rev2 (Q1 FQN cross-language decision — Swift entry).
**Roadmap context:** Slice 3 of 4 in operator-stack language coverage post-Solidity. Sequence: Slice 1 (Android Java/Kotlin) ✅ merged → Slice 2 (Android resources) deferred per `project_slice2_deferred_2026-04-30.md` → **Slice 3 (this — iOS Swift)** → Slice 4 (KMP bridge, after iOS).

## Goal

Add `symbol_index_swift` extractor to palace-mcp covering Swift code on iOS. Validate against real `unstoppable-wallet-ios` master via Apple's native IndexStoreDB → SCIP conversion path.

Unlike Slice 1 (Android), Sourcegraph has **no first-party scip-swift indexer** (no `sourcegraph/scip-swift` repo, not on npm, not in coursier `--contrib`). The Swift indexing path uses:
1. **Apple native IndexStoreDB** — generated automatically by `swiftc` and `clang` during `xcodebuild build` for Debug.
2. **`SwiftSCIPIndex`** (community, `Fostonger/SwiftSCIPIndex`, MIT, last commit 2026-01-05) — converts IndexStoreDB to SCIP protobuf format.
3. **palace-mcp's existing `scip_parser.py`** — supports per-document language detection (GIM-104) BUT **does not currently know Swift**: `_SCIP_LANGUAGE_MAP` (`scip_parser.py:209`) lacks `"swift"` key, and `_language_from_path` (`scip_parser.py:230`) lacks `.swift` extension fallback. **Required edits**: add `"swift": Language.SWIFT` to map + `.swift` (and possibly `.swiftinterface`) to path fallback. (`Language.SWIFT` enum value already exists at `models.py:32`.)

Apple-native IndexStoreDB tracks Swift compiler updates synchronously — that part is rock-solid. **The real unknown is `SwiftSCIPIndex` (community, 1⭐, single maintainer)** — its IndexStoreDB → SCIP mapping fidelity for modern Swift idioms (macros, property wrappers, Codable synthesis) has not been independently verified. Phase 1.0 spike validates this before PE Phase 2 starts.

The slice ships a **Hybrid SPM package + 1 Xcode app target fixture** (`uw-ios-mini-project`) with ~30 files exercising Swift core + modern idioms (SwiftUI, Combine, async/await) + Apple compile-time codegen (`@Observable` macro, Codable synthesis, property wrapper `$`-projection) + UIKit interop. Live-smoke runs the extractor against real `unstoppable-wallet-ios` master on operator's iMac.

## Sequence

```
Slice 1 (Android) ✅ merged @ 6492561
Slice 2 (Android resources) — deferred per 2026-04-30 strategy
Slice 3 (this — iOS Swift)
   ↓
deliverables:
   - new symbol_index_swift extractor (~80 LOC copy-paste from symbol_index_java runtime; reuses 101a foundation)
   - vendored fixture compiles + SwiftSCIPIndex emits valid index.scip
   - oracle-backed assertions on def/use/cross-target/AC#4 wide gate (3 of 3 generated-code targets)
   - real iOS project (UW-ios) registered + live-smoke
Slice 4 (KMP bridge) — after iOS Slice 3 merges
```

**Per-slice "максимум эффективности" mandate (qualified for Slice 3)**: ships full Swift **source-level** DEF+USE coverage for what `xcodebuild` IndexStoreDB + SwiftSCIPIndex actually expose. Apple's compile-time codegen (Codable synthesis, `@Observable` macro internals, property wrapper `$`-projection) **may or may not** appear as source-level symbols depending on SwiftSCIPIndex's mapping fidelity — Phase 1.0 spike empirically determines this and locks AC#4 branch (A/B-1/B-2). Slice does NOT promise generated-code coverage as a feature claim — only as a Phase 1.0 verification target.

## Hard dependencies

| Dependency | State |
|---|---|
| 101a foundation substrate (TantivyBridge, BoundedInDegreeCounter, ensure_custom_schema, …) | Stable, Slice 1 used it — REUSE |
| `scip_parser.py` per-document language detector (GIM-104) | **REUSE with required edits** — add `"swift": Language.SWIFT` to `_SCIP_LANGUAGE_MAP` (line 209) + `.swift` (and likely `.swiftinterface`) to `_language_from_path` (line 230). `Language.SWIFT` enum already exists at `models.py:32`. |
| Q1 FQN cross-language Variant B (GIM-105 rev2) | Locks Swift qualified_name format (see rev2 §Per-language action map) |
| `xcodebuild` for iOS targets | **Build host = operator's dev Mac (Apple Silicon, current macOS + Xcode)**. iMac is Intel x86_64 + macOS 13 + old Xcode (≤Swift 5.8) — **CANNOT build modern iOS Swift code** (UW master uses Swift 5.9+ with `@Observable` macros, iOS 17+ APIs). iMac upgrade infeasible (Apple dropped support for Intel-era macOS upgrades that meet current Xcode requirements). Fixture regen + real UW-ios indexing both happen on dev Mac; iMac receives pre-generated `index.scip` files for ingestion only. |
| **`SwiftSCIPIndex`** (community) | External binary. Build from source via `git clone https://github.com/Fostonger/SwiftSCIPIndex.git && swift build -c release`. SHA pinned per-regen in REGEN.md. |
| **XcodeGen** | `brew install xcodegen` — generates fixture's `.xcodeproj` from `project.yml` (deterministic, text-based) |
| `unstoppable-wallet-ios` clone on iMac | Operator clone @ master; SHA captured per-regen in REGEN.md |
| docker-compose bind-mount for `/repos/uw-ios:ro` | Add to `docker-compose.yml` |

## Architecture

### What's reused (no code changes)

| Component | Reuse status |
|---|---|
| 101a foundation substrate (schema bootstrap, TantivyBridge, eviction, circuit breaker, checkpoints) | Unchanged. |
| `scip_parser.iter_scip_occurrences()` | Unchanged. |
| 3-phase bootstrap pipeline | Unchanged — same `defs/decls → user_uses → vendor_uses` shape. |
| `palace.code.find_references` MCP tool | Unchanged in Slice 3 — depends on GIM-126 merge for cross-language operation. |
| `palace.ingest.run_extractor` MCP tool | Unchanged. |
| Existing Slice 1/2/4-language extractors (`symbol_index_python/typescript/java/solidity`) | Unchanged. |

### What's new

| Artefact | Description |
|---|---|
| `services/palace-mcp/src/palace_mcp/extractors/symbol_index_swift.py` | NEW extractor. **~150-200 LOC** — adapted from `symbol_index_java.py`, NOT pure copy-paste: rename literal `"java"` → `"swift"` in name/error-msgs/queries; replace `Language.JAVA` filter with `Language.SWIFT`; review primary-language logic for Swift-specific paths (e.g., handling `.swiftinterface` if needed); review error_code mappings; review vendor-noise filters (Swift's `.build`, `.swiftpm`, `Pods`, `Carthage`, `SourcePackages`, DerivedData paths differ from JVM `build/`). |
| `services/palace-mcp/src/palace_mcp/extractors/scip_parser.py` | **EDIT REQUIRED** — add `"swift": Language.SWIFT` to `_SCIP_LANGUAGE_MAP` (line 209) and `.swift` (and likely `.swiftinterface`) to `_language_from_path` (line 230). |
| `services/palace-mcp/src/palace_mcp/extractors/foundation/models.py` | NO EDIT — `Language.SWIFT = "swift"` already at line 32 (verified). |
| `services/palace-mcp/src/palace_mcp/extractors/registry.py` | Register new extractor: `EXTRACTORS["symbol_index_swift"] = SymbolIndexSwift()`. |
| `services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project/` | NEW vendored hybrid SPM+Xcode fixture, ~30 files. |
| `services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project/REGEN.md` | Vendor source pin (UW-ios SHA, SwiftSCIPIndex SHA), regen script doc, manual oracle table. |
| `services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project/regen.sh` | `xcodebuild build` + SwiftSCIPIndex extraction → `index.scip`. |
| `services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project/scip/index.scip` | Pre-generated SCIP binary, committed (~150-300 KB est.). |
| `services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project/LICENSE` | MIT, copy from upstream UW-ios. |
| `TestUwIosMiniProjectFixture` class in `services/palace-mcp/tests/extractors/unit/test_real_scip_fixtures.py` | NEW, ~14 oracle-backed assertions (Codable, @Observable macro, $-projection, cross-target USE pairs, qualified_name format, language=SWIFT). |
| `services/palace-mcp/tests/extractors/integration/test_symbol_index_swift_uw_integration.py` | NEW integration test (Slice 1 rev2 pattern: real fixture .scip + real Neo4j compose-reuse + Tantivy doc count oracle). |
| `services/palace-mcp/pyproject.toml` `[tool.pytest.ini_options].markers` | ADD `requires_scip_uw_ios: tests requiring uw-ios-mini-project/index.scip fixture`. |
| `docker-compose.yml` | ADD bind-mount `/Users/Shared/Ios/unstoppable-wallet-ios:/repos/uw-ios:ro`. |
| `.env.example` | Document `PALACE_SCIP_INDEX_PATHS` Swift slug (`"uw-ios": "/repos/uw-ios/scip/index.scip"`). |
| `CLAUDE.md` | NEW "Operator workflow: iOS Swift symbol index" subsection in §Extractors; project mount table extended with `uw-ios` row; non-iMac contributor override note (continued from Slice 1 rev2 pattern). |

### Toolchain pipeline

```
xcodebuild build -workspace UwMiniApp/UwMiniApp.xcworkspace -scheme UwMiniApp
        ↓
~/Library/Developer/Xcode/DerivedData/UwMiniApp-*/Index.noindex/  (Apple-native)
        ↓
SwiftSCIPIndex --derived-data <DerivedData path> --output ./scip/index.scip
        ↓
.scip protobuf (Sourcegraph-compatible)
        ↓
palace-mcp scip_parser.iter_scip_occurrences (lang-agnostic, recognizes Language.SWIFT)
        ↓
symbol_index_swift extractor → 3-phase bootstrap → Tantivy + Neo4j IngestRun
        ↓
operator can query via palace.code.find_references (post-GIM-126 merge)
```

Critical advantage over Slice 1 (Android): IndexStoreDB is generated by Apple's compiler infrastructure during normal `swift build`/`xcodebuild`. No separate compiler plugin (like semanticdb-kotlinc 0.5.0 we used for Android) — Apple does it natively. SwiftSCIPIndex is a standalone converter, not a compiler plugin — significantly less risk of toolchain version skew.

### Fixture layout

Path: `services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project/`

```
uw-ios-mini-project/
├── REGEN.md                             # vendor source pin (UW-ios SHA, SwiftSCIPIndex SHA), oracle table
├── regen.sh                             # xcodegen + xcodebuild + SwiftSCIPIndex
├── LICENSE                              # MIT, copy from UW-ios
├── .gitignore                           # .build/, DerivedData/, .swiftpm/, *.xcodeproj/
├── project.yml                          # XcodeGen config
├── scip/
│   └── index.scip                       # committed SCIP binary
│
├── UwMiniCore/                          # SPM package (~7 files)
│   ├── Package.swift                    # swift-tools-version: 5.9
│   └── Sources/UwMiniCore/
│       ├── Model/
│       │   ├── Wallet.swift             # Codable struct (AC#4 Codable target)
│       │   └── Transaction.swift        # Codable + nested types + enum with associated values
│       ├── State/
│       │   └── WalletStore.swift        # @Observable class (AC#4 macro target)
│       ├── Repository/
│       │   └── WalletRepository.swift   # async/await + property wrappers + generics
│       └── Util/
│           └── String+Hash.swift        # ⚡ VENDORED VERBATIM from UW-ios
│
└── UwMiniApp/                           # Xcode app target (~12 files)
    ├── UwMiniApp.xcodeproj/             # generated by XcodeGen during regen
    │   └── project.pbxproj              # NOT committed — regenerated
    ├── UwMiniApp.xcworkspace/           # for SPM-Xcode integration
    ├── Sources/
    │   ├── App/
    │   │   ├── UwMiniApp.swift          # @main App + Scene
    │   │   ├── AppDelegate.swift        # UIKit AppDelegate (UIKit interop, @MainActor)
    │   │   └── ContentView.swift        # SwiftUI root @ViewBuilder
    │   ├── Views/
    │   │   ├── WalletListView.swift     # SwiftUI + @State + observes WalletStore (AC#4 $-projection)
    │   │   ├── WalletDetailView.swift   # SwiftUI + @Binding + $projection
    │   │   ├── ChartViewRepresentable.swift  # UIViewRepresentable (UIKit↔SwiftUI bridge)
    │   │   └── ColorPalette.swift       # ⚡ VENDORED VERBATIM from UW-ios
    │   ├── Legacy/
    │   │   ├── LegacyWalletViewController.swift  # UIKit ViewController
    │   │   └── DateFormatters.swift     # ⚡ VENDORED VERBATIM from UW-ios
    │   └── Info.plist
```

**~30 файлов total** (target: 25-35 from D-tier scope). 3 vendored verbatim from UW-ios + ~27 synthesized in UW-ios style.

### Vendoring strategy (per Q4 brainstorm answer)

| Module / file | Source | Strategy |
|---|---|---|
| `LICENSE` | UW-ios root | Literal copy |
| `UwMiniCore/Util/String+Hash.swift` | UW-ios `UnstoppableWallet/.../Helpers/String+Hash.swift` (Phase 1.0 verifies path) | **VENDORED VERBATIM** — Foundation-only, standalone |
| `UwMiniApp/Views/ColorPalette.swift` | UW-ios `UnstoppableWallet/.../Theme/ColorPalette.swift` or equivalent | **VENDORED VERBATIM** — SwiftUI Color constants |
| `UwMiniApp/Legacy/DateFormatters.swift` | UW-ios `UnstoppableWallet/.../Util/DateFormatters.swift` | **VENDORED VERBATIM** — Foundation-only |
| `UwMiniCore/Model/{Wallet,Transaction}.swift` | UW-ios Codable patterns | SYNTHESIZED |
| `UwMiniCore/State/WalletStore.swift` | UW-ios @Observable patterns | SYNTHESIZED |
| `UwMiniCore/Repository/WalletRepository.swift` | UW-ios repository idioms | SYNTHESIZED |
| `UwMiniApp/App/*.swift` | UW-ios `@main App` patterns | SYNTHESIZED |
| `UwMiniApp/Views/{WalletListView,WalletDetailView,ChartViewRepresentable}.swift` | UW-ios SwiftUI/UIKit interop patterns | SYNTHESIZED |
| `UwMiniApp/Legacy/LegacyWalletViewController.swift` | UW-ios UIKit ViewController patterns | SYNTHESIZED |
| `project.yml` (XcodeGen) | hand-written | NEW |

**Vendor justification**: 3 of 30 truly vendored from real UW-ios; 27 synthesized in UW-ios idiom style. Synthesized portion gives controllable AC#4 generated-code targets (we know exactly what `@Observable` / Codable / property wrapper patterns to expect).

### Toolchain dependencies (one-time setup, like Slice 1's gradle/scip-java)

| Tool | Install | Why |
|---|---|---|
| Xcode CLI tools (`xcodebuild`) | `xcode-select --install` (default macOS) | Compile + IndexStoreDB generation |
| Swift toolchain ≥5.9 | Bundled in Xcode 15+ | macros support (Apple-bundled) |
| **XcodeGen** | `brew install xcodegen` | YAML → .xcodeproj |
| **SwiftSCIPIndex** | `git clone https://github.com/Fostonger/SwiftSCIPIndex.git && cd SwiftSCIPIndex && swift build -c release` | IndexStoreDB → SCIP converter |

iMac one-time setup ~10 min. Subsequent regens are `bash regen.sh` (5-10 min depending on Xcode build cache state).

## Architecture decisions

### From GIM-105 rev2 §Per-language action map — Swift (locked)

| Field | Swift |
|---|---|
| Manager token | `apple` (proxy for SwiftPM/Xcode; per Q1 decision) |
| Package format | `<bundle-id>` or `<module-name>` |
| Version token | `.` placeholder (Variant B strip) |
| Descriptor chain | Type `#`, method `().`, property `.` |
| Generics policy | `keep_brackets` |
| Qualified_name | `<module>:<descriptor-chain>` after Variant B strip |
| Local symbols | Skip function-body locals; store type members globally |

### Decisions resolved (rev1)

| Decision | Resolution |
|---|---|
| Fixture target structure | Hybrid SPM package (`UwMiniCore`) + 1 Xcode app target (`UwMiniApp`); app depends on package via local Package.swift reference. |
| Feature exercise depth | D-tier: Swift core + modern idioms + macros/Codable + UIKit interop. |
| Vendor strategy | B: 3-5 standalone vendored from UW-ios + ~27 synthesized in UW-ios style. |
| AC#4 conditional gate | B (wide): 3 of 3 generated-code targets visible — Codable synthesis + `@Observable` macro + property wrapper `$`-projection. |
| SwiftSCIPIndex install | Build from source on iMac (one-time `swift build -c release`); SHA pinned in REGEN.md. |
| XcodeGen vs commit `.xcodeproj` | XcodeGen — `project.yml` text-readable, `.xcodeproj` gitignored. |
| `index.scip` binary | Committed (existing pattern across all 5 prior fixtures). |
| Test marker | `requires_scip_uw_ios` — symmetric with `requires_scip_uw_android`. |
| `find_references` in AC#7 evidence | Conditional on GIM-126 merge (PR #70 OPEN). Fallback to `palace.memory.lookup`-style verification (Slice 1 pattern) until GIM-126 merges. |
| iMac SHA pin | Track UW-ios `master`; SHA captured per-regen in REGEN.md. |
| Process discipline (rev1) | Phase 4.1 evidence MUST include real run timestamps + Neo4j cypher transcripts (lessons from `feedback_pe_qa_evidence_fabrication.md`). CTO Phase 4.2 must cross-check evidence numbers against oracle constants before merge. |

## Non-goals (explicitly defer)

- ❌ **C/C++/Obj-C indexing** — UW-ios is pure Swift (per `find . -name "*.swift" | wc -l` = 1704 .swift, 0 C/C++/Obj-C/.mm). scip-clang is a separate slice if other UW repos (e.g., EvmKit dependencies) need it.
- ❌ **Other UW Swift repos** (`EvmKit.Swift`, `Eip20Kit.Swift`, `aa-swift`) — separate followup slices.
- ❌ **App Extensions** in fixture — UW-ios has IntentExtension + Widget; fixture has only main app target. Real UW-ios live-smoke exercises them implicitly through workspace build.
- ❌ **Swift Concurrency Sendable analysis** (`Sendable` conformance) — extractor-level, not language-level.
- ❌ **iOS 17+ macros beyond `@Observable`** (custom user macros) — fixture exercises only Apple-published macros.
- ❌ **Cross-language Swift↔ObjC bridges** — UW-ios doesn't use.
- ❌ **`palace.code.find_references` lang-agnostic fix for Swift** — tracked via GIM-126; out of this slice's code scope.

## Test strategy

| Test layer | File | Purpose |
|---|---|---|
| Unit (parser-level) | `services/palace-mcp/tests/extractors/unit/test_real_scip_fixtures.py` :: `TestUwIosMiniProjectFixture` | Parse committed `index.scip`; assert oracle counts + named symbols + cross-target USE pairs + qualified_name format + AC#4 wide gate. ~14 assertions. Skipped via `requires_scip_uw_ios` marker. |
| Integration (extractor end-to-end) | `services/palace-mcp/tests/extractors/integration/test_symbol_index_swift_uw_integration.py` | Real Neo4j (testcontainers/compose-reuse) + Tantivy. Run `symbol_index_swift` against the new fixture; assert IngestRun success, phase1+phase2 checkpoints, Tantivy doc count matches oracle ±2%. Imports `_UW_IOS_N_TANTIVY_DOCS` (post-dedup constant) like Slice 1's pattern. |
| Live-smoke (Phase 4.1, QAEngineer + operator on iMac) | Manual MCP tool calls + Cypher | Real UW-ios indexing: clone UW-ios @ master + xcodebuild + SwiftSCIPIndex + register_project + run_extractor. **Real timestamps + run_id + transcripts mandatory** (per fabrication-prevention discipline). |

Drift-check: regen UW-ios → `index.scip` differs → oracle counts must update. Pattern symmetric to Slice 1.

## Phase 1.0 spike requirements (mandatory, BEFORE PE Phase 2)

This is a **dedicated spike** — not a paper exercise. Operator (or designated agent) executes on dev Mac and posts findings before PE Phase 2 begins. Output is REGEN.md draft + AC#4 branch decision + go/no-go on the rest of the slice as currently specified.

### Toolchain pinning

- [ ] **Pin SwiftSCIPIndex SHA**: `cd ~/.local/opt/SwiftSCIPIndex && git rev-parse HEAD` → record in REGEN.md draft. If main branch changes during slice → re-pin or document divergence.
- [ ] **Capture dev Mac toolchain versions**: `sw_vers -productVersion` (macOS), `xcode-select -p`, `xcodebuild -version`, `swift --version` — record all in REGEN.md.
- [ ] **iMac Xcode/macOS confirmed too old to build UW master**: explicit baseline note in REGEN.md (rationale for Track A/B split).

### Generate raw SCIP fixture

- [ ] On dev Mac: build minimal 1-file Swift package or Xcode project with a Codable struct + `@Observable` class + `@State` SwiftUI view (smaller scope than full fixture; just enough for Phase 1.0 verifications).
- [ ] Run `xcodebuild build` then `SwiftSCIPIndex --derived-data ... --output spike.scip`.
- [ ] Verify spike.scip parses via `parse_scip_file()` (use existing `services/palace-mcp/src/palace_mcp/extractors/scip_parser.py`). Note: BEFORE adding Swift to language map, parser will return `Language.UNKNOWN` for these documents — that's expected.

### Verify `document.language` actual values

- [ ] Inspect `index.documents[i].language` for the spike Swift sources. Capture exact string (e.g., `"swift"`, `"Swift"`, `"swift_lang"` — SwiftSCIPIndex's specific value). Record in REGEN.md.
- [ ] Document the exact mapping needed in `_SCIP_LANGUAGE_MAP` (line 209 of scip_parser.py).

### Add Swift to scip_parser

- [ ] Edit `services/palace-mcp/src/palace_mcp/extractors/scip_parser.py`:
  - Line ~209 `_SCIP_LANGUAGE_MAP`: add `"<exact-string>": Language.SWIFT` (key = whatever SwiftSCIPIndex emits).
  - Line ~230 `_language_from_path`: add `if relative_path.endswith((".swift", ".swiftinterface")): return Language.SWIFT`.
- [ ] Run existing parser tests: `cd services/palace-mcp && uv run pytest tests/extractors/unit/test_scip_parser_*.py -v` — must still pass.
- [ ] Re-parse spike.scip — confirm Swift documents now have `Language.SWIFT`.

### AC#4 generated-code visibility check

For each of the 3 targets, query spike.scip for expected symbols:

- [ ] **Codable synthesis**: `grep init.from\\: spike.scip || python3 -c "<parser-based check>"` — observe presence/absence of `Wallet#init(from:)` and `Wallet#encode(to:)`.
- [ ] **`@Observable` macro**: query for `_$observationRegistrar`, `withMutation(keyPath:_:)`, `access(keyPath:_:)`. Document which (if any) appear.
- [ ] **Property wrapper $-projection**: SwiftUI `@State var foo: Int` should produce `_foo` storage and `$foo` projected — query both. Document presence.
- [ ] **Lock AC#4 branch**: A (all visible), B-1 (visible after workaround — try `-Xfrontend -emit-symbol-graph`, alternate SwiftSCIPIndex flags), or B-2 (not visible even with workaround). Record decision + rationale in REGEN.md draft.

### FQN format check (against GIM-105 rev2 expectations)

- [ ] Sample 3-5 Swift symbols from spike.scip. Compare actual `qualified_name` format against GIM-105 rev2 §Per-language action map — Swift entry: `<module>:<descriptor-chain>` after Variant B strip.
- [ ] If actual format diverges (e.g., manager token differs, or descriptors not as expected) → document in REGEN.md + propose either (a) accept actual format and update GIM-105 cross-reference, OR (b) post-process in extractor.

### Path-noise enumeration

Run real UW-ios `xcodebuild build` on dev Mac. Inspect the resulting DerivedData and `index.scip` for noise paths:

- [ ] List all top-level path prefixes that appear in `index.scip` documents (likely: `UnstoppableWallet/...`, `~/Library/Developer/Xcode/DerivedData/.../Index.noindex/.../`, `.build/...`, `.swiftpm/...`, `Pods/...`, `Carthage/...`, `SourcePackages/...`).
- [ ] For each prefix, classify as PROJECT (keep) or VENDOR (filter). Document in REGEN.md.
- [ ] Lock vendor-filter rules for `symbol_index_swift` extractor config.

### Effort and check-out

- [ ] Spike duration: ~0.75-1.5 days (operator-time on dev Mac).
- [ ] Output: REGEN.md draft + AC#4 branch + Swift parser-edit PR (small, separate from main slice PR — can merge first to develop) + go/no-go signal on PE Phase 2.
- [ ] If go: PE Phase 2 starts with locked oracle table + locked AC#4 branch + parser already supports Swift.
- [ ] If no-go (R1 surfaces fundamentally): spec rev3 with alternative path; PE Phase 2 deferred or re-scoped.

## Acceptance criteria

| AC# | Condition | Verification |
|---|---|---|
| AC#1 | Vendored fixture compiles | `xcodegen generate -s project.yml -p UwMiniApp/UwMiniApp.xcodeproj && xcodebuild build -workspace UwMiniApp/UwMiniApp.xcworkspace -scheme UwMiniApp -destination "generic/platform=iOS Simulator"` exit 0 |
| AC#2 | SwiftSCIPIndex emits valid `index.scip` | SwiftSCIPIndex run produces non-empty `index.scip`; parses via `parse_scip_file()` without exception |
| AC#3 | Oracle counts match (Phase 1.0 locked) | All assertions in `TestUwIosMiniProjectFixture` pass |
| **AC#4 (CONDITIONAL — Phase 1.0 gate, B-2 plausible)** | **Generated-code visibility branch locked before PE Phase 2** | Phase 1.0 spike checks each independently in `index.scip`:<br>(a) **Codable synthesis** — `Wallet#init(from:)` + `Wallet#encode(to:)` (compiler-emitted)<br>(b) **`@Observable` macro** — `WalletStore#_$observationRegistrar` / `withMutation(keyPath:_:)`<br>(c) **Property wrapper `$`-projection** — `_state` storage + `$state` projected on `@State`/`@Binding`<br><br>**Branch A** (best case): all 3 visible → AC#4 asserts presence of all.<br>**Branch B-1**: visible after workaround (e.g., `-Xfrontend -emit-symbol-graph`, IndexStoreDB include flag, alternate SwiftSCIPIndex SHA) → AC#4 asserts presence with workaround documented in REGEN.md.<br>**Branch B-2** (plausible): not visible even with workaround → AC#4 narrows to "Swift source-level symbols indexed correctly; generated-code visibility tracked as followup issue (proposed GIM-N+M)". Realistic outcome — Apple's IndexStoreDB exposure of compiler-internal symbols is undocumented and not part of public Swift symbol API. PE Phase 2 proceeds with B-2-narrowed scope; slice ships valid even if generated-code is invisible.<br><br>**No assumption that A or B-1 is the default.** Phase 1.0 is empirical. |
| AC#5 | Cross-target USE resolves — **5 USE pairs** | Tests:<br>• 1/5 **app→SPM**: `WalletListView.swift` USE `WalletStore` (`UwMiniCore`)<br>• 2/5 **app→SPM**: `WalletDetailView.swift` USE `Wallet` Codable struct (`UwMiniCore`)<br>• 3/5 **app→SPM**: `ChartViewRepresentable.swift` USE `Transaction` (UIKit interop ↔ SPM types)<br>• 4/5 **intra-SPM cross-package**: `WalletRepository.swift` USE `Wallet` + `Transaction`<br>• 5/5 **macro-generated→source**: `WalletStore`'s `withMutation(...)` generated body USE `_$observationRegistrar` (conditional on AC#4 Branch A). Skipped if Branch B-2. |
| AC#6 | All DEFs language=`SWIFT` | `WalletStore` + `Wallet` + `WalletListView` (3 representative DEFs) all have `occ.language == Language.SWIFT`. Requires `Language.SWIFT` enum value in `extractors/foundation/models.py` (verified Phase 1.0). |
| AC#7 | Integration test green | `tests/extractors/integration/test_symbol_index_swift_uw_integration.py` passes locally + on iMac. NEW pattern — real fixture .scip + real Neo4j (Slice 1 rev2 pattern). Test uses fixture's committed `.scip`; does NOT require iOS build on iMac. |
| **AC#7.5 (Phase 4.1 evidence — fixture-based, NOT raw threshold)** | Live-smoke demonstrates **fixture-based extractor pipeline works on iMac**; real UW-ios indexing **deferred** to operator's dev Mac as separate evidence | iMac live-smoke (gate for merge):<br>(a) `palace.ingest.run_extractor name=symbol_index_swift project=uw-ios-mini` against committed fixture `index.scip` (mounted at `/repos/uw-ios-mini`) → ok:true with real timestamps + run_id<br>(b) Tantivy doc counts per phase match fixture oracle ±2% (post-dedup constant `_UW_IOS_MINI_N_TANTIVY_DOCS` locked Phase 1.0)<br>(c) Cypher: IngestRun in Neo4j with success=true<br>(d) Language distribution: 100% SWIFT in fixture (controlled — if not, parser bug)<br><br>**Real UW-ios indexing as separate evidence** (deferred-not-blocked):<br>(e) Operator's dev Mac runs xcodebuild + SwiftSCIPIndex on real UW-ios master, generates `index.scip`, transfers to iMac mount, runs extractor with `project=uw-ios`. Evidence comment posted on slice followup-issue (proposed GIM-N+M).<br>(f) Real-source criteria (when run): ≥1000 DEFs from UW main paths (`UnstoppableWallet/UnstoppableWallet/.../`); ≥3 known named symbols (e.g., `WalletManager`, `MarketKit`); ≥10 cross-file USE refs; <5% UNKNOWN language. Excluded paths: `DerivedData/`, `.build/`, `Pods/`, `Carthage/`, `SourcePackages/`.<br><br>**Why split**: iMac (Intel + macOS 13 + old Xcode) cannot build modern Swift. Forcing real-UW-ios on iMac would require either (1) iMac upgrade (infeasible — Apple dropped Intel support), or (2) UW-ios SHA pin to pre-Swift-5.9 era (loses operator's interest in current UW master analysis). Solution: split — fixture-based merge gate + real-source as deferred operator-Mac evidence. |
| AC#8 | `docker-compose.yml` bind-mount added | 1 entry: `/Users/Shared/Ios/unstoppable-wallet-ios:/repos/uw-ios:ro`. |
| AC#9 | `.env.example` documented | `PALACE_SCIP_INDEX_PATHS={..., "uw-ios": "/repos/uw-ios/scip/index.scip"}` example shown. |
| AC#10 | CLAUDE.md updated | New "Operator workflow: iOS Swift symbol index" subsection + project mount table row + non-iMac override note (continuing Slice 1 rev2 pattern). |

### Phase 4.1 live-smoke evidence — TWO TRACKS (revised rev2)

**Track A — fixture live-smoke on iMac (MERGE GATE)**

This is the hard merge requirement. Demonstrates extractor pipeline works on iMac production palace-mcp.

```
[1] palace.ingest.list_extractors → returns existing list + symbol_index_swift (NEWLY added)
[2] palace.memory.register_project slug=uw-ios-mini → ok:true (fixture slug)
[3] Bind-mount fixture into container (docker-compose.yml addition; or copy fixture path):
    /Users/Shared/Ios/Gimle-Palace/services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project:/repos/uw-ios-mini:ro
[4] PALACE_SCIP_INDEX_PATHS includes {"uw-ios-mini":"/repos/uw-ios-mini/scip/index.scip"}
[5] palace.ingest.run_extractor name=symbol_index_swift project=uw-ios-mini
    → ok:true with REAL timestamps + run_id (mandatory; no fabrication path)
[6] Direct cypher verification (palace.memory.lookup does NOT support 'IngestRun' entity type):
    docker exec gimle-palace-neo4j-1 cypher-shell -u neo4j -p $NEO4J_PASSWORD \
      "MATCH (r:IngestRun {run_id:'<from-step-5>'}) RETURN r.success, r.started_at, r.finished_at"
[7] Phase counts via TantivyBridge.count_docs_for_run_async (Slice 1 pattern):
    expected: phase1_defs ≥ <oracle>, language_distribution = 100% SWIFT, ±2% drift
```

**Track B — real UW-ios live-smoke on operator's dev Mac (DEFERRED-NOT-BLOCKED)**

iMac (Intel x86_64 + macOS 13 + old Xcode ≤Swift 5.8) cannot build modern Swift code. Operator's dev Mac (Apple Silicon + current Xcode) is the only host that can build UW-ios master.

This evidence is captured as a **separate followup-issue** post-merge:

```
[1] On dev Mac:
    git clone https://github.com/horizontalsystems/unstoppable-wallet-ios.git
    cd unstoppable-wallet-ios
    git rev-parse HEAD                          # capture SHA
    date -u +%FT%TZ                             # capture timestamp BEFORE
    xcodebuild build -workspace UnstoppableWallet/UnstoppableWallet.xcworkspace \
                    -scheme UnstoppableWallet \
                    -destination "generic/platform=iOS Simulator"
    SwiftSCIPIndex --derived-data ~/Library/Developer/Xcode/DerivedData/UnstoppableWallet-* \
                  --output ./scip/uw-ios-master.scip
    date -u +%FT%TZ                             # capture timestamp AFTER
[2] Transfer to iMac: scp uw-ios-master.scip imac:/Users/Shared/Ios/unstoppable-wallet-ios-scip/
[3] Update iMac .env: PALACE_SCIP_INDEX_PATHS={..., "uw-ios":"/repos/uw-ios-scip/uw-ios-master.scip"}
[4] Add bind-mount in docker-compose.yml: /Users/Shared/Ios/unstoppable-wallet-ios-scip:/repos/uw-ios-scip:ro
[5] Restart palace-mcp on iMac
[6] palace.memory.register_project slug=uw-ios → ok:true
[7] palace.ingest.run_extractor name=symbol_index_swift project=uw-ios → real result with timestamps
[8] Substantive criteria (per AC#7.5 row "f"): ≥1000 main-source DEFs, ≥3 named UW symbols, ≥10 cross-file USE refs, <5% UNKNOWN
[9] (Post-GIM-126) palace.code.find_references qualified_name=WalletManager project=uw-ios → ≥3 USEs across distinct files
```

Track B is operator-Mac-bound and post-merge; this prevents iMac toolchain limitations from blocking the slice.

**Process discipline (per `feedback_pe_qa_evidence_fabrication.md`)**:
- Evidence MUST include real timestamps from `date -u` BEFORE/AFTER each major step
- Evidence MUST include `git rev-parse HEAD` output (UW-ios source SHA captured)
- Evidence MUST include actual `palace.ingest.run_extractor` response JSON, not paraphrased
- CTO Phase 4.2 review: **cross-check** numbers in evidence against any prior oracle/fixture constants — refuse merge if numbers exactly match a fixture/oracle constant
- QAEngineer (NOT PythonEngineer) authors the evidence section in PR body

## Risks

| # | Risk | Mitigation |
|---|---|---|
| **R1** ⚡ | **SwiftSCIPIndex output quality is THE primary unknown** — community 1⭐, single maintainer (`Fostonger`), last commit 2026-01-05. Apple's IndexStoreDB itself is solid; the COMMUNITY CONVERTER is what may misbehave. May crash on complex Xcode workspaces, skip generated code, output non-standard SCIP, mishandle modern Swift idioms. | **Phase 1.0 spike** (mandatory, before PE Phase 2 starts) runs end-to-end on fixture AND real UW-ios on dev Mac, captures actual `document.language` values, generated-code visibility, FQN format. Documents result in REGEN.md + locks AC#4 branch. If SwiftSCIPIndex fundamentally fails → spec rev3 with alternative path (e.g., manual IndexStoreDB walker, or wait for upstream, or write own). |
| **R2** ⚡ | **iMac CANNOT build modern iOS** (Intel x86_64 + macOS 13 + Xcode ≤Swift 5.8). UW master uses Swift 5.9+ macros, iOS 17+ APIs. Forcing iMac build = fail. iMac upgrade infeasible (Apple dropped Intel macOS upgrade path). | **Resolution (rev2)**: split Phase 4.1 into Track A (fixture-based on iMac, hard merge gate) + Track B (real UW-ios on operator's dev Mac, deferred-not-blocked, separate followup-issue evidence). Container ingests pre-generated `.scip` files regardless of build host — `.scip` is platform-portable. iMac role limited to palace-mcp runtime. |
| R3 | IndexStoreDB path varies by Xcode/macOS version | `regen.sh` uses `~/Library/Developer/Xcode/DerivedData/<scheme>-*/Index.noindex` glob. REGEN.md instructs operator to verify path on dev Mac (build host). |
| R4 | Swift compiler plugin / macro classpath skew between SwiftSCIPIndex's expected Swift version vs operator's dev Mac Xcode | Phase 1.0 captures dev Mac Xcode version + Swift version + SwiftSCIPIndex SHA. If skew → SwiftSCIPIndex rebuild from main branch OR pin to SwiftSCIPIndex SHA known-compatible with operator's Xcode. |
| R5 | XcodeGen — extra dependency on dev Mac (one-time `brew install xcodegen`) | Document in REGEN.md. Alternative (commit pre-generated `.xcodeproj`) is worse — `project.pbxproj` is unreadable mess. |
| R6 | fixture regen on dev Mac slower than Slice 1's gradle (~2-5 min vs 30-60s) | Acceptable; CI doesn't regen (committed `.scip`). PE waits for `regen.sh` on initial fixture build. |
| R7 | IndexStoreDB may emit compiler-internal symbols (mangled names like `$s4...`, `_$s...`) as noise | Phase 1.0 inspect — if noisy enough to skew oracle counts or pollute UI, filter in `symbol_index_swift` (path-based for `.swiftinterface` etc., name-based for mangled). Filter list documented in REGEN.md. |
| **R8** | Effort underestimate if R1/R2 surface significantly | Phase 1.0 spike catches ASAP. Buffer: PE 5-6d + 2-3d buffer = ~10-12d wall-clock. If Phase 1.0 reveals R1 fundamental → escalate to spec rev3 + scope reduction. |
| **R9** | Phase 4.1 evidence fabrication (Slice 1 GIM-127 incident — PE wrote oracle constants into PR body without running) | **Hardened (rev2)**: Track A fixture-based smoke includes Tantivy+Neo4j cypher transcripts; CTO Phase 4.2 cross-checks evidence numbers vs fixture oracle constants — refuse merge if exact match (suspicious). QAEngineer (not PE) authors evidence section. Memory `feedback_pe_qa_evidence_fabrication.md` codifies. |
| R10 | Vendor-noise paths in real UW-ios (DerivedData, .build, .swiftpm, Pods, Carthage, SourcePackages) inflate symbol count without project value | Phase 1.0 spike enumerates noise paths in real UW-ios DerivedData output; vendor-filter list locked in `symbol_index_swift` config. AC#7.5 substantive criteria explicitly count "non-vendor" symbols. |
| R11 | `palace.code.find_references` blocked by GIM-126 (PR #70 OPEN) for cross-language fix | Track A and B Phase 4.1 evidence use Tantivy direct lookup (Slice 1 pattern) until GIM-126 merges. Spec rev3 (or follow-up issue) restores `find_references` step. |

## Effort estimate

**PE Phase 2: 5-6 days. Total wall-clock with phase ritual + buffer: ~10-12 days.**

Phase breakdown:
- Phase 1.0 Board oracle gate: **0.75d** (heavier than Slice 1 — Xcode build setup + SwiftSCIPIndex install + 3 generated-targets verify)
- Phase 1.1 CTO formalize: 0.25d
- Phase 1.2 CR plan-first review: 0.25d
- **Phase 2 PE TDD: 5-6d** (largest unit; Swift extractor + fixture + tests + CLAUDE.md)
- Phase 3.1 CR mechanical: 0.25d (with mandatory `gh pr checks` verification per `feedback_cr_phase31_ci_verification.md`)
- Phase 3.2 Opus adversarial: 0.25d
- Phase 4.1 QA live-smoke: 1d (heavier — first xcodebuild on iMac, SwiftSCIPIndex new tool; QAEngineer authors evidence with full transcripts)
- Phase 4.2 CTO merge: 0.1d (with mandatory evidence cross-check vs oracle per `feedback_pe_qa_evidence_fabrication.md`)
- Buffer: 2-3d for R1/R7/R8 surprises

## Operator host setup (rev2: split between dev Mac and iMac)

### Dev Mac (operator's primary, Apple Silicon, current Xcode) — build host

For Phase 1.0 spike + fixture regen + (post-merge) real UW-ios indexing for Track B:

1. `xcode-select -p` → expect `/Applications/Xcode.app/Contents/Developer` (full Xcode, not Command Line Tools)
2. `brew install xcodegen` (one-time)
3. `git clone https://github.com/Fostonger/SwiftSCIPIndex.git ~/.local/opt/SwiftSCIPIndex && cd ~/.local/opt/SwiftSCIPIndex && swift build -c release` (one-time, builds from source against operator's Xcode toolchain)
4. Symlink `~/.local/opt/SwiftSCIPIndex/.build/release/SwiftSCIPIndex` into PATH
5. (Track B) `git clone https://github.com/horizontalsystems/unstoppable-wallet-ios.git ~/iOS-projects/unstoppable-wallet-ios`

### iMac (Intel x86_64, macOS 13, runtime palace-mcp host) — ingestion only

Phase 4.1 Track A merge gate runs here. iMac DOES NOT build iOS code:

1. Edit `docker-compose.yml` (committed via this slice's PR): adds bind-mount for `uw-ios-mini` fixture path
2. (Optional, post-merge) Operator transfers Track B's real `.scip` from dev Mac to iMac via scp + adds `uw-ios` bind-mount
3. `bash paperclips/scripts/imac-deploy.sh --target <merge-sha>` — restart palace-mcp
4. Via MCP HTTP `localhost:8080/mcp/`: `palace.memory.register_project slug=uw-ios-mini` (Track A) and/or `slug=uw-ios` (Track B)

**This split is the key rev2 change**: iMac never tries to build modern Swift. Build happens on dev Mac; iMac receives pre-generated `.scip` for ingestion. Container environment is host-portable for the .scip file.
6. For Phase 4.1 live-smoke: `xcodebuild build` + SwiftSCIPIndex extraction on UW-ios, set `PALACE_SCIP_INDEX_PATHS`, restart, run `symbol_index_swift`.

### Non-iMac contributors

`docker-compose.yml` real-project mounts (`gimle`, `uw-android`, `uw-ios`) use absolute Mac paths for operator-iMac convenience. Non-iMac contributors:
- Either create `docker-compose.override.yml` redirecting these paths to local clones
- Or run `docker compose --profile review up` with fixture-only mounts only (paths under `./services/palace-mcp/tests/extractors/fixtures/...` work cross-platform)
- Documented in CLAUDE.md per AC#10.

iOS slice extends the mount table from Slice 1's pattern.

## Operator review verification (rev1)

| # | Operator question (brainstorm Q1-Q5) | Resolution |
|---|---|---|
| Q1 | iOS slice scope | Only `unstoppable-wallet-ios` for live-smoke; Kit repos out of scope for Slice 3. |
| Q2 | Fixture structure | Hybrid SPM + 1 Xcode app target (Variant D). |
| Q3 | Feature exercise depth | D-tier (max — core + modern + macros + UIKit interop). |
| Q4 | Vendor strategy | B (3-5 standalone vendored, ~27 synthesized). |
| Q5 | AC#4 conditional gate formulation | B (wide — 3 of 3 generated-code targets visible: Codable + macro + property-wrapper $-projection). |
