# palace-swift-scip-emit

Custom Swift emitter that reads Xcode IndexStoreDB and emits canonical
Sourcegraph SCIP protobuf for ingestion by palace-mcp's `symbol_index_swift`
extractor.

## Current status

This branch now contains the initial end-to-end emission path:

- Swift reads IndexStoreDB with the Task 3-compatible `IndexStoreReader`
- `ScipEmitter` builds a deterministic payload from Swift-only occurrences
- a repo-local Python serializer writes canonical SCIP protobuf via the
  already-vendored `palace_mcp.proto.scip_pb2`

The runtime proof on the operator dev Mac showed that `IndexStoreDB` at the
pinned revision can read Xcode 26 DataStore records, but the broad empty-pattern
canonical-occurrence query is not a safe "all symbols" iterator. Reader code in
this package therefore uses a two-phase traversal:

1. `allSymbolNames()`
2. `canonicalOccurrences(ofName:)` outside the symbol-name callback

Do not reintroduce nested canonical lookups inside `forEachSymbolName` or the
empty-pattern broad query without re-proving them; the approved Task 3 evidence
found those paths unreliable on the dev-Mac environment.

## Build (dev Mac only)

```bash
cd services/palace-mcp/scip_emit_swift
xcrun swift build -c release
```

Binary target path:

```text
.build/release/palace-swift-scip-emit-cli
```

## Required toolchain (dev Mac)

- Xcode 16+
- `apple/swift-protobuf` pinned in `Package.swift` to exact `1.37.0`
- `protoc` `34.1`
- `protoc-gen-swift` `1.37.0`
- Full pin-truth and verification commands recorded in:
  `docs/research/2026-05-03-gim-128-phase-1-1-pin-truth.md`

## Why custom

See `docs/research/2026-05-01-swift-indexstore-spike.md` and the GIM-128 issue
thread for the Task 3 runtime-proof evidence and the rationale for replacing
the original SwiftSCIPIndex path with a custom emitter.
