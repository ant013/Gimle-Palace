# Slice 3 — iOS Swift extractor (`symbol_index_swift`) — rev3

**Status:** Board draft (rev3, 2026-05-01) — paperclip-issue [GIM-128](https://paperclip.ant013.work/issues/2087656e-1530-4fe5-a7cd-5d9517947895). Phase 1.0 COMPLETE — see [findings](../../research/2026-05-01-swift-indexstore-spike.md). Awaits CTO Phase 1.1 formalization on rev3 + plan rev2.

**Revision history:**
- rev1 (2026-04-30) — initial brainstorm Q1-Q5 draft
- rev2 (2026-04-30) — operator review fixes (7 findings); SwiftSCIPIndex assumed viable
- **rev3 (2026-05-01) — Phase 1.0 spike on dev Mac proved SwiftSCIPIndex NO-GO on Xcode 26 (0 symbols read; non-canonical output). Operator approved Option C: custom Swift emitter built on Apple's `indexstore-db` SPM package, emitting canonical Sourcegraph SCIP protobuf. Implementation rewritten end-to-end; ACs adapted; Phase 4.1 Track A/B unchanged.**

**Predecessor merge:** `6492561` (GIM-127 Android scip-java validation merged 2026-04-30).
**Companion (NOT a blocker):** GIM-126 `find_references` lang-agnostic fix (PR #70 awaiting Phase 4.2 merge).
**Roadmap context:** Slice 3 of strategic Swift audit roadmap (`docs/research/2026-05-01-swift-audit-roadmap.md`).

## Goal

Add `symbol_index_swift` extractor to palace-mcp covering Swift code on iOS. Validate against real `unstoppable-wallet-ios` master via a **custom Swift binary** (`palace-swift-scip-emit`) that reads Apple's IndexStoreDB and emits **canonical Sourcegraph SCIP protobuf**. Output is byte-compatible with palace-mcp's existing `parse_scip_file` (the same parser already used by Java/Kotlin/TypeScript/Python extractors).

The extractor handles `.swift` files in one pass via per-document language auto-detection (precedent: `symbol_index_typescript` GIM-104, `symbol_index_java` GIM-127). 3-phase bootstrap: defs/decls → user uses → vendor uses.

## Why custom emitter (rev3 pivot)

Rev2 assumed SwiftSCIPIndex (community, `Fostonger/SwiftSCIPIndex`) would convert IndexStoreDB → SCIP. Phase 1.0 spike on operator's dev Mac (macOS 26.3.1, Xcode 26.3, Swift 6.2.4) revealed two blockers:

1. **0 symbols read.** `swift-scip-indexer` returns 0 symbols on both synthetic SPM build (1067 indexstore files) AND real UW-ios DerivedData (34245 records). Likely IndexStoreDB API/format mismatch with Xcode 26's `libIndexStore.dylib`. Recent commits ("dynamically locate libIndexStore.dylib") show the maintainer was already chasing this; the fix is incomplete.
2. **Non-canonical output.** SwiftSCIPIndex emits SQLite `.db` or custom JSON, not Sourcegraph SCIP protobuf. Adapter would add 150-300 LOC of fragile conversion code.

Operator explicitly chose quality + control over wait-for-upstream. Custom emitter rationale:

| Factor | SwiftSCIPIndex (rejected) | Custom emitter (accepted) |
|---|---|---|
| Output format | non-canonical | canonical Sourcegraph SCIP protobuf |
| Xcode 26 compat | broken now | we control |
| Maintenance | community single-maintainer | we maintain alongside Solidity emitter |
| Time to working slice | indeterminate | 2-4 days estimated |
| Cross-file refs (USE) | theoretically yes | designed in from start |
| Bonus | none | reusable for Slice 4 multi-repo SPM ingest |

Precedent: `services/palace-mcp/src/palace_mcp/scip_emit/solidity.py` (Solidity v1, GIM-124) — a Python module that builds canonical SCIP protobuf programmatically from Slither AST output. Different language, different paradigm (no compile step), but same **architectural principle**: when no first-party scip-X exists, palace-mcp owns the emitter and outputs canonical Sourcegraph SCIP. Swift emitter is necessarily a **Swift binary** (IndexStoreDB API is Swift-only) but follows the same architectural principle.

## Implementation overview

```
services/palace-mcp/scip_emit_swift/         (NEW — Swift Package; sibling to src/palace_mcp/scip_emit/ Python emitters)
├── Package.swift                             SPM package, deps:
│                                              - apple/swift-protobuf >= 1.31.0 (pinned tag)
│                                              - swiftlang/indexstore-db (pinned SHA — locked Phase 1.1)
│                                              - apple/swift-argument-parser >= 1.5.0 (pinned tag)
├── README.md                                 Build + run instructions; protoc/protoc-gen-swift versions
├── Sources/
│   ├── PalaceSwiftScipEmitCore/              Library target — testable; imports without main()
│   │   ├── IndexStoreReader.swift            Iterates units + symbol occurrences via IndexStoreDB API
│   │   ├── ScipEmitter.swift                 Builds scip.proto Index message; serializes via swift-protobuf
│   │   ├── SymbolBuilder.swift               USR → stable SCIP `symbol` field (USR-as-descriptor scheme)
│   │   ├── DisplayNameBuilder.swift          Pretty FQN for Scip_SymbolInformation.display_name (NOT identity)
│   │   ├── PathFilter.swift                  Excludes only system/outside-root noise; vendor-INSIDE-root passes
│   │   └── Proto/
│   │       ├── scip.proto                    Vendored from sourcegraph/scip @ pinned tag (locked Phase 1.1)
│   │       └── scip.pb.swift                 Generated by `protoc --swift_out` (committed verbatim)
│   └── PalaceSwiftScipEmitCLI/               Executable target — thin wrapper around Core
│       └── main.swift                        ParsableCommand entry; depends on Core
├── Tests/
│   └── PalaceSwiftScipEmitCoreTests/         Targets Core (importable; not the executable)
│       ├── SymbolBuilderTests.swift
│       ├── PathFilterTests.swift
│       ├── ProtoSmokeTests.swift             Empty Scip_Index() roundtrip; written-to-file readability
│       ├── EdgeCaseTests.swift               AC#12 — deterministic re-emit, missing DerivedData, empty IndexStore
│       └── DisplayNameTests.swift
└── regen-scip.sh                             Helper called by fixture regen.sh

services/palace-mcp/src/palace_mcp/extractors/
└── symbol_index_swift.py                     (NEW — Python extractor; reads .scip emitted by binary)

services/palace-mcp/src/palace_mcp/extractors/scip_parser.py
                                              (1-line ADD: "swift": Language.SWIFT to _SCIP_LANGUAGE_MAP;
                                               also ".swift"/".swiftinterface" to path fallback)

services/palace-mcp/tests/extractors/
├── unit/test_symbol_index_swift.py           (NEW — mocked driver tests)
├── integration/test_symbol_index_swift_integration.py  (NEW — Neo4j IngestRun + Tantivy assertions)
└── fixtures/uw-ios-mini-project/             (NEW — fixture)
    ├── REGEN.md                              How to regen .scip on dev Mac; oracle table; pinned tool versions
    ├── LICENSE                               Vendored from UW-ios (MIT)
    ├── project.yml                           XcodeGen project config
    ├── regen.sh                              Build + scip_emit invocation script
    ├── .gitignore                            Excludes .build/, DerivedData/
    ├── UwMiniCore/                           SPM library target (~15 files)
    │   └── Sources/UwMiniCore/...
    ├── UwMiniApp/                            Xcode app target (~12 files)
    │   └── ...
    ├── Tests/                                ~3 files (XCTest fixtures)
    └── scip/index.scip                       Pre-generated, committed (binary, ~50-200 KB)
```

The Python extractor (`symbol_index_swift.py`) is structurally identical to `symbol_index_java.py` minus the language list (`Language.SWIFT` only). Vendor classification is **owned by the Python extractor** (same pattern as `symbol_index_java._is_vendor()`); the Swift emitter does NOT pre-filter vendor paths — vendor occurrences are emitted into `.scip` and Phase 3 ingestion classifies them by path prefix.

## Symbol identity (rev3 — USR-as-descriptor)

`palace-swift-scip-emit` writes the SCIP `symbol` field as:

```
scip-swift apple <module> . <usr-as-descriptor>
```

Where `<usr-as-descriptor>` is the IndexStoreDB-provided USR (e.g., `s:5UwSpike11WalletStoreC6select1iyS_tF`) with SCIP-special characters escaped via percent-encoding (`%28` for `(`, `%29` for `)`, etc., per Sourcegraph SCIP descriptor grammar).

**Why USR-as-descriptor (rev3 from earlier prefix-length-then-suffix scheme):**
- IndexStoreDB guarantees USR consistency across all occurrences of the same logical symbol within a single project's index. Cross-document refs work via string equality of the SCIP `symbol` field.
- USRs disambiguate overloads, extensions, generics, protocol methods, nested types — all native concerns Swift mangling already resolves. A constructed FQN scheme would either replicate that complexity or collide.
- GIM-105 rev2 Variant B compatibility preserved: `apple` manager + `<module>` package + `.` version placeholder.
- Pretty FQN (`WalletStore#select(_:).` etc.) lives separately in `Scip_SymbolInformation.display_name` for human-readable output. NOT used as identity.

**Trade-off:** SCIP `symbol` strings become opaque to tools that try to PARSE them for descriptor-walking. palace-mcp does not do that today; cross-document join uses string equality only. If future slices require parsable descriptors, a SymbolBuilder evolution emits both fields (legacy parse-friendly form + USR-stable identity) — followup, not v1.

## Distribution model

The Swift emitter binary is built **only on dev Mac** (Apple Silicon, modern Xcode). It is NOT built on iMac (Intel + macOS 13 cannot build Swift 6) and NOT built in palace-mcp container (no Swift toolchain).

Workflow:

1. **Operator on dev Mac:** clones target Swift project, runs `xcodebuild` to generate DerivedData, then runs `palace-swift-scip-emit ... --output project.scip`.
2. **Operator transfers `.scip` to iMac:** via `scp project.scip user@imac:/path/to/scip-mounts/`.
3. **palace-mcp container:** ingests via `palace.ingest.run_extractor(name="symbol_index_swift", project="<slug>")` — same pattern as `symbol_index_java`.

The `palace-swift-scip-emit` Swift sources live in this repo. Operator/CI builds the binary once per dev Mac; binary itself is NOT committed (build artifact gitignored).

## Acceptance criteria

ACs adapted from rev2. Coverage criteria (#1-3) preserved; visibility criteria (#4-5) preserved with custom emitter contracts; language detection (#6) preserved; live-smoke (#7) preserved; pipeline (#8-10) preserved; emitter-specific NEW criteria #11-12.

### AC#1 — Coverage on fixture (Track A merge gate)

After ingest of fixture's pre-generated `index.scip`:
- `MATCH (i:IngestRun {project:"uw-ios-mini", source:"extractor.symbol_index_swift"}) RETURN i.nodes_written` ≥ 200. **Note:** `nodes_written` here is the count of Tantivy occurrence-documents written, not Neo4j nodes (Neo4j receives only `:IngestRun` + 3 phase checkpoints; per `symbol_index_java.py:230` precedent, `ExtractorStats.nodes_written` = Tantivy doc count).
- Phase checkpoint `phase1_defs` populated; `phase2_user_uses` non-zero; **`phase3_vendor_uses > 0`** (vendor analysis is live; exact ratio to user_uses depends on what the fixture vendors and is locked in REGEN.md).

Exact thresholds locked during fixture regen (REGEN.md oracle table).

### AC#2 — USE occurrences emitted (binary-level contract)

The `palace-swift-scip-emit` binary MUST emit DEF and USE roles distinguishably. Verified at fixture-build time:

```bash
python3 -c "
from palace_mcp.proto import scip_pb2
idx = scip_pb2.Index()
idx.ParseFromString(open('fixture/scip/index.scip','rb').read())
roles = collections.Counter()
for d in idx.documents:
    for o in d.occurrences:
        roles[o.symbol_roles] += 1
print(roles)
"
```

Expected: at least 50 DEF occurrences (`SymbolRole.Definition` bit set) AND at least 100 USE occurrences (Definition bit clear) in fixture `index.scip`.

### AC#3 — Vendor classification (Python-side; emitter is permissive)

Vendor classification is **owned by the Python extractor**, not the Swift emitter. The emitter passes through everything inside `--project-root` (excluding only system framework paths like `/Library/Developer/`, `/Applications/Xcode.app/`); the Python extractor then routes occurrences with paths matching `Pods/`, `Carthage/`, `SourcePackages/`, `.build/`, `.swiftpm/`, `DerivedData/` to phase 3 (vendor uses), and other paths to phase 1 (DEFs) and phase 2 (user uses).

Verification: in fixture, `Pods/Foo/Foo.swift` produces occurrences in `phase3_vendor_uses`; `UwMiniCore/Sources/UwMiniCore/Wallet.swift` produces them in `phase1_defs` (DEFs) and `phase2_user_uses` (USEs). Tantivy `language="swift"` filter shows both classes. `phase3_vendor_uses > 0` AND `phase2_user_uses > 0`.

### AC#4 — Generated-code visibility (binary outcome; A or B-2 only)

With custom emitter and IndexStoreDB direct access, we emit **all** symbols IndexStoreDB exposes. This includes compiler-synthesized members iff IndexStoreDB indexes them:
- Codable: `Wallet.init(from:)`, `Wallet.encode(to:)`, `CodingKeys` enum cases
- `@Observable` macro: `_$observationRegistrar`, `withMutation`, `access` accessors
- Property wrapper `$`-projection: `_counter` storage, `$counter` projected accessor

**Branch decision (binary; rev3 removes B-1):**

- **Branch A** — All 3 categories visible in emitted `.scip` from fixture build → AC#4 hard. Generated-code symbols counted in `phase1_defs` oracle.
- **Branch B-2** — Some or all 3 categories NOT visible. AC#4 narrows to "Swift source-level symbols indexed correctly; generated-code visibility deferred to followup-issue (e.g., 'Slice 3 followup — generated-code visibility via SwiftSyntax')." This followup may add a parallel emit path that uses SwiftSyntax for syntactic synthesis-detection — but it is **NOT in scope for v1**.

Exact branch locked during Plan rev2 Phase 1 Task 8 (spike-against-fixture). Rev3 removes B-1 (`-emit-symbol-graph` workaround) — that flag produces a separate `.symbols.json` artifact for DocC, orthogonal to IndexStoreDB occurrences. Adding a symbolgraph ingestion path = scope creep.

### AC#5 — Cross-file references resolve correctly (Tantivy contract)

In fixture, `WalletStore.select(_:)` defined in `UwMiniCore/Sources/UwMiniCore/WalletStore.swift` AND used in `UwMiniApp/UwMiniApp/ContentView.swift`. Both occurrences share the same SCIP `symbol` field (`scip-swift apple UwMiniCore . <USR-of-select>`) because IndexStoreDB-USR equality is preserved across documents.

Verification path 1 — via `palace.code.find_references` MCP tool (lang-agnostic post-GIM-126 merge):

```python
hits = palace.code.find_references(
    qualified_name="<exact SCIP symbol from fixture oracle>",
    project="uw-ios-mini"
)
assert hits["count"] >= 2  # at least DEF + 1 USE
paths = {h["relative_path"] for h in hits["results"]}
assert "UwMiniCore/Sources/UwMiniCore/WalletStore.swift" in paths
assert "UwMiniApp/UwMiniApp/ContentView.swift" in paths
```

Verification path 2 — direct Tantivy query (used by integration test before find_references is wired into MCP for some test contexts):

```python
from palace_mcp.extractors.foundation.tantivy_bridge import TantivyBridge
async with TantivyBridge.open_for_search(tantivy_path) as bridge:
    results = await bridge.search_by_symbol(
        symbol_qualified_name="<oracle symbol>",
        project="uw-ios-mini",
        limit=100,
    )
    paths = {r.relative_path for r in results}
    assert "UwMiniCore/Sources/UwMiniCore/WalletStore.swift" in paths
    assert "UwMiniApp/UwMiniApp/ContentView.swift" in paths
```

(The `:Symbol`/`:SymbolOccurrence` Neo4j graph nodes referenced in rev2's AC#5 do not exist for this extractor family — `symbol_index_java`/_python/_typescript only persist `:IngestRun` + checkpoints to Neo4j; occurrence-graph lives entirely in Tantivy. AC#5 corrected accordingly in rev3.)

### AC#6 — Language detection per-document

Tantivy index has documents tagged `language="swift"` (as emitted by `palace-swift-scip-emit` per `document.language` field). Test:

```python
hits = tantivy_bridge.search(query="*", filter={"language": "swift"})
assert len(hits) > 0
```

### AC#7 — UW-ios live-smoke (Track B; deferred-not-blocked)

After running emitter on real UW-ios on dev Mac and ingesting on iMac:

- ≥10000 Tantivy occurrence-documents from project paths (excluding vendor); reported as `IngestRun.nodes_written` minus `phase3_vendor_uses`
- Tantivy hits for at least 5 named UW-ios types: `MainViewController`, `WalletManager`, `Kit`, `App`, `Configuration`
- Language distribution: ≥95% `language="swift"`
- Cross-file refs: at least 3 occurrences each for `Kit`, `WalletManager`
- ≤1% `language="UNKNOWN"`

### AC#8 — Pipeline integration

`palace.ingest.run_extractor(name="symbol_index_swift", project="uw-ios-mini")` returns `ok: true` with valid IngestRun id, all 3 phase checkpoints written to Neo4j, no Tantivy bridge errors, `ensure_custom_schema` succeeds (the generic 101a substrate's idempotent schema bootstrap, which checks IngestRun-related shape; this extractor does not introduce new node types so no extractor-specific schema drift is possible).

### AC#9 — Track A merge gate (committed fixture)

Fixture `services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project/scip/index.scip` is committed as binary (~50-200 KB). Container ingestion via `PALACE_SCIP_INDEX_PATHS` mount succeeds. AC#1-#6 verified on this path. **No real UW-ios source touch required for merge.**

### AC#10 — Track B captured but deferred

Real UW-ios live-smoke (AC#7) is captured as a separate followup-issue (e.g., GIM-129 "Slice 3 Track B — UW-ios real-source smoke"). Operator runs on dev Mac post-merge; results posted on followup-issue, not GIM-128 PR.

### AC#11 (NEW) — Emitter binary builds + emits canonical SCIP protobuf

`xcrun swift build -c release --package-path services/palace-mcp/scip_emit_swift` succeeds on operator's dev Mac. Built binary `.build/release/palace-swift-scip-emit-cli` (or `palace-swift-scip-emit` if executable target keeps that name) exists. Run on fixture's UwMiniCore/UwMiniApp + their DerivedData produces a `.scip` file that:

1. Parses without error via `palace_mcp.extractors.scip_parser.parse_scip_file()`.
2. Has non-empty `metadata.tool_info.name = "palace-swift-scip-emit"`.
3. Has at least 1 document with `language = "swift"`.
4. Has at least 1 symbol whose SCIP `symbol` field is USR-derived and round-trips through `symbol_id_for()` without exception.

### AC#12 (NEW) — Emitter handles edge cases gracefully

Three explicit cases, each covered by an XCTest in `EdgeCaseTests.swift`:

- **Deterministic re-emit:** running emitter twice against same DerivedData produces byte-identical `.scip` output (or deterministically-equivalent — i.e., document order, occurrence order, symbol order all stable). Verified by `diff` on two `.scip` files.
- **Missing DerivedData:** emitter on a non-existent `--derived-data` path exits non-zero AND writes an actionable diagnostic to stderr (e.g., `error: DerivedData path does not exist: /tmp/no-such-path`).
- **Empty IndexStore:** emitter on a DerivedData root with no records (e.g., a freshly-cleaned project that hasn't been built) emits a valid SCIP file with `documents = []`, `metadata.tool_info.name = "palace-swift-scip-emit"`, and exits 0.

## Track A / Track B (unchanged from rev2)

Per memory `reference_imac_toolchain_limits.md`:

- **Track A (HARD MERGE GATE):** Pre-generated `index.scip` committed to repo (binary, ~50-200 KB). palace-mcp container ingests via mount/COPY. iMac role limited to running palace-mcp container.
- **Track B (DEFERRED-NOT-BLOCKED):** Real UW-ios source on dev Mac. Operator builds + runs `palace-swift-scip-emit` to generate `.scip`. `scp` to iMac mount path. palace-mcp container ingests via runtime mount.

The new emitter binary itself is built only on dev Mac. iMac is not the build host; iMac receives only the resulting `.scip` byte-file plus paperclip MCP tools.

## Phase 1.0 — DONE 2026-05-01 (findings doc)

See `docs/research/2026-05-01-swift-indexstore-spike.md` for full evidence. Summary: SwiftSCIPIndex unviable on Xcode 26; custom emitter approved.

The operator-facing PHASE 1.0 work is complete. Plan rev2 Phase 1 starts the new emitter implementation (Phase 1 = "build the binary"; PE Phase 2 = "wire it up in palace-mcp").

## Risks (rev3)

| # | Risk | Mitigation |
|---|---|---|
| 1 | `indexstore-db` SPM package API changes between Xcode versions | Pin SHA in `Package.resolved`; CI regen test on every Xcode major bump; documented in REGEN.md |
| 2 | Generated-code visibility not exposed by IndexStoreDB | Plan rev2 has explicit Phase 1 task to enumerate IndexStoreDB output on synthetic Codable + @Observable + property wrapper sample; AC#4 has Branch B-2 fallback |
| 3 | USR → SCIP `symbol_qualified_name` mapping non-trivial for Swift (generics, extensions, protocols) | SymbolBuilder.swift owns this; reference Sourcegraph SCIP spec §"Symbol grammar"; unit tests for each Swift kind; spike against UW-ios sample types early |
| 4 | swift-protobuf serialization correctness | Vendor `scip.proto` from sourcegraph/scip; regenerate `scip.pb.swift` via `protoc --swift_out` exactly once; verify output round-trips through Python `scip_pb2.Index().ParseFromString()` |
| 5 | Build time on UW-ios (1700+ Swift files, large DerivedData) | Acceptable — emitter is read-only on DerivedData; no recompile. Initial estimate: 30-60s for full UW-ios index emit. Verify in Plan rev2 Phase 1 final task. |
| 6 | Cross-file ref resolution requires USR matching across documents | IndexStoreDB exposes `symbol.usr` consistently; build symbol-graph in single pass over all units; `SymbolBuilder` uses USR as graph node-id |
| 7 | Path normalization (project-root relative vs absolute) | PathFilter takes explicit `--project-root` arg; emit relative paths; reject paths outside root unless explicitly `--include` |
| 8 | iMac container ingestion must accept the new emitter's `.scip` | Already covered — output is canonical Sourcegraph SCIP, byte-compatible with existing `parse_scip_file` |
| 9 | First-time fixture regen on dev Mac is non-trivial | REGEN.md must be very explicit; plan rev2 has per-step instructions; expected manual time ~30 min |
| 10 | Performance regression in 3-phase bootstrap from large UW-ios graph | Carry-over Slice 1 mitigations: Tantivy bridge writes async; circuit breaker per-phase; eviction round-3 if needed |

## Operator host setup (rev3)

**Dev Mac (operator's primary, Apple Silicon, modern Xcode):**

- Build host for `palace-swift-scip-emit`. Runs `xcrun swift build -c release` in `services/palace-mcp/scip_emit_swift/`.
- Build host for fixture (`UwMiniApp.xcodeproj` via XcodeGen).
- Source for `index.scip` artifact committed to repo.
- For Track B: clones UW-ios, runs `xcodebuild`, runs `palace-swift-scip-emit-cli`, scp's `.scip` to iMac.
- Required tooling on dev Mac (REGEN.md captures exact versions):
  - Xcode 16+ (operator's session captured at 26.3 — works)
  - `protoc` ≥ 25.x (`brew install protobuf`)
  - `protoc-gen-swift` matching swift-protobuf version (`brew install swift-protobuf`)
  - XcodeGen (`brew install xcodegen`) — needed only for fixture regen, not for emitter build itself

**iMac (production palace-mcp host, Intel + macOS 13):**

- Receives `.scip` byte-files only (Track A via repo, Track B via scp).
- palace-mcp container ingests via `palace.ingest.run_extractor`.
- Does NOT build emitter, does NOT run emitter, does NOT touch Swift toolchain.

## Out of scope (rev3)

- **AGP 9 / Kotlin 2.3 retry** — orthogonal Android concern.
- **`scip-swift` integration** — Sourcegraph has no first-party Swift indexer. Our custom emitter IS the canonical path for palace-mcp.
- **Slice 4 multi-repo SPM ingest** — separate slice; this slice ships single-project ingest only.
- **Real-time Swift indexing** — emitter is batch-mode, ingested on demand. Continuous indexing is a far-future concern.
- **Live xcodebuild integration** — operator runs xcodebuild manually; emitter consumes resulting DerivedData.

## Decision points needing CTO + CR validation

1. **Vendoring `scip.proto`** — copy from sourcegraph/scip at a pinned tag. Re-pin on Sourcegraph SCIP version updates. Decision: which tag (must match Python `scip_pb2` proto3 version currently deployed).
2. **`indexstore-db` pin** — pin to specific Apple commit SHA, not `main`, to avoid silent breakage. Decision: which SHA (CTO/CR pick during Phase 1.1; SHA must successfully read Xcode 26's `Index.noindex/DataStore` records on operator's dev Mac).
3. **`protoc` + `protoc-gen-swift` version pin** — both must be installable on dev Mac AND match the swift-protobuf SPM dep version. Decision: pin major.minor in REGEN.md + Package.swift comment; document `brew install` commands.
4. **Vendor-vs-exclude policy in emitter** — codified explicit: emitter ONLY excludes paths outside `--project-root` and known system framework prefixes (`/Library/Developer/`, `/Applications/Xcode.app/`). Vendor paths INSIDE `--project-root` (`Pods/`, `Carthage/`, `SourcePackages/`, `.build/`, `.swiftpm/`, `DerivedData/`) are kept; Python extractor classifies them at ingest time. Decision: confirm CR + Opus accept this division.
5. **Binary distribution to CI** — build on each developer's dev Mac, OR commit pre-built binary, OR GitHub Actions macOS runner builds. Recommendation: GitHub Actions macOS runner builds on tag (out-of-scope-for-Slice-3, Slice 4 concern).
6. **CLI flag taxonomy** — exact set of `--include`/`--exclude`/`--module`/`--verbose` flags. Plan rev2 picks minimal viable set; future flags added as needed. Decision: confirm minimal set sufficient for Slice 4 reuse.

## Companion references

- `docs/research/2026-05-01-swift-indexstore-spike.md` — Phase 1.0 spike evidence (NO-GO for SwiftSCIPIndex)
- `docs/research/2026-05-01-swift-audit-roadmap.md` — Strategic Swift audit roadmap
- `services/palace-mcp/scip_emit/solidity/` — Solidity v1 custom emitter precedent (GIM-124)
- `services/palace-mcp/src/palace_mcp/extractors/symbol_index_java.py` — Slice 1 Android extractor (sibling pattern)
- `docs/superpowers/specs/2026-04-30-android-scip-java-validation.md` — Slice 1 spec
- `docs/superpowers/plans/2026-04-30-GIM-128-ios-swift-extractor-rev2.md` — Plan rev2 (companion)
- Sourcegraph SCIP: https://github.com/sourcegraph/scip
- Apple indexstore-db: https://github.com/swiftlang/indexstore-db
- Apple swift-protobuf: https://github.com/apple/swift-protobuf

## Memory references

- `reference_imac_toolchain_limits.md` — iMac is runtime-only (still applies)
- `project_palace_purpose_unstoppable.md` — palace-mcp primary purpose = UW ecosystem
- `feedback_pe_qa_evidence_fabrication.md` — Phase 4.1 evidence discipline
- `feedback_silent_scope_reduction.md` — keep this slice scoped; do NOT bundle Slice 4 multi-repo work
- (NEW) `project_swift_emitter_strategy_2026-05-01.md` — to be written; captures Option C decision
