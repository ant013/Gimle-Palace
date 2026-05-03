# Slice 3 — iOS Swift extractor (`symbol_index_swift`) Implementation Plan (rev2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `symbol_index_swift` extractor + `uw-ios-mini-project` fixture to palace-mcp. Implementation pivots (rev3 spec) to a **custom Swift emitter** (`palace-swift-scip-emit`) built on Apple's `indexstore-db` SPM package, emitting **canonical Sourcegraph SCIP protobuf**. This replaces the failed SwiftSCIPIndex (community) approach from rev1.

**Architecture:** Three layers in this slice:
1. **Swift emitter binary** (NEW, `services/palace-mcp/scip_emit_swift/`) — reads Xcode IndexStoreDB via `indexstore-db` SPM dep, emits `.scip` protobuf via `swift-protobuf`. Built on dev Mac only.
2. **Python extractor** (NEW, `symbol_index_swift.py`) — structurally identical to `symbol_index_java.py`. Reads emitter output via existing `parse_scip_file`. Runs in palace-mcp container.
3. **Fixture** (NEW, `uw-ios-mini-project/`) — hybrid SPM + Xcode app, ~30 files, regen via `palace-swift-scip-emit`. Pre-generated `.scip` committed.

**Tech stack:** Python 3.12 (palace-mcp), Swift 6+ (emitter + fixture), Xcode 16+, XcodeGen, swiftlang/indexstore-db (pinned), apple/swift-protobuf, scip-code/scip proto, pytest, testcontainers/compose-reuse Neo4j, Tantivy.

**Predecessor SHA:** `6492561` (GIM-127 Slice 1 Android merged 2026-04-30).
**Spec:** `docs/superpowers/specs/2026-04-30-ios-swift-extractor-rev3.md`.
**Phase 1.0 findings:** `docs/research/2026-05-01-swift-indexstore-spike.md`.
**Phase 1.1 pin truth:** `docs/research/2026-05-03-gim-128-phase-1-1-pin-truth.md`.
**Companion (NOT a blocker):** GIM-126 PR #70 (`find_references` lang-agnostic).

**Phase 1.1 locked pins (2026-05-03):**
- `indexstore-db`: `swiftlang/indexstore-db` revision `4ee7a49edc48e94361c3477623deeffb25dbed0d`. This is the current upstream `main` SHA used for API compatibility in this plan. Runtime proof that it reads Xcode 26 `Index.noindex/DataStore` records remains Task 3's hard gate; if Task 3 returns 0 USRs after diagnostics, stop and return to spec rev4.
- `scip.proto`: `scip-code/scip` tag `v0.7.1`, sha256 `387f91bea3357a6ab72ae6214c569bf33fddcd3c726a8eacfa1435d65ac347e8`, size `32283` bytes. This matches the deployed Python proto line (`github.com/scip-code/scip/...`) in `palace_mcp.proto.scip_pb2`.
- `swift-protobuf`: exact SPM tag `1.37.0` (`81558271e243f8f47dfe8e9fdd55f3c2b5413f68`). `protoc-gen-swift` must report `1.37.0`.
- `protobuf`/`protoc`: Homebrew formula `protobuf` stable `34.1`; `protoc --version` must report `libprotoc 34.1`.

---

## Phase 1.0 — Spike (DONE 2026-05-01)

Operator + Board completed Phase 1.0 spike on dev Mac (macOS 26.3.1, Xcode 26.3, Swift 6.2.4). Outcome: SwiftSCIPIndex (community) is **NO-GO** on Xcode 26 (returns 0 symbols on real DerivedData; non-canonical output format). Operator approved pivot to **Option C (custom emitter)** documented in spec rev3.

Findings doc captures evidence + decision rationale. **Phase 1 below begins the new emitter implementation.**

---

## Phase 1: Build the Swift emitter binary (Board/operator + Implementer; ~3-4 days)

> Phase 1 produces the `palace-swift-scip-emit` binary. Until this binary exists and emits valid SCIP protobuf, Phase 2 (Python extractor) cannot integration-test. Phase 1 ends at Task 8 with a working binary that has been smoke-tested against a synthetic spike + the partial `uw-ios-mini-project` fixture.

### Task 1: SPM package scaffold (Core library + CLI executable split)

**Files:**
- Create: `services/palace-mcp/scip_emit_swift/Package.swift`
- Create: `services/palace-mcp/scip_emit_swift/Sources/PalaceSwiftScipEmitCLI/main.swift`
- Create: `services/palace-mcp/scip_emit_swift/Sources/PalaceSwiftScipEmitCore/Placeholder.swift` (replaced in Tasks 3-7)
- Create: `services/palace-mcp/scip_emit_swift/README.md`
- Create: `services/palace-mcp/scip_emit_swift/.gitignore`

