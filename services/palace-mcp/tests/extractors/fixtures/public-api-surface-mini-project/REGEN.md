# public-api-surface-mini-project Fixture Notes

Этот fixture вручную зафиксирован для GIM-190 как parser-truth для `public_api_surface`.
Он не редактирует production UW/HS build files и не зависит от локального Gradle/Xcode.

## Layout

- `.palace/public-api/kotlin/UwMiniCore.api` — минимальный Kotlin BCV-style dump
- `.palace/public-api/swift/UwMiniKit.swiftinterface` — минимальный Swift module interface

## Coverage

- Kotlin: `public`, `protected`, `internal`, `private`, class, interface, initializer, function, property, nested names, companion form
- Kotlin policy note: fixture includes `PublishedApiBridge` to prove v1 does not guess `published_api_internal` from plain BCV text when the artifact does not expose that distinction
- Swift: `public`, `open`, `package`, `internal`, `private`, struct, class, enum, protocol, initializer, function, property, typealias, extension

## Contract

GIM-190 v1 ожидает pre-generated artifacts внутри repo under:

- `.palace/public-api/kotlin/*.api`
- `.palace/public-api/swift/*.swiftinterface`

SKIE overlay для v1 optional и в этом fixture отсутствует намеренно; integration test
явно проверяет successful skip evidence: extractor succeeds, `is_bridge_exported=true`
symbols are absent, and `bridge_source` remains empty.
