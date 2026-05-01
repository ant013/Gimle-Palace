# Slice 3 — iOS Swift extractor (`symbol_index_swift`) Implementation Plan (rev2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `symbol_index_swift` extractor + `uw-ios-mini-project` fixture to palace-mcp. Implementation pivots (rev3 spec) to a **custom Swift emitter** (`palace-swift-scip-emit`) built on Apple's `indexstore-db` SPM package, emitting **canonical Sourcegraph SCIP protobuf**. This replaces the failed SwiftSCIPIndex (community) approach from rev1.

**Architecture:** Three layers in this slice:
1. **Swift emitter binary** (NEW, `services/palace-mcp/scip_emit/swift/`) — reads Xcode IndexStoreDB via `indexstore-db` SPM dep, emits `.scip` protobuf via `swift-protobuf`. Built on dev Mac only.
2. **Python extractor** (NEW, `symbol_index_swift.py`) — structurally identical to `symbol_index_java.py`. Reads emitter output via existing `parse_scip_file`. Runs in palace-mcp container.
3. **Fixture** (NEW, `uw-ios-mini-project/`) — hybrid SPM + Xcode app, ~30 files, regen via `palace-swift-scip-emit`. Pre-generated `.scip` committed.

**Tech stack:** Python 3.12 (palace-mcp), Swift 6+ (emitter + fixture), Xcode 16+, XcodeGen, swiftlang/indexstore-db (pinned), apple/swift-protobuf, sourcegraph/scip proto, pytest, testcontainers/compose-reuse Neo4j, Tantivy.

**Predecessor SHA:** `6492561` (GIM-127 Slice 1 Android merged 2026-04-30).
**Spec:** `docs/superpowers/specs/2026-04-30-ios-swift-extractor-rev3.md`.
**Phase 1.0 findings:** `docs/research/2026-05-01-swift-indexstore-spike.md`.
**Companion (NOT a blocker):** GIM-126 PR #70 (`find_references` lang-agnostic).

---

## Phase 1.0 — Spike (DONE 2026-05-01)

Operator + Board completed Phase 1.0 spike on dev Mac (macOS 26.3.1, Xcode 26.3, Swift 6.2.4). Outcome: SwiftSCIPIndex (community) is **NO-GO** on Xcode 26 (returns 0 symbols on real DerivedData; non-canonical output format). Operator approved pivot to **Option C (custom emitter)** documented in spec rev3.

Findings doc captures evidence + decision rationale. **Phase 1 below begins the new emitter implementation.**

---

## Phase 1: Build the Swift emitter binary (Board/operator + Implementer; ~3-4 days)

> Phase 1 produces the `palace-swift-scip-emit` binary. Until this binary exists and emits valid SCIP protobuf, Phase 2 (Python extractor) cannot integration-test. Phase 1 ends at Task 8 with a working binary that has been smoke-tested against a synthetic spike + the partial `uw-ios-mini-project` fixture.

### Task 1: SPM package scaffold

**Files:**
- Create: `services/palace-mcp/scip_emit/swift/Package.swift`
- Create: `services/palace-mcp/scip_emit/swift/Sources/PalaceSwiftScipEmit/main.swift`
- Create: `services/palace-mcp/scip_emit/swift/README.md`
- Create: `services/palace-mcp/scip_emit/swift/.gitignore`

- [ ] **Step 1: Write Package.swift**

```swift
// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "palace-swift-scip-emit",
    platforms: [.macOS(.v14)],
    products: [
        .executable(name: "palace-swift-scip-emit", targets: ["PalaceSwiftScipEmit"]),
    ],
    dependencies: [
        // indexstore-db: pin to a specific SHA known to work on Xcode 16+ (CTO confirms exact SHA in Phase 1.1)
        .package(url: "https://github.com/swiftlang/indexstore-db.git", revision: "TBD-pin-sha"),
        .package(url: "https://github.com/apple/swift-protobuf.git", from: "1.31.0"),
        .package(url: "https://github.com/apple/swift-argument-parser.git", from: "1.5.0"),
    ],
    targets: [
        .executableTarget(
            name: "PalaceSwiftScipEmit",
            dependencies: [
                .product(name: "IndexStoreDB", package: "indexstore-db"),
                .product(name: "SwiftProtobuf", package: "swift-protobuf"),
                .product(name: "ArgumentParser", package: "swift-argument-parser"),
            ],
            exclude: ["Proto/scip.proto"]
        ),
        .testTarget(
            name: "PalaceSwiftScipEmitTests",
            dependencies: ["PalaceSwiftScipEmit"]
        ),
    ]
)
```

