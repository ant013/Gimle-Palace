# Reactive Dependency Tracer Fixture

Фикстура для `reactive_dependency_tracer` v1 хранит заранее подготовленный
`reactive_facts.json` и Swift-first fixture tree:

- `Sources/App/CounterView.swift` — `@State`, `@Binding`, `@ObservedObject`,
  `.onChange`, lifecycle-only `.task`.
- `Sources/App/SessionModel.swift` — `ObservableObject`, `@Published`,
  Combine `sink`.
- `Sources/App/LegacyController.swift` — UIKit callback candidate.
- `vendor/GeneratedCounterView.swift` — generated/vendor skip path.

В этом срезе live helper execution запрещён. Если контракт helper JSON меняется,
обновляй `reactive_facts.json` вручную и синхронно правь unit/integration tests.

Проверка после обновления fixture:

```bash
cd services/palace-mcp
uv run pytest tests/extractors/unit/test_reactive_dependency_tracer_*.py -v
uv run pytest tests/extractors/integration/test_reactive_dependency_tracer_integration.py -m integration -v
```
