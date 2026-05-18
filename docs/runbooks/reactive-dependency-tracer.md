# Reactive Dependency Tracer

## Назначение

`reactive_dependency_tracer` читает заранее подготовленный Swift helper JSON и
пишет в Neo4j `ReactiveComponent`, `ReactiveState`, `ReactiveEffect`,
`ReactiveDiagnostic` и связи между ними. v1 Swift-first: Kotlin/Compose только
как structured skip diagnostics, без Kotlin graph facts.

## Scope v1

- Источник данных: только pre-generated `reactive_facts.json`.
- Live SwiftSyntax helper execution запрещён в v1.
- Exact symbol correlation разрешён только к существующим
  `SymbolOccurrenceShadow` и `PublicApiSymbol`.
- Lifecycle-only эффекты (`.task {}`, `.onAppear`) не создают
  `TRIGGERS_EFFECT`, если helper не дал explicit trigger evidence.

## Pre-generated JSON workflow

1. Подготовь repo с Swift sources.
2. Сгенерируй helper JSON вне `palace-mcp` runtime.
3. Положи файл `reactive_facts.json` в корень target repo.
4. Убедись, что пути внутри JSON относительные к repo root и не содержат `..`,
   Windows separators, home paths или raw source snippets.
5. Запусти extractor:

```python
palace.ingest.run_extractor(name="reactive_dependency_tracer", project="<slug>")
```

## Fixture smoke

Локальный smoke для этой repo:

```bash
cd services/palace-mcp
uv run pytest tests/extractors/integration/test_reactive_dependency_tracer_integration.py -m integration -v
```

Fixture покрывает:

- `@State`
- `@Binding`
- `ObservableObject` + `@Published`
- Combine `sink`
- explicit `.onChange`
- lifecycle-only `.task`
- UIKit callback candidate
- generated/vendor skip
- exact `SymbolOccurrenceShadow` / `PublicApiSymbol` correlation

## Environment / config

- Нужен доступный Neo4j driver через обычный extractor runtime.
- Для integration smoke нужен Neo4j на `COMPOSE_NEO4J_URI` или testcontainers
  environment, принятый в `services/palace-mcp/tests/extractors/integration/`.
- Дополнительных runtime flags для v1 extractor не требуется.

## Future helper launcher constraints

Если live helper execution будет разрешён в будущем revision, launcher обязан:

- запускать fixed trusted binary path вне target repo;
- не использовать shell invocation;
- применять sanitized env allowlist;
- запускать с `stdin=DEVNULL`;
- ограничивать stdout/stderr и размер batch;
- иметь timeout + process-group kill;
- не наследовать user config, package caches и build settings repo.

Этот runbook не описывает live execution path, потому что для v1 он запрещён.

## Sample Cypher

State -> effect with explicit trigger:

```cypher
MATCH (state:ReactiveState {project: $project})
      -[rel:TRIGGERS_EFFECT]->
      (effect:ReactiveEffect {project: $project})
RETURN state.state_name, rel.trigger_kind, effect.effect_kind
ORDER BY state.state_name
```

View -> driving states:

```cypher
MATCH (component:ReactiveComponent {project: $project})
      -[:DECLARES_STATE]->
      (state:ReactiveState {project: $project})
RETURN component.qualified_name, collect(state.state_name) AS states
ORDER BY component.qualified_name
```

Lifecycle-only effects:

```cypher
MATCH (effect:ReactiveEffect {project: $project, effect_kind: 'task'})
WHERE NOT EXISTS {
  MATCH (:ReactiveState)-[:TRIGGERS_EFFECT]->(effect)
}
RETURN effect.id, effect.file_path, effect.start_line
```

Low-confidence callback candidates:

```cypher
MATCH (effect:ReactiveEffect {project: $project, confidence: 'low'})
RETURN effect.component_id, effect.effect_kind, effect.file_path
ORDER BY effect.file_path, effect.start_line
```

## Troubleshooting

Missing helper JSON:

- Symptom: `swift_helper_unavailable`.
- Action: проверь, что `reactive_facts.json` лежит в корне target repo.

Parse failure:

- Symptom: `swift_parse_failed` или `swift_helper_version_unsupported`.
- Action: проверь `schema_version`, ref integrity, ranges, path normalization и
  unsupported edge kinds.
- v1 сохраняет valid files даже если соседний file record невалиден.

Generated/vendor Swift file skipped:

- Symptom: `swift_generated_or_vendor_skipped`.
- Action: это ожидаемо для `vendor/`, `Pods/`, `DerivedData/`, `.build/`.

Missing symbol correlation:

- Symptom: `symbol_correlation_unavailable`.
- Action: проверь, что exact `SymbolOccurrenceShadow` существует для
  `group_id + symbol_id + symbol_qualified_name`, либо что exact
  `PublicApiSymbol` существует для `project + commit_sha + language +
  symbol_qualified_name`.

Absolute/home path rejected:

- Symptom: `path_absolute_outside_repo`, `path_windows_separator`,
  `path_parent_traversal`, `path_symlink_escape`.
- Action: helper JSON должен содержать только repo-relative POSIX paths.
