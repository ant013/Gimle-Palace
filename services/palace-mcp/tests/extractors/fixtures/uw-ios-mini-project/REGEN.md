# uw-ios-mini-project Fixture Regeneration

GIM-160 generates `scip/index.scip` from the local Swift fixture on a dev Mac
using Xcode IndexStoreDB and `palace-swift-scip-emit`.

## Drift Status

The currently committed `scip/index.scip` evidence was generated with a toolchain
that does **not** match the locked Phase 1.1 truth in
`docs/research/2026-05-03-gim-128-phase-1-1-pin-truth.md`:

- locked truth requires `protoc 34.1` and `protoc-gen-swift 1.37.0`
- current committed evidence below records `protoc 32.1` and
  `protoc-gen-swift 1.31.1`

Do not treat the current artifact as Phase 3.1-closing evidence until one of
these happens:

1. GIM-160 reruns the fixture generation with the locked pins and updates this file.
2. The board explicitly approves changing the locked toolchain truth.

## Current Committed Artifact Toolchain

- Xcode: 26.3 (build 17C529)
- `xcrun swift --version`: Apple Swift 6.2.4 (`swiftlang-6.2.4.1.4 clang-1700.6.4.2`), target `arm64-apple-macosx26.0`
- `protoc --version`: `libprotoc 34.1`
- `protoc-gen-swift --version`: `protoc-gen-swift 1.37.0`
- `apple/swift-protobuf`: exact `1.37.0` in `services/palace-mcp/scip_emit_swift/Package.swift`

## Oracle Counts

| Metric | Value |
|---|---:|
| N_DOCUMENTS_TOTAL | 5 |
| N_DEFS_TOTAL | 117 |
| N_USES_TOTAL | 253 |
| N_OCCURRENCES_TOTAL | 370 |

## Branch Notes

- AC#4 Branch: B-2. IndexStoreDB exposes source-level Swift symbols and also some macro-expanded `@Observable` support symbols, but this first locked fixture does not assert full generated-code visibility for Codable synthesis or every compiler-generated member.
- Cross-file symbol proof: `WalletStore` is defined in `Sources/UwMiniCore/State/WalletStore.swift` and referenced from `Sources/UwMiniApp/main.swift` as `scip-swift apple UwMiniCore . s%3A10UwMiniCore11WalletStoreC`.

## Document Breakdown

| Document | Occurrences | Symbols |
|---|---:|---:|
| `Sources/UwMiniApp/main.swift` | 11 | 3 |
| `Sources/UwMiniCore/Model/Transaction.swift` | 62 | 25 |
| `Sources/UwMiniCore/Model/Wallet.swift` | 50 | 20 |
| `Sources/UwMiniCore/Repository/WalletRepository.swift` | 54 | 16 |
| `Sources/UwMiniCore/State/WalletStore.swift` | 193 | 47 |

## Verification

```bash
cd services/palace-mcp/scip_emit_swift
protoc --proto_path=Sources/PalaceSwiftScipEmitCore/Proto \
  --swift_out=Visibility=Public:Sources/PalaceSwiftScipEmitCore/Proto \
  Sources/PalaceSwiftScipEmitCore/Proto/scip.proto

xcrun swift build -c release

cd ../tests/extractors/fixtures/uw-ios-mini-project
./regen.sh
# documents=5 occurrences=370

cd ../../../..
uv run python - <<'PY'
from pathlib import Path
from palace_mcp.proto import scip_pb2
idx = scip_pb2.Index()
idx.ParseFromString(Path("tests/extractors/fixtures/uw-ios-mini-project/scip/index.scip").read_bytes())
print(len(idx.documents), sum(len(d.occurrences) for d in idx.documents))
PY
# 5 370
```

Full Swift smoke tests pass on the MacBook with Xcode SDK/toolchain includes
isolated from `/usr/local/include`:

```bash
cd services/palace-mcp/scip_emit_swift
SDK=$(xcrun --sdk macosx --show-sdk-path)
TOOLCHAIN=/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain
xcrun swift test \
  -Xcc -nostdinc \
  -Xcc -isystem -Xcc "$SDK/usr/include/c++/v1" \
  -Xcc -isystem -Xcc "$TOOLCHAIN/usr/lib/clang/17/include" \
  -Xcc -isystem -Xcc "$SDK/usr/include" \
  -Xcc -isystem -Xcc "$TOOLCHAIN/usr/include" \
  -Xcc -F -Xcc "$SDK/System/Library/Frameworks" \
  -Xcc -F -Xcc "$SDK/System/Library/SubFrameworks"
# Executed 5 tests, with 0 failures (0 unexpected)
```

The explicit include set is required on this host because a stale
`/usr/local/include/IOKit` directory shadows the Xcode SDK IOKit headers when
XCTest is imported. The smoke test itself passes once the compiler include path
is constrained to the Xcode SDK/toolchain.
