# Phase 1.0 Spike — SwiftSCIPIndex (community) NO-GO on Xcode 26

**Date:** 2026-05-01
**Status:** Phase 1.0 spike outcome for GIM-128
**Conclusion:** SwiftSCIPIndex (community) is unviable on Xcode 26 toolchain. Pivot to **custom Swift emitter** (Option C) approved by operator 2026-05-01.

---

## 1. Spike host

Operator's primary dev Mac (where Claude session ran):

| Component | Value |
|---|---|
| macOS | 26.3.1 (build 25D771280a) |
| Architecture | arm64 (Apple Silicon) |
| Xcode | 26.3 (build 17C529) |
| Swift (xcrun) | 6.2.4 (swiftlang-6.2.4.1.4 clang-1700.6.4.2) |
| iOS SDK | 26.2 |
| XcodeGen | installed via Homebrew |
| Free disk on `~` | 95 GB |

`swift` on PATH points to `~/.swiftly/bin/swift` (Swiftly-managed, version 5.8.1). Production Xcode toolchain accessed via `xcrun swift` — version 6.2.4. All commands in spike used `xcrun` to ensure correct toolchain.

## 2. Tools tested

### 2.1 SwiftSCIPIndex (community)

- Repository: `https://github.com/Fostonger/SwiftSCIPIndex`
- SHA pinned during spike: `88c222d17c3649083eb226b4459643d59dfb3d40`
- Last commit: "Refactor IndexStoreReader to dynamically locate libIndexStore.dylib"
- License: not stated in repo header
- Maintainer activity: low (community single-maintainer)

### 2.2 Build outcome

`Package.swift` declared `.macOS(.v13)` but its dependency `IndexStoreDB` requires `.v14`:

```
error: the executable 'SwiftSCIPIndexer' requires macos 13.0,
but depends on the product 'IndexStoreDB' which requires macos 14.0
```

After patching `Package.swift` to `.macOS(.v14)`, `xcrun swift build -c release` succeeded in 24.5s. Binary produced at `.build/release/swift-scip-indexer`.

## 3. Discovery 1 — Output format mismatch

`swift-scip-indexer` emits **non-canonical** output formats:

- **Default:** SQLite `.db` (proprietary internal schema, not Sourcegraph-compatible)
- **`--json`:** Custom JSON, structurally similar to canonical SCIP but **not the canonical Sourcegraph SCIP-JSON projection**

From `Sources/SwiftSCIPIndexer/SCIP/SCIPJSONWriter.swift`:

```swift
struct SCIPOutput: Codable {
    let metadata: Metadata { version, toolInfo, projectRoot, textDocumentEncoding }
    let documents: [Document {
        relativePath: String,
        language: String,
        symbols: [SymbolInfo],
        occurrences: [OccurrenceInfo]
    }]
}
```

The fields match Sourcegraph SCIP at the surface level, but field-naming convention (camelCase vs snake_case), enum encoding (string vs int), and nested structures (e.g., `relationship.kind`) require verification against canonical proto. Likely incompatible without an adapter.

palace-mcp's `parse_scip_file` (`services/palace-mcp/src/palace_mcp/extractors/scip_parser.py:91`) calls `index.ParseFromString(data)` — expects raw protobuf bytes only. Adding JSON adapter would be ~150-300 LOC of scaffolding.

## 4. Discovery 2 — IndexStoreDB read returns 0 symbols on Xcode 26

Spike Setup A — synthetic SPM package:

```bash
mkdir /tmp/uw-ios-spike && cd /tmp/uw-ios-spike
# Package.swift + Sources/UwSpike/Wallet.swift (Codable + @Observable + property wrapper)
xcrun swift build -Xswiftc -index-store-path -Xswiftc /tmp/uw-ios-spike/.index-store
# Build complete. .index-store has 1067 files.

# Re-layer for swift-scip-indexer's expected DerivedData/Index/DataStore path
mkdir -p .derived-data/Index && cp -R .index-store .derived-data/Index/DataStore
~/.local/bin/swift-scip-indexer index \
    --derived-data /tmp/uw-ios-spike/.derived-data \
    --project-root /tmp/uw-ios-spike \
    --output spike.json --json --verbose

# Output:
#    Found 0 symbols
#    Found 0 occurrences
#    Done! Output size: 245 bytes
```