> Path note: this lives at `services/palace-mcp/scip_emit_swift/` (sibling-not-child of `src/palace_mcp/scip_emit/` Python module — Python emitters are importable Python modules; Swift emitter is a standalone SPM package, can't be inside the Python tree).

> Naming note: per operator review, package is split into two targets — `PalaceSwiftScipEmitCore` (library) and `PalaceSwiftScipEmitCLI` (executable). All implementation logic lives in Core (testable, importable). CLI is a thin `@main` ParsableCommand that calls into Core. Tests target Core directly.

- [ ] **Step 1: Write Package.swift (library + executable split)**

```swift
// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "palace-swift-scip-emit",
    platforms: [.macOS(.v14)],
    products: [
        .library(name: "PalaceSwiftScipEmitCore", targets: ["PalaceSwiftScipEmitCore"]),
        .executable(name: "palace-swift-scip-emit-cli", targets: ["PalaceSwiftScipEmitCLI"]),
    ],
    dependencies: [
        // indexstore-db: Phase 1.1 API-compatible pin. Task 3 proves runtime read against Xcode 26.
        .package(url: "https://github.com/swiftlang/indexstore-db.git", revision: "4ee7a49edc48e94361c3477623deeffb25dbed0d"),
        // swift-protobuf: exact tag matching protoc-gen-swift 1.37.0 from Homebrew swift-protobuf.
        .package(url: "https://github.com/apple/swift-protobuf.git", exact: "1.37.0"),
        .package(url: "https://github.com/apple/swift-argument-parser.git", from: "1.5.0"),
    ],
    targets: [
        .target(
            name: "PalaceSwiftScipEmitCore",
            dependencies: [
                .product(name: "IndexStoreDB", package: "indexstore-db"),
                .product(name: "SwiftProtobuf", package: "swift-protobuf"),
            ],
            exclude: ["Proto/scip.proto"]  // .proto vendored; .pb.swift is the actual generated source
        ),
        .executableTarget(
            name: "PalaceSwiftScipEmitCLI",
            dependencies: [
                "PalaceSwiftScipEmitCore",
                .product(name: "ArgumentParser", package: "swift-argument-parser"),
            ]
        ),
        .testTarget(
            name: "PalaceSwiftScipEmitCoreTests",
            dependencies: ["PalaceSwiftScipEmitCore"]
        ),
    ]
)
```

The `indexstore-db` revision is locked by CTO Phase 1.1. Task 3 is still the runtime proof: if this SHA cannot read the operator's Xcode 26 `Index.noindex/DataStore`, stop before Phase 2 and return to spec rev4 with diagnostic transcripts.

- [ ] **Step 2: Write CLI main.swift skeleton (--help works)**

```swift
import ArgumentParser
import Foundation
import PalaceSwiftScipEmitCore

@main
struct PalaceSwiftScipEmit: ParsableCommand {
    static let configuration = CommandConfiguration(
        commandName: "palace-swift-scip-emit",
        abstract: "Emit canonical Sourcegraph SCIP protobuf from Xcode IndexStoreDB.",
        version: "0.1.0"
    )

    @Option(name: .long, help: "Path to Xcode DerivedData root for the project.")
    var derivedData: String

    @Option(name: .long, help: "Project root path (used for relative-path normalization).")
    var projectRoot: String

    @Option(name: [.short, .long], help: "Output path for SCIP protobuf file.")
    var output: String

    @Option(name: .long, parsing: .upToNextOption,
            help: "Optional include path globs (relative to project-root). Default: all in-project paths.")
    var include: [String] = []

    @Option(name: .long, parsing: .upToNextOption,
            help: "Optional exclude path globs (in addition to system-framework defaults). Default: empty (only system frameworks excluded).")
    var exclude: [String] = []

    @Flag(help: "Verbose progress output.")
    var verbose: Bool = false

    mutating func run() throws {
        FileHandle.standardError.write("palace-swift-scip-emit 0.1.0 — Phase 1 Task 1 skeleton\n".data(using: .utf8)!)
        FileHandle.standardError.write("Not yet implemented; stay tuned for Tasks 2-8.\n".data(using: .utf8)!)
        throw ExitCode.failure
    }
}
```

- [ ] **Step 3: Write Core placeholder**

```swift
// Sources/PalaceSwiftScipEmitCore/Placeholder.swift
import Foundation

public enum PalaceSwiftScipEmitCore {
    public static let version = "0.1.0"
    // Real implementation lands in Tasks 3-7.
}
```

- [ ] **Step 4: Write .gitignore**

```
.build/
.swiftpm/
.index-store/
DerivedData/
*.xcodeproj/
*.scip
.DS_Store
```

- [ ] **Step 5: Write README.md**

```markdown
# palace-swift-scip-emit

Custom Swift emitter that reads Xcode IndexStoreDB and emits canonical Sourcegraph SCIP protobuf for ingestion by palace-mcp's `symbol_index_swift` extractor.

## Build (dev Mac only)

    cd services/palace-mcp/scip_emit_swift
    xcrun swift build -c release

Binary at `.build/release/palace-swift-scip-emit-cli`.

## Required toolchain (dev Mac)

- Xcode 16+ (operator's session captured 26.3 — works)
- `protoc` ≥ 25.x (`brew install protobuf`)
- `protoc-gen-swift` matching the swift-protobuf SPM dep (`brew install swift-protobuf`); used at proto regeneration time only — not needed for incremental builds since `.pb.swift` is committed
- iMac is NOT a build host — see `docs/research/2026-05-01-swift-indexstore-spike.md` for context

## Run

    palace-swift-scip-emit \
        --derived-data ~/Library/Developer/Xcode/DerivedData/MyProject-xxxxx \
        --project-root /path/to/MyProject \
        --output myproject.scip

Output is a Sourcegraph SCIP protobuf file consumable by `palace-mcp`'s `parse_scip_file()`.

## Why custom

See `docs/research/2026-05-01-swift-indexstore-spike.md` for the Phase 1.0 NO-GO evidence on SwiftSCIPIndex (community) and the rationale for this custom emitter (Option C, GIM-128 spec rev3).
```

- [ ] **Step 6: Verify build (skeleton compiles, --help works)**

```bash
cd services/palace-mcp/scip_emit_swift
xcrun swift build -c release 2>&1 | tail -5
.build/release/palace-swift-scip-emit-cli --help
```

Expected: build completes; --help prints usage including all flags.

> **Phase 1.1 pin:** `indexstore-db` is locked to `4ee7a49edc48e94361c3477623deeffb25dbed0d`. Build may succeed before runtime read is proven; Task 3 remains the hard stop if Xcode 26 records produce 0 USRs.

- [ ] **Step 7: Commit**

```bash
git add services/palace-mcp/scip_emit_swift/
git commit -m "chore(GIM-128): scip_emit_swift SPM scaffold — Core lib + CLI exec split (Phase 1 Task 1)"
```

---

### Task 2: Vendor + generate scip.proto bindings

**Files:**
- Create: `services/palace-mcp/scip_emit_swift/Sources/PalaceSwiftScipEmitCore/Proto/scip.proto`
- Create: `services/palace-mcp/scip_emit_swift/Sources/PalaceSwiftScipEmitCore/Proto/scip.pb.swift` (generated)
- Create: `services/palace-mcp/scip_emit_swift/Tests/PalaceSwiftScipEmitCoreTests/ProtoSmokeTests.swift`

- [ ] **Step 1: Vendor scip.proto from scip-code/scip**

Pin to the exact tag confirmed during Phase 1.1: `scip-code/scip` `v0.7.1`. This matches the currently deployed Python proto line (`github.com/scip-code/scip/...` in `palace_mcp.proto.scip_pb2`).

```bash
cd services/palace-mcp/scip_emit_swift/Sources/PalaceSwiftScipEmitCore/Proto/
curl -fsSLo scip.proto https://raw.githubusercontent.com/scip-code/scip/v0.7.1/scip.proto
shasum -a 256 scip.proto
# Expected: 387f91bea3357a6ab72ae6214c569bf33fddcd3c726a8eacfa1435d65ac347e8  scip.proto
```

- [ ] **Step 2: Generate scip.pb.swift**

Requires `protoc` + `protoc-gen-swift` plugin. Install if missing:

```bash
brew install protobuf swift-protobuf
protoc --version              # expected: libprotoc 34.1
protoc-gen-swift --version    # expected: 1.37.0; must match swift-protobuf exact SPM dep
```

Generate:

```bash
cd services/palace-mcp/scip_emit_swift/Sources/PalaceSwiftScipEmitCore/Proto/
protoc --swift_out=. --swift_opt=Visibility=Public scip.proto
ls -la scip.pb.swift
```

Result: ~1500 LOC `scip.pb.swift` — vendored generated code. Commit verbatim. Re-run only when `scip.proto` source tag changes (not on every build).

- [ ] **Step 3: Write XCTest for empty Index roundtrip**

```swift
// Tests/PalaceSwiftScipEmitCoreTests/ProtoSmokeTests.swift
import XCTest
@testable import PalaceSwiftScipEmitCore
import SwiftProtobuf

final class ProtoSmokeTests: XCTestCase {
    func testEmptyIndexRoundtrip() throws {
        let idx = Scip_Index()
        let data = try idx.serializedData()
        let decoded = try Scip_Index(serializedData: data)
        XCTAssertEqual(decoded.documents.count, 0)
    }

    /// Writes an empty Scip_Index to a fixed temp path so a separate
    /// CI shell-step can verify Python parses it identically.
    /// (Avoids the bogus `swift run <<EOF` heredoc trick — Swift binaries
    /// do not eval stdin as Swift source.)
    func testEmptyIndexFileRoundtrip() throws {
        let tmp = FileManager.default.temporaryDirectory.appendingPathComponent("palace-empty-index.scip")
        let data = try Scip_Index().serializedData()
        try data.write(to: tmp)
        let reread = try Scip_Index(serializedData: try Data(contentsOf: tmp))
        XCTAssertEqual(reread.documents.count, 0)
        // Note: Python-side verification happens in regen.sh / CI shell-step,
        // NOT inside this Swift XCTest.
    }
}
```

- [ ] **Step 4: Run XCTest**

```bash
cd services/palace-mcp/scip_emit_swift
xcrun swift test 2>&1 | tail -5
```

Expected: 2 tests pass.

- [ ] **Step 5: Python parse check (separate post-build CI step)**

This is a SHELL command (not embedded inside Swift test). Run after `swift test` succeeds:

```bash
# Re-run the file-write test as a post-build verification step
xcrun swift test --filter ProtoSmokeTests/testEmptyIndexFileRoundtrip
# That XCTest writes /var/folders/.../palace-empty-index.scip — find it
TMPFILE=$(find $TMPDIR -name "palace-empty-index.scip" 2>/dev/null | head -1)
test -n "$TMPFILE" && cp "$TMPFILE" /tmp/empty.scip

cd /Users/ant013/Android/Gimle-Palace/services/palace-mcp
uv run python -c "
from palace_mcp.proto import scip_pb2
idx = scip_pb2.Index()
idx.ParseFromString(open('/tmp/empty.scip','rb').read())
print(f'parsed: documents={len(idx.documents)}')
assert len(idx.documents) == 0
print('OK — Python proto byte-compatibility verified.')
"
```

Expected: `parsed: documents=0` + `OK`.

- [ ] **Step 6: Commit**

```bash
git add services/palace-mcp/scip_emit_swift/Sources/PalaceSwiftScipEmitCore/Proto/ services/palace-mcp/scip_emit_swift/Tests/
git commit -m "chore(GIM-128): vendor scip.proto + generated swift bindings + ProtoSmoke XCTests (Phase 1 Task 2)"
```

---

### Task 3: IndexStoreReader — minimal hello-world + critical-gate diagnostic

> Goal: prove `indexstore-db` SPM dep can read Xcode 26's DataStore at all. If this works, the format-mismatch problem from Phase 1.0 NO-GO is in SwiftSCIPIndex, not in indexstore-db itself.
>
> **Critical gate:** if step 4 returns 0 USRs (the SwiftSCIPIndex symptom on Xcode 26), execute the diagnostic checklist in Step 5 BEFORE escalating to spec rev4. The diagnostic narrows the failure to one of: missing DataStore path, wrong libIndexStore path, indexstore-db API mismatch, or a permissions/env issue.

**Files:**
- Create: `services/palace-mcp/scip_emit_swift/Sources/PalaceSwiftScipEmitCore/IndexStoreReader.swift`

- [ ] **Step 1: Write minimal IndexStoreReader**

```swift
import Foundation
import IndexStoreDB

/// Wraps IndexStoreDB queries for SCIP emit.
///
/// Locates `Index.noindex/DataStore` (Xcode 14+) or `Index/DataStore` (older Xcode)
/// inside DerivedData; iterates units + occurrences per source file.
struct IndexStoreReader {
    let derivedData: URL
    let projectRoot: URL
    private let store: IndexStoreDB

    init(derivedDataPath: URL, projectRoot: URL, libIndexStorePath: URL? = nil) throws {
        self.derivedData = derivedDataPath
        self.projectRoot = projectRoot

        let dataStorePath = Self.locateDataStore(in: derivedDataPath)
        let libPath = libIndexStorePath ?? Self.defaultLibIndexStorePath()
        let lib = try IndexStoreLibrary(dylibPath: libPath.path)

        // Database path: per-derived-data unique, so use derivedData itself + .palace-scip-cache
        let dbPath = derivedDataPath.appendingPathComponent(".palace-scip-cache")

        self.store = try IndexStoreDB(
            storePath: dataStorePath.path,
            databasePath: dbPath.path,
            library: lib,
            listenToUnitEvents: false
        )
        store.pollForUnitChangesAndWait()
    }

    private static func locateDataStore(in derivedData: URL) -> URL {
        let noindex = derivedData.appendingPathComponent("Index.noindex").appendingPathComponent("DataStore")
        if FileManager.default.fileExists(atPath: noindex.path) { return noindex }
        return derivedData.appendingPathComponent("Index").appendingPathComponent("DataStore")
    }

    private static func defaultLibIndexStorePath() -> URL {
        URL(fileURLWithPath: "/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/lib/libIndexStore.dylib")
    }

    /// Returns count of unique USRs reachable in the index. Phase 1 Task 3 proof-of-life.
    func countSymbols() -> Int {
        var seen = Set<String>()
        store.forEachCanonicalSymbolOccurrence(
            containing: "",
            anchorStart: false,
            anchorEnd: false,
            subsequence: true,
            ignoreCase: true
        ) { occ in
            seen.insert(occ.symbol.usr)
            return true
        }
        return seen.count
    }
}
```

- [ ] **Step 2: Wire into main.swift run() — quick smoke**

Replace the `throw ExitCode.failure` with:

```swift
let reader = try IndexStoreReader(
    derivedDataPath: URL(fileURLWithPath: derivedData),
    projectRoot: URL(fileURLWithPath: projectRoot)
)
let count = reader.countSymbols()
print("PalaceSwiftScipEmit: found \(count) unique USRs in \(derivedData)")
```

- [ ] **Step 3: Verify on synthetic SPM spike from Phase 1.0**

```bash
# Re-create the synthetic spike (it was at /tmp/uw-ios-spike/ during Phase 1.0)
mkdir -p /tmp/uw-ios-spike/Sources/UwSpike
# (... Wallet.swift content from Phase 1.0 spike ...)
cd /tmp/uw-ios-spike
xcrun swift build -Xswiftc -index-store-path -Xswiftc /tmp/uw-ios-spike/.index-store
mkdir -p .derived-data/Index && cp -R .index-store .derived-data/Index/DataStore

cd /Users/ant013/Android/Gimle-Palace/services/palace-mcp/scip_emit_swift
xcrun swift build -c release
.build/release/palace-swift-scip-emit-cli \
    --derived-data /tmp/uw-ios-spike/.derived-data \
    --project-root /tmp/uw-ios-spike \
    --output /tmp/spike.scip
```

**Expected:** `found NN unique USRs` where NN > 100 (likely 200-500 from Wallet.swift + system frameworks).

- [ ] **Step 4: Verify on real UW-ios DerivedData**

```bash
UW_DD=$(ls -t -d ~/Library/Developer/Xcode/DerivedData/UnstoppableWallet-* | head -1)
.build/release/palace-swift-scip-emit-cli \
    --derived-data "$UW_DD" \
    --project-root /Users/ant013/Ios/HorizontalSystems/unstoppable-wallet-ios \
    --output /tmp/uw-ios-task3.scip
```

**Expected:** USR count > 50000 (UW-ios + system frameworks).

- [ ] **Step 5: CRITICAL-GATE diagnostic (RUN ONLY IF Step 3 OR Step 4 RETURN 0)**

Before escalating to spec rev4, narrow the failure mode with these 4 diagnostic checks. Each is a separate one-liner; record outputs in REGEN.md or paperclip comment if escalating.

  **5.1 — DataStore path verification:**
  ```bash
  UW_DD=$(ls -t -d ~/Library/Developer/Xcode/DerivedData/UnstoppableWallet-* | head -1)
  ls -la "$UW_DD/Index.noindex/DataStore/v5/units/" 2>&1 | head -5
  find "$UW_DD/Index.noindex/DataStore/v5/records" -type f | wc -l
  ```
  Expected: tens of thousands of files. If 0 → IndexStoreDB has nothing to read; the project wasn't built with index-store enabled.

  **5.2 — libIndexStore.dylib path verification:**
  ```bash
  XCODE_PATH=$(xcode-select -p)
  ls -la "$XCODE_PATH/Toolchains/XcodeDefault.xctoolchain/usr/lib/libIndexStore.dylib"
  file "$XCODE_PATH/Toolchains/XcodeDefault.xctoolchain/usr/lib/libIndexStore.dylib"
  ```
  Expected: file exists, reports as Mach-O dynamic library. If missing → wrong xcode-select target or non-default Xcode install.

  **5.3 — Direct minimal IndexStoreDB API call:**
  Add a temporary test target/script that constructs `IndexStoreDB` and immediately catches errors with `try?` and stderr-prints the result. Common failure patterns: `failed to load library`, `corrupt store`, `version mismatch`, `database lock contention`. Record exact error message.

  **5.4 — Known-symbol query:**
  If 5.1-5.3 show no errors but `forEachCanonicalSymbolOccurrence` still returns 0, try a targeted query for a USR you know exists (e.g., a Foundation type's USR). If THAT returns 0, the iteration API is broken on this Xcode version. If it returns >0, the issue is the broad-iteration API specifically.

  **Decision:**
  - All 4 diagnostics show indexstore-db works → bug is in our IndexStoreReader code; fix and retry.
  - 5.1 shows empty DataStore → re-build target project with `xcodebuild` (not `swift build`); re-run.
  - 5.2 shows missing dylib → fix xcode-select or pass `--lib-index-store-path` flag (add to CLI if not present).
  - 5.3-5.4 show indexstore-db API errors → escalate to spec rev4 with diagnostic transcripts attached.

- [ ] **Step 6: Commit**

```bash
git add services/palace-mcp/scip_emit_swift/Sources/PalaceSwiftScipEmitCore/IndexStoreReader.swift services/palace-mcp/scip_emit_swift/Sources/PalaceSwiftScipEmitCLI/main.swift
git commit -m "feat(GIM-128): IndexStoreReader hello-world + critical-gate diagnostic (Phase 1 Task 3)"
```

---

### Task 4: ScipEmitter — emit one document, one symbol

**Files:**
- Create: `services/palace-mcp/scip_emit_swift/Sources/PalaceSwiftScipEmitCore/ScipEmitter.swift`
- Update: `services/palace-mcp/scip_emit_swift/Sources/PalaceSwiftScipEmitCLI/main.swift`

- [ ] **Step 1: Write ScipEmitter — minimal Index builder**

```swift
import Foundation
import IndexStoreDB
import SwiftProtobuf

/// Builds a Sourcegraph SCIP protobuf Index from IndexStoreReader output.
///
/// Phase 1 Task 4: one document, one symbol — proof-of-life.
/// Phase 1 Task 6 expands to full iteration.
struct ScipEmitter {
    let reader: IndexStoreReader
    let projectRoot: URL

    func emit(toolName: String = "palace-swift-scip-emit", toolVersion: String = "0.1.0") throws -> Scip_Index {
        var idx = Scip_Index()
        idx.metadata.version = .unspecifiedProtocolVersion  // SCIP 0.x
        idx.metadata.toolInfo.name = toolName
        idx.metadata.toolInfo.version = toolVersion
        idx.metadata.projectRoot = "file://\(projectRoot.path)"
        idx.metadata.textDocumentEncoding = .utf8

        // Phase 1 Task 4: emit a stub document with one symbol.
        // Replaced in Task 6 with full iteration.
        var doc = Scip_Document()
        doc.relativePath = "STUB_TASK4"
        doc.language = "swift"
        var occ = Scip_Occurrence()
        occ.symbol = "stub-task4-symbol"
        occ.symbolRoles = Int32(Scip_SymbolRole.definition.rawValue)
        doc.occurrences.append(occ)
        idx.documents.append(doc)

        return idx
    }
}
```

- [ ] **Step 2: Wire into main.swift**

```swift
let reader = try IndexStoreReader(
    derivedDataPath: URL(fileURLWithPath: derivedData),
    projectRoot: URL(fileURLWithPath: projectRoot)
)
let emitter = ScipEmitter(reader: reader, projectRoot: URL(fileURLWithPath: projectRoot))
let index = try emitter.emit()

let outputURL = URL(fileURLWithPath: output)
try index.serializedData().write(to: outputURL)
print("Emitted \(index.documents.count) documents to \(output)")
```

- [ ] **Step 3: Run on spike + verify Python parses output**

```bash
.build/release/palace-swift-scip-emit \
    --derived-data /tmp/uw-ios-spike/.derived-data \
    --project-root /tmp/uw-ios-spike \
    --output /tmp/task4.scip

cd /Users/ant013/Android/Gimle-Palace/services/palace-mcp
uv run python -c "
from palace_mcp.proto import scip_pb2
idx = scip_pb2.Index()
idx.ParseFromString(open('/tmp/task4.scip','rb').read())
print(f'metadata.tool_info.name={idx.metadata.tool_info.name!r}')
print(f'documents={len(idx.documents)}')
for d in idx.documents:
    print(f'  doc {d.relative_path!r} lang={d.language!r} occ={len(d.occurrences)}')
    for o in d.occurrences:
        print(f'    sym={o.symbol!r} roles={o.symbol_roles}')
"
```

**Expected:**
```
metadata.tool_info.name='palace-swift-scip-emit'
documents=1
  doc 'STUB_TASK4' lang='swift' occ=1
    sym='stub-task4-symbol' roles=1
```

This proves the byte-pipeline is end-to-end Swift → protobuf → Python parse. AC#11 partially satisfied.

- [ ] **Step 4: Commit**

```bash
git add services/palace-mcp/scip_emit_swift/Sources/PalaceSwiftScipEmitCore/
git commit -m "feat(GIM-128): ScipEmitter stub doc/symbol; verified Python parse (Phase 1 Task 4)"
```

---

### Task 5: SymbolBuilder — USR-as-descriptor stable identity + DisplayNameBuilder pretty FQN

> Goal: produce stable SCIP `symbol` field that disambiguates Swift overloads, extensions, generics, protocol methods reliably. Per spec rev3, identity uses USR; pretty FQN is a separate field.
>
> **Why USR-as-descriptor (rev3 reformulation):** IndexStoreDB-USR equality is the only reliable way to track the same logical symbol across documents in Swift. Hand-built FQN schemes (the rev1 prefix-length-then-suffix approach) collapse on overloaded methods, generic specializations, extension methods, and protocol witnesses. USRs are Apple-maintained and stable across builds within a project.

**Files:**
- Create: `services/palace-mcp/scip_emit_swift/Sources/PalaceSwiftScipEmitCore/SymbolBuilder.swift`
- Create: `services/palace-mcp/scip_emit_swift/Sources/PalaceSwiftScipEmitCore/DisplayNameBuilder.swift`
- Create: `services/palace-mcp/scip_emit_swift/Tests/PalaceSwiftScipEmitCoreTests/SymbolBuilderTests.swift`
- Create: `services/palace-mcp/scip_emit_swift/Tests/PalaceSwiftScipEmitCoreTests/DisplayNameTests.swift`

- [ ] **Step 1: Sourcegraph SCIP symbol grammar reference**

```
<scheme> ' ' <manager> ' ' <package-name> ' ' <package-version> ' ' <descriptor>+
```

For Swift v1 (rev3):
- `scheme`: `scip-swift`
- `manager`: `apple` (per GIM-105 rev2 Variant B)
- `package-name`: module name extracted from USR (e.g., `UwSpike`, `UwMiniCore`); fallback `UnknownModule` for USRs without recognizable mangling
- `package-version`: `.` (placeholder — Variant B "strip")
- `descriptor`: percent-escaped USR (NOT a hand-built name+suffix chain)

Example:
- USR `s:5UwSpike11WalletStoreC6select1iyS_tF` → SCIP symbol `scip-swift apple UwSpike . s%3A5UwSpike11WalletStoreC6select1iyS_tF` (the `:` after `s` is percent-encoded as `%3A`).

This is OPAQUE to descriptor-walking tools but cross-document-stable. palace-mcp join is by string equality, not parsing.

- [ ] **Step 2: Write SymbolBuilder (USR identity)**

```swift
import Foundation
import IndexStoreDB

/// Builds SCIP `symbol` field using USR-as-descriptor (rev3 stable-identity scheme).
public enum SymbolBuilder {
    /// Build the SCIP symbol string for an IndexStoreDB USR.
    public static func scipSymbol(usr: String) -> String {
        let module = extractModule(usr: usr) ?? "UnknownModule"
        let escaped = escapeForSCIPDescriptor(usr)
        return "scip-swift apple \(module) . \(escaped)"
    }

    /// Extract module name from a Swift USR (`s:<len><module>...`). Returns nil for non-Swift or unparseable.
    public static func extractModule(usr: String) -> String? {
        guard usr.hasPrefix("s:") else { return nil }
        let rest = String(usr.dropFirst(2))
        guard let firstDigit = rest.firstIndex(where: { $0.isNumber }) else { return nil }
        var lenStr = ""
        var idx = firstDigit
        while idx < rest.endIndex, rest[idx].isNumber {
            lenStr.append(rest[idx])
            idx = rest.index(after: idx)
        }
        guard let len = Int(lenStr), len > 0,
              rest.distance(from: idx, to: rest.endIndex) >= len else { return nil }
        let endIdx = rest.index(idx, offsetBy: len)
        return String(rest[idx..<endIdx])
    }

    /// Percent-encode characters that are special in SCIP descriptor grammar.
    /// Per scip.proto SCIP_SYMBOL grammar, these are: space, `(`, `)`, `,`, `.`, `:`,
    /// `/`, `[`, `]`, `<`, `>`, `\`, `#`, backtick. Use percent-encoding for stability.
    public static func escapeForSCIPDescriptor(_ s: String) -> String {
        var out = ""
        out.reserveCapacity(s.count)
        for ch in s.unicodeScalars {
            switch ch {
            case " ":  out += "%20"
            case "(":  out += "%28"
            case ")":  out += "%29"
            case ",":  out += "%2C"
            case ".":  out += "%2E"
            case ":":  out += "%3A"
            case "/":  out += "%2F"
            case "[":  out += "%5B"
            case "]":  out += "%5D"
            case "<":  out += "%3C"
            case ">":  out += "%3E"
            case "\\": out += "%5C"
            case "#":  out += "%23"
            case "`":  out += "%60"
            default:
                out.unicodeScalars.append(ch)
            }
        }
        return out
    }
}
```

- [ ] **Step 3: Write DisplayNameBuilder (pretty FQN; NOT identity)**

```swift
import Foundation
import IndexStoreDB

/// Builds human-readable display name for `Scip_SymbolInformation.display_name`.
/// This is a UX field and is NOT used for cross-document join — that role belongs to SymbolBuilder.scipSymbol.
public enum DisplayNameBuilder {
    public static func displayName(name: String, kind: IndexSymbolKind, parentChain: [String] = []) -> String {
        let suffix: String
        switch kind {
        case .class, .struct, .enum, .protocol, .extension, .typealias, .associatedtype:
            suffix = "#"
        case .instanceMethod, .classMethod, .staticMethod, .constructor, .destructor,
             .function, .freeFunction:
            suffix = "()."
        case .instanceProperty, .classProperty, .staticProperty,
             .variable, .field, .parameter, .enumConstant, .enumerator:
            suffix = "."
        default:
            suffix = "."
        }
        return (parentChain + ["\(name)\(suffix)"]).joined()
    }
}
```

- [ ] **Step 4: Write unit tests for SymbolBuilder (USR-based identity)**

```swift
import XCTest
@testable import PalaceSwiftScipEmitCore

final class SymbolBuilderTests: XCTestCase {
    func testStructUSRSymbol() {
        let s = SymbolBuilder.scipSymbol(usr: "s:5UwSpike6WalletV")
        XCTAssertEqual(s, "scip-swift apple UwSpike . s%3A5UwSpike6WalletV")
    }

    func testMethodUSRSymbol() {
        let s = SymbolBuilder.scipSymbol(usr: "s:5UwSpike11WalletStoreC6select1iyS_tF")
        XCTAssertEqual(s, "scip-swift apple UwSpike . s%3A5UwSpike11WalletStoreC6select1iyS_tF")
    }

    func testOverloadDisambiguation() {
        // Two methods named `select` with different signatures have different USRs.
        // Stable identity preserves disambiguation; hand-built FQN would collide.
        let s1 = SymbolBuilder.scipSymbol(usr: "s:5UwSpike11WalletStoreC6select1iyS_tF")
        let s2 = SymbolBuilder.scipSymbol(usr: "s:5UwSpike11WalletStoreC6select5walletyAA0E0_pF")
        XCTAssertNotEqual(s1, s2)
    }

    func testNonSwiftUSR() {
        // ObjC USRs use different mangling — emit with UnknownModule fallback.
        let s = SymbolBuilder.scipSymbol(usr: "c:objc(cs)NSObject")
        XCTAssertEqual(s, "scip-swift apple UnknownModule . c%3Aobjc%28cs%29NSObject")
    }

    func testExtractModule() {
        XCTAssertEqual(SymbolBuilder.extractModule(usr: "s:5UwSpike6WalletV"), "UwSpike")
        XCTAssertEqual(SymbolBuilder.extractModule(usr: "s:11UwMiniCore6WalletV"), "UwMiniCore")
        XCTAssertNil(SymbolBuilder.extractModule(usr: "c:objc(cs)NSObject"))
    }

    func testEscapeForSCIPDescriptor() {
        XCTAssertEqual(SymbolBuilder.escapeForSCIPDescriptor("a:b.c(d)"), "a%3Ab%2Ec%28d%29")
    }
}
```

- [ ] **Step 5: Write unit tests for DisplayNameBuilder**

```swift
import XCTest
@testable import PalaceSwiftScipEmitCore

final class DisplayNameTests: XCTestCase {
    func testStruct() {
        XCTAssertEqual(DisplayNameBuilder.displayName(name: "Wallet", kind: .struct, parentChain: []), "Wallet#")
    }
    func testNestedMethod() {
        XCTAssertEqual(
            DisplayNameBuilder.displayName(name: "select", kind: .instanceMethod, parentChain: ["WalletStore#"]),
            "WalletStore#select()."
        )
    }
    func testProperty() {
        XCTAssertEqual(
            DisplayNameBuilder.displayName(name: "selectedID", kind: .instanceProperty, parentChain: ["WalletStore#"]),
            "WalletStore#selectedID."
        )
    }
}
```

- [ ] **Step 6: Run tests**

```bash
cd services/palace-mcp/scip_emit_swift
xcrun swift test 2>&1 | tail -15
```

Expected: all SymbolBuilder + DisplayName tests pass.

- [ ] **Step 7: Commit**

```bash
git add services/palace-mcp/scip_emit_swift/Sources/PalaceSwiftScipEmitCore/SymbolBuilder.swift services/palace-mcp/scip_emit_swift/Sources/PalaceSwiftScipEmitCore/DisplayNameBuilder.swift services/palace-mcp/scip_emit_swift/Tests/
git commit -m "feat(GIM-128): SymbolBuilder USR-as-descriptor + DisplayNameBuilder pretty FQN (Phase 1 Task 5)"
```

---

### Task 6: Full iteration over units + occurrences

**Files:**
- Update: `services/palace-mcp/scip_emit_swift/Sources/PalaceSwiftScipEmitCore/IndexStoreReader.swift`
- Update: `services/palace-mcp/scip_emit_swift/Sources/PalaceSwiftScipEmitCore/ScipEmitter.swift`

- [ ] **Step 1: Add full-iteration API to IndexStoreReader**

```swift
extension IndexStoreReader {
    /// Group occurrences by source file (relative to projectRoot).
    /// Returns Dict<relative-path, [(usr, name, kind, role, line, column)]>.
    func collectOccurrencesByFile() -> [String: [OccurrenceRecord]] {
        var result: [String: [OccurrenceRecord]] = [:]
        var seenUSRs = Set<String>()

        store.forEachCanonicalSymbolOccurrence(
            containing: "", anchorStart: false, anchorEnd: false,
            subsequence: true, ignoreCase: true
        ) { canonical in
            seenUSRs.insert(canonical.symbol.usr)
            return true
        }

        for usr in seenUSRs {
            store.forEachSymbolOccurrence(byUSR: usr, roles: .all) { occ in
                let absPath = occ.location.path
                guard absPath.hasPrefix(projectRoot.path) else { return true }
                let relPath = String(absPath.dropFirst(projectRoot.path.count + 1))
                guard relPath.hasSuffix(".swift") else { return true }

                let rec = OccurrenceRecord(
                    usr: occ.symbol.usr,
                    name: occ.symbol.name,
                    kind: occ.symbol.kind,
                    roles: occ.roles,
                    line: occ.location.line,
                    column: occ.location.utf8Column,
                    relations: occ.relations.map { ($0.symbol.usr, $0.roles) }
                )
                result[relPath, default: []].append(rec)
                return true
            }
        }

        return result
    }
}

struct OccurrenceRecord {
    let usr: String
    let name: String
    let kind: IndexSymbolKind
    let roles: SymbolRole
    let line: Int
    let column: Int
    let relations: [(usr: String, roles: SymbolRole)]
}
```

- [ ] **Step 2: Update ScipEmitter.emit() to use full iteration with USR-based identity**

Replace the stub document with a real loop. Note: rev3 SymbolBuilder takes only `usr` (no `parentPath` parameter — USR alone is enough for stable identity). DisplayNameBuilder produces the human-readable form, which goes into `Scip_SymbolInformation.display_name`.

```swift
func emit(toolName: String = "palace-swift-scip-emit", toolVersion: String = "0.1.0") throws -> Scip_Index {
    var idx = Scip_Index()
    idx.metadata.version = .unspecifiedProtocolVersion
    idx.metadata.toolInfo.name = toolName
    idx.metadata.toolInfo.version = toolVersion
    idx.metadata.projectRoot = "file://\(projectRoot.path)"
    idx.metadata.textDocumentEncoding = .utf8

    let byFile = reader.collectOccurrencesByFile()

    // Sort for deterministic output (AC#12 — re-emit must be byte-identical)
    for (relPath, records) in byFile.sorted(by: { $0.key < $1.key }) {
        var doc = Scip_Document()
        doc.relativePath = relPath
        doc.language = "swift"

        // Sort by (line, column, usr) for deterministic occurrence order
        let sorted = records.sorted {
            ($0.line, $0.column, $0.usr) < ($1.line, $1.column, $1.usr)
        }

        var seenDefSymbols = Set<String>()
        for rec in sorted {
            var occ = Scip_Occurrence()
            occ.symbol = SymbolBuilder.scipSymbol(usr: rec.usr)
            occ.symbolRoles = mapRoles(rec.roles)
            occ.range = makeRange(line: rec.line, column: rec.column, name: rec.name)
            doc.occurrences.append(occ)

            // If DEF role and not already emitted: append a SymbolInformation entry to doc.symbols
            // with display_name set for human-readable identification.
            if rec.roles.contains(.definition) && !seenDefSymbols.contains(occ.symbol) {
                var info = Scip_SymbolInformation()
                info.symbol = occ.symbol
                info.kind = mapKind(rec.kind)
                info.displayName = DisplayNameBuilder.displayName(name: rec.name, kind: rec.kind)
                doc.symbols.append(info)
                seenDefSymbols.insert(occ.symbol)
            }
        }

        idx.documents.append(doc)
    }

    return idx
}

private func mapRoles(_ roles: SymbolRole) -> Int32 {
    var bits: Int32 = 0
    if roles.contains(.definition) { bits |= Int32(Scip_SymbolRole.definition.rawValue) }
    if roles.contains(.implicit) { bits |= Int32(Scip_SymbolRole.imported.rawValue) }
    // Other roles (reference, write-access, read-access) currently default to 0;
    // expand mapping in followup if needed.
    return bits
}

private func makeRange(line: Int, column: Int, name: String) -> [Int32] {
    // SCIP range: [start_line, start_char, end_line, end_char] (0-indexed)
    let start = Int32(line - 1)
    let startCol = Int32(column - 1)
    let endCol = Int32(column - 1 + name.utf8.count)
    return [start, startCol, start, endCol]
}

private func mapKind(_ k: IndexSymbolKind) -> Scip_SymbolInformation.Kind {
    switch k {
    case .class: return .class
    case .struct: return .struct
    case .enum: return .enum
    case .protocol: return .interface
    case .instanceMethod, .classMethod, .staticMethod: return .method
    case .function, .freeFunction: return .function
    case .instanceProperty, .classProperty, .staticProperty: return .property
    case .variable, .field: return .variable
    case .typealias: return .typealias
    case .extension: return .namespace
    default: return .unspecifiedKind
    }
}
```

The rev1 `enclosingChain()` helper is REMOVED — USR-based identity makes it unnecessary. `relations` field on `OccurrenceRecord` may also become unused; if so, drop it from the struct in this commit.

- [ ] **Step 3: Test on synthetic spike**

```bash
.build/release/palace-swift-scip-emit \
    --derived-data /tmp/uw-ios-spike/.derived-data \
    --project-root /tmp/uw-ios-spike \
    --output /tmp/task6.scip

cd /Users/ant013/Android/Gimle-Palace/services/palace-mcp
uv run python <<'PYEOF'
from palace_mcp.proto import scip_pb2
idx = scip_pb2.Index()
idx.ParseFromString(open('/tmp/task6.scip','rb').read())
print(f'documents={len(idx.documents)}')
total_occ = sum(len(d.occurrences) for d in idx.documents)
print(f'total occurrences={total_occ}')
for d in idx.documents[:3]:
    print(f'  {d.relative_path}  lang={d.language}  occ={len(d.occurrences)}  syms={len(d.symbols)}')
PYEOF
```

Expected: at least 1 document with `relative_path = Sources/UwSpike/Wallet.swift`, `language = "swift"`, and ≥10 occurrences, including DEFs for `Wallet`, `WalletStore`, `Counter`, `CounterHolder`.

- [ ] **Step 4: Commit**

```bash
git add services/palace-mcp/scip_emit_swift/Sources/PalaceSwiftScipEmitCore/
git commit -m "feat(GIM-128): full iteration emit; USR-based identity; deterministic order (Phase 1 Task 6)"
```

---

### Task 7: PathFilter — exclude only system + outside-root noise (vendor INSIDE root passes)

> Per spec rev3 AC#3: vendor classification is owned by the **Python extractor** (`symbol_index_swift.py`), not by the emitter. The emitter must NOT pre-filter `Pods/`, `Carthage/`, `SourcePackages/`, `.build/`, `.swiftpm/`, `DerivedData/` paths if they are inside `--project-root` — those must reach `.scip` so Phase 3 (vendor uses) ingestion has data.
>
> The emitter ONLY excludes:
> - paths outside `--project-root` (already enforced by IndexStoreReader's `hasPrefix(projectRoot.path)` guard in Task 6)
> - explicit user-provided `--exclude` globs (additive, not pre-set)
> - system-framework-installed paths (paths starting with `/Library/Developer/`, `/Applications/Xcode.app/`, `/Applications/Xcode-beta.app/`) — extra defense in case projectRoot is set unusually

**Files:**
- Create: `services/palace-mcp/scip_emit_swift/Sources/PalaceSwiftScipEmitCore/PathFilter.swift`
- Create: `services/palace-mcp/scip_emit_swift/Tests/PalaceSwiftScipEmitCoreTests/PathFilterTests.swift`
- Update: `services/palace-mcp/scip_emit_swift/Sources/PalaceSwiftScipEmitCLI/main.swift` (wire CLI `--include`/`--exclude` to PathFilter)

- [ ] **Step 1: Write PathFilter (permissive default)**

```swift
import Foundation

/// Path filter for the Swift SCIP emitter.
///
/// IMPORTANT (rev3 design): the emitter does NOT pre-classify vendor paths. Vendor
/// classification is owned by the Python extractor `symbol_index_swift.py`. This
/// filter excludes only system framework paths and user-supplied `--exclude` globs.
public struct PathFilter {
    public let includes: [String]
    public let excludes: [String]

    /// System-framework path prefixes always excluded. Emitter never emits these.
    /// (No project-vendor patterns — those are per-project and belong to Python extractor.)
    public static let alwaysExcludePrefixes: [String] = [
        "/Library/Developer/",
        "/Applications/Xcode.app/",
        "/Applications/Xcode-beta.app/",
    ]

    public init(includes: [String] = [], excludes: [String] = []) {
        self.includes = includes
        self.excludes = excludes
    }

    /// Return true if this path should be emitted into the .scip file.
    public func accepts(absolutePath: String, relativePath: String) -> Bool {
        // 1. Hard exclude: system framework paths
        if Self.alwaysExcludePrefixes.contains(where: { absolutePath.hasPrefix($0) }) {
            return false
        }
        // 2. User-supplied excludes
        if excludes.contains(where: { relativePath.contains($0) }) {
            return false
        }
        // 3. User-supplied includes (if specified)
        if !includes.isEmpty && !includes.contains(where: { relativePath.contains($0) }) {
            return false
        }
        return true
    }
}
```

- [ ] **Step 2: Write unit tests**

```swift
import XCTest
@testable import PalaceSwiftScipEmitCore

final class PathFilterTests: XCTestCase {
    func testAcceptsVendorInsideProject() {
        // CRITICAL: Pods/, Carthage/, SourcePackages/, .build/, .swiftpm/ ARE accepted by emitter.
        // The Python extractor classifies them as vendor at ingest time, not the emitter.
        let filter = PathFilter()
        XCTAssertTrue(filter.accepts(absolutePath: "/proj/Pods/Alamofire/Source/Alamofire.swift",
                                     relativePath: "Pods/Alamofire/Source/Alamofire.swift"))
        XCTAssertTrue(filter.accepts(absolutePath: "/proj/SourcePackages/checkouts/Alamofire/Source/Alamofire.swift",
                                     relativePath: "SourcePackages/checkouts/Alamofire/Source/Alamofire.swift"))
        XCTAssertTrue(filter.accepts(absolutePath: "/proj/.build/release/x.swift",
                                     relativePath: ".build/release/x.swift"))
    }

    func testAcceptsProjectSource() {
        let filter = PathFilter()
        XCTAssertTrue(filter.accepts(absolutePath: "/proj/UnstoppableWallet/UnstoppableWallet/Modules/Wallet.swift",
                                     relativePath: "UnstoppableWallet/UnstoppableWallet/Modules/Wallet.swift"))
    }

    func testRejectsSystemFrameworks() {
        let filter = PathFilter()
        XCTAssertFalse(filter.accepts(absolutePath: "/Library/Developer/CommandLineTools/usr/lib/swift/Foundation.swiftmodule/x.swiftinterface",
                                      relativePath: ".."))
        XCTAssertFalse(filter.accepts(absolutePath: "/Applications/Xcode.app/Contents/Developer/usr/lib/x.swift",
                                      relativePath: ".."))
    }

    func testUserExcludeAdditive() {
        // User can add ad-hoc excludes (e.g., a generated-code dir they don't want indexed)
        let filter = PathFilter(includes: [], excludes: ["GeneratedSources/"])
        XCTAssertFalse(filter.accepts(absolutePath: "/proj/GeneratedSources/Foo.swift",
                                      relativePath: "GeneratedSources/Foo.swift"))
        XCTAssertTrue(filter.accepts(absolutePath: "/proj/UwMiniCore/Wallet.swift",
                                     relativePath: "UwMiniCore/Wallet.swift"))
    }

    func testIncludeWhitelist() {
        let filter = PathFilter(includes: ["UwMiniCore/"], excludes: [])
        XCTAssertTrue(filter.accepts(absolutePath: "/proj/UwMiniCore/Wallet.swift",
                                     relativePath: "UwMiniCore/Wallet.swift"))
        XCTAssertFalse(filter.accepts(absolutePath: "/proj/UwMiniApp/AppDelegate.swift",
                                      relativePath: "UwMiniApp/AppDelegate.swift"))
    }
}
```

- [ ] **Step 3: Wire into ScipEmitter**

Update IndexStoreReader.collectOccurrencesByFile() to apply PathFilter when filtering occurrences. Replace the `hasPrefix(projectRoot.path)` + `hasSuffix(".swift")` check with PathFilter.accepts() in addition.

> Phase 2 wiring: the Python extractor (`symbol_index_swift.py`) phase-classifies based on path. So actually PathFilter on the emitter side is for `--exclude` only (skip system frameworks). Phase classification happens in Python. Simplify accordingly.

- [ ] **Step 4: Test**

```bash
xcrun swift test 2>&1 | tail -3
```

- [ ] **Step 5: Commit**

```bash
git add services/palace-mcp/scip_emit_swift/Sources/PalaceSwiftScipEmitCore/PathFilter.swift services/palace-mcp/scip_emit_swift/Tests/PalaceSwiftScipEmitCoreTests/PathFilterTests.swift services/palace-mcp/scip_emit_swift/Sources/PalaceSwiftScipEmitCore/ScipEmitter.swift
git commit -m "feat(GIM-128): PathFilter for emitter --exclude rules (Phase 1 Task 7)"
```

---

### Task 8: Phase 1 integration smoke + AC#4 branch lock

**Files:**
- Update: `services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project/REGEN.md` (NEW — write Phase 1.0+1.8 outcomes here)

- [ ] **Step 1: Run emitter on synthetic spike, capture Phase 1.0 generated-code visibility**

```bash
.build/release/palace-swift-scip-emit-cli \
    --derived-data /tmp/uw-ios-spike/.derived-data \
    --project-root /tmp/uw-ios-spike \
    --output /tmp/task8-spike.scip

cd /Users/ant013/Android/Gimle-Palace/services/palace-mcp
uv run python <<'PYEOF'
from palace_mcp.proto import scip_pb2
idx = scip_pb2.Index()
idx.ParseFromString(open('/tmp/task8-spike.scip','rb').read())

# AC#4 visibility checks
codable = []
observable = []
projected = []

for d in idx.documents:
    for o in d.occurrences:
        s = o.symbol
        if 'init(from:)' in s or 'encode(to:)' in s:
            codable.append(s)
        if '_$observationRegistrar' in s or 'withMutation' in s:
            observable.append(s)
        if s.endswith('._counter') or '$counter' in s:
            projected.append(s)

print(f'AC#4 Codable synthesis: {len(codable)} symbols')
for s in codable[:3]: print(f'  {s}')
print(f'AC#4 @Observable: {len(observable)}')
for s in observable[:3]: print(f'  {s}')
print(f'AC#4 Property wrapper $-projection: {len(projected)}')
for s in projected[:3]: print(f'  {s}')
PYEOF
```

- [ ] **Step 2: Lock AC#4 branch in REGEN.md (binary; rev3 removes B-1)**

Based on Step 1 output:

- All 3 categories non-zero → **Branch A**. Default emit captures everything; AC#4 hard.
- Any category zero → **Branch B-2**. Generated-code visibility tracked as a separate followup-issue (e.g., "Slice 3 followup — generated-code visibility via SwiftSyntax"). v1 narrows AC#4 to source-level symbols only.

Branch B-1 from rev1 is removed: `-Xswiftc -emit-symbol-graph` produces a separate `.symbols.json` artifact for DocC, not IndexStoreDB occurrences. It would not affect Step 1 results, so trying it would be wasted effort. If generated-code visibility is required, it goes in a separate followup that adds a parallel SwiftSyntax-based emit path.

Write decision into REGEN.md (`AC#4 Branch: A` or `AC#4 Branch: B-2 (followup-issue: GIM-XXX)`).

- [ ] **Step 3: Run emitter on real UW-ios DerivedData, capture vendor-noise paths**

```bash
UW_DD=$(ls -t -d ~/Library/Developer/Xcode/DerivedData/UnstoppableWallet-* | head -1)
.build/release/palace-swift-scip-emit-cli \
    --derived-data "$UW_DD" \
    --project-root /Users/ant013/Ios/HorizontalSystems/unstoppable-wallet-ios \
    --output /tmp/uw-ios-task8.scip

uv run python <<'PYEOF'
from collections import Counter
from palace_mcp.proto import scip_pb2
idx = scip_pb2.Index()
idx.ParseFromString(open('/tmp/uw-ios-task8.scip','rb').read())
prefixes = Counter()
for d in idx.documents:
    parts = d.relative_path.split('/')
    pref = '/'.join(parts[:2]) if len(parts) >= 2 else parts[0]
    prefixes[pref] += 1
for p, cnt in prefixes.most_common(20):
    print(f'  {cnt:>6}  {p}')
PYEOF
```

Expected top prefixes (for documentation in REGEN.md): `UnstoppableWallet/UnstoppableWallet`, `SourcePackages/`, `Pods/`, etc.

- [ ] **Step 4: Lock vendor-noise paths in REGEN.md**

Add section to REGEN.md classifying each prefix as PROJECT or VENDOR.

- [ ] **Step 5: Phase 1 GO/NO-GO signal**

| Check | Result |
|---|---|
| Emitter binary builds (Core lib + CLI exec) | PASS / FAIL |
| Synthetic spike: USR count > 100 | PASS / FAIL |
| Real UW-ios: USR count > 50000 | PASS / FAIL |
| Python parses output (canonical SCIP roundtrip) | PASS / FAIL |
| AC#4 branch locked | A / B-2 |
| Vendor paths enumerated; classification pasted in REGEN.md | PASS / FAIL |
| AC#12 EdgeCaseTests pass (Task 7.5) | PASS / FAIL |

If all PASS → **GO** for Phase 2 (PE Tasks 9-12).
If any FAIL → **NO-GO**, escalate to spec rev4 (with Step 5 critical-gate diagnostic transcripts attached if applicable).

- [ ] **Step 6: Push Phase 1 commits + paperclip update**

```bash
cd /Users/ant013/Android/Gimle-Palace
git push origin feature/GIM-128-ios-swift-extractor

# Paperclip comment on GIM-128:
# "Phase 1 GO. Emitter binary at scip_emit_swift/.build/release/palace-swift-scip-emit-cli.
#  Spike + UW-ios both work. AC#4 branch=<A/B-2>. Reassigning to PE for Phase 2."
```

---

### Task 7.5 (NEW per AC#12): Emitter edge-case XCTests

> Closes coverage gap on AC#12 from operator review of plan rev2: deterministic re-emit, missing DerivedData, empty IndexStore.

**Files:**
- Create: `services/palace-mcp/scip_emit_swift/Tests/PalaceSwiftScipEmitCoreTests/EdgeCaseTests.swift`

- [ ] **Step 1: Write XCTests for the 3 AC#12 cases**

```swift
import XCTest
import Foundation
@testable import PalaceSwiftScipEmitCore

final class EdgeCaseTests: XCTestCase {
    /// AC#12.1 — Deterministic re-emit: running emitter twice on the same DerivedData
    /// produces byte-identical .scip output.
    func testDeterministicReEmit() throws {
        // Pre-condition: synthetic spike is built (Phase 1 Task 3 setup)
        let spikeRoot = URL(fileURLWithPath: "/tmp/uw-ios-spike")
        let derivedData = spikeRoot.appendingPathComponent(".derived-data")
        guard FileManager.default.fileExists(atPath: derivedData.path) else {
            throw XCTSkip("Synthetic spike DerivedData not present; rerun Phase 1 Task 3 setup.")
        }

        let outA = FileManager.default.temporaryDirectory.appendingPathComponent("emit-a.scip")
        let outB = FileManager.default.temporaryDirectory.appendingPathComponent("emit-b.scip")

        try EmitterRunner.run(derivedData: derivedData, projectRoot: spikeRoot, output: outA)
        try EmitterRunner.run(derivedData: derivedData, projectRoot: spikeRoot, output: outB)

        let dataA = try Data(contentsOf: outA)
        let dataB = try Data(contentsOf: outB)
        XCTAssertEqual(dataA, dataB, "Two emitter runs against the same DerivedData should produce byte-identical output")
    }

    /// AC#12.2 — Missing DerivedData: emitter exits non-zero with actionable stderr.
    func testMissingDerivedDataExitsNonZero() throws {
        let bogus = URL(fileURLWithPath: "/tmp/no-such-derived-data-\(UUID().uuidString)")
        let projRoot = URL(fileURLWithPath: "/tmp")
        let out = FileManager.default.temporaryDirectory.appendingPathComponent("missing-dd.scip")

        do {
            try EmitterRunner.run(derivedData: bogus, projectRoot: projRoot, output: out)
            XCTFail("Should have thrown for missing DerivedData")
        } catch let error as EmitterError {
            // Expected: actionable diagnostic. Test the structured error case.
            switch error {
            case .derivedDataNotFound(let path):
                XCTAssertEqual(path, bogus.path)
            default:
                XCTFail("Wrong error case: \(error)")
            }
        }
    }

    /// AC#12.3 — Empty IndexStore: emitter exits 0 with valid empty Scip_Index.
    func testEmptyIndexStoreEmitsValidEmptyScip() throws {
        // Build a DerivedData layout with empty Index.noindex/DataStore
        let tmpDD = FileManager.default.temporaryDirectory.appendingPathComponent("empty-dd-\(UUID().uuidString)")
        let dataStore = tmpDD.appendingPathComponent("Index.noindex/DataStore/v5/records")
        try FileManager.default.createDirectory(at: dataStore, withIntermediateDirectories: true)

        let projRoot = FileManager.default.temporaryDirectory.appendingPathComponent("empty-proj-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: projRoot, withIntermediateDirectories: true)

        let out = FileManager.default.temporaryDirectory.appendingPathComponent("empty-out.scip")
        try EmitterRunner.run(derivedData: tmpDD, projectRoot: projRoot, output: out)

        // Output must be a valid SCIP Index proto with documents=[]
        let data = try Data(contentsOf: out)
        let parsed = try Scip_Index(serializedData: data)
        XCTAssertEqual(parsed.documents.count, 0)
        XCTAssertEqual(parsed.metadata.toolInfo.name, "palace-swift-scip-emit")
    }
}
```

- [ ] **Step 2: Provide minimal `EmitterRunner` + `EmitterError` in Core**

If not already factored out during Task 6, add a small Core entrypoint that the CLI calls AND tests use:

```swift
// PalaceSwiftScipEmitCore/EmitterRunner.swift
import Foundation

public enum EmitterError: Error {
    case derivedDataNotFound(path: String)
    case libIndexStoreNotFound(path: String)
    case readerInitFailed(underlying: Error)
}

public enum EmitterRunner {
    public static func run(derivedData: URL, projectRoot: URL, output: URL,
                           pathFilter: PathFilter = PathFilter()) throws {
        guard FileManager.default.fileExists(atPath: derivedData.path) else {
            throw EmitterError.derivedDataNotFound(path: derivedData.path)
        }
        let reader = try IndexStoreReader(derivedDataPath: derivedData, projectRoot: projectRoot)
        let emitter = ScipEmitter(reader: reader, projectRoot: projectRoot, pathFilter: pathFilter)
        let idx = try emitter.emit()
        try idx.serializedData().write(to: output)
    }
}
```

CLI `main.swift` collapses to:

```swift
mutating func run() throws {
    try EmitterRunner.run(
        derivedData: URL(fileURLWithPath: derivedData),
        projectRoot: URL(fileURLWithPath: projectRoot),
        output: URL(fileURLWithPath: output),
        pathFilter: PathFilter(includes: include, excludes: exclude)
    )
}
```

- [ ] **Step 3: Run XCTests**

```bash
cd services/palace-mcp/scip_emit_swift
xcrun swift test --filter EdgeCaseTests 2>&1 | tail -10
```

Expected: all 3 tests pass.

- [ ] **Step 4: Commit**

```bash
git add services/palace-mcp/scip_emit_swift/Sources/PalaceSwiftScipEmitCore/EmitterRunner.swift services/palace-mcp/scip_emit_swift/Tests/PalaceSwiftScipEmitCoreTests/EdgeCaseTests.swift services/palace-mcp/scip_emit_swift/Sources/PalaceSwiftScipEmitCLI/main.swift
git commit -m "test(GIM-128): AC#12 edge-case XCTests — deterministic, missing-DD, empty-IS (Phase 1 Task 7.5)"
```

---

## Phase 2: PE — Python extractor (after Phase 1 GO)

> Phase 2 wires the emitter output through palace-mcp's existing extractor framework. Tightly mirrors `symbol_index_java.py` (GIM-127). PE works on FB without rebuilding the Swift binary; PE depends on Phase 1 having committed a working binary tree.

### Task 9: Extractor scaffold + parser language map

**Files:**
- Create: `services/palace-mcp/src/palace_mcp/extractors/symbol_index_swift.py`
- Update: `services/palace-mcp/src/palace_mcp/extractors/scip_parser.py` (add Swift to language map)
- Update: `services/palace-mcp/src/palace_mcp/extractors/registry.py` (register)

- [ ] **Step 1: Add Swift to scip_parser language map**

```python
# scip_parser.py:209 (_SCIP_LANGUAGE_MAP) — add row
"swift": Language.SWIFT,

# scip_parser.py:230 (_language_from_path) — add fallback
".swift": Language.SWIFT,
".swiftinterface": Language.SWIFT,
```

`Language.SWIFT` already exists at `models.py:32`.

- [ ] **Step 2: Copy symbol_index_java.py → symbol_index_swift.py and adapt**

Differences vs Java:
- `name = "symbol_index_swift"`
- `description = "Swift symbol indexer for iOS/macOS projects."`
- `_SUPPORTED_LANGUAGES = (Language.SWIFT,)` (single — Swift only)
- **Swift-specific vendor path prefixes** (per spec rev3 AC#3 — vendor classification owned here, NOT by emitter):
  ```python
  _VENDOR_PATH_PREFIXES = (
      "Pods/",
      "Carthage/",
      "SourcePackages/",
      ".build/",
      ".swiftpm/",
      "DerivedData/",
  )
  ```
  An occurrence is classified as vendor (routed to `phase3_vendor_uses`) if `relative_path.startswith(any-of-prefix)` OR `<prefix>` appears as a path segment (mirror `symbol_index_java._is_vendor()` logic).
- `_VENDOR_USR_PREFIXES = ()` — Swift USRs are project-scoped; no USR-level filter needed.
- Phase ordering / Tantivy bridge usage / Neo4j checkpoint writing — IDENTICAL to Java extractor (3-phase bootstrap via 101a foundation; `write_checkpoint` writes IngestRun + 3 phase rows; `nodes_written` returned in `ExtractorStats` is Tantivy doc count).

- [ ] **Step 3: Register in registry.py**

```python
from palace_mcp.extractors.symbol_index_swift import SymbolIndexSwift
EXTRACTORS["symbol_index_swift"] = SymbolIndexSwift()
```

- [ ] **Step 4: Verify lint + import**

```bash
cd services/palace-mcp
uv run ruff check src/palace_mcp/extractors/symbol_index_swift.py
uv run mypy src/palace_mcp/extractors/symbol_index_swift.py
uv run python -c "from palace_mcp.extractors.symbol_index_swift import SymbolIndexSwift; print(SymbolIndexSwift.name)"
```

Expected: clean. Module imports.

- [ ] **Step 5: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/extractors/symbol_index_swift.py services/palace-mcp/src/palace_mcp/extractors/scip_parser.py services/palace-mcp/src/palace_mcp/extractors/registry.py
git commit -m "feat(GIM-128): symbol_index_swift extractor + Language.SWIFT in scip_parser (Phase 2 Task 9)"
```

---

### Task 10: Unit tests with mocked driver

**Files:**
- Create: `services/palace-mcp/tests/extractors/unit/test_symbol_index_swift.py`

- [ ] **Step 1: Write tests modeled on test_symbol_index_java.py**

Cover:
1. Phase 1 def emit (DEF role only, USE role suppressed)
2. Phase 2 user uses (USE role on non-vendor paths)
3. Phase 3 vendor uses (USE role on vendor paths)
4. Language detection (only Language.SWIFT processed)
5. Vendor path classification (Pods/, .build/, etc.)
6. Empty `.scip` handles gracefully
7. Unknown SymbolKind handled (UNKNOWN tagged in Tantivy, not error)
8. Cross-file refs preserved (USR shared between files)

- [ ] **Step 2: Run tests**

```bash
uv run pytest tests/extractors/unit/test_symbol_index_swift.py -v
```

Expected: all tests pass.

- [ ] **Step 3: Commit**

```bash
git add services/palace-mcp/tests/extractors/unit/test_symbol_index_swift.py
git commit -m "test(GIM-128): unit tests for symbol_index_swift (Phase 2 Task 10)"
```

---

### Task 11: Integration test with fixture

**Files:**
- Create: `services/palace-mcp/tests/extractors/integration/test_symbol_index_swift_integration.py`

> This task BLOCKS until Phase 3 (fixture creation) is complete — fixture's `index.scip` is required input.

- [ ] **Step 1: Write integration test**

Modeled on `test_symbol_index_java_integration.py`:

```python
import pytest
from pathlib import Path

@pytest.mark.integration
async def test_symbol_index_swift_full_run(neo4j_driver, tantivy_path, monkeypatch):
    fixture_scip = Path(__file__).parent.parent / "fixtures/uw-ios-mini-project/scip/index.scip"
    monkeypatch.setenv("PALACE_SCIP_INDEX_PATHS", f'{{"uw-ios-mini": "{fixture_scip}"}}')

    from palace_mcp.extractors.symbol_index_swift import SymbolIndexSwift
    from palace_mcp.extractors.foundation.context import ExtractorContext

    extractor = SymbolIndexSwift()
    ctx = ExtractorContext(
        project="uw-ios-mini",
        driver=neo4j_driver,
        tantivy_path=tantivy_path,
    )

    stats = await extractor.extract(ctx)

    # AC#1 — coverage. nodes_written is Tantivy doc count, NOT Neo4j node count.
    assert stats.nodes_written >= _UW_IOS_MINI_N_TANTIVY_DOCS_EXPECTED  # constant from REGEN.md oracle

    # AC#1 invariant — phase checkpoints written to Neo4j by 101a foundation.
    async with neo4j_driver.session() as s:
        result = await s.run(
            "MATCH (i:IngestRun {project: $p, source: $s}) "
            "RETURN i.phase1_defs AS p1, i.phase2_user_uses AS p2, i.phase3_vendor_uses AS p3, i.nodes_written AS nw "
            "ORDER BY i.completed_at DESC LIMIT 1",
            p="uw-ios-mini", s="extractor.symbol_index_swift",
        )
        record = await result.single()
        assert record["p1"] > 0   # phase1_defs populated
        assert record["p2"] > 0   # phase2_user_uses non-zero
        assert record["p3"] > 0   # phase3_vendor_uses live (rev3 invariant: just non-zero)
        assert record["nw"] == stats.nodes_written

    # AC#2 — DEF/USE roles distinguishable via Tantivy
    n_def, n_use = await _count_tantivy_roles(tantivy_path, "uw-ios-mini")
    assert n_def >= 50
    assert n_use >= 100

    # AC#5 — cross-file ref via Tantivy direct query (NOT Neo4j Symbol/SymbolOccurrence —
    # those nodes don't exist for this extractor family; symbol_index_java/_python/_typescript
    # only persist IngestRun + checkpoints to Neo4j, occurrences live in Tantivy).
    from palace_mcp.extractors.foundation.tantivy_bridge import TantivyBridge
    async with TantivyBridge.open_for_search(tantivy_path) as bridge:
        results = await bridge.search_by_symbol(
            symbol_qualified_name=_UW_IOS_MINI_CROSS_FILE_SYMBOL,  # locked in REGEN.md
            project="uw-ios-mini",
            limit=100,
        )
        paths = {r.relative_path for r in results}
        assert "UwMiniCore/Sources/UwMiniCore/WalletStore.swift" in paths
        assert "UwMiniApp/UwMiniApp/ContentView.swift" in paths

    # AC#6 — language detection
    n_swift, n_unknown = await _count_tantivy_languages(tantivy_path, "uw-ios-mini")
    assert n_swift > 0
    assert n_unknown / (n_swift + n_unknown) < 0.05  # < 5% UNKNOWN
```

`_UW_IOS_MINI_N_TANTIVY_DOCS_EXPECTED` and `_UW_IOS_MINI_CROSS_FILE_SYMBOL` (the SCIP `symbol` field for `WalletStore.select(_:)` produced by the emitter — see SymbolBuilder USR-as-descriptor scheme) are constants locked in fixture `REGEN.md` (Phase 3 Task 16 oracle table).

> Note (rev3): `find_references` MCP tool (GIM-126 merged) is the production path for cross-file refs in app code. The integration test uses Tantivy direct query because `find_references` is an MCP tool layered above Tantivy and pulling its full path into pytest setup is heavier than the direct query. Both paths produce identical results since they share the same Tantivy index.

- [ ] **Step 2: Run integration test (fails until fixture exists)**

```bash
uv run pytest tests/extractors/integration/test_symbol_index_swift_integration.py -v
```

Expected (post-Phase 3): test passes. Before fixture exists: test fails with "fixture/scip/index.scip not found".

- [ ] **Step 3: Commit (test only; fixture deferred to Phase 3)**

```bash
git add services/palace-mcp/tests/extractors/integration/test_symbol_index_swift_integration.py
git commit -m "test(GIM-128): integration test scaffold for symbol_index_swift (Phase 2 Task 11)"
```

---

### Task 12: Documentation

**Files:**
- Update: `CLAUDE.md` (add symbol_index_swift to extractors table + operator workflow)
- Update: `services/palace-mcp/README.md` (if extractor list there)

- [ ] **Step 1: Update CLAUDE.md extractors section**

Add row to "Registered extractors" table:

```markdown
- `symbol_index_swift` — Swift symbol indexer for iOS/macOS projects (GIM-128).
  Reads a pre-generated `.scip` file produced by `palace-swift-scip-emit-cli`
  (custom emitter at `services/palace-mcp/scip_emit_swift/`, built on dev Mac via
  `xcrun swift build -c release`; iMac is runtime-only). Handles `.swift` and
  `.swiftinterface` files in one pass via per-document language auto-detection.
  Same 3-phase bootstrap as `symbol_index_python`. Uses `PALACE_SCIP_INDEX_PATHS`
  — set the project slug to the emitter output path. Vendor classification (
  `Pods/`, `Carthage/`, `SourcePackages/`, `.build/`, `.swiftpm/`, `DerivedData/`)
  is owned by the Python extractor at ingest time; emitter passes vendor
  occurrences through. SCIP scheme: `scip-swift apple <module> . <USR-escaped>`
  (USR-as-descriptor scheme — opaque to descriptor-walking but cross-document
  stable).
```

- [ ] **Step 2: Add operator workflow section**

```markdown
### Operator workflow: Swift / iOS symbol index

Custom emitter required (no first-party scip-swift exists). All emitter work runs on operator's dev Mac (Apple Silicon, modern Xcode). iMac is runtime-only.

1. Build emitter binary (one-time per dev Mac):
   ```bash
   cd services/palace-mcp/scip_emit_swift
   xcrun swift build -c release
   ```
   Binary: `.build/release/palace-swift-scip-emit-cli`.

2. Build target Swift project via `xcodebuild` to populate DerivedData:
   ```bash
   cd /path/to/swift-project
   xcodebuild -workspace Foo.xcworkspace -scheme Foo -destination "generic/platform=iOS Simulator" build
   ```

3. Emit `.scip` file:
   ```bash
   palace-swift-scip-emit-cli \
       --derived-data ~/Library/Developer/Xcode/DerivedData/Foo-xxxxx \
       --project-root /path/to/swift-project \
       --output /tmp/foo.scip
   ```

4. Transfer `.scip` to iMac (via scp or volume mount).

5. Update `.env` on iMac:
   ```
   PALACE_SCIP_INDEX_PATHS={..., "foo": "/repos/foo/scip/index.scip"}
   ```

6. Run extractor:
   ```
   palace.ingest.run_extractor(name="symbol_index_swift", project="foo")
   ```
```

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(GIM-128): symbol_index_swift extractor + operator workflow (Phase 2 Task 12)"
```

---

## Phase 3: PE — Fixture creation

### Task 13: Vendor fixture root configs

**Files:**
- Create: `services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project/LICENSE` (vendored from UW-ios)
- Create: `services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project/project.yml` (XcodeGen)
- Create: `services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project/regen.sh`
- Create: `services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project/.gitignore`

- [ ] **Step 1: Vendor LICENSE**

```bash
cp /Users/ant013/Ios/HorizontalSystems/unstoppable-wallet-ios/LICENSE \
   services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project/LICENSE
```

- [ ] **Step 2: Write project.yml (XcodeGen config)**

```yaml
name: UwMiniApp
options:
  bundleIdPrefix: io.horizontalsystems.uwmini
  deploymentTarget:
    iOS: "17.0"
  developmentLanguage: en
  createIntermediateGroups: true
packages:
  UwMiniCore:
    path: UwMiniCore
targets:
  UwMiniApp:
    type: application
    platform: iOS
    sources: [UwMiniApp]
    dependencies:
      - package: UwMiniCore
```

- [ ] **Step 3: Write regen.sh**

```bash
#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

# 1. Generate Xcode project from XcodeGen config
xcodegen generate

# 2. Build via xcodebuild (populates DerivedData with index store)
DERIVED_DATA="./.derived-data"
rm -rf "$DERIVED_DATA"
xcodebuild build \
    -workspace UwMiniApp.xcworkspace \
    -scheme UwMiniApp \
    -destination "generic/platform=iOS Simulator" \
    -derivedDataPath "$DERIVED_DATA"

# 3. Pin tool versions (must be installed; pinned in REGEN.md)
PROTOC_VERSION=$(protoc --version)
PROTOC_GEN_SWIFT_VERSION=$(protoc-gen-swift --version 2>&1 | head -1)
echo "protoc: $PROTOC_VERSION"
echo "protoc-gen-swift: $PROTOC_GEN_SWIFT_VERSION"
test "$PROTOC_VERSION" = "libprotoc 34.1"
test "$PROTOC_GEN_SWIFT_VERSION" = "1.37.0"
# (xcodegen + xcodebuild + xcrun swift versions also captured.)

# 4. Build emitter (if not already built)
EMITTER_REPO="../../../../../scip_emit_swift"
if [ ! -f "$EMITTER_REPO/.build/release/palace-swift-scip-emit-cli" ]; then
    (cd "$EMITTER_REPO" && xcrun swift build -c release)
fi

# 5. Run emitter
EMITTER="$EMITTER_REPO/.build/release/palace-swift-scip-emit-cli"
mkdir -p scip
"$EMITTER" \
    --derived-data "$DERIVED_DATA" \
    --project-root "$(pwd)" \
    --output scip/index.scip

# 6. Verify
echo "Generated index.scip ($(stat -f%z scip/index.scip) bytes)"
```

Make executable: `chmod +x regen.sh`.

- [ ] **Step 4: Write .gitignore**

```
.derived-data/
.build/
.swiftpm/
*.xcodeproj/
*.xcworkspace/
DerivedData/
.DS_Store
```

> Note: `scip/index.scip` is NOT gitignored — it's the committed binary fixture.

- [ ] **Step 5: Commit**

```bash
git add services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project/
git commit -m "test(GIM-128): uw-ios-mini-project fixture root configs (Phase 3 Task 13)"
```

---

### Task 14: Vendor 3 verbatim files from UW-ios

**Files:**
- Create: `services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project/UwMiniCore/Sources/UwMiniCore/Vendored/String+Hash.swift`
- Create: `services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project/UwMiniCore/Sources/UwMiniCore/Vendored/ColorPalette.swift`
- Create: `services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project/UwMiniCore/Sources/UwMiniCore/Vendored/DateFormatters.swift`

- [ ] **Step 1: Identify 3 small UW-ios source files to vendor verbatim**

Per spec rev3 — 3 files only. Pick small, self-contained, MIT-licensed files. Suggested:
- A `String` extension with hashing helper
- A color palette / brand colors enum
- A formatter utilities file

Search UW-ios source for candidates:

```bash
find /Users/ant013/Ios/HorizontalSystems/unstoppable-wallet-ios -name "*.swift" -size -3k | head -10
```

- [ ] **Step 2: Vendor each file under `UwMiniCore/Sources/UwMiniCore/Vendored/`**

Add comment block at top of each vendored file:

```swift
//
// Vendored verbatim from horizontalsystems/unstoppable-wallet-ios
// Source: <path/in/UW-ios>
// SHA: <UW-ios commit hash at vendoring time>
// License: MIT (see LICENSE)
//
```

- [ ] **Step 3: Commit**

```bash
git add services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project/UwMiniCore/Sources/UwMiniCore/Vendored/
git commit -m "test(GIM-128): vendor 3 verbatim files from UW-ios (Phase 3 Task 14)"
```

---

### Task 15: Synthesize ~27 fixture files

**Files:** ~27 new Swift files under `UwMiniCore/Sources/UwMiniCore/` and `UwMiniApp/UwMiniApp/`.

**File breakdown (target ~30 total including vendored 3):**

| Module | Files | Purpose |
|---|---|---|
| UwMiniCore (~15) | Wallet.swift, WalletStore.swift, Coin.swift, BlockchainKit.swift, Transaction.swift, Adapter.swift, Logger.swift, Configuration.swift, Reachability.swift, AppError.swift, Result+Extensions.swift, Async+Extensions.swift, JSON+Codable.swift, Hex.swift, BIP39.swift | Core domain models + utilities; demonstrate Codable, @Observable, generics, protocol-oriented design |
| UwMiniApp (~12) | AppDelegate.swift, ContentView.swift, MainTabView.swift, WalletListView.swift, WalletDetailView.swift, AddWalletView.swift, SettingsView.swift, AboutView.swift, ViewModifiers.swift, CustomColors.swift, AppCoordinator.swift, Bootstrap.swift | SwiftUI views + UIKit interop; demonstrate @State, @Binding, EnvironmentObject, navigation |
| Tests (~3) | UwMiniCoreTests.swift, WalletStoreTests.swift, BIP39Tests.swift | XCTest fixtures; demonstrate mock + assert + async test |

**Content pattern per file:** ~30-80 LOC each, idiomatic UW-ios style (similar naming, structure, comment density). Demonstrates the Swift idioms PE Phase 4.1 will assert on.

- [ ] **Step 1-N: Create files in batches**

Group into ~5 commits to keep diffs reviewable:
- Commit 1: UwMiniCore domain models (Wallet, Coin, Transaction, Adapter, BlockchainKit)
- Commit 2: UwMiniCore utilities (Logger, Configuration, Reachability, AppError, Result+Extensions)
- Commit 3: UwMiniCore async/codable/hex/BIP39
- Commit 4: UwMiniApp SwiftUI views (ContentView, MainTabView, WalletListView, WalletDetailView, AddWalletView)
- Commit 5: UwMiniApp settings + bootstrap (SettingsView, AboutView, ViewModifiers, CustomColors, AppCoordinator, Bootstrap, AppDelegate)
- Commit 6: Tests/ files

- [ ] **Final step: Verify fixture builds**

```bash
cd services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project
xcodegen generate
xcodebuild build -workspace UwMiniApp.xcworkspace -scheme UwMiniApp -destination "generic/platform=iOS Simulator" 2>&1 | tail -5
```

Expected: build succeeds.

---

### Task 16: Generate fixture index.scip + lock oracle

**Files:**
- Create: `services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project/scip/index.scip` (binary, committed)
- Update: REGEN.md (final oracle table)

- [ ] **Step 1: Run regen.sh**

```bash
cd services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project
bash regen.sh
ls -la scip/index.scip
```

Expected: `index.scip` ~50-200 KB.

- [ ] **Step 2: Lock oracle table in REGEN.md**

```bash
uv run python <<'PYEOF'
from palace_mcp.proto import scip_pb2
idx = scip_pb2.Index()
idx.ParseFromString(open('scip/index.scip','rb').read())

n_docs = len(idx.documents)
n_total_occ = sum(len(d.occurrences) for d in idx.documents)
n_total_def = sum(1 for d in idx.documents for o in d.occurrences if o.symbol_roles & 1)  # 1 = Definition bit
n_total_use = n_total_occ - n_total_def
n_unique_symbols = len({o.symbol for d in idx.documents for o in d.occurrences})
print(f'oracle: documents={n_docs}, occ={n_total_occ}, def={n_total_def}, use={n_total_use}, unique={n_unique_symbols}')
PYEOF
```

Update REGEN.md "Manual oracle table" with concrete numbers.

- [ ] **Step 3: Update Python integration test constants**

```python
# tests/extractors/integration/test_symbol_index_swift_integration.py
_UW_IOS_MINI_N_TANTIVY_DOCS_EXPECTED = <oracle: total Tantivy doc count, ±2% margin>
_UW_IOS_MINI_CROSS_FILE_SYMBOL = "scip-swift apple UwMiniCore . s%3A<USR-of-WalletStore.select>"
# (paste exact escaped USR captured in REGEN.md "Cross-file ref oracle" row)
```

- [ ] **Step 4: Commit fixture binary + REGEN.md + test updates**

```bash
git add services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project/scip/index.scip services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project/REGEN.md services/palace-mcp/tests/extractors/integration/test_symbol_index_swift_integration.py
git commit -m "test(GIM-128): commit fixture index.scip + oracle table + integration constants (Phase 3 Task 16)"
```

- [ ] **Step 5: Run full integration test against committed fixture**

```bash
cd services/palace-mcp
uv run pytest tests/extractors/integration/test_symbol_index_swift_integration.py -v
```

Expected: all assertions pass.

---

## Phase 4.1: QA — Live-smoke (Track A on iMac, Track B on dev Mac post-merge)

### Task 17: Track A — iMac fixture live-smoke (HARD MERGE GATE)

> Track A runs in palace-mcp container on iMac, ingesting the committed fixture. AC#1, #3, #5, #6, #8, #9 verified here. AC#2, #11, #12 verified at PE phase via Python tests; QA re-verifies on iMac through MCP.

**Pre-conditions:**
- All Phase 1-3 commits pushed to FB
- CR Phase 3.1 + Opus Phase 3.2 APPROVE
- iMac palace-mcp container rebuilt from FB head (manual `imac-deploy.sh`)
- `.env` on iMac has `PALACE_SCIP_INDEX_PATHS={..., "uw-ios-mini": "/repos/uw-ios-mini/scip/index.scip"}`
- Fixture mounted in docker-compose: `./services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project:/repos/uw-ios-mini:ro`

- [ ] **Step 1: ssh to iMac**

Operator opens tunnel: `ssh -L 8080:localhost:8080 imac-ssh.ant013.work`. QA agent runs commands via ssh transcript.

- [ ] **Step 2: Run extractor via MCP**

```
palace.ingest.run_extractor(name="symbol_index_swift", project="uw-ios-mini")
```

Capture `run_id` and `nodes_written` in evidence.

- [ ] **Step 3: Verify checkpoints in Neo4j**

```cypher
MATCH (i:IngestRun {project: "uw-ios-mini", source: "extractor.symbol_index_swift"})
WHERE i.run_id = "<from-step-2>"
RETURN i.phase1_defs, i.phase2_user_uses, i.phase3_vendor_uses, i.nodes_written, i.completed_at
```

- [ ] **Step 4: Verify cross-file refs via `palace.code.find_references` MCP tool**

```
palace.code.find_references(
    qualified_name="<exact SCIP symbol from REGEN.md cross-file oracle>",
    project="uw-ios-mini"
)
```

Expected: at least 2 results (DEF + ≥1 USE), with `relative_path` values including both `UwMiniCore/Sources/UwMiniCore/WalletStore.swift` and `UwMiniApp/UwMiniApp/ContentView.swift`.

- [ ] **Step 5: Verify language distribution via Tantivy MCP tool**

Use the MCP tool that wraps Tantivy aggregation queries (or a direct call into the container). Expected: `language="swift"` is the dominant value; `language="UNKNOWN"` is < 5%.

(Note: `:SymbolOccurrence` Neo4j nodes do NOT exist for this extractor — occurrences live in Tantivy only. A Cypher MATCH on `:SymbolOccurrence` would return empty. The aggregation must run against Tantivy.)

- [ ] **Step 6: Compose evidence comment**

Required in QA Phase 4.1 evidence (per `feedback_pe_qa_evidence_fabrication.md`):
- `date -u` before/after extractor run
- ssh transcript showing the actual MCP call
- `run_id` from real `palace.ingest.run_extractor` response
- Cypher result excerpts for each AC verification
- Path to fixture used (explicitly stated as `uw-ios-mini`, NOT relabeled as `uw-ios`)

Post evidence on GIM-128 paperclip with `[@CTO](agent://7fb0fdbb-...)` mention for Phase 4.2 handoff.

---

### Task 18: Track B — Real UW-ios live-smoke (DEFERRED-NOT-BLOCKED)

> Captured as separate followup-issue (e.g., GIM-129 "Slice 3 Track B — UW-ios real-source smoke"). Operator runs on dev Mac post-merge.

- Operator builds UW-ios via xcodebuild
- Operator runs `palace-swift-scip-emit` to emit `.scip`
- scp `.scip` to iMac
- iMac palace-mcp ingests via MCP
- AC#7 substantive criteria verified
- Evidence posted on followup-issue

> Do NOT block GIM-128 merge on Track B completion. Track A alone is the hard gate.

---

## Phase 4.2: CTO — Squash-merge

After Track A QA evidence + CR Phase 3.1 + Opus Phase 3.2 APPROVE:

1. Verify CI green on PR head: `gh pr checks <pr#>`
2. Squash-merge to develop: `gh pr merge <pr#> --squash`
3. Post Phase 4.2 confirmation comment on GIM-128
4. Close GIM-128 to status=done

> CTO MUST verify CI green via `gh pr checks` (per `feedback_cr_phase31_ci_verification.md`). Local pytest run is NOT sufficient — Linux CI may have subtle drift from macOS dev.

---

## Out of plan-rev2 scope

- **Slice 4 multi-repo SPM ingest** — separate slice; rev2 ships single-project ingest only.
- **iMac toolchain install** — irrelevant; emitter runs on dev Mac. iMac runs only the palace-mcp container with pre-generated `.scip`.
- **AGP 9 / Kotlin 2.3 retry** — Android concern, not this slice.
- **scip-swift first-party integration** — does not exist; our custom emitter IS the canonical path.
- **Slice 3 Track B execution** — deferred-not-blocked per spec rev3 §10.

---

## Self-review checklist (before paperclip handoff)

- [x] All ACs from spec rev3 mapped to specific plan tasks (cross-check below)
- [x] No `<TBD>` placeholders in code blocks (REGEN.md oracle values are TBD until fixture build, by design)
- [x] All commits have explicit messages (`feat`/`test`/`docs`/`chore`)
- [x] CTO Phase 1.1 has clear inputs: indexstore-db SHA pin, scip.proto tag pin, protoc + protoc-gen-swift versions, dev-Mac toolchain pinned in REGEN.md
- [x] PE Phase 2 has clear precondition (Phase 1 GO + Tasks 1-8 + 7.5 committed)
- [x] QA Phase 4.1 has explicit evidence requirements per `feedback_pe_qa_evidence_fabrication.md`
- [x] AC#11 (emitter builds) tested in Phase 1 Task 1, verified end-to-end Task 4
- [x] AC#12 (deterministic / missing-DD / empty-IS) covered by Task 7.5 EdgeCaseTests
- [x] AC#5 corrected to Tantivy contract (rev3) — no Cypher on `:Symbol`/`:SymbolOccurrence` (those nodes don't exist for this extractor family)
- [x] Vendor filtering owned by Python extractor (Task 9), NOT by emitter (Task 7); resolves AC#1/AC#3 conflict from earlier rev2 draft
- [x] SymbolBuilder uses USR-as-descriptor stable identity (Task 5), not hand-built FQN; resolves overload/extension/generic collision risk
- [x] AC#4 binary (A or B-2 only); B-1 removed
- [x] SPM split: Core library + CLI executable

### AC → Task mapping (rev3 corrected)

| AC | Task |
|---|---|
| #1 — Coverage (Tantivy doc count + checkpoint invariants) | Task 11 (integration test); Task 17 (Track A live-smoke) |
| #2 — DEF/USE roles distinguishable | Task 6 (emitter `mapRoles`); Task 11 (integration assert) |
| #3 — Vendor classification (Python-side) | Task 9 (Python `_VENDOR_PATH_PREFIXES`); Task 7 (emitter is permissive); Task 11 (assert) |
| #4 — Generated-code visibility (binary A/B-2) | Task 8 (spike + branch lock) |
| #5 — Cross-file refs (Tantivy / find_references) | Task 11 (Tantivy direct); Task 17 (find_references MCP) |
| #6 — Language detection per-document | Task 9 (parser map); Task 11 (assert) |
| #7 — Real UW-ios live-smoke | Task 18 (Track B, deferred) |
| #8 — Pipeline integration (IngestRun + checkpoints + Tantivy) | Task 17 |
| #9 — Track A merge gate | Task 17 |
| #10 — Track B captured but deferred | Task 18 |
| #11 — Emitter binary works | Tasks 1-6 (Phase 1) |
| #12 — Edge cases (deterministic / missing-DD / empty-IS) | Task 7.5 (NEW EdgeCaseTests) |