The `revision: "TBD-pin-sha"` placeholder gets locked in Phase 1.1 by CTO. Pick a recent indexstore-db `main` SHA that the operator's Xcode 26 toolchain successfully reads. Verify by inspecting `git log` on the dependency.

- [ ] **Step 2: Write main.swift skeleton (--help works)**

```swift
import ArgumentParser
import Foundation

@main
struct PalaceSwiftScipEmit: ParsableCommand {
    static let configuration = CommandConfiguration(
        commandName: "palace-swift-scip-emit",
        abstract: "Emit canonical Sourcegraph SCIP protobuf from Xcode IndexStoreDB.",
        version: "0.1.0"
    )

    @Option(name: .long, help: "Path to Xcode DerivedData root for the project (e.g., ~/Library/Developer/Xcode/DerivedData/UnstoppableWallet-xxxxx).")
    var derivedData: String

    @Option(name: .long, help: "Project root path (used for relative-path normalization).")
    var projectRoot: String

    @Option(name: [.short, .long], help: "Output path for SCIP protobuf file.")
    var output: String

    @Option(name: .long, parsing: .upToNextOption, help: "Path glob to include (default: project root).")
    var include: [String] = []

    @Option(name: .long, parsing: .upToNextOption, help: "Path glob to exclude (default: vendor patterns).")
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

- [ ] **Step 3: Write .gitignore**

```
.build/
.swiftpm/
.index-store/
DerivedData/
*.xcodeproj/
*.scip
.DS_Store
```

- [ ] **Step 4: Write README.md**

```markdown
# palace-swift-scip-emit

Custom Swift emitter that reads Xcode IndexStoreDB and emits canonical Sourcegraph SCIP protobuf for ingestion by palace-mcp's `symbol_index_swift` extractor.

## Build (dev Mac only)

    cd services/palace-mcp/scip_emit/swift
    xcrun swift build -c release

Binary at `.build/release/palace-swift-scip-emit`.

## Run

    palace-swift-scip-emit \
        --derived-data ~/Library/Developer/Xcode/DerivedData/MyProject-xxxxx \
        --project-root /path/to/MyProject \
        --output myproject.scip

Output is a Sourcegraph SCIP protobuf file consumable by `palace-mcp`'s `parse_scip_file()`.

## Why custom

See `docs/research/2026-05-01-swift-indexstore-spike.md` for the Phase 1.0 NO-GO evidence on SwiftSCIPIndex (community) and the rationale for this custom emitter (Option C, GIM-128 spec rev3).
```

- [ ] **Step 5: Verify build (skeleton compiles, --help works)**

```bash
cd services/palace-mcp/scip_emit/swift
xcrun swift build -c release 2>&1 | tail -5
.build/release/palace-swift-scip-emit --help
```

Expected: build completes; --help prints usage including all flags.

> **Note for CTO Phase 1.1:** Lock `indexstore-db` revision SHA in Package.swift before approving this task. Build will fail until SHA is real.

- [ ] **Step 6: Commit**

```bash
git add services/palace-mcp/scip_emit/swift/
git commit -m "chore(GIM-128): scip_emit/swift SPM package scaffold (Phase 1 Task 1)"
```

---

### Task 2: Vendor + generate scip.proto bindings

**Files:**
- Create: `services/palace-mcp/scip_emit/swift/Sources/PalaceSwiftScipEmit/Proto/scip.proto`
- Create: `services/palace-mcp/scip_emit/swift/Sources/PalaceSwiftScipEmit/Proto/scip.pb.swift` (generated)
- Update: `services/palace-mcp/scip_emit/swift/Package.swift` (add `.process` for proto)

- [ ] **Step 1: Vendor scip.proto from sourcegraph/scip**

Pin to a specific tag/SHA. Recommendation: latest `v0.5.x` tag verified compatible with `palace_mcp.proto.scip_pb2` Python version (4.25+). CTO confirms exact tag.

```bash
cd services/palace-mcp/scip_emit/swift/Sources/PalaceSwiftScipEmit/Proto/
curl -sLO https://raw.githubusercontent.com/sourcegraph/scip/v0.5.2/scip.proto
sha256sum scip.proto  # record hash for REGEN.md
```

- [ ] **Step 2: Generate scip.pb.swift**

Requires `protoc` + `protoc-gen-swift` plugin. Install if missing:

```bash
brew install protobuf swift-protobuf
which protoc-gen-swift  # verify
```

Generate:

```bash
cd services/palace-mcp/scip_emit/swift/Sources/PalaceSwiftScipEmit/Proto/
protoc --swift_out=. --swift_opt=Visibility=Public scip.proto
ls -la scip.pb.swift
```

Result: ~1500 LOC `scip.pb.swift` — vendored generated code. Commit verbatim.

- [ ] **Step 3: Verify Index() roundtrip**

Add a tiny test target that creates an empty `Scip_Index()` and verifies serialization works:

```swift
// Tests/PalaceSwiftScipEmitTests/ProtoSmokeTests.swift
import XCTest
@testable import PalaceSwiftScipEmit
import SwiftProtobuf

