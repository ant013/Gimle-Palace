# Reactive Dependency Tracer Fixture

Фикстура для `reactive_dependency_tracer` v1 хранит заранее подготовленный
`reactive_facts.json` и минимальный SwiftUI source file.

В этом срезе live helper execution запрещён. Если контракт helper JSON меняется,
обновляй `reactive_facts.json` вручную и синхронно правь unit/integration tests.
