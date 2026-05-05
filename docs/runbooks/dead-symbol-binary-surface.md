# Runbook: dead_symbol_binary_surface

## Обзор

Экстрактор `dead_symbol_binary_surface` ingest'ит reviewable dead-symbol
candidates и binary-surface retention facts из заранее подготовленного
`Periphery` JSON fixture. В v1:

- Swift/Periphery path обязателен.
- `Reaper` остаётся schema-ready/no-op и не парсится без отдельного reviewed
  offline report contract.
- `CodeQL` опционален и отсутствие CodeQL input не должно валить run.

Экстрактор не запускает `Periphery`, `Reaper` или `CodeQL` сам. Он читает уже
закоммиченные артефакты из repo.

## Обязательные входные артефакты

### 1. Periphery raw output

Для mini fixture:

```text
services/palace-mcp/tests/extractors/fixtures/dead-symbol-binary-surface-mini-project/periphery/periphery-3.7.4-swiftpm.json
```

### 2. Signed parser contract

```text
services/palace-mcp/tests/extractors/fixtures/dead-symbol-binary-surface-mini-project/periphery/contract.json
```

### 3. Project-local skiplist

```text
<repo>/.palace/dead-symbol-skiplist.yaml
```

Для mini fixture path такой:

```text
services/palace-mcp/tests/extractors/fixtures/dead-symbol-binary-surface-mini-project/.palace/dead-symbol-skiplist.yaml
```

### 4. Reaper no-op evidence

V1 не требует report file. Источник решения:

```text
docs/research/2026-05-04-dead-symbol-tool-output-spike/README.md
```

Именно этот spike фиксирует, что публичного offline `Reaper` report contract для
v1 нет, поэтому ожидаемое поведение экстрактора — `reaper_report_unavailable`
skip path.

## Команда Periphery, зафиксированная для fixture

Источник истины:

```text
docs/research/2026-05-04-dead-symbol-tool-output-spike/README.md
```

Команда, которой был получен signed fixture:

```bash
HOME=/private/tmp/gim193-home \
CLANG_MODULE_CACHE_PATH=/private/tmp/gim193-clang-module-cache \
/private/tmp/periphery-3.7.4-release/periphery scan \
  --project-root . \
  --format json \
  --relative-results \
  --disable-update-check \
  --write-results /private/tmp/gim193-periphery-output/periphery-scan.json
```

Использованный fixture project root:

```text
services/palace-mcp/tests/extractors/fixtures/dead-symbol-binary-surface-mini-project/
```

## Запуск экстрактора

### Через MCP

```text
palace.ingest.run_extractor(name="dead_symbol_binary_surface", project="<slug>")
```

Ожидаемый success envelope:

```json
{
  "ok": true,
  "extractor": "dead_symbol_binary_surface",
  "project": "<slug>",
  "success": true,
  "nodes_written": 0,
  "edges_written": 0,
  "duration_ms": 0
}
```

`nodes_written`/`edges_written` зависят от того, был ли это первый run,
idempotent rerun, или третий run после upstream change.

### Локальная validation bundle

```bash
cd services/palace-mcp
uv run pytest tests/extractors/unit/test_dead_symbol_binary_surface*.py
uv run pytest tests/extractors/integration/test_dead_symbol_binary_surface_integration.py -v
uv run ruff format --check src tests
uv run ruff check src tests
uv run mypy src
```

Если `COMPOSE_NEO4J_URI` и Docker socket недоступны, integration file будет
guarded-skip и Phase 4.1 evidence нужно добирать на review-profile host.

## Review-profile smoke

```bash
docker compose --profile review up -d --wait --build
```

После этого compose Neo4j доступен с host-side тестов по localhost:

```bash
export COMPOSE_NEO4J_URI=bolt://127.0.0.1:7687
export COMPOSE_NEO4J_USER=neo4j
export COMPOSE_NEO4J_PASSWORD="$(grep '^NEO4J_PASSWORD=' .env | cut -d= -f2-)"
```

Тогда integration suite переиспользует уже поднятый compose runtime вместо
отдельного testcontainers Neo4j.

После старта окружения:

```text
palace.ingest.run_extractor(name="dead_symbol_binary_surface", project="<slug>")
```

### Обязательный evidence paste в Phase 4.1

```cypher
MATCH (d:DeadSymbolCandidate)
RETURN d.candidate_state, count(*) ORDER BY d.candidate_state;

MATCH (b:BinarySurfaceRecord)
RETURN count(b);

MATCH (d:DeadSymbolCandidate {candidate_state: 'unused_candidate'})-[:BACKED_BY_PUBLIC_API]->(p:PublicApiSymbol)
WHERE p.visibility IN ['public', 'open']
RETURN count(*) AS invalid_public_unused;

MATCH (d:DeadSymbolCandidate {candidate_state: 'unused_candidate'})-[:BLOCKED_BY_CONTRACT_SYMBOL]->(:PublicApiSymbol)
RETURN count(*) AS invalid_contract_unused;

MATCH (d:DeadSymbolCandidate)-[rel:BLOCKED_BY_CONTRACT_SYMBOL]->(p:PublicApiSymbol)
RETURN d.id AS candidate_id,
       p.id AS public_symbol_id,
       p.symbol_qualified_name AS public_symbol_key,
       properties(rel) AS blocker_provenance
ORDER BY candidate_id;
```

