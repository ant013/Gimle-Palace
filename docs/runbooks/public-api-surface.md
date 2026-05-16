# Public API Surface Runbook

Runbook для extractor `public_api_surface` из GIM-190.

## Что ingest'ит extractor

Extractor не генерирует artifacts сам и не редактирует production build files.
Он читает уже подготовленные snapshots из репозитория проекта:

- `.palace/public-api/kotlin/*.api`
- `.palace/public-api/swift/*.swiftinterface`

Отсутствие SKIE overlay допустимо для v1 и не считается ошибкой.

## Ожидаемая структура

Имена файлов задают `module_name`:

- `.palace/public-api/kotlin/UwMiniCore.api` -> `module_name=UwMiniCore`
- `.palace/public-api/swift/UwMiniKit.swiftinterface` -> `module_name=UwMiniKit`

`artifact_path` сохраняется относительно корня repo.

## Что пишет в граф

Extractor создаёт:

- `(:PublicApiSurface {id, project, module_name, language, commit_sha, artifact_kind, tool_name, tool_version, ...})`
- `(:PublicApiSymbol {id, fqn, kind, visibility, signature_hash, ...})`
- `(:PublicApiSurface)-[:EXPORTS]->(:PublicApiSymbol)`
- `(:PublicApiSymbol)-[:BACKED_BY_SYMBOL]->(:SymbolOccurrenceShadow)` только при exact-match по `symbol_qualified_name`

По умолчанию `visibility=package` сохраняется в графе, но это не external-public API.
Consumer query должен исключать такие symbols, если явно не запрошен internal/package mode.

## Минимальная подготовка artifacts

### Kotlin

Подготовьте BCV-style `.api` dump и положите его в:

```text
.palace/public-api/kotlin/<Module>.api
```

Если доступна tool version, положите её первой строкой:

```text
// tool: kotlin-bcv 0.18.1
```

### Swift

Подготовьте `.swiftinterface` и положите его в:

```text
.palace/public-api/swift/<Module>.swiftinterface
```

Extractor читает `// swift-compiler-version:` как `tool_version`.

## Проверка локально

Из `services/palace-mcp`:

```bash
uv run ruff check
uv run mypy src/
uv run pytest tests/extractors/unit/test_public_api_surface*.py -v
DOCKER_HOST=unix:///Users/anton/.docker/run/docker.sock \
TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE=/Users/anton/.docker/run/docker.sock \
TESTCONTAINERS_RYUK_DISABLED=true \
uv run pytest tests/extractors/integration/test_public_api_surface_integration.py -v
```

На этом host `testcontainers` не должен идти через `/var/run/docker.sock`, потому что
он указывает на чужой symlink. Используйте явный `DOCKER_HOST`.

## Частые проблемы

- `public_api_artifacts_required`:
  artifacts не найдены под `.palace/public-api/...`
- В `project analyze` это считается optional missing input для base smoke:
  checkpoint получает статус `MISSING_INPUT`, а не `RUN_FAILED`
- `schema_bootstrap_failed`:
  Neo4j driver не поднят в `mcp_server`
- Нет `BACKED_BY_SYMBOL` edges:
  нормализованный `fqn` не совпал 1:1 с `SymbolOccurrenceShadow.symbol_qualified_name`
