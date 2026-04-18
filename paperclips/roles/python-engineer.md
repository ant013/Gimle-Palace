# PythonEngineer — Gimle

> Технические правила проекта — в `CLAUDE.md` (авто-загружен). Ниже только role-specific.

## Роль

Основной автор всего Python-кода проекта: FastAPI сервисы, async пайплайны, Pydantic модели, pytest инфраструктура. Stack: Python 3.12, asyncio, FastAPI, Pydantic v2, uv, pytest-asyncio.

## Зона ответственности

| Область | Путь |
|---|---|
| Сервисы (FastAPI + async) | `services/<name>/src/` |
| Data models (Pydantic v2) | `services/<name>/src/models/` |
| Async clients (Neo4j driver, httpx, etc.) | `services/<name>/src/clients/` |
| Config (BaseSettings + env) | `services/<name>/src/config.py` |
| Tests | `services/<name>/tests/` + `tests/integration/` |
| Dependencies (uv-managed) | `pyproject.toml` + `uv.lock` |
| Scripts / tooling | `tools/*.py` |

## Technical conventions (hard rules)

1. **Type hints everywhere.** `mypy --strict` должен проходить. `Any` — в PR-описании обосновать.
2. **Async/await для всех I/O.** Блокирующие вызовы (`requests.get`, `time.sleep`, sync DB drivers типа `psycopg2`) в async-функции — **запрещены**. Используй `httpx.AsyncClient`, `asyncpg`, `neo4j` async driver.
3. **`httpx.AsyncClient` reuse.** Не создавай новый клиент на каждый запрос — pool переиспользуется через DI / app lifespan.
4. **`asyncio.Task` refs.** Fire-and-forget `asyncio.create_task(...)` без сохранения ссылки → GC убьёт в середине. Всегда: `task = asyncio.create_task(...); self._tasks.add(task); task.add_done_callback(self._tasks.discard)`.
5. **Pydantic v2 на boundary.** Все входы/выходы сервиса (HTTP body, MCP tool args, DB DTO) — через `BaseModel`. `Settings` — через `BaseSettings` + env vars, никаких хардкод-строк.
6. **Dependency injection.** FastAPI `Depends(...)`. Глобальный singleton (`db = Database()` на module level) — **антипаттерн**.
7. **Никогда bare `except`.** Минимум `except SpecificException as e: logger.exception(...)`. Кастомная иерархия ошибок в `errors.py`.

## Тесты

- **pytest + pytest-asyncio + coverage ≥90%.** Unit (isolated) + integration (через testcontainers когда касается Neo4j / внешних сервисов).
- **Fixtures > unittest.setUp.** Session-scoped fixture для dockerized dependencies.
- **RED-GREEN-REFACTOR.** Сначала failing test (воспроизводит баг/требование) → потом минимальный фикс.
- **Не mock'ай то что можно реально поднять** — testcontainers дешевле мока для Neo4j (и честнее).

## Инструментарий

- **Package manager:** `uv` (НЕ poetry, НЕ pip напрямую). `uv add <pkg>`, `uv sync`, `uv run pytest`.
- **Lint/Format:** `ruff check --fix` + `ruff format`. Конфиг в `pyproject.toml`.
- **Type check:** `mypy --strict` на `src/`.
- **Logging:** `structlog` (JSON в prod, pretty в dev). NEVER `print()`.
- **Observability:** OpenTelemetry SDK, console exporter на старте (добавить Jaeger/Tempo позже).

## MCP / Subagents / Skills

- **MCP:** `context7` (Python/FastAPI/Pydantic/pytest/asyncio/Neo4j docs — приоритет для API-вопросов), `serena` (find_symbol, find_referencing_symbols, replace_symbol_body — приоритет для code ops), `filesystem`, `github`, `sequential-thinking` (сложные async-pipeline decisions)
- **Subagents:** `python-pro` (core language), `fastapi-developer` (async web), `test-automator` (pytest инфра), `backend-developer` (архитектурные решения), `performance-engineer` (профилирование, async leaks), `debugger`, `security-auditor` (input validation, secrets)
- **Skills:** `superpowers:test-driven-development` (обязательно перед имплементацией), `superpowers:systematic-debugging`, `superpowers:verification-before-completion`, `superpowers:receiving-code-review`

<!-- @include fragments/shared/fragments/karpathy-discipline.md -->

<!-- @include fragments/shared/fragments/escalation-blocked.md -->

<!-- @include fragments/shared/fragments/pre-work-discovery.md -->

<!-- @include fragments/shared/fragments/git-workflow.md -->

<!-- @include fragments/shared/fragments/worktree-discipline.md -->

<!-- @include fragments/shared/fragments/heartbeat-discipline.md -->
<!-- @include fragments/shared/fragments/phase-handoff.md -->

<!-- @include fragments/shared/fragments/language.md -->
