# Runbook: native `project analyze`

**Audience:** оператор Gimle, запускающий анализ на локальном native
`palace-mcp`.

**Goal:** обновить один проект через `project analyze --mode incremental` и
получить `summary.json` и `report.md` без запуска Docker.

## Runtime contract

| Path | MCP URL | Runtime ownership | Docker side effects |
|---|---|---|---|
| Native default | `http://localhost:8765/mcp` | Уже запущенный launchd service | Нет |
| Legacy iMac/Docker | `http://localhost:8080/mcp` | CLI с явным `--manage-runtime` | Есть |

Без `--manage-runtime` команда:

- не запускает Docker, Docker Compose или Colima;
- не создаёт
  `.gimle/runtime/project-analyze/docker-compose.project-analyze.yml`;
- не перезапускает Neo4j или `palace-mcp`;
- не изменяет compose-only mapping `PALACE_SCIP_INDEX_PATHS` в `.env`;
- использует уже запущенный MCP по переданному `--url`.

`--manage-runtime` — legacy opt-in. Он не нужен для обычного incremental
update.

## Prerequisites

Native service должен отвечать на порту `8765`:

```bash
curl -fsS http://localhost:8765/healthz
```

Ответ должен содержать:

```json
{"status":"ok","neo4j":"reachable"}
```

Исходники анализируемых iOS-проектов берутся из чистых mirror checkout:

```text
/Users/Shared/Ios/Gimle-Repos/HorizontalSystems/
```

Не используйте product-development checkout или старый
`/Users/ant013/Ios/HorizontalSystems/`, если оператор явно не выбрал другой
источник.

CLI запускается существующим native Python. Не создавайте отдельный `.venv` в
каждом task worktree:

```bash
export PALACE_PYTHON="/Users/ant013/Android/Gimle-Palace-native/.venv/bin/python"

# Используйте тот же source root, что и активный launchd service.
# Текущее значение можно увидеть в launchd environment:
launchctl print gui/$(id -u)/work.ant013.palace-mcp-native |
  grep PALACE_SERVICE_ROOT

# TODO: подставьте путь из launchd; если override отсутствует, используйте
# default из launch_native_macos.sh.
export PALACE_SERVICE_ROOT="/absolute/path/to/Gimle-Palace/services/palace-mcp"

test -x "$PALACE_PYTHON"
test -d "$PALACE_SERVICE_ROOT/src/palace_mcp"
```

Выведенный `PALACE_SERVICE_ROOT` — активный runtime workspace (на текущем хосте
это может быть `Gimle-Palace-serving`). Не удаляйте его как старый task
worktree, пока launchd ссылается на этот путь.

Проверить CLI:

```bash
cd "$PALACE_SERVICE_ROOT"
PYTHONPATH="$PALACE_SERVICE_ROOT/src" \
  "$PALACE_PYTHON" -m palace_mcp.cli project analyze --help
```

В help должны присутствовать `--mode {full,incremental}`, `--url` и
`--manage-runtime`. Последний выключен по умолчанию.

## Native incremental update

### 1. Подготовить переменные

Пример для Swift kit:

```bash
export GIMLE_ROOT="$(cd "$PALACE_SERVICE_ROOT/../.." && pwd)"
export TARGET_REPO="/Users/Shared/Ios/Gimle-Repos/HorizontalSystems/TronKit.Swift"
export TARGET_SLUG="tron-kit"
export TARGET_PROFILE="swift_kit"
export REPORT_OUT="$GIMLE_ROOT/.gimle/runtime/project-analyze/$TARGET_SLUG-analysis-report.md"
export SUMMARY_OUT="$GIMLE_ROOT/.gimle/runtime/project-analyze/$TARGET_SLUG-analysis-summary.json"

test -d "$TARGET_REPO/.git"
```

Для другого проекта замените только `TARGET_REPO`, `TARGET_SLUG` и
`TARGET_PROFILE`.

### 2. Запустить incremental analysis

```bash
cd "$PALACE_SERVICE_ROOT"
PYTHONPATH="$PALACE_SERVICE_ROOT/src" \
  "$PALACE_PYTHON" -m palace_mcp.cli project analyze \
  --repo-path "$TARGET_REPO" \
  --slug "$TARGET_SLUG" \
  --language-profile "$TARGET_PROFILE" \
  --mode incremental \
  --depth quick \
  --url http://localhost:8765/mcp \
  --report-out "$REPORT_OUT" \
  --summary-out "$SUMMARY_OUT"
```

Не добавляйте `--manage-runtime` в native-команду.

Requested mode остаётся `incremental`, но Gimle безопасно переключает
конкретный запуск на effective `full`, если:

- отсутствует предыдущий `indexed_commit`;
- текущий repo HEAD или file count нельзя определить;
- `detect_changes` недоступен, unusable или truncated;
- доля изменённых файлов превышает защитный threshold.

