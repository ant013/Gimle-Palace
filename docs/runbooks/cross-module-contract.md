# Cross-Module Contract Runbook

## Что строит extractor

`cross_module_contract` записывает:

- `(:ModuleContractSnapshot)` для пары `consumer_module_name` → `producer_module_name` на конкретном `commit_sha`
- `(:ModuleContractSnapshot)-[:CONSUMES_PUBLIC_SYMBOL]->(:PublicApiSymbol)`
- опциональный `(:ModuleContractDelta)` для явно выбранных old/new commit pairs из `.palace/cross-module-contract/delta-requests.json`

v1 не создает `(:ContractSymbol)` и не добавляет public MCP/API surface.

## Предусловия

- для target project уже существуют `PublicApiSurface` / `PublicApiSymbol` от GIM-190
- в Tantivy уже есть occurrence docs для того же `commit_sha`
- consumer module owner можно вывести либо из `(:Module)-[:CONTAINS]->(:File)`, либо из committed map:
  `.palace/cross-module-contract/module-owners.json`
- если нужен minimal delta, explicit commit pair задается в:
  `.palace/cross-module-contract/delta-requests.json`

## Базовый smoke

```bash
cd services/palace-mcp
uv run pytest tests/extractors/unit/test_cross_module_contract.py -v
uv run pytest tests/extractors/integration/test_cross_module_contract_integration.py -v
```

## Neo4j проверки

### Snapshot count

```cypher
MATCH (snap:ModuleContractSnapshot {project: $project})
RETURN snap.consumer_module_name,
       snap.producer_module_name,
       snap.commit_sha,
       snap.symbol_count,
       snap.use_count,
       snap.file_count,
       snap.skipped_symbol_count
ORDER BY snap.consumer_module_name, snap.producer_module_name;
```

### Запрещенные duplicate symbols

```cypher
MATCH (n:ContractSymbol)
RETURN count(n) AS duplicate_contract_symbols;
```

Ожидается: `0`.

### Все consumed targets должны быть `PublicApiSymbol`

```cypher
MATCH (:ModuleContractSnapshot)-[r:CONSUMES_PUBLIC_SYMBOL]->(target)
WHERE NOT target:PublicApiSymbol
RETURN count(r) AS invalid_targets;
```

Ожидается: `0`.

### Commit boundaries

```cypher
MATCH (snap:ModuleContractSnapshot)-[r:CONSUMES_PUBLIC_SYMBOL]->(sym:PublicApiSymbol)
WHERE snap.commit_sha <> sym.commit_sha OR r.commit_sha <> sym.commit_sha
RETURN count(r) AS cross_commit_edges;
```

Ожидается: `0`.

### Same-module snapshots запрещены

```cypher
MATCH (snap:ModuleContractSnapshot)
WHERE snap.consumer_module_name = snap.producer_module_name
RETURN count(snap) AS same_module_snapshots;
```

Ожидается: `0`.

### Package visibility default policy

```cypher
MATCH (:ModuleContractSnapshot {project: $project})
      -[:CONSUMES_PUBLIC_SYMBOL]->(sym:PublicApiSymbol {visibility: "package"})
RETURN count(sym) AS package_symbols_in_default_contract;
```

Ожидается: `0` для default run.

### Evidence props на consumed edges

```cypher
MATCH (:ModuleContractSnapshot)-[r:CONSUMES_PUBLIC_SYMBOL]->(:PublicApiSymbol)
WHERE r.match_symbol_id IS NULL
   OR r.first_seen_path IS NULL
   OR r.evidence_paths_sample IS NULL
RETURN count(r) AS missing_consumer_evidence;
```

Ожидается: `0`.

### Delta inspection

```cypher
MATCH (delta:ModuleContractDelta {project: $project})
      -[:DELTA_FROM]->(from_snapshot:ModuleContractSnapshot)
MATCH (delta)-[:DELTA_TO]->(to_snapshot:ModuleContractSnapshot)
RETURN delta.consumer_module_name,
       delta.producer_module_name,
       delta.from_commit_sha,
       delta.to_commit_sha,
       delta.removed_consumed_symbol_count,
       delta.signature_changed_consumed_symbol_count,
       delta.added_consumed_symbol_count,
       delta.affected_use_count,
       from_snapshot.commit_sha AS from_snapshot_commit_sha,
       to_snapshot.commit_sha AS to_snapshot_commit_sha
ORDER BY delta.consumer_module_name, delta.producer_module_name;
```

### Delta targets must stay on `PublicApiSymbol`

```cypher
MATCH (:ModuleContractDelta)-[r:AFFECTS_PUBLIC_SYMBOL]->(target)
WHERE NOT target:PublicApiSymbol
RETURN count(r) AS invalid_delta_targets;
```

Ожидается: `0`.

## Tantivy limitation в v1

Текущий Tantivy schema позволяет:

- exact filter по `symbol_id`
- exact filter по `commit_sha`
- exact filter по `phase`
- вернуть `file_path` и `commit_sha`
- восстановить `line` и `col_start` из `doc_key`

Текущий schema не позволяет вернуть persisted `col_end` без schema change. Это сознательно не делается в GIM-192 v1, потому что approved spec прямо держит Tantivy schema migration вне scope.
