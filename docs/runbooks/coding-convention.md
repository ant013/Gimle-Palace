# Coding Convention Runbook

Runbook для extractor `coding_convention` из GIM-238.

## Что ingest'ит extractor

Extractor читает `.swift` и `.kt` файлы прямо из repo path и строит
heuristic-based snapshot проектных соглашений по модулям.

Сейчас v1 покрывает 7 rule kinds:

- `naming.type_class`
- `naming.test_class`
- `naming.module_protocol`
- `structural.adt_pattern`
- `structural.error_modeling`
- `idiom.collection_init`
- `idiom.computed_vs_property`

По каждому `(module, kind)` extractor вычисляет dominant choice и
записывает outliers.

## Что пишет в граф

Extractor создаёт:

- `(:Convention {project_id, module, kind, dominant_choice, confidence, sample_count, outliers, run_id})`
- `(:ConventionViolation {project_id, module, kind, file, start_line, end_line, message, severity, run_id})`
- `(:IngestRun {run_id, extractor_name="coding_convention", project, success, error_code})`

`confidence` сейчас всегда `heuristic`, потому что v1 использует Python-side
pattern matching без SwiftSyntax/Konsist subprocess pipeline.

## Как запустить

Через MCP tool:

```text
palace.ingest.run_extractor(name="coding_convention", project="<slug>")
```

Для локальной разработки из `services/palace-mcp`:

```bash
uv run pytest tests/extractors/unit/test_coding_convention_*.py -v
uv run pytest tests/audit/unit/test_audit_contracts.py tests/audit/unit/test_audit_renderer.py -v
uv run pytest tests/extractors/integration/test_coding_convention_e2e.py -m integration -v
```

## Neo4j / Docker notes

Integration test использует `tests/extractors/integration/conftest.py`:

- если задан `COMPOSE_NEO4J_URI`, будет reuse уже поднятого Neo4j;
- если переменная не задана, fixture пытается поднять throwaway Neo4j через
  `testcontainers`.

Если `COMPOSE_NEO4J_URI=bolt://localhost:7687`, но локальный compose Neo4j не
запущен, integration test упадёт на connect step ещё до выполнения extractor.

На этом host Docker socket может требовать явный override:

```bash
DOCKER_HOST=unix:///Users/anton/.docker/run/docker.sock \
TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE=/Users/anton/.docker/run/docker.sock \
TESTCONTAINERS_RYUK_DISABLED=true \
uv run pytest tests/extractors/integration/test_coding_convention_e2e.py -m integration -v
```

## Как читать результат

- `sample_count` — сколько signal sites поддерживают observed pattern.
- `dominant_choice` — победивший стиль внутри модуля.
- `outliers` — сколько sites не совпали с dominant choice.
- `severity` на violation:
  - `high`, если `sample_count >= 5` и outlier ratio `>= 10%`
  - `medium`, если outliers есть, но high threshold не достигнут
  - `low`, если outlier нет

Примеры `dominant_choice`:

- `suffix_tests` / `prefix_test` / `suffix_spec`
- `suffix_able` / `suffix_protocol` / `suffix_ing`
- `throws` / `result` / `nullable`
- `literal_empty` / `constructor` / `factory`
- `computed_property` / `lazy_property`

## Полезные Cypher-проверки

### Summary per module

```cypher
MATCH (c:Convention {project_id: $project})
RETURN c.module,
       c.kind,
       c.dominant_choice,
       c.sample_count,
       c.outliers,
       c.confidence,
       c.run_id
ORDER BY c.module, c.kind;
```

### Violations

```cypher
MATCH (v:ConventionViolation {project_id: $project})
RETURN v.module,
       v.kind,
       v.file,
       v.start_line,
       v.severity,
       v.message
ORDER BY v.severity DESC, v.module, v.kind, v.file;
```

### Successful ingest runs

```cypher
MATCH (r:IngestRun {project: $project, extractor_name: "coding_convention"})
RETURN r.run_id, r.success, r.error_code
ORDER BY r.started_at DESC;
```

## Как добавить новое правило

Текущая реализация не разбита на отдельные `rules/*.py`; v1 держит rule
heuristics в `services/palace-mcp/src/palace_mcp/extractors/coding_convention/extractor.py`.

Минимальный процесс:

1. Добавить новый detector в `_extract_signals()` или helper рядом.
2. Вернуть `ConventionSignal` с новым `kind` и ожидаемым `choice`.
3. Добавить unit fixture / assertions в
   `tests/extractors/unit/test_coding_convention_extractor.py`.
4. Если rule должен рендериться в audit, убедиться, что шаблон
   `src/palace_mcp/audit/templates/coding_convention.md` остаётся понятным
   при новом `kind`.
