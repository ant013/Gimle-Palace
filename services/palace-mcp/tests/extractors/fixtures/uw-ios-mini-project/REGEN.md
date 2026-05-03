# uw-ios-mini-project Fixture Regeneration

GIM-160 generates `scip/index.scip` from the local Swift fixture on a dev Mac
using Xcode IndexStoreDB and `palace-swift-scip-emit`.

## Toolchain

- Xcode: 26.3 (build 17C529)
- `xcrun swift --version`: Apple Swift 6.2.4 (`swiftlang-6.2.4.1.4 clang-1700.6.4.2`), target `arm64-apple-macosx26.0`
- `protoc --version`: `libprotoc 32.1`
- `protoc-gen-swift --version`: `protoc-gen-swift 1.31.1`

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
./regen.sh
# documents=5 occurrences=370

cd services/palace-mcp
uv run python - <<'PY'
from pathlib import Path
from palace_mcp.proto import scip_pb2
idx = scip_pb2.Index()
idx.ParseFromString(Path("tests/extractors/fixtures/uw-ios-mini-project/scip/index.scip").read_bytes())
print(len(idx.documents), sum(len(d.occurrences) for d in idx.documents))
PY
# 5 370
```
