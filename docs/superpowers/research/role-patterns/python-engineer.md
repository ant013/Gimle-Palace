# Python Engineer — Research Notes

**Research date:** 2026-04-15
**Purpose:** inform `templates/engineers/python-engineer.md` in paperclip-shared-fragments
**Target deployment:** Gimle-Palace PythonEngineer role (Graphiti + FastAPI + asyncio + palace-mcp + Neo4j)

## 1. Sources reviewed

| Source | Type | Credibility | Key file |
|---|---|---|---|
| voltagent-subagents/python-pro | community plugin | VoltAgent marketplace | `python-pro.md` (237 lines) |
| voltagent-subagents/fastapi-developer | community plugin | VoltAgent marketplace | `fastapi-developer.md` (205 lines) |
| voltagent-subagents/backend-developer | community plugin | VoltAgent marketplace | `backend-developer.md` (215 lines) |
| claude-agents/python-development/python-pro | community plugin (wshobson-style) | opus-model, 2024/2025 ecosystem | `python-pro.md` |
| claude-agents/python-development/fastapi-pro | community plugin | opus-model | `fastapi-pro.md` |
| claude-agents/python-development/skills/ | skill bundle | 16 skills incl. `python-anti-patterns`, `async-python-patterns`, `python-testing-patterns`, `python-type-safety`, `uv-package-manager` | per-skill `SKILL.md` |
| claude-agents/backend-development/ | agents | incl. `temporal-python-pro`, `tdd-orchestrator`, `test-automator`, `performance-engineer`, `security-auditor` | agents list |
| claude-agents/api-scaffolding/ | agents | incl. `fastapi-pro`, `django-pro`, `backend-architect` | agents list |
| Medic paperclips/kmp-engineer.md | field-tested role (in-prod) | author's previous template | `kmp-engineer.md` (37 lines) |
| Medic paperclips/backend-engineer.md | field-tested role (in-prod) | author's previous template | `backend-engineer.md` (37 lines) |
| zhanymkanov/fastapi-best-practices | GitHub (~10k+ stars) | widely-cited reference | web |
| FastAPI official async docs | official | tiangolo | web |
| orchestrator.dev FastAPI 2025 | blog | — | web |
| pytest-asyncio patterns (Mergify, Medium) | articles 2025 | — | web |

10 primary role/plugin prompts + skill bundle + 4 web articles = enough signal.

## 2. Common structural patterns

Aggregate section frequency across the 5 community prompts (voltagent × 3 + claude-agents × 2):

| Section | Count | Notes |
|---|---|---|
| Role / Purpose statement (1-2 lines) | 5/5 | Universal |
| "When invoked" numbered trigger list | 3/5 | voltagent-style only |
| Development / implementation checklist | 5/5 | Universal (typing, tests, security, perf) |
| Capability taxonomy (Pythonic patterns, async, types, DB, web, perf, security) | 5/5 | All use flat "Area: bullets" blocks |
| Testing methodology block | 5/5 | pytest + coverage + fixtures + hypothesis |
| Package / dependency mgmt block | 4/5 | uv or poetry |
| Performance optimization block | 5/5 | |
| Security best practices block | 4/5 | |
| Communication Protocol / JSON context query | 3/5 | voltagent-only — likely overhead in our context |
| "Integration with other agents" | 4/5 | cross-agent delegation |
| Behavioral traits / Response approach | 2/5 | claude-agents only |
| Example interactions | 2/5 | claude-agents only |

Medic templates (37-line skeleton) use a much tighter shape:
- Role (1-2 lines)
- Responsibility table (path map)
- Pre-work checklist (if applicable)
- MCP / Subagents / Skills (single line each)
- `@include` fragments (git-workflow, worktree-discipline, heartbeat, language, pre-work-discovery)

**Divergence:** community prompts are 200-line prose capability dumps; Medic's are ~40-line operational role-cards. Our template should follow Medic's shape (per spec §4.1 ≤2000 token budget) and **use** community prompts only as a content-rule catalogue, not a structural model.

## 3. Canonical content rules (aggregate consensus)

Top rules appearing in 3+ sources (ranked by signal):