Нужно приложить и JSON response от `palace.ingest.run_extractor`, и результаты
этих Cypher queries.

## Полезные Neo4j проверки

### Все candidates

```cypher
MATCH (d:DeadSymbolCandidate {project: $project})
RETURN d.display_name,
       d.candidate_state,
       d.skip_reason,
       d.confidence,
       d.source_file,
       d.source_line
ORDER BY d.display_name;
```

### Retained public API symbols

```cypher
MATCH (d:DeadSymbolCandidate {project: $project, candidate_state: 'retained_public_api'})
OPTIONAL MATCH (d)-[:HAS_BINARY_SURFACE]->(b:BinarySurfaceRecord)
RETURN d.display_name, d.skip_reason, b.surface_kind, b.retention_reason
ORDER BY d.display_name;
```

### Contract blockers with copied provenance

```cypher
MATCH (d:DeadSymbolCandidate {project: $project})-[rel:BLOCKED_BY_CONTRACT_SYMBOL]->(p:PublicApiSymbol)
RETURN d.display_name,
       p.symbol_qualified_name,
       rel.contract_snapshot_id,
       rel.consumer_module_name,
       rel.producer_module_name,
       rel.commit_sha,
       rel.use_count,
       rel.evidence_paths_sample
ORDER BY d.display_name;
```

### Skiplist / generated skips

```cypher
MATCH (d:DeadSymbolCandidate {project: $project, candidate_state: 'skipped'})
RETURN d.display_name, d.skip_reason, d.source_file
ORDER BY d.display_name;
```

### Backing edges to indexed source symbols

```cypher
MATCH (d:DeadSymbolCandidate {project: $project})-[:BACKED_BY_SYMBOL]->(s:SymbolOccurrenceShadow)
RETURN d.display_name, s.symbol_qualified_name, s.symbol_id
ORDER BY d.display_name;
```

## False-positive warnings

`Periphery` output нельзя трактовать как deletion proof без контекста сборки.
Перед review/operator decision отдельно проверить:

1. Все ли релевантные targets были реально собраны перед `periphery scan`.
2. Не выпали ли declarations, удерживаемые через `public/open` API surface.
3. Нет ли runtime-only retention через reflection, ObjC selectors, dynamic
   entry points, generated code, macro/codegen outputs.
4. Не отсутствует ли `.palace/dead-symbol-skiplist.yaml` для generated/dynamic
   paths.
5. Не устарел ли upstream `PublicApiSymbol` / `ModuleContractSnapshot`
   относительно текущего `HEAD` commit.

Если хоть один из пунктов не доказан, candidate остаётся review-only и не
должен использоваться как основание для удаления кода.

## Rollback

### Удалить все candidate / binary-surface nodes для проекта

```cypher
MATCH (d:DeadSymbolCandidate {project: $project})
DETACH DELETE d;

MATCH (b:BinarySurfaceRecord {project: $project})
DETACH DELETE b;
```

### Удалить только edge families

```cypher
MATCH (:DeadSymbolCandidate {project: $project})-[rel:BACKED_BY_SYMBOL]->(:SymbolOccurrenceShadow)
DELETE rel;

MATCH (:DeadSymbolCandidate {project: $project})-[rel:BACKED_BY_PUBLIC_API]->(:PublicApiSymbol)
DELETE rel;

MATCH (:DeadSymbolCandidate {project: $project})-[rel:HAS_BINARY_SURFACE]->(:BinarySurfaceRecord)
DELETE rel;

MATCH (:DeadSymbolCandidate {project: $project})-[rel:BLOCKED_BY_CONTRACT_SYMBOL]->(:PublicApiSymbol)
DELETE rel;
```

### Полный rollback для проекта

```cypher
MATCH (d:DeadSymbolCandidate {project: $project})
DETACH DELETE d;

MATCH (b:BinarySurfaceRecord {project: $project})
DETACH DELETE b;
```

## Связанные артефакты

- Спецификация:
  `docs/superpowers/specs/2026-05-04-roadmap-33-dead-symbol-binary-surface.md`
- План:
  `docs/superpowers/plans/2026-05-04-roadmap-33-dead-symbol-binary-surface.md`
- Gate 0 spike:
  `docs/research/2026-05-04-dead-symbol-tool-output-spike/README.md`
- Код:
  `services/palace-mcp/src/palace_mcp/extractors/dead_symbol_binary_surface/`
- Unit tests:
  `services/palace-mcp/tests/extractors/unit/test_dead_symbol_binary_surface*.py`
- Integration tests:
  `services/palace-mcp/tests/extractors/integration/test_dead_symbol_binary_surface_integration.py`