final class ProtoSmokeTests: XCTestCase {
    func testEmptyIndexRoundtrip() throws {
        let idx = Scip_Index()
        let data = try idx.serializedData()
        let decoded = try Scip_Index(serializedData: data)
        XCTAssertEqual(decoded.documents.count, 0)
    }
}
```

```bash
xcrun swift test 2>&1 | tail -3
```

Expected: 1 test passes.

- [ ] **Step 4: Verify Python parse compatibility**

```bash
cd services/palace-mcp/scip_emit/swift
xcrun swift build -c release
.build/release/palace-swift-scip-emit --help  # still works
# (no real emit yet; that's Task 4)

# manually verify the Swift-emitted Index is byte-readable by Python:
xcrun swift run --package-path . -c release > /tmp/empty.scip <<'SWIFT_EOF'
// inline test — can be in a separate file under Tests/
import SwiftProtobuf
@_exported import PalaceSwiftScipEmit
let idx = Scip_Index()
let data = try idx.serializedData()
FileManager.default.createFile(atPath: "/tmp/empty.scip", contents: data)
SWIFT_EOF
# hack alternative: run the test target which writes the file as side-effect

cd /Users/ant013/Android/Gimle-Palace/services/palace-mcp
uv run python -c "
from palace_mcp.proto import scip_pb2
idx = scip_pb2.Index()
idx.ParseFromString(open('/tmp/empty.scip','rb').read())
print(f'parsed: documents={len(idx.documents)}')
"
```

Expected: Python parses without error; reports 0 documents. (Note: Step 4 verification can simplify to running ProtoSmokeTests + a small integration shell script that pipes through.)

- [ ] **Step 5: Commit**

```bash
git add services/palace-mcp/scip_emit/swift/Sources/PalaceSwiftScipEmit/Proto/ services/palace-mcp/scip_emit/swift/Tests/
git commit -m "chore(GIM-128): vendor scip.proto + generated swift bindings (Phase 1 Task 2)"
```

---

### Task 3: IndexStoreReader — minimal hello-world

> Goal: prove `indexstore-db` SPM dep can read Xcode 26's DataStore at all. If this works, the format-mismatch problem from Phase 1.0 NO-GO is in SwiftSCIPIndex, not in indexstore-db itself.

**Files:**
- Create: `services/palace-mcp/scip_emit/swift/Sources/PalaceSwiftScipEmit/IndexStoreReader.swift`

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

cd /Users/ant013/Android/Gimle-Palace/services/palace-mcp/scip_emit/swift
xcrun swift build -c release
.build/release/palace-swift-scip-emit \
    --derived-data /tmp/uw-ios-spike/.derived-data \
    --project-root /tmp/uw-ios-spike \
    --output /tmp/spike.scip
```

**Expected:** `found NN unique USRs` where NN > 100 (likely 200-500 from Wallet.swift + system frameworks).

> **CRITICAL gate:** if this returns 0 (the SwiftSCIPIndex symptom), indexstore-db SPM dep does NOT work on Xcode 26 either, and we have a deeper toolchain incompatibility. Operator + CTO escalate to spec rev4 (different approach: tree-sitter + custom symbol resolver, or downgrade Xcode).

- [ ] **Step 4: Verify on real UW-ios DerivedData**

```bash
UW_DD=$(ls -t -d ~/Library/Developer/Xcode/DerivedData/UnstoppableWallet-* | head -1)
.build/release/palace-swift-scip-emit \
    --derived-data "$UW_DD" \
    --project-root /Users/ant013/Ios/HorizontalSystems/unstoppable-wallet-ios \
    --output /tmp/uw-ios-task3.scip
```