1. **Type hints everywhere** (PEP 484+, mypy strict) — 5/5 sources. Public API 100% annotated; generic types, Protocol, TypedDict, Literal, Annotated.
2. **Async/await for all I/O; never block the event loop** — 5/5. Ban `requests`/`time.sleep`/sync SQLAlchemy in `async def`. Use `httpx`, `asyncio.sleep`, `asyncpg`/`aiosqlite`/`SQLAlchemy 2.0 async`.
3. **pytest + pytest-asyncio; coverage > 90%** — 5/5. Fixtures > `setUp`, parameterize over loops, `httpx.AsyncClient` for FastAPI integration tests, Hypothesis for invariants.
4. **Pydantic v2 for all boundary data (request, response, settings)** — 4/5. `BaseSettings` for config; no hard-coded secrets.
5. **Dependency injection (FastAPI `Depends` or explicit constructor-based)** — 4/5. No globals, no module-level state.
6. **Modern tooling: uv + ruff + mypy (or pyright) + pyproject.toml** — 4/5. uv replacing pip/poetry, ruff replacing black+isort+flake8.
7. **Structured logging + correlation IDs (structlog or loguru)** — 4/5. No `print()`; JSON-ish logs; OpenTelemetry traces for production.
8. **Connection pooling and session management for DBs/HTTP clients** — 4/5. pool_pre_ping, pool_recycle, reuse `httpx.AsyncClient`.
9. **Custom exception hierarchy; never bare `except:` or silent pass** — 4/5. Domain errors with types, FastAPI exception handlers.
10. **Security: input validation via Pydantic, OWASP basics, bandit scan, secret env-var only** — 4/5.
11. **Background tasks offloaded (BackgroundTasks for light; Celery/Dramatiq/arq for heavy); track `asyncio.Task` refs** — 3/5 + strong web signal (orphaned tasks = leak).
12. **12-factor / lifespan events for startup+shutdown; graceful shutdown of resources** — 3/5.

## 4. Tooling recommendations

### MCP servers (pre-wire for Python role)

- **serena** (semantic code nav — symbol search, rename, references) — mirrors Medic roles
- **context7** — Python/FastAPI/Pydantic/SQLAlchemy/asyncio/pytest docs (critical: training data lag)
- **github** — PR/issue/CI workflows
- **filesystem** — non-Serena fallback ops
- **sequential-thinking** — for non-trivial async state machines, Graphiti graph schema
- **graphiti / neo4j MCP** (project-specific) — if palace product has an MCP for the memory-graph backend, pre-wire it; otherwise note as "add when available"

### Subagents invoked as tools

Primary: `python-pro`, `fastapi-pro` (or `fastapi-developer`).
Support: `test-automator`, `tdd-orchestrator`, `backend-architect`, `performance-engineer`, `security-auditor`, `debugger`, `refactoring-expert`.
Graphiti/Neo4j-specific: `database-administrator`, `postgres-pro` patterns transfer but Neo4j-specific subagent may not exist — note gap.

### Skills

- `superpowers:test-driven-development` — RED-GREEN-REFACTOR, pytest-first
- `superpowers:systematic-debugging` — when async tests flake or event-loop deadlock
- `superpowers:verification-before-completion` — run `pytest`, `ruff check`, `mypy` before claiming done
- `superpowers:receiving-code-review`, `simplify`
- If available: the claude-agents `python-anti-patterns` + `async-python-patterns` + `python-testing-patterns` skill pack — these are pure reference checklists, cheap to include by name.

### External refs (URL only, never paste inline)

- FastAPI docs: https://fastapi.tiangolo.com/
- FastAPI async: https://fastapi.tiangolo.com/async/
- zhanymkanov/fastapi-best-practices: https://github.com/zhanymkanov/fastapi-best-practices
- Pydantic v2: https://docs.pydantic.dev/
- SQLAlchemy 2.0 async: https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html
- pytest: https://docs.pytest.org/ — pytest-asyncio: https://pytest-asyncio.readthedocs.io/
- uv: https://docs.astral.sh/uv/ — ruff: https://docs.astral.sh/ruff/
- PEP 8 / PEP 484 / PEP 604 / PEP 695
- asyncio: https://docs.python.org/3/library/asyncio.html

## 5. Anti-patterns / mistakes to call out

Explicit bans the template should surface (signal: 3+ sources OR load-bearing for Gimle-Palace):

- `requests.get()`, `time.sleep()`, sync SQLAlchemy inside `async def` — **blocks event loop, kills throughput**.
- `asyncio.create_task(...)` without holding the reference — **orphaned tasks get GC'd mid-flight; use TaskGroup or a set+discard pattern**.
- Hard-coded secrets / config — **use `pydantic_settings.BaseSettings` + env vars**.
- Module-level global state / singletons instead of DI — **breaks tests, breaks async concurrency**.
- Double retry (retry at client AND at application layer) — **exponential pain**.
- `print()` for logging; string-concatenated log messages — **use structlog/loguru with keyword kwargs**.
- Bare `except:`, `except Exception: pass`, swallowing coroutines — **hidden bugs**.
- `setUp/tearDown` (unittest) instead of pytest fixtures — **no dependency injection of test resources**.
- Missing `await` (returns coroutine object, falsy-truthy bug) — **mypy + ruff + `RuntimeWarning: coroutine was never awaited` catch these**.
- One giant `main.py` for FastAPI — **use routers + services + repositories; keep path operations thin**.
- Shared mutable state between async tasks without `asyncio.Lock` — **races**.
- Mixing sync + async ORM sessions in the same transaction — **session corruption**.
- No `lifespan` event manager — **resources (DB pool, HTTP client, Neo4j driver) leak on shutdown**.

