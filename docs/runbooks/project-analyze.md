# Runbook: `project analyze`

**Audience:** оператор Gimle, запускающий host-side orchestration через `palace-mcp` CLI.  
**Goal:** от checkout до `summary.json` и `report.md` для одного проекта через `project analyze`.  
**Target time-to-first-success:** ≤ 10 минут на хосте с рабочими `docker compose`, `uv` и `docker buildx >= 0.17.0`.  
**Measured on 2026-05-15:** полный success на этой машине не достигнут из-за двух host-specific блокеров: stale Neo4j credentials в существующем volume и `docker buildx 0.10.5`.

## Что именно делает CLI

`uv run python -m palace_mcp.cli project analyze ...`:

1. валидирует `--repo-path`, `--slug`, `--language-profile`;
2. резолвит host repo path в container path;
3. пишет compose override в `.gimle/runtime/project-analyze/docker-compose.project-analyze.yml`;
4. для `swift_kit` проверяет/генерирует `scip/index.scip` и `scip/index.scip.meta.json`;
5. для `swift_kit` мерджит `PALACE_SCIP_INDEX_PATHS=` в `.env`;
6. поднимает `neo4j` и `palace-mcp` через `docker compose --profile review up -d`;
7. ждёт `http://localhost:8080/healthz`;
8. вызывает MCP tools `palace.project.analyze`, затем циклически `palace.project.analyze_status`, а при `RESUMABLE` вызывает `palace.project.analyze_resume`;
9. пишет:
   - `.gimle/runtime/project-analyze/<slug>-analysis-report.md`
   - `.gimle/runtime/project-analyze/<slug>-analysis-summary.json`

## Prerequisites

Подтверждено из `docker-compose.yml` и `services/palace-mcp/src/palace_mcp/cli.py`:

- host-порт runtime: `8080`;
- MCP URL по умолчанию: `http://localhost:8080/mcp`;
- health endpoint: `http://localhost:8080/healthz`;
- compose profile для operator path: `review`;
- CLI entrypoint: `uv run python -m palace_mcp.cli`;
- env file по умолчанию: repo-root `.env`.

Проверьте окружение:

```bash
cd /Users/Shared/Ios/worktrees/cx/Gimle-Palace
docker --version
docker compose version
docker buildx version
test -f .env
```

Ожидаемо:

- `docker` и `docker compose` отвечают без ошибки;
- `docker buildx version` показывает `0.17.0` или новее;
- `.env` существует.

## Step 1. Проверка entrypoint и fallback script

```bash
cd /Users/Shared/Ios/worktrees/cx/Gimle-Palace/services/palace-mcp
uv run python -m palace_mcp.cli project analyze --help
uv run python -m palace_mcp.cli tool call --help
cd /Users/Shared/Ios/worktrees/cx/Gimle-Palace
bash paperclips/scripts/scip_emit_swift_kit.sh --help
```

Ожидаемо:

- `project analyze --help` показывает `--repo-path`, `--slug`, `--language-profile`, `--emit-scip`, `--env-file`, `--report-out`, `--summary-out`;
- `tool call --help` показывает форму `palace-mcp tool call [--url URL] [--json JSON] tool_name`;
- fallback script показывает options `--repo-path`, `--remote-host`, `--remote-base`, `--remote-relative-path`.

Если запускать `python -m palace_mcp.cli ...` без `uv run`, можно получить `ModuleNotFoundError`.

## Step 2. Подготовка переменных

Ниже минимальный copy-paste-safe шаблон. Меняйте только строки с `# TODO`.

```bash
export GIMLE_ROOT="/Users/Shared/Ios/worktrees/cx/Gimle-Palace"
export ENV_FILE="$GIMLE_ROOT/.env"
export REPORT_OUT="$GIMLE_ROOT/.gimle/runtime/project-analyze/py-mini-project-analysis-report.md"
export SUMMARY_OUT="$GIMLE_ROOT/.gimle/runtime/project-analyze/py-mini-project-analysis-summary.json"

export TARGET_REPO="$GIMLE_ROOT/services/palace-mcp/tests/extractors/fixtures/py-mini-project"
export TARGET_SLUG="py-mini-project"
export TARGET_PROFILE="python_service"

# TODO: for a real project, replace TARGET_REPO/TARGET_SLUG/TARGET_PROFILE.
# Example Swift project:
# export TARGET_REPO="/absolute/path/to/TronKit.Swift"
# export TARGET_SLUG="tron-kit"
# export TARGET_PROFILE="swift_kit"
```

Проверка:

```bash
test -d "$TARGET_REPO"
printf '%s\n' "$TARGET_SLUG" "$TARGET_PROFILE"
```

## Step 3. Правила `--emit-scip` и `.env` merge

Этот шаг относится только к `--language-profile swift_kit`.

`--emit-scip` работает так:

- `auto`: если `scip/index.scip` отсутствует, пустой или metadata устарела, CLI попытается сгенерировать новый SCIP локально;
- `always`: всегда форсирует новый local emit;
- `never`: новый emit запрещён; если usable SCIP artifact отсутствует или metadata stale, CLI падает с `missing_required_scip_artifact`.