**Expected:** USR count > 50000 (UW-ios + system frameworks). 0 = same critical-gate failure.

- [ ] **Step 5: Commit**

```bash
git add services/palace-mcp/scip_emit/swift/Sources/PalaceSwiftScipEmit/IndexStoreReader.swift services/palace-mcp/scip_emit/swift/Sources/PalaceSwiftScipEmit/main.swift
git commit -m "feat(GIM-128): IndexStoreReader hello-world (Phase 1 Task 3 — verifies indexstore-db on Xcode 26)"
```

---

### Task 4: ScipEmitter — emit one document, one symbol

**Files:**
- Create: `services/palace-mcp/scip_emit/swift/Sources/PalaceSwiftScipEmit/ScipEmitter.swift`
- Update: `services/palace-mcp/scip_emit/swift/Sources/PalaceSwiftScipEmit/main.swift`

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
git add services/palace-mcp/scip_emit/swift/Sources/PalaceSwiftScipEmit/
git commit -m "feat(GIM-128): ScipEmitter stub doc/symbol; verified Python parse (Phase 1 Task 4)"
```

---

### Task 5: SymbolBuilder — USR → SCIP symbol grammar

> Goal: convert IndexStoreDB's USR (Apple's mangled symbol identifier, e.g. `s:5UwSpike6WalletStruct`) into Sourcegraph SCIP `symbol_qualified_name` per the SCIP symbol grammar.

**Files:**
- Create: `services/palace-mcp/scip_emit/swift/Sources/PalaceSwiftScipEmit/SymbolBuilder.swift`
- Create: `services/palace-mcp/scip_emit/swift/Tests/PalaceSwiftScipEmitTests/SymbolBuilderTests.swift`

- [ ] **Step 1: Reference Sourcegraph SCIP symbol grammar**

Per `services/palace-mcp/scip_emit/swift/Sources/PalaceSwiftScipEmit/Proto/scip.proto` SCIP_SYMBOL grammar:

```
<scheme> ' ' <manager> ' ' <package-name> ' ' <package-version> ' ' <descriptor>+
```

For Swift (per GIM-105 rev2 Variant B "strip" decision):
- scheme: `scip-swift`
- manager: `apple` (proxy for SwiftPM/Xcode)
- package-name: module name (e.g., `UwSpike`, `UwMiniCore`)
- package-version: `.` (placeholder, not real version)
- descriptor: chain of `<name><suffix>` where suffix is `#` for type, `.` for property/var, `().` for method, `(<param>:)` for method-with-params

Example:
- USR `s:5UwSpike6WalletV` (struct Wallet) → `scip-swift apple UwSpike . Wallet#`
- USR `s:5UwSpike11WalletStoreC6select1iyS_tF` (method `select(_:)`) → `scip-swift apple UwSpike . WalletStore#select(_:).`

- [ ] **Step 2: Write SymbolBuilder**

```swift
import Foundation
import IndexStoreDB

/// Converts IndexStoreDB USRs to Sourcegraph SCIP symbol_qualified_name strings.
///
/// Per GIM-105 rev2 Variant B (strip) and Sourcegraph SCIP symbol grammar:
///   scip-swift apple <module> . <descriptor-chain>
struct SymbolBuilder {
    static func scipSymbol(usr: String, name: String, kind: IndexSymbolKind, parentPath: [String]) -> String {
        let module = extractModule(usr: usr) ?? "UnknownModule"
        let suffix = kindSuffix(kind: kind, name: name)
        let chain = (parentPath + ["\(name)\(suffix)"]).joined(separator: "")
        return "scip-swift apple \(module) . \(chain)"
    }

    /// Extract module name from USR. Swift USRs encode module as `s:<len><module>...`.
    /// Returns nil if not parseable.
    static func extractModule(usr: String) -> String? {
        guard usr.hasPrefix("s:") else { return nil }
        let rest = String(usr.dropFirst(2))
        // Mangling: s:<digit>+<module><...>
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

    static func kindSuffix(kind: IndexSymbolKind, name: String) -> String {
        switch kind {
        case .class, .struct, .enum, .protocol, .extension:
            return "#"
        case .typealias, .associatedtype:
            return "#"
        case .instanceMethod, .classMethod, .staticMethod, .constructor, .destructor:
            // For now, use simple `().` — Phase 1 Task 6 may expand to full param list
            return "()."
        case .instanceProperty, .classProperty, .staticProperty:
            return "."
        case .variable, .field, .parameter:
            return "."
        case .function, .freeFunction:
            return "()."
        case .enumConstant, .enumerator:
            return "."
        default:
            return "."  // fallback
        }
    }
}
```