Gimle-Palace specific (Graphiti + Neo4j):
- Opening a new Neo4j driver per request instead of one app-scoped driver — **connection storm**.
- Synchronous Neo4j driver in async FastAPI path — **must use `neo4j.AsyncGraphDatabase`**.
- Writing to Graphiti without idempotency keys for episodic ingestion — **duplicate nodes**.

## 6. Recommendations for template

**Structure decision:** mirror Medic's role-card shape (Role, Responsibility table, Checklist, MCP/Subagents/Skills, `@include` fragments). Community 200-line capability dumps blow the token budget. Push the 12 canonical rules into a short "Правила" block (5-7 lines max) and delegate detail to `context7` + anti-patterns skill. Put the Gimle-Palace-specific section (Graphiti/Neo4j) inline because no external skill covers it.

**Content bans to include (explicit, short list):**
- no blocking I/O in `async def` (banned libs: `requests`, `time.sleep`, sync SQLAlchemy, sync `neo4j.GraphDatabase` in async paths)
- no `asyncio.create_task` without reference retention — use TaskGroup
- no hard-coded secrets / module-level config — `pydantic_settings.BaseSettings` only
- no globals — DI via FastAPI `Depends` or constructor
- no `print()` — structlog/loguru with structured fields
- no bare `except:` or swallowed coroutines
- no `pytest` without `pytest-asyncio` + `httpx.AsyncClient` for API tests

**Tooling to pre-wire (final list):**
- MCP: `serena`, `context7`, `github`, `filesystem`, `sequential-thinking` (+ Graphiti/Neo4j MCP if product exposes one; otherwise flag as TODO)
- Subagents: `python-pro`, `fastapi-pro`, `test-automator`, `backend-architect`, `performance-engineer`, `security-auditor`, `debugger`
- Skills: `superpowers:test-driven-development`, `superpowers:systematic-debugging`, `superpowers:verification-before-completion`, `superpowers:receiving-code-review`, `simplify`

**Responsibility table (Gimle-Palace-tailored) candidate:**

| Область | Путь |
|---|---|
| FastAPI service | `palace-mcp/` or `services/*/` (TBC with user) |
| Graphiti ingestion | `ingestion/` pipeline |
| Neo4j driver / queries | `graph/` adapter |
| Telemetry | `telemetry/` (structlog + OTEL) |
| Tests | `tests/` (pytest, pytest-asyncio, httpx) |
| Config | `pyproject.toml` + `.env.example` |

**Verification gate (Medic-style, must-do before done):**
- `uv run pytest` green
- `uv run ruff check` clean
- `uv run mypy` (or `pyright`) clean
- if FastAPI: `uvicorn app:app` boots + `/health` 200 + `/docs` renders

**Tokens budget estimate:** target ≤1500 tokens for the role body; after `@include` of standard fragments (pre-work-discovery, git-workflow, worktree-discipline, heartbeat-discipline, language) total ≈1800-2000 tokens. Fits spec §4.1.

## 7. Open questions for user

1. **Exact Gimle-Palace directory layout** — I inferred `palace-mcp/`, `ingestion/`, `graph/`, `telemetry/` from the brief but need the actual tree to write the responsibility table. Should I probe `/Users/ant013/Android/Gimle-Palace/` locally, or will you supply canonical paths?
2. **uv vs poetry vs pip** — canonical choice for Gimle-Palace? (uv is the 2025 default in community prompts; confirm.)
3. **Neo4j MCP** — is there a `neo4j` or `graphiti` MCP server the team uses? If yes, name it so I can pre-wire. If no, template flags as "add when available".
4. **Logging/Telemetry stack** — structlog vs loguru vs stdlib? OpenTelemetry exporter target (Honeycomb, Tempo, local)? Affects the `telemetry/` responsibility + observability rule wording.
5. **Test framework** — pytest + pytest-asyncio is the universal community default, but does Graphiti or palace-mcp use anything custom (behave, hypothesis-stateful, testcontainers)?
6. **Python version floor** — 3.11 (voltagent community baseline) vs 3.12+ (claude-agents baseline). Template should pin one.
7. **Include anti-patterns skill inline, or rely on `context7`?** — the claude-agents `python-anti-patterns` SKILL.md is ~100 lines of great content but belongs to a plugin not in your current marketplace. Options: (a) reference by name, (b) copy 5-10 most-critical items inline (chose #5 path in §5 above as a preview), (c) link to a doc.