Metadata-файл должен лежать в:

```bash
$TARGET_REPO/scip/index.scip.meta.json
```

`.env` merge для `PALACE_SCIP_INDEX_PATHS` работает так:

- если ключа нет, CLI добавляет строку `PALACE_SCIP_INDEX_PATHS=<json>`;
- если ключ есть и JSON валиден, CLI сохраняет существующие slug->path пары и обновляет только текущий `slug`;
- если JSON невалиден или это не object из string->string, CLI падает до запуска runtime.

## Step 4. Запуск анализа

```bash
cd "$GIMLE_ROOT/services/palace-mcp"
uv run python -m palace_mcp.cli project analyze \
  --repo-path "$TARGET_REPO" \
  --slug "$TARGET_SLUG" \
  --language-profile "$TARGET_PROFILE" \
  --depth quick \
  --env-file "$ENV_FILE" \
  --report-out "$REPORT_OUT" \
  --summary-out "$SUMMARY_OUT"
```

Для Swift при необходимости добавьте явную политику:

```bash
cd "$GIMLE_ROOT/services/palace-mcp"
uv run python -m palace_mcp.cli project analyze \
  --repo-path "$TARGET_REPO" \
  --slug "$TARGET_SLUG" \
  --language-profile "$TARGET_PROFILE" \
  --emit-scip auto \
  --depth quick \
  --env-file "$ENV_FILE" \
  --report-out "$REPORT_OUT" \
  --summary-out "$SUMMARY_OUT"
```

CLI сам использует:

```bash
docker compose \
  --env-file "$ENV_FILE" \
  -f "$GIMLE_ROOT/docker-compose.yml" \
  -f "$GIMLE_ROOT/.gimle/runtime/project-analyze/docker-compose.project-analyze.yml" \
  --profile review \
  up -d neo4j palace-mcp
```

Ожидаемо:

- создаётся или обновляется override-файл `.gimle/runtime/project-analyze/docker-compose.project-analyze.yml`;
- CLI poll-ит `palace.project.analyze_status` каждые 2 секунды;
- при статусе `RESUMABLE` CLI сам вызывает `palace.project.analyze_resume`.

## Step 5. Проверка compose override и runtime

```bash
cd "$GIMLE_ROOT"
sed -n '1,40p' .gimle/runtime/project-analyze/docker-compose.project-analyze.yml
docker compose \
  --env-file "$ENV_FILE" \
  -f docker-compose.yml \
  -f .gimle/runtime/project-analyze/docker-compose.project-analyze.yml \
  --profile review \
  ps
curl -fsS http://localhost:8080/healthz
```

Ожидаемо:

- override-файл существует по пути `.gimle/runtime/project-analyze/docker-compose.project-analyze.yml`;
- если repo уже покрыт существующим mount из `docker-compose.yml`, override может быть просто `services: {}`;
- если нужен новый bind mount, override содержит `palace-mcp.volumes: - <host-parent>:<container-parent>:ro`;
- `docker compose ... ps` показывает `neo4j` и `palace-mcp`;
- `curl` возвращает успешный ответ;
- health wait внутри CLI ограничен 60 секундами.

## Step 6. Проверка артефактов

```bash
test -f "$REPORT_OUT"
test -f "$SUMMARY_OUT"
sed -n '1,40p' "$REPORT_OUT"
sed -n '1,220p' "$SUMMARY_OUT"
```

Ожидаемо:

- markdown начинается с `# AnalysisRun <run_id>`;
- `summary.json` содержит как минимум:
  - `"slug"`
  - `"repo_path"`
  - `"language_profile"`
  - `"compose_files"`
  - `"compose_override_changed"`
  - `"env_changed"`
  - `"palace_recreated"`
  - `"run_id"`
  - `"status"`
  - `"report_out"`
  - `"summary_out"`
  - `"result"`

Текущий implementation fact:

- в текущем `project_analyze.py` финализация идёт в `SUCCEEDED_WITH_FAILURES` и при all-OK checkpoints, и при partial failures;
- поэтому ориентируйтесь не только на `status`, но и на `summary.json -> result`, `overview`, `audit`, `next_actions`.

## Step 7. Проверка `status` / `resume` вручную

Если CLI был прерван или нужно вручную проверить durable state:

```bash
cd "$GIMLE_ROOT/services/palace-mcp"
uv run python -m palace_mcp.cli tool call palace.project.analyze_status \
  --url http://localhost:8080/mcp \
  --json '{"run_id":"# TODO: replace with real run_id"}'
```

Если ответ вернул `status: "RESUMABLE"`:

```bash
cd "$GIMLE_ROOT/services/palace-mcp"
uv run python -m palace_mcp.cli tool call palace.project.analyze_resume \
  --url http://localhost:8080/mcp \
  --json '{"run_id":"# TODO: replace with real run_id"}'
```

Что важно:

- `palace.project.analyze_status` читает durable состояние из Neo4j;
- `RUNNING` с истёкшим lease переводится в `RESUMABLE`;
- `palace.project.analyze_resume` продолжает с первого checkpoint со статусом `NOT_ATTEMPTED`;
- poll interval в CLI по умолчанию `2` секунды.

## Step 8. Swift fallback: MacBook emit, iMac continue

Если local Swift toolchain отсутствует или local emit падает, CLI пишет `SCIP_EMIT_TOOLCHAIN_UNSUPPORTED` и сохраняет `fallback_command` в `summary.json`.

Форма fallback-команды:

```bash
# TODO: replace tron-kit with your Swift slug
bash paperclips/scripts/scip_emit_swift_kit.sh tron-kit \
  --repo-path /Users/ant013/Ios/HorizontalSystems/TronKit.Swift \
  --remote-host imac-ssh.ant013.work \
  --remote-base /Users/Shared/Ios/HorizontalSystems \
  --remote-relative-path TronKit.Swift
```

Правило продолжения:

- SCIP emit делается на MacBook, где есть рабочий Swift toolchain;
- script копирует `scip/index.scip` и `scip/index.scip.meta.json` на iMac repo mount;
- metadata с `artifact_origin: "remote_copy"` считается валидной для последующего запуска `project analyze` на iMac;
- после успешного копирования повторно запускайте обычный `project analyze` уже на iMac/операторском хосте.

## Step 9. Follow-up queries в Memory Palace

После успешного runtime smoke можно делать follow-up запросы через тот же CLI:

```bash
cd "$GIMLE_ROOT/services/palace-mcp"
uv run python -m palace_mcp.cli tool call palace.memory.lookup \
  --url http://localhost:8080/mcp \
  --json '{"entity_type":"Project","filters":{"slug":"py-mini-project"},"project":"gimle","limit":5}'
```

```bash
cd "$GIMLE_ROOT/services/palace-mcp"
uv run python -m palace_mcp.cli tool call palace.memory.lookup \
  --url http://localhost:8080/mcp \
  --json '{"entity_type":"Symbol","project":"py-mini-project","limit":5}'
```

Если анализ запускался с `--bundle`, проверьте bundle freshness:

```bash
cd "$GIMLE_ROOT/services/palace-mcp"
uv run python -m palace_mcp.cli tool call palace.memory.bundle_status \
  --url http://localhost:8080/mcp \
  --json '{"bundle":"# TODO: replace with real bundle name"}'
```

## Top-3 troubleshooting

### 1. `neo4j` stuck in `health: starting` + `The client is unauthorized due to authentication failure`

Симптом:

```bash
cd /Users/Shared/Ios/worktrees/cx/Gimle-Palace
docker compose --profile review ps
docker compose logs --tail=80 neo4j
```

Причина:

- существующий `neo4j_data` volume был создан с другим паролем;
- текущий `.env` уже содержит другой `NEO4J_PASSWORD`;
- healthcheck использует `cypher-shell -u neo4j -p ... 'RETURN 1'`.

Что делать:

- проверьте `NEO4J_PASSWORD` в `.env`;
- для чистого smoke используйте isolated volumes/project name;
- не переиспользуйте чужой рабочий volume вслепую.

### 2. `compose build requires buildx 0.17.0 or later`

Симптом:

```bash
cd /Users/Shared/Ios/worktrees/cx/Gimle-Palace/services/palace-mcp
uv run python -m palace_mcp.cli project analyze --repo-path "$TARGET_REPO" --slug "$TARGET_SLUG" --language-profile "$TARGET_PROFILE"
```

Причина:

- runtime поднимает `palace-mcp` через compose build;
- локальный `docker buildx` старее требуемого порога.

Что делать:

```bash
docker buildx version
```

- обновите Docker/buildx до `0.17.0+`;
- затем повторите `project analyze`.

### 3. `ModuleNotFoundError: No module named 'palace_mcp'`

Симптом:

```bash
cd /Users/Shared/Ios/worktrees/cx/Gimle-Palace/services/palace-mcp
python -m palace_mcp.cli project analyze --help
```

Причина:

- запуск идёт вне `uv`-managed environment.

Что делать:

```bash
cd /Users/Shared/Ios/worktrees/cx/Gimle-Palace/services/palace-mcp
uv run python -m palace_mcp.cli project analyze --help
```

## Verification captured for this doc

Команды, выполненные при подготовке runbook:

```bash
cd /Users/Shared/Ios/worktrees/cx/Gimle-Palace/services/palace-mcp
uv run python -m palace_mcp.cli project analyze --help

cd /Users/Shared/Ios/worktrees/cx/Gimle-Palace
docker compose --profile review ps
docker compose logs --tail=80 neo4j
docker inspect --format '{{json .State.Health}}' gimle-palace-neo4j-1
docker buildx version
```

Observed on 2026-05-15:

- CLI help matched source flags.
- Runtime smoke was blocked by two host-specific issues:
  - stale Neo4j credentials in existing Docker volume;
  - `docker buildx` version `0.10.5`, while compose requires `0.17.0+` for this path.