Spike Setup B — real UW-ios DerivedData (existed from operator's prior Xcode work):

```bash
UW_DD=/Users/ant013/Library/Developer/Xcode/DerivedData/UnstoppableWallet-aipcfhbdpyobaffxsznjdpftpubn
# 34245 record files, freshly built 2026-04-30
~/.local/bin/swift-scip-indexer index \
    --derived-data "$UW_DD" \
    --project-root /Users/ant013/Ios/HorizontalSystems/unstoppable-wallet-ios \
    --output uw-ios.scip.json --json --no-include-snippets --verbose

# Output:
#    Found 0 symbols
#    Found 0 occurrences
#    Done! Time elapsed: 15.36s. Output size: 289 bytes
```

`forEachCanonicalSymbolOccurrence` returned 0 on both spike SPM build AND real Xcode-generated DerivedData with 34245 records.

## 5. Root-cause hypothesis

`SwiftSCIPIndex` depends on Apple's `IndexStoreDB` Swift package (`https://github.com/swiftlang/indexstore-db`) which it pins to `branch: main`. This dependency dynamically locates `libIndexStore.dylib` from Xcode toolchain path:

```swift
// IndexStoreReader.swift:99-108
let libPath = "\(xcodePath)/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/lib/libIndexStore.dylib"
```

Xcode 26's `libIndexStore.dylib` ABI/protocol may have evolved beyond what indexstore-db's tracked `main` was last validated against. The 15.36s read on 34K records (vs. 0.21s on 1K records) suggests files ARE being scanned but no symbols decoded — symptom of binary record format mismatch.

Notably, swift-scip-indexer's recent commits ("dynamically locate libIndexStore.dylib", "Implement dynamic detection of libIndexStore library path") indicate the maintainer was already chasing toolchain compatibility issues. The fix landed but is incomplete for Xcode 26.

## 6. Decision — Option C (custom emitter)

Operator decision 2026-05-01: **build our own Swift emitter**, similar to `services/palace-mcp/scip_emit/solidity/` precedent (Solidity v1, GIM-124).

### Rationale

| Criterion | SwiftSCIPIndex (rejected) | Custom emitter (accepted) |
|---|---|---|
| Output format | Non-canonical SQLite/JSON | Canonical Sourcegraph SCIP protobuf |
| Toolchain compatibility | Broken on Xcode 26 | We control via vendored `indexstore-db` SPM dep + tracked Xcode SDK |
| Maintenance | Community single-maintainer, low activity | We maintain alongside Solidity emitter |
| Time to working slice | Indeterminate (wait for upstream fix) | 2-4 days estimated |
| Cross-file refs (USE occurrences) | Theoretically yes (if it worked) | We design from start |
| Bonus | none | Reusable for Slice 4 multi-repo SPM ingest |

### Architecture

```
services/palace-mcp/scip_emit/swift/      (NEW)
├── Package.swift                          (SPM package, depends on swiftlang/indexstore-db + apple/swift-protobuf)
├── README.md
├── Sources/
│   └── PalaceSwiftScipEmit/
│       ├── main.swift                     (CLI entry point)
│       ├── IndexStoreReader.swift         (wraps IndexStoreDB iterator)
│       ├── ScipEmitter.swift              (builds scip.proto Index message)
│       ├── SymbolBuilder.swift            (USR → SCIP symbol_qualified_name)
│       ├── PathFilter.swift               (project vs vendor classification)
│       └── proto/scip.pb.swift            (vendored from sourcegraph/scip)
├── Tests/
│   └── PalaceSwiftScipEmitTests/
│       └── ...
└── regen-scip.sh                          (helper used by fixture regen.sh)
```

CLI invocation (run on dev Mac, NOT in palace-mcp container):

```
palace-swift-scip-emit \
    --derived-data ~/Library/Developer/Xcode/DerivedData/UnstoppableWallet-xxx \
    --project-root /Users/ant013/Ios/HorizontalSystems/unstoppable-wallet-ios \
    --output unstoppable-wallet-ios.scip
```

Output: canonical SCIP protobuf (`.scip` file). Byte-compatible with Sourcegraph's `scip` CLI tooling and palace-mcp's existing `parse_scip_file`.

### Track A / Track B (unchanged from rev2)

- **Track A (merge gate):** committed `index.scip` fixture in repo + iMac container ingestion via `PALACE_SCIP_INDEX_PATHS`. Sufficient for extractor pipeline correctness.
- **Track B (deferred-not-blocked):** real UW-ios source, generated by the new emitter on dev Mac, scp'd to iMac. Sufficient for AC#7 substantive criteria.

The new emitter binary itself is built only on dev Mac (Apple Silicon, modern Xcode). iMac is not the build host; iMac receives only the resulting `.scip` byte-file.

## 7. References

- spec rev3: `docs/superpowers/specs/2026-04-30-ios-swift-extractor-rev3.md`
- plan rev2: `docs/superpowers/plans/2026-04-30-GIM-128-ios-swift-extractor-rev2.md`
- Solidity emitter precedent: `services/palace-mcp/scip_emit/solidity/`
- Sourcegraph SCIP proto: `services/palace-mcp/src/palace_mcp/proto/scip_pb2.py`
- Apple IndexStoreDB: https://github.com/swiftlang/indexstore-db
- swift-protobuf: https://github.com/apple/swift-protobuf
- Memory: `reference_imac_toolchain_limits.md` — iMac is runtime-only host (still applies)

## 8. Spike artifacts (not committed)

Local-only at `/tmp/uw-ios-spike/` and `~/.local/opt/SwiftSCIPIndex/` on operator's dev Mac. Retained until Plan rev2 Phase 1 completion in case re-verification needed.
