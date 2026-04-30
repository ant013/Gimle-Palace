# Slice 3 — iOS Swift extractor (`symbol_index_swift`)

**Status:** Board draft (rev1, 2026-04-30) — paperclip-issue pending; awaits CTO Phase 1.1 formalization.
**GIM-NN:** placeholder — CTO swaps in Phase 1.1
**Predecessor merge:** `6492561` (GIM-127 Android scip-java validation merged 2026-04-30; spec rev3 pin policy and rev2 review-fix patterns inform this spec)
**Related:** GIM-127 Slice 1 Android (sibling pattern), GIM-126 find_references lang-agnostic fix (pending merge — affects AC#7 evidence script), GIM-105 rev2 (Q1 FQN cross-language decision — Swift entry).
**Roadmap context:** Slice 3 of 4 in operator-stack language coverage post-Solidity. Sequence: Slice 1 (Android Java/Kotlin) ✅ merged → Slice 2 (Android resources) deferred per `project_slice2_deferred_2026-04-30.md` → **Slice 3 (this — iOS Swift)** → Slice 4 (KMP bridge, after iOS).

## Goal

Add `symbol_index_swift` extractor to palace-mcp covering Swift code on iOS. Validate against real `unstoppable-wallet-ios` master via Apple's native IndexStoreDB → SCIP conversion path.

Unlike Slice 1 (Android), Sourcegraph has **no first-party scip-swift indexer** (no `sourcegraph/scip-swift` repo, not on npm, not in coursier `--contrib`). The Swift indexing path uses:
1. **Apple native IndexStoreDB** — generated automatically by `swiftc` and `clang` during `xcodebuild build` for Debug.
2. **`SwiftSCIPIndex`** (community, `Fostonger/SwiftSCIPIndex`, MIT, last commit 2026-01-05) — converts IndexStoreDB to SCIP protobuf format.
3. **palace-mcp's existing `scip_parser.py`** (lang-agnostic since GIM-104) — reads the SCIP, no parser changes if SwiftSCIPIndex output is spec-compliant.

This avoids the scip-java/AGP-9 incompatibility lock-in we hit in Slice 1, because Apple maintains IndexStoreDB centrally for SourceKit-LSP — it tracks Swift compiler updates synchronously, no third-party tooling lag.

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

**Per-slice "максимум эффективности" mandate**: each language slice ships full Swift source DEF+USE coverage from day 1 (parallel to Slice 1's Java/Kotlin DEF+USE).

## Hard dependencies

| Dependency | State |
|---|---|
| 101a foundation substrate (TantivyBridge, BoundedInDegreeCounter, ensure_custom_schema, …) | Stable, Slice 1 used it — REUSE |
| `scip_parser.py` lang-agnostic parser (GIM-104) | REUSE; needs `Language.SWIFT` enum value addition in `extractors/foundation/models.py` if absent |
| Q1 FQN cross-language Variant B (GIM-105 rev2) | Locks Swift qualified_name format (see rev2 §Per-language action map) |
| `xcodebuild` | macOS host with Xcode CLI (no full Xcode.app required for SwiftSCIPIndex flow — test on iMac during Phase 1.0) |
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
| `services/palace-mcp/src/palace_mcp/extractors/symbol_index_swift.py` | NEW extractor. ~80 LOC copy-paste from `symbol_index_java.py` with literal `"java"` → `"swift"` rename + `Language.SWIFT` filter. 3-phase ingest unchanged. |
| `services/palace-mcp/src/palace_mcp/extractors/foundation/models.py` | ADD `Language.SWIFT = "swift"` if not already present (verify Phase 1.0). |
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

**Vendor justification**: 3 of 30 truly vendored; 27 synthesized in UW-ios style. Same 1:N ratio as Slice 1 (UW-android: 3 chartview files vendored verbatim, 27 synthesized).

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

## Acceptance criteria

| AC# | Condition | Verification |
|---|---|---|
| AC#1 | Vendored fixture compiles | `xcodegen generate -s project.yml -p UwMiniApp/UwMiniApp.xcodeproj && xcodebuild build -workspace UwMiniApp/UwMiniApp.xcworkspace -scheme UwMiniApp -destination "generic/platform=iOS Simulator"` exit 0 |
| AC#2 | SwiftSCIPIndex emits valid `index.scip` | SwiftSCIPIndex run produces non-empty `index.scip`; parses via `parse_scip_file()` without exception |
| AC#3 | Oracle counts match (Phase 1.0 locked) | All assertions in `TestUwIosMiniProjectFixture` pass |
| **AC#4 (CONDITIONAL — Phase 1.0 gate)** | **3 of 3 generated-code targets visible** | Phase 1.0 grep'ает `index.scip` на:<br>(a) **Codable synthesis** — `Wallet#init(from:)` + `Wallet#encode(to:)` (compiler-generated)<br>(b) **`@Observable` macro** — `WalletStore#_$observationRegistrar` или `withMutation(keyPath:_:)`<br>(c) **Property wrapper `$`-projection** — `_state` storage + `$state` projected on `@State`/`@Binding`<br><br>**Branch A** (default expected): all 3 visible → AC#4 hard.<br>**Branch B-1**: workaround (e.g., `-Xfrontend -emit-symbol-graph` flag or specific IndexStoreDB include path) makes the missing target(s) visible → AC#4 hard with workaround documented in REGEN.md.<br>**Branch B-2**: any of 3 not visible after workaround attempts → spec rev2 + followup-issue. PE Phase 2 blocked until branch locked. |
| AC#5 | Cross-target USE resolves — **5 USE pairs** | Tests:<br>• 1/5 **app→SPM**: `WalletListView.swift` USE `WalletStore` (`UwMiniCore`)<br>• 2/5 **app→SPM**: `WalletDetailView.swift` USE `Wallet` Codable struct (`UwMiniCore`)<br>• 3/5 **app→SPM**: `ChartViewRepresentable.swift` USE `Transaction` (UIKit interop ↔ SPM types)<br>• 4/5 **intra-SPM cross-package**: `WalletRepository.swift` USE `Wallet` + `Transaction`<br>• 5/5 **macro-generated→source**: `WalletStore`'s `withMutation(...)` generated body USE `_$observationRegistrar` (conditional on AC#4 Branch A). Skipped if Branch B-2. |
| AC#6 | All DEFs language=`SWIFT` | `WalletStore` + `Wallet` + `WalletListView` (3 representative DEFs) all have `occ.language == Language.SWIFT`. Requires `Language.SWIFT` enum value in `extractors/foundation/models.py` (verified Phase 1.0). |
| AC#7 | Integration test green | `tests/extractors/integration/test_symbol_index_swift_uw_integration.py` passes locally + on iMac. NEW pattern — real fixture .scip + real Neo4j (Slice 1 rev2 pattern). |
| AC#8 | `docker-compose.yml` bind-mount added | 1 entry: `/Users/Shared/Ios/unstoppable-wallet-ios:/repos/uw-ios:ro`. |
| AC#9 | `.env.example` documented | `PALACE_SCIP_INDEX_PATHS={..., "uw-ios": "/repos/uw-ios/scip/index.scip"}` example shown. |
| AC#10 | CLAUDE.md updated | New "Operator workflow: iOS Swift symbol index" subsection + project mount table row + non-iMac override note (continuing Slice 1 rev2 pattern). |

### Phase 4.1 live-smoke evidence script (mandatory, real, with transcripts)

```
[1] palace.ingest.list_extractors → returns existing list + symbol_index_swift (NEWLY added)
[2] palace.memory.register_project slug=uw-ios → ok:true
[3] On iMac (real session, real timestamps):
    cd /Users/Shared/Ios/unstoppable-wallet-ios
    git rev-parse HEAD  # capture SHA
    date -u +%FT%TZ     # capture timestamp BEFORE
    xcodebuild build -workspace UnstoppableWallet/UnstoppableWallet.xcworkspace \
                    -scheme UnstoppableWallet \
                    -destination "generic/platform=iOS Simulator"
    SwiftSCIPIndex --derived-data ~/Library/Developer/Xcode/DerivedData/UnstoppableWallet-* \
                  --output ./scip/index.scip
    date -u +%FT%TZ     # capture timestamp AFTER xcodebuild
[4] Update .env: PALACE_SCIP_INDEX_PATHS={..., "uw-ios":"/repos/uw-ios/scip/index.scip"}
[5] Restart palace-mcp container
[6] palace.ingest.run_extractor name=symbol_index_swift project=uw-ios
    → expect: ok:true, nodes_written > 5000 (UW-ios has 1704 .swift files)
[7] palace.memory.lookup entity_type=IngestRun (NOTE: 'IngestRun' not in palace.memory entity types — use direct cypher instead)
    OR direct cypher: MATCH (r:IngestRun {run_id: "<from-step-6>"}) RETURN r.success, r.started_at, r.finished_at
[8] (If GIM-126 merged) palace.code.find_references qualified_name=WalletStore project=uw-ios
    → returns DEFs + USEs across UW-ios codebase
```

**Process discipline (per `feedback_pe_qa_evidence_fabrication.md`)**:
- Evidence MUST include real timestamps from `date -u` BEFORE/AFTER each major step
- Evidence MUST include `git rev-parse HEAD` output (UW-ios source SHA captured)
- Evidence MUST include actual `palace.ingest.run_extractor` response JSON, not paraphrased
- CTO Phase 4.2 review: **cross-check** numbers in evidence against any prior oracle/fixture constants — refuse merge if numbers exactly match a fixture/oracle constant
- QAEngineer (NOT PythonEngineer) authors the evidence section in PR body

## Risks

| # | Risk | Mitigation |
|---|---|---|
| **R1** ⚡ | **SwiftSCIPIndex output quality unknown** — community 1⭐, single maintainer, last update Jan 2026. May crash on complex Xcode workspace OR skip Swift macros (= AC#4 Branch B/C trigger) OR produce non-standard SCIP. | **Phase 1.0 prerequisite**: end-to-end run on fixture before PE Phase 2. AC#4 wide gate (3 of 3 generated targets) catches frequent failure mode. If R1 surfaces on real UW-ios — spec rev2 with workaround flags or SHA pin. |
| R2 | IndexStoreDB path varies by Xcode/macOS version | `regen.sh` uses `~/Library/Developer/Xcode/DerivedData/<scheme>-*/Index.noindex` glob. REGEN.md instructs operator to verify path. |
| R3 | `xcodebuild` requires macOS host with Xcode (cannot run in Docker) | Existing pattern — Slice 1 also generated `.scip` outside container. operator runs regen on iMac, palace-mcp container reads result. |
| R4 | Swift macros require Swift ≥5.9 (Xcode ≥15) | Pinned in `project.yml` + REGEN.md. UW-ios already on Swift 5.9+ (per `.swift-version`). |
| R5 | XcodeGen — extra dependency | Document in REGEN.md: `brew install xcodegen` one-time. Alternative (commit pre-generated `.xcodeproj`) is worse — `project.pbxproj` is unreadable mess. |
| R6 | fixture regen slower than Slice 1 (2-5 min vs 30-60 sec for gradle) | Acceptable; CI doesn't regen (committed `.scip`). PE on regen waits. |
| R7 | IndexStoreDB may include compiler-internal symbols (mangled names like `$s4...`) | Phase 1.0 inspect — if noisy, filter in `symbol_index_swift` extractor. |
| **R8** | Effort underestimate if R1 surfaces — fallback to "wait for upstream" / write own | Phase 1.0 oracle gate catches ASAP. Buffer: 5-6d PE + 2-3d = ~10-12d wall-clock. |
| R9 | Phase 4.1 evidence fabrication (Slice 1 incident) | **Hardened**: spec mandates real timestamps + transcripts + git rev-parse output; CTO Phase 4.2 must cross-check numbers vs oracle constants. Memory `feedback_pe_qa_evidence_fabrication.md` codifies the lesson. |

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

## iMac ops setup (parallel to slice — not blocking PR merge)

1. `git clone https://github.com/horizontalsystems/unstoppable-wallet-ios.git /Users/Shared/Ios/unstoppable-wallet-ios` (operator)
2. Toolchain install (one-time):
   - `brew install xcodegen` (operator)
   - `git clone https://github.com/Fostonger/SwiftSCIPIndex.git ~/SwiftSCIPIndex && cd ~/SwiftSCIPIndex && swift build -c release` (operator)
   - Add `~/SwiftSCIPIndex/.build/release/SwiftSCIPIndex` to PATH (or alias)
3. Edit `docker-compose.yml` (committed via this slice's PR): adds bind-mount for `uw-ios`.
4. `bash paperclips/scripts/imac-deploy.sh --target <merge-sha>` — restart palace-mcp.
5. Via MCP: `palace.memory.register_project slug=uw-ios`.
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