- [ ] **Step 3: Write unit tests**

```swift
import XCTest
@testable import PalaceSwiftScipEmit

final class SymbolBuilderTests: XCTestCase {
    func testStruct() {
        let s = SymbolBuilder.scipSymbol(
            usr: "s:5UwSpike6WalletV",
            name: "Wallet",
            kind: .struct,
            parentPath: []
        )
        XCTAssertEqual(s, "scip-swift apple UwSpike . Wallet#")
    }

    func testInstanceMethod() {
        let s = SymbolBuilder.scipSymbol(
            usr: "s:5UwSpike11WalletStoreC6select1iyS_tF",
            name: "select",
            kind: .instanceMethod,
            parentPath: ["WalletStore#"]
        )
        XCTAssertEqual(s, "scip-swift apple UwSpike . WalletStore#select().")
    }

    func testProperty() {
        let s = SymbolBuilder.scipSymbol(
            usr: "s:5UwSpike11WalletStoreC8selectedIDSSSgvp",
            name: "selectedID",
            kind: .instanceProperty,
            parentPath: ["WalletStore#"]
        )
        XCTAssertEqual(s, "scip-swift apple UwSpike . WalletStore#selectedID.")
    }

    func testExtractModule() {
        XCTAssertEqual(SymbolBuilder.extractModule(usr: "s:5UwSpike6WalletV"), "UwSpike")
        XCTAssertEqual(SymbolBuilder.extractModule(usr: "s:11UwMiniCore6WalletV"), "UwMiniCore")
        XCTAssertNil(SymbolBuilder.extractModule(usr: "c:objc(cs)NSObject"))
    }
}
```

- [ ] **Step 4: Run tests**

```bash
cd services/palace-mcp/scip_emit/swift
xcrun swift test 2>&1 | tail -10
```

Expected: all SymbolBuilder tests pass.

- [ ] **Step 5: Commit**

```bash
git add services/palace-mcp/scip_emit/swift/Sources/PalaceSwiftScipEmit/SymbolBuilder.swift services/palace-mcp/scip_emit/swift/Tests/PalaceSwiftScipEmitTests/SymbolBuilderTests.swift
git commit -m "feat(GIM-128): SymbolBuilder USR → SCIP symbol grammar (Phase 1 Task 5)"
```

---

### Task 6: Full iteration over units + occurrences

**Files:**
- Update: `services/palace-mcp/scip_emit/swift/Sources/PalaceSwiftScipEmit/IndexStoreReader.swift`
- Update: `services/palace-mcp/scip_emit/swift/Sources/PalaceSwiftScipEmit/ScipEmitter.swift`

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

- [ ] **Step 2: Update ScipEmitter.emit() to use full iteration**

Replace the stub document with a real loop:

```swift
func emit(toolName: String = "palace-swift-scip-emit", toolVersion: String = "0.1.0") throws -> Scip_Index {
    var idx = Scip_Index()
    idx.metadata.version = .unspecifiedProtocolVersion
    idx.metadata.toolInfo.name = toolName
    idx.metadata.toolInfo.version = toolVersion
    idx.metadata.projectRoot = "file://\(projectRoot.path)"
    idx.metadata.textDocumentEncoding = .utf8

    let byFile = reader.collectOccurrencesByFile()

    for (relPath, records) in byFile.sorted(by: { $0.key < $1.key }) {
        var doc = Scip_Document()
        doc.relativePath = relPath
        doc.language = "swift"

        for rec in records {
            var occ = Scip_Occurrence()
            occ.symbol = SymbolBuilder.scipSymbol(
                usr: rec.usr,
                name: rec.name,
                kind: rec.kind,
                parentPath: enclosingChain(for: rec, in: byFile)
            )
            occ.symbolRoles = mapRoles(rec.roles)
            occ.range = makeRange(line: rec.line, column: rec.column, name: rec.name)
            doc.occurrences.append(occ)

            // If DEF role: also append a SymbolInformation entry to doc.symbols
            if rec.roles.contains(.definition) {
                var info = Scip_SymbolInformation()
                info.symbol = occ.symbol
                info.kind = mapKind(rec.kind)
                doc.symbols.append(info)
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
    // remaining bits left as references (default 0)
    return bits
}

private func makeRange(line: Int, column: Int, name: String) -> [Int32] {
    // SCIP range: [start_line, start_char, end_line, end_char] (0-indexed; line 1-indexed → 0-indexed)
    let start = Int32(line - 1)
    let startCol = Int32(column - 1)
    let endCol = Int32(column - 1 + name.utf8.count)
    return [start, startCol, start, endCol]
}

private func enclosingChain(for rec: OccurrenceRecord, in byFile: [String: [OccurrenceRecord]]) -> [String] {
    // Phase 1 Task 6: simple — look at rec.relations for `.childOf` and walk up
    // Phase 2 may improve; for now, return [] for top-level and parent USR-based for nested
    for (relUSR, relRoles) in rec.relations where relRoles.contains(.childOf) {
        // childOf points at parent. Build parent symbol.
        // For minimal Phase 1, just return [parentName + suffix]
        // ... simplified; real implementation in Task 6
    }
    return []
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
git add services/palace-mcp/scip_emit/swift/Sources/PalaceSwiftScipEmit/
git commit -m "feat(GIM-128): full iteration emit — units, occurrences, USR groups (Phase 1 Task 6)"
```