Это fallback анализа, а не запуск Docker.

### 3. Проверить результат

```bash
test -f "$REPORT_OUT"
test -f "$SUMMARY_OUT"
sed -n '1,80p' "$REPORT_OUT"
sed -n '1,200p' "$SUMMARY_OUT"
```

В summary должны быть как минимум:

- `"mode": "incremental"` — requested mode CLI;
- `"run_id"` и terminal `"status"`;
- `"report_out"` и `"summary_out"`;
- details run/audit с effective mode и fallback reason, если был выбран full.

Успешные terminal status:

- `SUCCEEDED`
- `SUCCEEDED_WITH_SKIPS`
- `SUCCEEDED_WITH_FAILURES`

Последний означает, что orchestration завершился, но отдельные extractor
checkpoint требуют проверки.

### 4. Убедиться, что Docker не был задействован

Native path не требует запуска Docker. После команды не должны появиться:

```text
.gimle/runtime/project-analyze/docker-compose.project-analyze.yml
```

и новые Gimle containers/images. Если Docker Desktop вообще выключен,
incremental update должен работать при здоровом native MCP.

## Swift-specific notes

Для `--language-profile swift_kit` CLI может подготовить или проверить SCIP
через `ensure_swift_scip_artifact(...)`.

Поддерживаются:

- `--emit-scip auto`
- `--emit-scip always`
- `--emit-scip never`

Дорогой `scip_emit_swift/.build` является reusable build cache. Не удаляйте его
при обычной очистке.

Если emit невозможен, CLI возвращает bounded fallback-команду, например:

```bash
bash "$GIMLE_ROOT/paperclips/scripts/scip_emit_swift_kit.sh" tron-kit
```

Missing optional inputs могут дать `MISSING_INPUT`, `SKIPPED` или итоговый
`SUCCEEDED_WITH_SKIPS`; это не обязательно hard failure.

## Troubleshooting: native path

### `localhost:8765` не отвечает

Проверьте launchd и логи:

```bash
launchctl print gui/$(id -u)/work.ant013.palace-mcp-native |
  sed -n '1,120p'
tail -n 100 ~/Library/Logs/palace-mcp-native/palace-mcp.err
tail -n 100 ~/Library/Logs/palace-mcp-native/palace-mcp.out
```

Если source/environment корректны, перезапустите native job:

```bash
launchctl kickstart -k gui/$(id -u)/work.ant013.palace-mcp-native
curl -fsS http://localhost:8765/healthz
```

Не запускайте Docker как автоматический fallback.

### `ModuleNotFoundError: No module named 'palace_mcp'`

Убедитесь, что используются native Python и source root активного service:

```bash
test -x "$PALACE_PYTHON"
test -f "$PALACE_SERVICE_ROOT/src/palace_mcp/__init__.py"
PYTHONPATH="$PALACE_SERVICE_ROOT/src" \
  "$PALACE_PYTHON" -c 'import palace_mcp; print(palace_mcp.__file__)'
```

### Requested incremental стал effective full

Посмотрите fallback reason в report/summary. Срабатывание безопасного full
fallback не означает ошибку runtime и не требует Docker.

## Legacy iMac/Docker path

Используйте этот раздел только когда оператор явно запросил legacy Docker
runtime. В этом режиме нужны оба аргумента:

```bash
cd "$PALACE_SERVICE_ROOT"
PYTHONPATH="$PALACE_SERVICE_ROOT/src" \
  "$PALACE_PYTHON" -m palace_mcp.cli project analyze \
  --repo-path "$TARGET_REPO" \
  --slug "$TARGET_SLUG" \
  --language-profile "$TARGET_PROFILE" \
  --mode incremental \
  --depth quick \
  --manage-runtime \
  --url http://localhost:8080/mcp \
  --env-file "$GIMLE_ROOT/.env" \
  --report-out "$REPORT_OUT" \
  --summary-out "$SUMMARY_OUT"
```

Только с `--manage-runtime` CLI может:

- написать compose override;
- обновить compose SCIP mapping;
- выполнить `docker compose --profile review up -d`;
- запустить или пересоздать `neo4j` и `palace-mcp`.

Порт `8080` обязателен в этом примере: compose публикует `8080:8000`, а default
CLI `8765` относится к native service.

Docker/buildx/Neo4j volume troubleshooting относится только к этому explicit
legacy path. Основной native incremental run не должен зависеть от этих
компонентов.

## Contract verification

Runtime boundary зафиксирован тестами:

- `test_project_analyze_parser_defaults_to_native_port_8765`
- `test_project_analyze_parser_accepts_incremental_mode`
- `test_project_analyze_parser_accepts_legacy_runtime_management`
- `test_project_analyze_does_not_manage_runtime_by_default`

При изменении CLI или runbook эти тесты должны оставаться зелёными.
