# Runbook: `project analyze` operator path

**Audience:** оператор Gimle, запускающий host-side orchestration через `palace-mcp` CLI.  
**Goal:** от checkout до `summary.json` и `report.md` для одного проекта через `project analyze`.  
**Target time-to-first-success:** ≤ 10 минут на хосте с рабочими `docker compose`, `uv` и `docker buildx >= 0.17.0`.
**Measured on 2026-05-15:** full success на этой машине не достигнут из-за host blockers: stale Neo4j credentials volume и `docker buildx 0.10.5`.

## Что делает команда

`project analyze`:

1. резолвит host repo path в container path;
2. пишет override-файл `.gimle/runtime/project-analyze/docker-compose.project-analyze.yml`;
3. для `swift_kit` при необходимости готовит SCIP и обновляет `PALACE_SCIP_INDEX_PATHS` в `.env`;
4. поднимает runtime через `docker compose --profile review up -d neo4j palace-mcp`;
5. ждёт `http://localhost:8080/healthz`;
6. вызывает MCP tools:
   - `palace.project.analyze`
   - `palace.project.analyze_status`
   - `palace.project.analyze_resume`
7. пишет:
   - `.gimle/runtime/project-analyze/<slug>-analysis-report.md`
   - `.gimle/runtime/project-analyze/<slug>-analysis-summary.json`

## Prerequisites

Из project files подтверждены следующие зависимости:

- repo root содержит `docker-compose.yml`, `.env`, `services/palace-mcp/pyproject.toml`;
- runtime публикует `palace-mcp` на `http://localhost:8080`;
- health endpoint: `http://localhost:8080/healthz`;
- compose profile для operator path: `review`;
- CLI запускать через `uv run` из `services/palace-mcp`.

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
- `docker buildx version` показывает версию `0.17.0` или новее;
- `.env` существует.

## Step 1. Проверка CLI entrypoint

```bash
cd /Users/Shared/Ios/worktrees/cx/Gimle-Palace/services/palace-mcp
uv run python -m palace_mcp.cli project analyze --help
```

Ожидаемо:

- help выводит флаги `--repo-path`, `--slug`, `--language-profile`, `--depth`, `--env-file`, `--report-out`, `--summary-out`.

Если `python -m palace_mcp.cli ...` запускать без `uv run`, импорт пакета может не разрешиться.

## Step 2. Подготовка переменных

Ниже минимальный copy-paste-safe шаблон. Замените только строки с `# TODO`.

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

Ожидаемо:

```bash
test -d "$TARGET_REPO"
printf '%s\n' "$TARGET_SLUG" "$TARGET_PROFILE"
```

## Step 3. Запуск анализа

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

Во время запуска CLI сам использует:

```bash
docker compose \
  --env-file "$ENV_FILE" \
  -f "$GIMLE_ROOT/docker-compose.yml" \
  -f "$GIMLE_ROOT/.gimle/runtime/project-analyze/docker-compose.project-analyze.yml" \
  --profile review \
  up -d neo4j palace-mcp
```

Ожидаемо:

- создаётся override-файл `.gimle/runtime/project-analyze/docker-compose.project-analyze.yml`;
- `neo4j` и `palace-mcp` стартуют;
- CLI опрашивает `palace.project.analyze_status` каждые 2 секунды;
- при статусе `RESUMABLE` CLI сам вызывает `palace.project.analyze_resume`.

## Step 4. Проверка runtime

Пока команда работает или сразу после неё:

```bash
cd "$GIMLE_ROOT"
docker compose \
  --env-file "$ENV_FILE" \
  -f docker-compose.yml \
  -f .gimle/runtime/project-analyze/docker-compose.project-analyze.yml \
  --profile review \
  ps
curl -fsS http://localhost:8080/healthz
```

Ожидаемо:

- `docker compose ... ps` показывает `neo4j` и `palace-mcp`;
- `curl` возвращает успешный HTTP status;
- health wait в CLI ограничен 60 секундами.

## Step 5. Проверка артефактов

```bash
test -f "$REPORT_OUT"
test -f "$SUMMARY_OUT"
sed -n '1,40p' "$REPORT_OUT"
sed -n '1,160p' "$SUMMARY_OUT"
```

Ожидаемо:

- markdown начинается с `# AnalysisRun <run_id>`;
- JSON содержит поля:
  - `"slug"`
  - `"repo_path"`
  - `"language_profile"`
  - `"compose_files"`
  - `"run_id"`
  - `"status"`
  - `"report_out"`
  - `"summary_out"`

Успех CLI считается по terminal status:

- `SUCCEEDED`
- `SUCCEEDED_WITH_SKIPS`
- `SUCCEEDED_WITH_FAILURES`

Если вернулся terminal error, смотреть `summary.json -> result`.

## Swift-specific notes

Для `--language-profile swift_kit` CLI дополнительно:

- вызывает `ensure_swift_scip_artifact(...)`;
- поддерживает `--emit-scip auto|always|never`;
- обновляет `PALACE_SCIP_INDEX_PATHS` в `.env`;
- может завершиться `SCIP_EMIT_TOOLCHAIN_UNSUPPORTED` с fallback-командой вида:

```bash
# TODO: replace tron-kit with your Swift slug
bash paperclips/scripts/scip_emit_swift_kit.sh tron-kit
```

### Optional extractor inputs for `swift_kit`

Для `tron-kit` и похожих Swift kit missing optional inputs больше не должны
ломать base smoke:

- `public_api_surface` без `.palace/public-api/...` → checkpoint `MISSING_INPUT`
- `cross_module_contract` без результата `public_api_surface` → checkpoint `SKIPPED`
- `hot_path_profiler` без `profiles/` или trace files → checkpoint `MISSING_INPUT`
- `cross_repo_version_skew` без usable `:DEPENDS_ON` graph → checkpoint `MISSING_INPUT`

Эти статусы могут привести к terminal result `SUCCEEDED_WITH_SKIPS`, но не
должны переводить run в `SUCCEEDED_WITH_FAILURES`, если hard failures нет.

## Top-3 troubleshooting

### 1. `neo4j` stuck in `health: starting` + `The client is unauthorized due to authentication failure`

Симптом:

```bash
docker compose --profile review ps
docker compose logs --tail=80 neo4j
```

Причина:

- существующий `neo4j_data` volume был создан с другим паролем, а текущий `.env` уже содержит новый `NEO4J_PASSWORD`;
- healthcheck использует `cypher-shell -u neo4j -p ... 'RETURN 1'`, поэтому mismatch держит сервис в `starting`.

Что делать:

- проверьте, что `NEO4J_PASSWORD` в `.env` соответствует паролю volume;
- если нужен чистый локальный smoke, поднимайте isolated compose project с новыми volume;
- не меняйте production/local volumes без понимания, кто ими пользуется.

### 2. `compose build requires buildx 0.17.0 or later`

Симптом:

```bash
uv run python -m palace_mcp.cli project analyze ...
```

падает ещё до запуска анализа.

Причина:

- `project analyze` поднимает `palace-mcp` через compose build;
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
python -m palace_mcp.cli project analyze --help
```

Причина:

- запуск идёт вне `uv run`, поэтому проектовый package context не поднят.

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