---

### Task 7: PathFilter — project vs vendor classification

**Files:**
- Create: `services/palace-mcp/scip_emit/swift/Sources/PalaceSwiftScipEmit/PathFilter.swift`
- Create: `services/palace-mcp/scip_emit/swift/Tests/PalaceSwiftScipEmitTests/PathFilterTests.swift`
- Update: `services/palace-mcp/scip_emit/swift/Sources/PalaceSwiftScipEmit/main.swift` (default exclude list)

- [ ] **Step 1: Write PathFilter**

```swift
import Foundation

struct PathFilter {
    let includes: [String]  // glob patterns; empty = match all
    let excludes: [String]  // glob patterns

    static let defaultExcludes: [String] = [
        "Pods/",
        "Carthage/",
        "SourcePackages/",
        ".build/",
        ".swiftpm/",
        "DerivedData/",
        "/Library/Developer/Xcode/DerivedData/",
    ]

    init(includes: [String] = [], excludes: [String] = PathFilter.defaultExcludes) {
        self.includes = includes
        self.excludes = excludes
    }

    /// Return true if path passes filter (i.e., should be emitted).
    func accepts(_ relativePath: String) -> Bool {
        if !excludes.isEmpty && excludes.contains(where: { relativePath.contains($0) }) {
            return false
        }
        if includes.isEmpty { return true }
        return includes.contains(where: { relativePath.contains($0) })
    }

    /// Tag whether path is "vendor" (kept but flagged for downstream phase ordering).
    func isVendor(_ relativePath: String) -> Bool {
        return PathFilter.defaultExcludes.contains(where: { relativePath.contains($0) })
    }
}
```

- [ ] **Step 2: Write unit tests**

```swift
import XCTest
@testable import PalaceSwiftScipEmit

final class PathFilterTests: XCTestCase {
    func testDefaultRejectsPods() {
        let filter = PathFilter()
        XCTAssertFalse(filter.accepts("Pods/Alamofire/Source/Alamofire.swift"))
    }

    func testAcceptsProjectSource() {
        let filter = PathFilter()
        XCTAssertTrue(filter.accepts("UnstoppableWallet/UnstoppableWallet/Modules/Wallet.swift"))
    }

    func testIncludeOverridesAccept() {
        let filter = PathFilter(includes: ["MyModule/"], excludes: [])
        XCTAssertTrue(filter.accepts("MyModule/foo.swift"))
        XCTAssertFalse(filter.accepts("OtherModule/foo.swift"))
    }

    func testVendorTagging() {
        let filter = PathFilter()
        XCTAssertTrue(filter.isVendor("SourcePackages/checkouts/Alamofire/Source/Alamofire.swift"))
        XCTAssertFalse(filter.isVendor("UnstoppableWallet/UnstoppableWallet/Modules/Wallet.swift"))
    }
}
```

- [ ] **Step 3: Wire into ScipEmitter**

