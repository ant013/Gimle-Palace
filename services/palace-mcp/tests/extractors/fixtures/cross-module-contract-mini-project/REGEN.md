# cross-module-contract-mini-project Fixture Notes

Этот fixture зафиксирован для GIM-192 и покрывает ровно v1 extractor scope.

## Layout

- `.palace/public-api/swift/ProducerKit.swiftinterface` — producer public API artifact для GIM-190.
- `.palace/cross-module-contract/module-owners.json` — committed fallback map для owner resolution.
- `.palace/cross-module-contract/occurrences.json` — committed occurrence truth для seed в integration tests.
- `ConsumerApp/Sources/ConsumerApp/WalletFeature.swift` — cross-module consumer.
- `ProducerKit/Sources/ProducerKit/InternalUse.swift` — same-module reference, должен быть исключен.
- `UnknownFeature/Sources/UnknownFeature/Loose.swift` — unresolved consumer path, должен быть skipped.

## Coverage

- exact match по `Wallet.balance()`
- unmatched exported symbol (`staleExport()`)
- default exclusion для `packageHelper()`
- graph-first owner resolution для mapped files
- fallback module-root map в `.palace/cross-module-contract/module-owners.json`
- unresolved owner path without guessing
