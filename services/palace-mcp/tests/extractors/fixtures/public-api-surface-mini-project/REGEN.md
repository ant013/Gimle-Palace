# public-api-surface-mini-project Fixture Notes

Этот fixture вручную зафиксирован для GIM-190 как parser-truth для `public_api_surface`.
Он не редактирует production UW/HS build files и не зависит от локального Gradle/Xcode.

## Layout

- `.palace/public-api/kotlin/UwMiniCore.api` — минимальный Kotlin BCV-style dump
- `.palace/public-api/swift/UwMiniKit.swiftinterface` — минимальный Swift module interface

## Coverage

- Kotlin: `public`, `protected`, `internal`, `private`, class, initializer, function, property
- Swift: `public`, `package`, `internal`, `private`, struct, protocol, initializer, function, property, typealias, extension

## Contract

GIM-190 v1 ожидает pre-generated artifacts внутри repo under:

- `.palace/public-api/kotlin/*.api`
- `.palace/public-api/swift/*.swiftinterface`

SKIE overlay для v1 optional и в этом fixture отсутствует намеренно; тесты проверяют,
что отсутствие overlay не считается ошибкой extractor.