Update `emit()` to skip excluded paths, and add a property on `Scip_Document` for vendor tag (since SCIP proto has no first-class vendor flag, encode in `language` field as `"swift-vendor"` OR add a Document-level metadata field per palace-mcp's parser convention — verify with `parse_scip_file` behavior).

> Phase 2 wiring: the Python extractor (`symbol_index_swift.py`) phase-classifies based on path. So actually PathFilter on the emitter side is for `--exclude` only (skip system frameworks). Phase classification happens in Python. Simplify accordingly.

- [ ] **Step 4: Test**

```bash
xcrun swift test 2>&1 | tail -3
```

- [ ] **Step 5: Commit**

```bash
git add services/palace-mcp/scip_emit/swift/Sources/PalaceSwiftScipEmit/PathFilter.swift services/palace-mcp/scip_emit/swift/Tests/PalaceSwiftScipEmitTests/PathFilterTests.swift services/palace-mcp/scip_emit/swift/Sources/PalaceSwiftScipEmit/ScipEmitter.swift
git commit -m "feat(GIM-128): PathFilter for emitter --exclude rules (Phase 1 Task 7)"
```

---

### Task 8: Phase 1 integration smoke + AC#4 branch lock

**Files:**
- Update: `services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project/REGEN.md` (NEW — write Phase 1.0+1.8 outcomes here)

- [ ] **Step 1: Run emitter on synthetic spike, capture Phase 1.0 generated-code visibility**

```bash
.build/release/palace-swift-scip-emit \
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

- [ ] **Step 2: Lock AC#4 branch in REGEN.md**

Based on Step 1 output:

- All 3 categories non-zero → **Branch A**. Default emit captures everything; AC#4 hard.
- 1-2 categories non-zero → **Branch B-1**. Try `-Xswiftc -emit-symbol-graph` flag in spike rebuild; re-run; if fixes → document workaround in REGEN.md.
- All 3 zero → **Branch B-2**. Generated-code visibility tracked as Phase-2 followup.

Write decision into REGEN.md.

- [ ] **Step 3: Run emitter on real UW-ios DerivedData, capture vendor-noise paths**

```bash
UW_DD=$(ls -t -d ~/Library/Developer/Xcode/DerivedData/UnstoppableWallet-* | head -1)
.build/release/palace-swift-scip-emit \
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
| Emitter binary builds | PASS / FAIL |
| Synthetic spike: USR count > 100 | PASS / FAIL |
| Real UW-ios: USR count > 50000 | PASS / FAIL |
| Python parses output | PASS / FAIL |
| AC#4 branch locked | A / B-1 / B-2 |
| Vendor paths enumerated | PASS / FAIL |

If all PASS → **GO** for Phase 2 (PE Tasks 9-12).
If any FAIL → **NO-GO**, escalate to spec rev4.

- [ ] **Step 6: Push Phase 1 commits + paperclip update**

```bash
cd /Users/ant013/Android/Gimle-Palace
git push origin feature/GIM-128-ios-swift-extractor

# Paperclip comment on GIM-128:
# "Phase 1 GO. Emitter binary at scip_emit/swift/.build/release/palace-swift-scip-emit.
#  Spike + UW-ios both work. AC#4 branch=<A/B-1/B-2>. Reassigning to PE for Phase 2."
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
- `_VENDOR_PATH_PREFIXES = ("Pods/", "Carthage/", "SourcePackages/", ".build/", ".swiftpm/", "/Library/Developer/Xcode/DerivedData/")`
- `_VENDOR_USR_PREFIXES = ()` — Swift USRs are project-scoped; no need to filter by prefix
- Phase ordering / Tantivy / Neo4j — IDENTICAL to Java extractor

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

    # AC#1 — DEF coverage
    assert stats.nodes_written >= _UW_IOS_MINI_N_NODES_EXPECTED  # constant from REGEN.md oracle

    # AC#2 — USE occurrences in tantivy
    n_def, n_use = await _count_tantivy_roles(tantivy_path, "uw-ios-mini")
    assert n_def >= 50
    assert n_use >= 100

    # AC#5 — cross-file ref
    cross = neo4j_driver.run("""
        MATCH (sym:Symbol {qualified_name: "scip-swift apple UwMiniCore . WalletStore#select()."})
              <-[:USES]-(occ:SymbolOccurrence)
        RETURN count(occ) AS uses
    """).single()["uses"]
    assert cross >= 1

    # AC#6 — language detection
    n_swift, n_unknown = await _count_tantivy_languages(tantivy_path, "uw-ios-mini")
    assert n_swift > 0
    assert n_unknown / (n_swift + n_unknown) < 0.05  # < 5% UNKNOWN
```

`_UW_IOS_MINI_N_NODES_EXPECTED` is a constant locked in fixture `REGEN.md` (Phase 3 Task 16 oracle table).

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
  Reads a pre-generated `.scip` file produced by `palace-swift-scip-emit`
  (custom emitter at `services/palace-mcp/scip_emit/swift/`, built on dev Mac via
  `xcrun swift build -c release`). Handles `.swift` and `.swiftinterface` files
  in one pass via per-document language auto-detection. Same 3-phase bootstrap as
  `symbol_index_python`. Uses `PALACE_SCIP_INDEX_PATHS` — set the project slug to
  the emitter output path. SCIP scheme: `scip-swift apple <module> . <descriptor>`.
```

- [ ] **Step 2: Add operator workflow section**

```markdown
### Operator workflow: Swift / iOS symbol index

Custom emitter required (no first-party scip-swift exists). All emitter work runs on operator's dev Mac (Apple Silicon, modern Xcode). iMac is runtime-only.

1. Build emitter binary (one-time per dev Mac):
   ```bash
   cd services/palace-mcp/scip_emit/swift
   xcrun swift build -c release
   ```
   Binary: `.build/release/palace-swift-scip-emit`.

2. Build target Swift project via `xcodebuild` to populate DerivedData:
   ```bash
   cd /path/to/swift-project
   xcodebuild -workspace Foo.xcworkspace -scheme Foo -destination "generic/platform=iOS Simulator" build
   ```

3. Emit `.scip` file:
   ```bash
   palace-swift-scip-emit \
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

# 3. Build emitter (if not already built)
EMITTER_REPO="../../../../../scip_emit/swift"
if [ ! -f "$EMITTER_REPO/.build/release/palace-swift-scip-emit" ]; then
    (cd "$EMITTER_REPO" && xcrun swift build -c release)
fi

# 4. Run emitter
EMITTER="$EMITTER_REPO/.build/release/palace-swift-scip-emit"
mkdir -p scip
"$EMITTER" \
    --derived-data "$DERIVED_DATA" \
    --project-root "$(pwd)" \
    --output scip/index.scip

# 5. Verify
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
_UW_IOS_MINI_N_NODES_EXPECTED = <oracle value, ±2% margin>
_UW_IOS_MINI_N_TANTIVY_DOCS = <unique symbol count>
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

- [ ] **Step 4: Verify Tantivy hits**

```python
# inside palace-mcp container or via MCP tool
hits = palace.code.find_references(qualified_name="...WalletStore.select", project="uw-ios-mini")
assert len(hits) >= 1
```

- [ ] **Step 5: Verify language distribution**

```cypher
MATCH (n:SymbolOccurrence) WHERE n.project = "uw-ios-mini"
RETURN n.language, count(n) AS cnt ORDER BY cnt DESC
```

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

- [ ] All ACs from spec rev3 mapped to specific plan tasks (cross-check below)
- [ ] No `<TBD>` placeholders in code blocks
- [ ] All commits have explicit messages (`feat`/`test`/`docs`/`chore`)
- [ ] CTO Phase 1.1 has clear inputs: indexstore-db SHA pin, scip.proto tag pin, dev-Mac toolchain pinned in REGEN.md
- [ ] PE Phase 2 has clear precondition (Phase 1 GO)
- [ ] QA Phase 4.1 has explicit evidence requirements per `feedback_pe_qa_evidence_fabrication.md`
- [ ] AC#11 (emitter builds) tested in Phase 1 Task 1, verified end-to-end Task 4
- [ ] AC#12 (incremental + missing data) — needs explicit test (TODO: add micro-task in Task 8 or Task 16)

### AC → Task mapping

| AC | Task |
|---|---|
| #1 — DEF coverage | Task 11 (integration test); Task 17 (Track A live-smoke) |
| #2 — USE emitted | Task 6 (emitter implementation); Task 11 (integration assert) |
| #3 — Vendor filtering | Task 7 (PathFilter); Task 11 (assert) |
| #4 — Generated-code visibility | Task 8 (lock branch); Task 9 (extractor handles correctly) |
| #5 — Cross-file refs | Task 11; Task 17 |
| #6 — Language detection | Task 9 (parser map); Task 11 (assert) |
| #7 — Real UW-ios live-smoke | Task 18 (Track B, deferred) |
| #8 — Pipeline integration | Task 17 |
| #9 — Track A merge gate | Task 17 |
| #10 — Track B captured | Task 18 |
| #11 — Emitter binary works | Tasks 1-8 (Phase 1) |
| #12 — Edge cases | Task 8 (TODO: incremental + empty-index test) |
