# Gimlé Palace — Design Specification

*Project name origin: **Gimlé** — зал в скандинавской мифологии, последнее убежище достойных после Рагнарёка. Метафорически — защищённое место где хранится ценное знание, доступное только для тех, кто умеет к нему обратиться (в нашем случае — агенты с правильными MCP-эндпоинтами).*

**Document date:** 2026-04-15
**Status:** Draft · awaiting user review
**Author:** brainstorming session (Claude Opus 4.6 + Anton Stavnichiy)

---

## 1. Overview & Goals

**Problem.** AI-coding-agents (Claude Code, Codex, Gemini, Cursor, OpenCode) приходят в большой проект "вслепую": каждую сессию переоткрывают структуру репозитория через grep/read, быстро съедают контекстное окно разведкой и hallucinate'ят пути/абстракции. На масштабе 10+ библиотек и двух мобильных приложений (реальный пример — Unstoppable Wallet: android + ios + ~15 Kotlin/Swift kit-библиотек) эта проблема умножается.

**Solution.** Построить переносимый self-hostable **стек "memory palace + команда агентов"**, который:

1. При развёртывании однажды глубоко анализирует набор репозиториев (архитектура, UI-компоненты, API, layers, зависимости, security, blockchain specifics) силами команды специализированных reviewer-агентов;
2. Хранит результат анализа в bi-temporal knowledge graph с тегами, namespace'ами и историей итераций;
3. Выставляет эту память через MCP любому AI-coding-agent — локальному Claude Code / Codex на машине разработчика или "сотрудникам" Paperclip AI;
4. Сам себя поддерживает в актуальном состоянии через scheduled delta-updates на новых коммитах;
5. Пишет telemetry по каждому обращению → считает реальную экономию токенов и latency.

**Non-goals.**
- Не являемся замена IDE-расширений (Continue.dev, Cursor) — мы слой ПОД ними.
- Не переписываем Paperclip AI — когда он доступен, он **control plane** (оркестрация команды, budgets, approvals). Мы data plane + specialized tools.
- Не пишем полноценный agent framework уровня Paperclip/Letta/AutoGen (с GUI, governance UI, cross-agent messaging). **Но** — минимальный self-contained `lite-orchestrator` (§4.10) включён в стек для профилей `review` и `analyze`, где Paperclip выключен. Lite-orchestrator только спавнит задачи/агентов и логирует — без визуалки и сложной coordination.

**Portability requirement.** Стек должен быть полностью переносимым: склонировать репозиторий → задать `.env` + `projects/<name>.yaml` → `just setup` → работает на любом проекте любой платформы. **Zero Unstoppable-specific code в ядре.** Unstoppable Wallet — первый реальный подопытный, не предмет оптимизации.

---

## 2. Architecture Overview

### 2.1 Client / Server split

```
┌──────────────────────────────────────────┐   ┌──────────────────────────────┐
│           SERVER SIDE                    │   │          CLIENT SIDE         │
│      (docker-compose on server)          │   │   (dev machine, laptop)      │
│                                          │   │                              │
│  ┌─────────────────┐                     │   │   ~/.claude/mcp.json         │
│  │ Neo4j Community │                     │   │   ~/.claude/skills/*         │
│  └────────┬────────┘                     │   │   ~/.claude/agents/*         │
│           │                              │   │                              │
│  ┌────────▼────────┐   ┌──────────────┐  │   │   устанавливается одной      │
│  │ Graphiti svc    │←─→│ palace-mcp   │◀─┼───┼──▶  командой:                │
│  └─────────────────┘   └──────────────┘  │   │                              │
│                                          │   │   curl <server>/install |sh  │
│  ┌─────────────┐  ┌───────────────────┐  │   │   [--server <url>]           │
│  │ Serena MCP  │  │ code-analyzer     │  │   │                              │
│  │  (LSP nav)  │  │ MCPs:             │  │   │                              │
│  └─────────────┘  │  security         │  │   │                              │
│                   │  blockchain       │  │   │                              │
│  ┌─────────────┐  │  deadcode         │  │   │                              │
│  │ Telemetry   │  │  duplication      │  │   │                              │
│  │ (SQLite +   │  │  ...              │  │   │                              │
│  │  /stats)    │  └───────────────────┘  │   │                              │
│  └─────────────┘                         │   │                              │
│                                          │   │                              │
│  ┌──────────────────────────────────────┐│   │                              │
│  │ provisioners (one-shot jobs):        ││   │                              │
│  │  • skills-distributor                ││   │                              │
│  │  • paperclip-provisioner             ││   │                              │
│  │  • scheduler (cron/webhook)          ││   │                              │
│  └──────────────────────────────────────┘│   │                              │
│                                          │   │                              │
│  ┌──────────────────────────────────────┐│   │                              │
│  │ client-distribution HTTP endpoint    ││   │                              │
│  │  /install → install.sh               ││   │                              │
│  │  /client/skills.tar.gz               ││   │                              │
│  │  /client/mcp-config.json             ││   │                              │
│  └──────────────────────────────────────┘│   │                              │
└──────────────────────────────────────────┘   └──────────────────────────────┘
         ▲                                                    ▲
         │ shared docker network                              │
         │ (paperclip-agent-net)                              │
         │                                                    │
┌────────┴──────────────┐                       ┌─────────────┴───────────────┐
│  Paperclip AI         │                       │  User's local Claude Code / │
│  (external existing   │                       │  Codex / Cursor / ... —     │
│   OR inside compose   │                       │  MCP-клиент                 │
│   via --profile       │                       │                             │
│   with-paperclip)     │                       │                             │
└───────────────────────┘                       └─────────────────────────────┘
```

### 2.2 Deployment scenarios — матрица (profile × topology)

**Axis 1 — topology** (где живёт сервер):

| # | Topology |
|---|---|
| **A** | Full self-host (один developer, свой сервер или laptop) |
| **B** | Full self-host + existing external Paperclip (подключаемся к его REST API) |
| **C** | Remote-connect (общий team-сервер уже развёрнут — клиент ставится за 1 команду) |
| **D** | Client-only (вообще без сервера у себя — только MCP-клиент к чужому инстансу) |

**Axis 2 — profile** (какие компоненты активны — см. §3.5):

| Profile | Что включает |
|---|---|
| `review` | palace (read-only MCPs) + Serena + code-analyzer MCPs. **Без Paperclip**, без extractors, без scheduler. Lightweight для соло-разработчика. |
| `analyze` | `review` + extractors + ingest pipeline + scheduler. **Без Paperclip** — ручные триггеры через `just`. |
| `full` | `analyze` + Paperclip (embedded) + paperclip-provisioner + team-templates. **Default — всё включено**. |
| `custom` | Интерактивный выбор каждого компонента отдельно (§3.6). |

Комбинация topology × profile даёт 16 вариантов; реально используются ~5-6. Установка — всегда через **interactive installer** (§3.6), результат сохраняется в `.env` как `GIMLE_PROFILE=<name>` + `COMPOSE_PROFILES=<docker-compose-profiles>` чтобы повторный `just setup` был non-interactive.

### 2.3 Логические слои сервера

| Слой | Компоненты | Ответственность |
|---|---|---|
| **Storage** | Neo4j Community 5.x | Persistent граф |
| **Memory engine** | Graphiti (Python service) | Bi-temporal KG, hybrid retrieval, embedding pipeline |
| **Core MCPs** | palace-mcp, Serena MCP, code-analyzer family | Agent-facing tools |
| **Orchestration** | lite-orchestrator (always-on) + paperclip-provisioner (profile `full` only) | Спавн задач/агентов в профилях без Paperclip; bootstrap команды в Paperclip когда он есть |
| **Provisioners** | skills-distributor, scheduler | One-shot bootstrap + cron |
| **Telemetry** | SQLite + FastAPI `/stats` | Observability, ROI measurement |
| **Client distribution** | HTTP endpoint `/install` + `/client/*` | Раздача client artifacts |

---

## 3. Deployment & Bootstrap Sequence

### 3.1 Одна команда на чистом сервере

```bash
git clone https://github.com/<you>/gimle-palace.git
cd gimle-palace
cp .env.example .env && $EDITOR .env
just setup
```

`just setup` делает:
1. `docker network create paperclip-agent-net` (идемпотентно).
2. `docker compose up -d` с ожиданием healthy.
3. Проверяет `PAPERCLIP_URL` доступность (или стартует встроенный Paperclip если включён profile `with-paperclip`).
4. Prints client install hint.

### 3.2 Bootstrap dependency order (через `depends_on: service_healthy`)

```
Neo4j  ──►  Graphiti  ──►  palace-mcp  ──►  skills-distributor  ──►  paperclip-provisioner
                        │                 │
                        ├──►  Serena ─────┤
                        └──►  code-analyzers ──┘
                                             │
                                             ▼
                                      scheduler (активируется последним)
```

Критично: **skills-distributor запускается до paperclip-provisioner**, чтобы когда provisioner создаёт "сотрудников" в Paperclip, MCP endpoints и skills-manifests уже были зарегистрированы и доступны.

### 3.3 Paperclip co-existence — три режима (явный выбор, без автодетекта)

Режим Paperclip пользователь выбирает **руками** (через installer §3.6 либо флаг `--paperclip`). Мы **не** делаем автодетект запущенного Paperclip на машине — пользователь может дать ссылку на удалённый инстанс в другой сети с отдельными credentials, что автодетектом не нашли бы.

- **External:** Paperclip уже стоит (на этой машине, на сервере команды, где угодно доступно по URL). Вводится URL + optional login/password. `PAPERCLIP_MODE=external` + `PAPERCLIP_URL=https://paperclip.team.io` + `PAPERCLIP_USER=...` / `PAPERCLIP_PASSWORD=...` (или `PAPERCLIP_API_KEY=...`) в `.env`.
- **Embedded (default):** `docker compose --profile with-paperclip up` поднимает Paperclip внутри нашего stack (новый инстанс рядом с остальным набором). `PAPERCLIP_MODE=embedded`, `PAPERCLIP_URL=http://paperclip:3100`. Это defаulт для профиля `full` когда пользователь не указал иначе.
- **None:** Paperclip выключен. Активируется `lite-orchestrator` (§4.10) как замена — без UI, но достаточная для спавна задач. `PAPERCLIP_MODE=none`. Профили `review` и `analyze` идут в этом режиме.

Выбор через installer prompt (§3.6) или non-interactive флаги:
```bash
just setup --paperclip embedded                     # default for full
just setup --paperclip external \
  --paperclip-url https://paperclip.team.io \
  --paperclip-api-key-env PAPERCLIP_API_KEY        # creds через env var
just setup --paperclip none                         # review/analyze
```

### 3.4 Infrastructure-as-code

**Решение: Docker Compose + Justfile + `.env.example` + optional sops-encrypted secrets.** Обоснование в §15. Никакого Ansible/Helm/K8s в MVP (всё single-server).

Файловая структура:

```
gimle-palace/
├── docker-compose.yml
├── docker-compose.paperclip.yml       # profile: with-paperclip
├── .env.example
├── Justfile
├── install-server.sh                  # curl | sh для серверной установки
├── projects/
│   └── example.yaml                   # шаблон project.yaml
├── teams/
│   └── default-team-template.yaml     # шаблон team-template.yaml
├── services/
│   ├── palace-mcp/
│   ├── code-analyzer-core/
│   ├── paperclip-provisioner/
│   ├── skills-distributor/
│   ├── scheduler/
│   └── telemetry/
├── agents/                            # role manifests для Paperclip agents
│   ├── architecture-extractor.yaml
│   ├── ui-component-extractor.yaml
│   ├── security-reviewer.yaml
│   └── ...
├── client/
│   ├── install.sh.tmpl                # template для client installer
│   ├── skills/                        # skills inventory для ~/.claude/
│   └── subagents/                     # subagents inventory
├── installer/
│   ├── setup.sh                       # интерактивный installer (§3.6)
│   ├── profiles/                      # декларативные profile definitions
│   │   ├── review.yaml
│   │   ├── analyze.yaml
│   │   ├── full.yaml
│   │   └── client.yaml
│   └── questions.yaml                 # custom-профиль — schema вопросов
└── docs/
    └── superpowers/specs/             # design docs (этот файл)
```

### 3.5 Installation profiles (detailed)

Каждый profile — декларативный yaml в `installer/profiles/<name>.yaml`, описывающий какие compose-services, которые reviewer/extractor роли, какие client-артефакты включены. Installer парсит это и генерирует `.env` + `COMPOSE_PROFILES`.

#### 3.5.1 Profile `review` — lightweight reviewer boost

**Для кого:** соло developer, хочет получить мгновенное улучшение качества code review своими coding CLIs, без тяжёлой инфры. Без Paperclip.

**Что включено (server side):**
- Neo4j + Graphiti (baseline store)
- palace-mcp (read tools только — write tools disabled через env-флаг)
- Serena MCP
- code-analyzer MCPs (security, deadcode, duplication) — вызываются из локального Claude/Codex on-demand
- **lite-orchestrator (§4.10)** — для on-demand запуска reviewer'ов через `just review <file>` / `/palace-review` slash-command
- Telemetry (SQLite + `/stats`)
- ❌ extractors, ❌ scheduler, ❌ paperclip-provisioner, ❌ skills-distributor HTTP endpoint (доступен только локально)

**Что включено (client side):**
- MCP config → palace + code-analyzers
- Palace skill для Claude Code (чтобы вызывать reviewers одной командой)
- ❌ team-workspace setup, ❌ plugin matrix

**Ingest:** не поддерживается в этом профиле — палата наполняется **только** через записи из read-write `/record_*` tools когда явно вызваны из Claude. Либо upgrade → `analyze`.

**Docker compose footprint:** ~400 MB RAM, 4 контейнера.

#### 3.5.2 Profile `analyze` — palace + pipelines, без Paperclip

**Для кого:** developer/small team, хочет полный palace (с extractors, scheduled updates), но управляет командой агентов **не через Paperclip GUI**, а через CLI (`just ingest`, `just update`, `just report`). Ingest-агенты спавнятся через **lite-orchestrator (§4.10)** — который знает про team-template.yaml, бюджет, role manifests и умеет вызывать `claude code -p "..."` (или Codex/Gemini CLI) в параллель. Без UI и approval-gates, но с telemetry и budget enforcement.

**Что включено (server side):**
- Всё из `review`
- palace-mcp read+write
- Extractors (architecture, ui-component, api, data-layer, dependency)
- Ingest pipeline (Justfile targets)
- Scheduler (cron + webhook endpoint)
- Reports generator → `reports/<project>/<iteration>.md`
- ❌ paperclip-provisioner, ❌ Paperclip container

**Client side:**
- Всё из `review`
- `/palace-ingest`, `/palace-update`, `/palace-report` slash-commands

**Trade-off:** нет Paperclip GUI — no governance/budgets/approvals UI. Зато нулевые шансы что Paperclip mismatch сломает workflow. Отличный вариант для "quick value" без команды.

**Docker compose footprint:** ~900 MB RAM, 8-10 контейнеров.

#### 3.5.3 Profile `full` — всё включено (default)

**Для кого:** team/organization, хочет полный governance через Paperclip UI, budgets, approvals, multi-agent coordination.

**Что включено:** всё из `analyze` + Paperclip (embedded или external по выбору) + paperclip-provisioner + skills-distributor HTTP + workspace settings.json auto-install.

**Docker compose footprint:** ~1.5 GB RAM (Neo4j 600MB + Paperclip 500MB + прочее 400MB), 12-14 контейнеров.

#### 3.5.4 Profile `client` — только клиентская часть

**Для кого:** рядовой developer в команде, где team-сервер уже развёрнут (scenario C из §2.2).

**Что ставится:**
- Только `~/.claude/mcp.json` (merged non-destructively)
- Только `~/.claude/skills/palace-*` и `~/.claude/agents/palace-*`
- **Никакого Docker, никакого Neo4j.**

**Команда:** `curl <team-server>/install | sh --server <url>`. Сервер выдаёт готовый client-tarball и config с правильным endpoint'ом.

#### 3.5.5 Profile `custom` — интерактивный выбор с preset packs

Пользователь проходит через wizard (§3.6) и либо выбирает один из **preset packs**, либо собирает custom по галочкам. Preset packs — это "полу-готовые" комбинации для частых сценариев:

| Preset | Что даёт |
|---|---|
| `ui-only` | palace + Serena + ui-component-extractor + find_ui_components. Без security/blockchain. Для чистого frontend-work. |
| `security-audit` | palace + Serena + security-reviewer + blockchain-reviewer + penetration-tester subagent. Без extractors — только обзор существующего кода. |
| `docs-onboarding` | palace + Serena + architecture-extractor + report-writer. Делает только architecture report, не пишет Findings. Для новичков в команде. |
| `dead-code-hunt` | palace + deadcode-hunter + duplication-detector + report-writer. Generates cleanup backlog. |
| `blockchain-deep` | palace + blockchain-reviewer + security-reviewer + api-extractor (с crypto-focus). Для аудита web3/wallet codebases. |

После выбора preset — пользователь может дальше кастомизировать (добавить/убрать компонент). Результат сохраняется в `installer/profiles/custom-<timestamp>.yaml` для reproducibility и shareability (коллега может взять тот же yaml и получить идентичный setup).

#### 3.5.6 Summary matrix

| Feature | `review` | `analyze` | `full` | `client` | `custom` |
|---|---|---|---|---|---|
| Neo4j + Graphiti | ✅ | ✅ | ✅ | ❌ | ? |
| palace-mcp (read) | ✅ | ✅ | ✅ | n/a | ? |
| palace-mcp (write / `record_*`) | ❌ | ✅ | ✅ | n/a | ? |
| Serena MCP | ✅ | ✅ | ✅ | ❌ | ? |
| code-analyzer MCPs | ✅ | ✅ | ✅ | ❌ | ? |
| Extractors + ingest pipeline | ❌ | ✅ | ✅ | ❌ | ? |
| Scheduler (cron/webhook) | ❌ | ✅ | ✅ | ❌ | ? |
| Reports generator | ❌ | ✅ | ✅ | ❌ | ? |
| Paperclip (embedded) | ❌ | ❌ | ✅/(ext) | ❌ | ? |
| Workspace settings.json auto-install | ❌ | ❌ | ✅ | ❌ | ? |
| Client MCP install | ✅ | ✅ | ✅ | ✅ | ? |
| Client skills install | ✅ | ✅ | ✅ | ✅ | ? |
| Telemetry | ✅ | ✅ | ✅ | n/a | ? |
| lite-orchestrator | ✅ | ✅ | ✅ (fallback when Paperclip down) | ❌ | ? |
| **Min RAM** | 500 MB | 1.0 GB | 1.6 GB | 0 | varies |
| **First-time setup** | ~2 min | ~3 min | ~5 min | ~30 sec | varies |

#### 3.5.7 Optional / post-MVP profiles

Не входят в первый релиз, но предусмотрены архитектурно:

- **`enterprise`** — `full` + TLS/reverse-proxy (Caddy или Traefik), OIDC/LDAP auth на Paperclip + palace-mcp, audit логи в append-only store, backup на S3/MinIO. Нужен когда палате ходит команда 10+ человек со сложной авторизацией.
- **`ci-only`** — headless режим для CI/CD. Нет client-distribution endpoint, нет interactive installer, нет Paperclip UI. Только `just ingest` и `just report` — для автоматических прогонов на каждом релизном бранче с артефактом (markdown-отчёт) в CI-output.

Эти профили добавляются через отдельный yaml-файл в `installer/profiles/` без изменений в core. Pre-requisite: базовые профили (`review/analyze/full/client/custom`) стабилизированы в MVP.

### 3.6 Interactive installer

**Entry point:** `just setup` → `installer/setup.sh`.

**Non-interactive modes (для CI, scripted deploys):**
```bash
just setup --profile review                    # minimal
just setup --profile analyze                   # palace + pipelines
just setup --profile full --paperclip embedded # всё в одной коробке
just setup --profile client --server https://palace.team.io
just setup --profile custom --answers answers.yaml  # pre-filled answers

# Для максимально-быстрого старта:
just setup --yes                # profile=full, paperclip=embedded, sensible defaults,
                                # projects detected from cwd, team-template=default
                                # secrets — если есть env vars $ANTHROPIC_API_KEY etc. берёт
                                # их, иначе просит один раз в конце
```

**Interactive flow** (запуск `just setup` без флагов). Все 6 промптов имеют **sensible defaults**, можно быстро пройти Enter'ом через все:

```
╔══════════════════════════════════════════════════════════════════╗
║  Gimlé Palace — installer                                        ║
╚══════════════════════════════════════════════════════════════════╝

? What do you want to install?  [use ↑↓, space to select, enter to confirm]

  ❯ full      — all-in-one: memory palace + team of agents + Paperclip GUI
    analyze   — memory palace + ingest pipeline + scheduler  (no Paperclip)
    review    — lightweight reviewer boost for local Claude Code  (minimal)
    client    — I already have a Gimlé server, just hook up my laptop
    custom    — let me pick every component myself

↳ Selected: full

? Paperclip deployment?
  ❯ embedded — bundle Paperclip inside our docker-compose (default for full)
    external — I already run Paperclip somewhere (this/another host)
    skip     — no Paperclip, use lite-orchestrator instead

↳ embedded
  (if "external" selected, следующие 3 промпта:)

   ? Paperclip URL?            https://paperclip.team.io
   ? Auth type?                  ❯ api-key   basic (login/password)   none
   ? API key env variable name?  PAPERCLIP_API_KEY
   (if basic: login/password prompt, secrets masked, stored в .env)

? Which projects do you want to register now?
  (can be added later via `just add-project <path>`)
  ❯ detect — scan current directory for git repos
    manual — paste paths comma-separated
    later  — skip for now

↳ detect
[scanning... found 4 git repos]
  ☑ /Users/anton/Android/unstoppable-wallet-android
  ☑ /Users/anton/Android/bitcoin-kit-android
  ☐ /Users/anton/Android/ethereum-kit-android
  ☐ /Users/anton/Android/market-kit-android
[space to toggle, enter to confirm]

? Team template for detected projects?
  ❯ mobile-blockchain-default — architect + UI + API + security + blockchain + deadcode
    mobile-default            — architect + UI + API + deadcode
    backend-default           — architect + API + data + security + deadcode
    minimal                   — architect + deadcode only
    custom                    — edit yaml after install

? API keys — paste now or add later to .env?
  ❯ paste now  (secure input, not echoed)
    add later

   ANTHROPIC_API_KEY: ****** ✓
   OPENAI_API_KEY:    (empty, skipped — will be added later)

? Telemetry & privacy?
  ❯ full — log args for debugging (local SQLite only, not sent anywhere)
    hashed — hash arg values in logs (privacy-preserving)
    off — no telemetry

? Use local Ollama for embeddings / extraction? [auto-detect: Docker has 16 GB RAM available]
    cloud   — OpenAI embeddings + Claude extraction (recommended, best quality)  [default]
    hybrid  — local Ollama for embeddings, Claude for extraction (save $ on embeddings, 2 GB RAM)
    local   — everything via local Ollama (zero $, privacy++, quality⭐⭐⭐, needs 8+ GB RAM)
    external-ollama — I already have Ollama running somewhere (enter URL)

↳ cloud

? Ready to install:
     profile: full
     paperclip: embedded
     projects: 2
     team-template: mobile-blockchain-default
     secrets: 1 of 2 provided
     telemetry: full
  ❯ Install  (ctrl+c to cancel, e to edit)

▶ Generating .env ...                             ✓
▶ Generating docker-compose.override.yml ...      ✓
▶ docker compose pull ...                         ✓ (3 minutes)
▶ docker compose up -d ...                        ✓
▶ Waiting for healthchecks ...                    ✓ (45s)
▶ Running paperclip-provisioner ...               ✓ (2 companies created)
▶ Writing ~/.paperclip workspaces settings.json ... ✓ (9 agents configured)
▶ Generating client install URL ...               ✓

╔══════════════════════════════════════════════════════════════════╗
║  ✓ Installation complete!                                        ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                  ║
║  Paperclip UI:       http://localhost:3100                       ║
║  Palace stats:       http://localhost:8080/stats                 ║
║  Client install:     curl http://localhost:8080/install | sh     ║
║                                                                  ║
║  First ingest:       just ingest unstoppable-wallet-android      ║
║  Status:             just status                                 ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
```

**Technical stack для installer:**
- **`gum`** (charmbracelet) как primary prompt library — beautiful TTY, single Go binary, `brew install gum` или `apt install gum`. Работает через `gum choose`, `gum input`, `gum confirm`.
- **Fallback на `whiptail`** — встроен в большинство Linux distros (ncurses-based) если gum недоступен.
- **Last resort: plain bash `read`** — ASCII UI, работает всегда.

Installer автодетект'ит доступные tools в таком порядке и использует первый найденный. `setup.sh --plain-ui` форсит bash-fallback для тестов/CI.

**Idempotency.** Повторный `just setup` детектит существующий `.env` + `COMPOSE_PROFILES` → предлагает:
```
Detected existing install: profile=full, paperclip=embedded.
  ❯ Keep current config and restart services
    Reconfigure (walk through installer again)
    Upgrade in-place (pull latest images, re-migrate schemas)
    Uninstall (docker compose down -v, remove ~/.claude entries)
```

### 3.7 Profile-aware client installer

Client-side `install.sh` получает от сервера метаданные о активном профиле (`GET /server-profile`). Скрипт показывает user'у:

```
Connected to Gimlé server at https://palace.team.io
  profile:        full
  version:        1.0.3
  available MCP:  palace, serena, security-reviewer, blockchain-reviewer
  skills:         5 (palace-*)
  subagents:      2 (palace-*)

? Install all available components? [Y/n]
```

Пользователь может пропустить компоненты если не хочет. Например отказаться от `subagents` но взять `mcp` + `skills`.

### 4.1 Neo4j Community 5.x + backup sidecar

- Docker image: `neo4j:5-community`
- Persistent volume: `neo4j-data`
- Vector index plugin встроен (для hybrid retrieval из Graphiti)
- Лицензия: GPL v3 — **приемлемо** т.к. мы не distribut'им стек как продукт, это self-host tooling
- Plan B: FalkorDB (SSPL, Redis-based) — drop-in замена для тех, кому GPL неприемлема; переключается через env-флаг `GRAPH_BACKEND=neo4j|falkordb`

**Backup sidecar `neo4j-backup`:**

```yaml
# docker-compose.yml snippet
neo4j-backup:
  profiles: [analyze, full]
  image: neo4j:5-community
  depends_on: { neo4j: { condition: service_healthy } }
  volumes:
    - neo4j-data:/data:ro
    - backup-volume:/backups
  environment:
    - BACKUP_HOURLY_RETENTION=24    # keep last 24 hourly
    - BACKUP_DAILY_RETENTION=30     # keep last 30 daily
    - BACKUP_WEEKLY_RETENTION=12    # keep last 12 weekly
  entrypoint: /scripts/backup-runner.sh
```

Содержит crond + `neo4j-admin database dump palace --to-path=...` для hourly snapshots, автоматическая rotation по retention policy. Даёт паритет с Paperclip's built-in pg_dump hourly + 30-day retention.

**CLI commands:**
- `just backup-now` — manual snapshot сейчас (в папку `manual/` с timestamp)
- `just backups-list` — показывает все snapshots с размерами
- `just restore --timestamp <ts>` — восстановление из конкретного snapshot (останавливает Neo4j, заменяет volume, стартует)
- `just backup-config` — показывает текущую retention config

Retention настройка в `.env` — `BACKUP_HOURLY_RETENTION`, `BACKUP_DAILY_RETENTION`, `BACKUP_WEEKLY_RETENTION`.

### 4.2 Graphiti service

- Python 3.11 FastAPI wrapper над `graphiti-core` library (getzep/graphiti)
- Выставляет:
  - Internal gRPC/HTTP для palace-mcp
  - Official Graphiti MCP server v1.0 на отдельном порту (для Paperclip-агентов которым удобнее прямой MCP)
- **Embedding provider:** configurable через `.env`. Default cloud (OpenAI `text-embedding-3-large`). Alternative: local Ollama (§4.2.1 — opt-in checkbox в installer).
- **Entity extraction LLM:** configurable через `.env`. Default cloud (Claude Sonnet — cost/quality оптимум). Alternative: local Ollama (качество хуже, privacy+cost выигрыш).
- **Provider abstraction:** через LiteLLM router — любой OpenAI-compatible endpoint подключается без кода (Claude, Anthropic, OpenAI, Gemini, Ollama, Voyage AI, Together, Groq и т.д.).

#### 4.2.1 Ollama как opt-in local LLM runner

При `just setup` пользователь получает prompt (§3.6): *"Use local Ollama for embeddings/extraction? (recommended only if server has 8+ GB free RAM)"*. По умолчанию — **cloud**.

**Three режима** (env `LLM_MODE`):

| Mode | Embedding | Extraction | Cost | Quality | Min RAM extra |
|---|---|---|---|---|---|
| `cloud` (default) | OpenAI API | Claude API | $ per call | ⭐⭐⭐⭐⭐ | 0 |
| `hybrid` | Local Ollama (`nomic-embed-text`) | Claude API | $ only for extraction | ⭐⭐⭐⭐ | ~2 GB |
| `local` | Local Ollama (`nomic-embed-text`) | Local Ollama (`llama3.1:8b` или `qwen2.5-coder:7b`) | $0 | ⭐⭐⭐ | ~8 GB |

**Где и как поднимается Ollama:**

- `just setup` с Ollama-галочкой → `docker compose --profile with-ollama up`
- Compose service `ollama` (official `ollama/ollama` image), expose `:11434` на internal network
- Auto-pull моделей при первом запуске: `nomic-embed-text` (274 MB), `llama3.1:8b` (4.7 GB) — только если выбран соответствующий mode
- Если у пользователя **уже есть** native Ollama на хост-машине — можно указать `OLLAMA_URL=http://host.docker.internal:11434` в `.env`, profile `with-ollama` не включается, compose-сервис не поднимается.

**Installer RAM check:** при выборе `local`/`hybrid` mode installer запускает `docker info --format '{{.MemTotal}}'` и warn'ит если доступно < 8 GB: *"Your server has 6 GB RAM; Ollama may struggle with llama3.1:8b. Consider `hybrid` mode or stay with `cloud`."* Не блокирует — только warn.

**Соответствующие `.env` переменные (§4.2.2):**

```bash
# Default — cloud
LLM_MODE=cloud
EMBEDDING_PROVIDER=openai
EMBEDDING_MODEL=text-embedding-3-large
EXTRACTION_PROVIDER=anthropic
EXTRACTION_MODEL=claude-sonnet-4-6

# Hybrid
LLM_MODE=hybrid
EMBEDDING_PROVIDER=ollama
EMBEDDING_MODEL=nomic-embed-text
EXTRACTION_PROVIDER=anthropic
EXTRACTION_MODEL=claude-sonnet-4-6

# Fully local
LLM_MODE=local
EMBEDDING_PROVIDER=ollama
EMBEDDING_MODEL=nomic-embed-text
EXTRACTION_PROVIDER=ollama
EXTRACTION_MODEL=llama3.1:8b

# Ollama endpoint (always required if EMBEDDING_PROVIDER=ollama or EXTRACTION_PROVIDER=ollama)
OLLAMA_URL=http://ollama:11434                   # compose-internal (default with --profile with-ollama)
# OLLAMA_URL=http://host.docker.internal:11434   # native Ollama on host machine
# OLLAMA_URL=http://192.168.1.50:11434           # dedicated Ollama server
```

Режим можно поменять после install через `just reconfigure` — установщик проходит заново только релевантные вопросы.

### 4.3 palace-mcp

**Основной MCP-сервер** который видят клиенты. Python FastMCP. Оборачивает Graphiti + telemetry в удобные domain-level tools.

Exposed tools (read):

| Tool | Назначение |
|---|---|
| `find_context_for_task(task_description, project?)` | ⭐ **faceted retrieval** (§5.6) — grouped-by-purpose output для типовых задач типа "экран с адресом токена" |
| `search_memory(query, project?, filters?, top_k=10)` | generic semantic+BM25+graph search |
| `find_ui_components(kind, framework?, project?)` | кнопки/экраны/карточки + usage counts |
| `find_component_usage(name, project?)` | где используется |
| `find_similar_component(description_or_code, project?)` | semantic по UI |
| `find_utility(domain_concept, capability?, project?)` | "что умеет работать с hex + encode?" — по осям 3+4 (§5.4) |
| `find_api_contract(name_or_path, project?)` | REST/GraphQL endpoints + schemas |
| `find_screen(name_or_description, project?)` | экран по имени/описанию |
| `get_layer_dependencies(module, project?)` | архитектурные связи |
| `get_dependency_usage(library_name, project?)` | где используется 3rd-party lib |
| `get_iteration_notes(project?, since_iteration?)` | заметки предыдущих итераций |
| `get_iteration_diff(project, from, to)` | что изменилось между итерациями |
| `get_recent_iterations(project?, limit=5)` | последние N итераций + summary что изменилось |
| `find_decision_by_topic(topic, project?)` | быстрый поиск архитектурных правил по теме |
| `get_architecture_summary(project, depth="medium")` | one-shot overview: modules/layers/key-decisions (depth ∈ high/medium/detailed) |
| `list_projects()` | каталог проектов |
| `get_project_overview(project)` | high-level summary |

Exposed tools (write):

| Tool | Назначение |
|---|---|
| `record_decision(project, scope, text, tags?)` | архитектурное решение |
| `record_finding(project, scope, severity, text, tags?, source?)` | баг/уязвимость/anti-pattern. `source ∈ {"static","llm","hybrid"}` — см. §4.5 hybrid reviewer design |
| `record_iteration_note(project, text, tags?)` | свободная заметка из текущей работы |
| `link_items(from_id, to_id, relation)` | явно связать два узла графа (напр. `:Finding → :Decision :INVALIDATED_BY`) |
| `create_paperclip_issue(project, title, description, role_hint?)` | ставит задачу сотруднику Paperclip |

Все tools возвращают `{ok: bool, data?: T, error?: string, meta: {latency_ms, tokens_est, avoided_tokens_est, event_id, last_ingest_at?, staleness_warning?}}`. Поля `last_ingest_at` и `staleness_warning` добавляются когда response основан на snapshot старше `STALENESS_WARN_HOURS` (default 12h) — см. §4.4.

### 4.3.1 Branch-aware ingest

В дополнение к `just ingest <project>` (main branch) — поддержка feature branches:

```bash
just re-ingest <project> --branch feature/swap-v2
# → создаёт namespace project/<slug>#branch/<branch-name> в Graphiti
# → все queries с filter {branch: "feature/swap-v2"} возвращают knowledge
#   текущей ветки, fallback на main для отсутствующих фактов
# → при merge PR: `just merge-branch <project> feature/swap-v2` —
#   либо применяет branch knowledge в main namespace, либо отбрасывает
#   (выбор при merge)
```

Используется когда работаешь над фичей больше суток и хочется чтобы palace понимал твою ветку, не дожидаясь scheduled update. Не связано со scheduled updates — это on-demand.

### 4.4 Serena MCP — local vs server coexistence

**Две разные instance Serena** могут жить параллельно — у пользователя на машине и у нас в контейнере. Они работают в **разных filesystem namespace'ах** и служат **разным целям**.

#### 4.4.1 Две instance, разный scope

| | Local Serena (у пользователя) | Server Serena (наш контейнер, alias `palace-serena`) |
|---|---|---|
| **Видит** | твой личный checkout + uncommitted changes | server-side mirror репо (mount в `/repos/`) |
| **Обновление** | мгновенно при редактировании | при `just ingest` / scheduled update |
| **Запускается** | `~/.local/share/uv/tools/serena-agent/bin/serena` | Docker container |
| **Alias в `~/.claude/mcp.json`** | `serena` | `palace-serena` |
| **Primary для кейсов** | работа в текущем live коде, find_references по только что отредактированному | обзор snapshot-knowledge по проектам которые не cloneнуты у тебя локально |

В profile `client` — user не имеет локального checkout'а обязательно, но обычно имеет. Оба MCP остаются доступны — Claude routing (§4.4.3) решает что когда.

#### 4.4.2 Docker setup для server Serena

Standalone контейнер поверх official image. Конфигурируется через volume mount путей анализируемых репозиториев в `/repos/<project-slug>`. Запускается в режиме `--transport streamable-http` на порту в `paperclip-agent-net`. Регистрируется в client MCP config **под alias `palace-serena`** (не `serena` — чтобы не конфликтовать с локальной).

#### 4.4.3 Routing: какой Serena использовать для какой задачи

Tool descriptions в `palace-serena` явно говорят: *"This Serena instance works on the server-side snapshot of team-registered projects. For navigation in your current local checkout, use the local `serena` tool instead."*

Claude routing auto-таблица:

| User ask | Tool |
|---|---|
| "где используется метод `signTransaction` в моём коде?" | local `serena.find_references` |
| "сколько раз `ButtonPrimary` используется в проекте?" | `palace-mcp.find_component_usage` (synthesized count) |
| "покажи call graph для `WalletViewModel`" (в моём локальном checkout) | local `serena.call_hierarchies` |
| "есть ли в другом репо команды (`ethereum-kit`) что-то похожее на это?" | `palace-serena` + `palace-mcp` |
| "какие decisions приняты про swap?" | `palace-mcp.find_decision_by_topic` |

#### 4.4.4 Staleness semantics — palace не видит uncommitted

**Правило:** palace = shared team knowledge, live local workdir = личное in-progress. Uncommitted changes **не попадают** в palace пока не push'ены + re-ingest отработал.

Это **фича**, не баг: экспериментальный scratch не засоряет shared knowledge. Но требует user-awareness:

- `palace-mcp` в каждом ответе прокидывает `meta.last_ingest_at` + `meta.last_ingest_commit_sha`.
- Если разница между `last_ingest_commit_sha` и `git HEAD` в локальном checkout > threshold — `meta.staleness_warning: "Palace is behind by 18 commits; your local changes not reflected"`.
- Claude инструктирован (через client skill `palace-awareness`) сообщать user'у: *"По данным палаты (snapshot 18 коммитов назад)... в твоих локальных изменениях возможно уже другое."*

#### 4.4.5 Когда твоя ветка отличается сильно

Для большой долгоживущей feature branch — используй `just re-ingest <project> --branch <name>` (§4.3.1). Тогда palace знает и main, и ветку отдельно, и на запросы с `branch=feature-x` отдаёт branch-aware ответ. Без этого — default main snapshot + staleness warning.

### 4.5 Code-analyzer — hybrid architecture (2 deterministic MCPs + 5 roles)

**Ключевая идея:** разные типы багов требуют разных инструментов. Formal patterns (reentrancy, known CVE, hardcoded secrets в git history) — детерминированные tools объективно быстрее, дешевле и надёжнее. Business-logic bugs (wrong approve amount, reversed condition, architecture misuse) — LLM объективно эффективнее. Ни одно из двух не заменяет другое.

Поэтому — **hybrid**:

#### 4.5.1 Два deterministic MCP-сервера (формальный слой)

**`security-tools-mcp`** (1 контейнер с необходимыми CLI tools установленными):

| Tool | Wraps | Назначение |
|---|---|---|
| `run_semgrep(path, ruleset)` | semgrep CLI | OWASP, CWE, custom wallet-security rulesets |
| `scan_secrets_in_history(repo_path)` | trufflehog | Поиск hardcoded keys/tokens во всей git-истории |
| `check_cve_in_dependencies(path)` | osv-scanner, trivy | Known CVE в direct + transitive deps |
| `check_tls_config(path)` | custom scanner | cleartext traffic, missing certificate pinning, weak TLS |
| `verify_keystore_usage(path, lang)` | ast-based | Kotlin EncryptedSharedPreferences vs SharedPreferences, Swift Keychain vs UserDefaults для sensitive data |
| `run_slither(path)` | slither CLI, conditional | Solidity static analysis (активируется только если Solidity файлы detected) |

**`code-analysis-mcp`** (1 контейнер):

| Tool | Wraps | Назначение |
|---|---|---|
| `detect_duplicates(path, threshold)` | jscpd + semantic embedding dedup | copy-paste detection + semantic near-duplicates |
| `find_unreferenced_symbols(path)` | через palace-serena `find_references` | dead code (0 references → flag) |
| `extract_public_surface(path, lang)` | ast-based | entry points + exported APIs — "вот что внешний user может вызвать" |
| `compute_complexity(file)` | McCabe, Halstead | cyclomatic complexity, halstead effort — hotspots для refactor |
| `parse_build_deps(path)` | gradle/swift-pm/cargo/package.json parsers | 3rd-party libs + versions |

Оба сервиса — stateless, `POST /tool/{name}` с JSON body, отдают JSON findings. Включаются в profiles `review`/`analyze`/`full`.

#### 4.5.2 Пять reviewer ролей (LLM-слой, используют MCPs выше)

Каждая роль — запись в `team-template.yaml`, spawn'ится через Paperclip / lite-orchestrator. **Не имеет собственного docker-сервиса.** Использует:
- `palace-mcp` для записи findings
- `palace-serena` для code navigation
- `security-tools-mcp` / `code-analysis-mcp` для formal checks
- Plugin'ы и subagents из существующего inventory (§13.3)

| Role | Plugins / subagents из inventory | Что добавлено нашим fragment'ом |
|---|---|---|
| `security-reviewer` | `voltagent-qa-sec` (`security-auditor`, `penetration-tester`), `code-review`, `pr-review-toolkit` | OWASP-focused prompt + workflow "сначала run_semgrep → record static findings → дальше LLM reasoning по business logic" |
| `blockchain-reviewer` | `voltagent-qa-sec` (`security-auditor`) | `fragments/blockchain-invariants.md` — checklist из 25+ пунктов (reentrancy, signature verification, nonce handling, key storage, front-running, integer overflow, access control). Вызывает `run_slither` если Solidity, `verify_keystore_usage` для Kotlin/Swift. |
| `deadcode-hunter` | `pr-review-toolkit:code-simplifier` | Вызывает `find_unreferenced_symbols`, добавляет reasoning "может это используется через reflection?" |
| `duplication-detector` | `pr-review-toolkit:code-simplifier` | Вызывает `detect_duplicates`, потом LLM группирует похожие дубликаты по семантике |
| `dependency-analyzer` | (generic) | Вызывает `parse_build_deps` + `check_cve_in_dependencies`, reasoning "какие deps реально используются vs dead dependencies" |

#### 4.5.3 Дуальная confidence в `:Finding`

`record_finding` принимает параметр `source ∈ {"static","llm","hybrid"}`. Для каждой finding в палате:

```json
{
  "severity": "high",
  "category": "key-storage",
  "text": "Private key stored in UserDefaults without encryption",
  "file": "WalletManager.swift", "line": 42,
  "source": "hybrid",
  "static_confidence": 0.95,    // verify_keystore_usage вернул match
  "llm_confidence": 0.85,        // reviewer подтвердил + написал reasoning
  "evidence": {
    "static_rule": "verify_keystore_usage:userdefaults-for-sensitive",
    "llm_reasoning": "В WalletManager.swift:42 `UserDefaults.set(privateKey, forKey:)` —
                      UserDefaults не encrypted by default, не имеет hw-backing. В то же
                      время в проекте используется Keychain для других sensitive values
                      (AuthManager.swift:18). Inconsistent usage — явная ошибка."
  }
}
```

Это даёт audit trail: security-ревьюер команды или auditor видит **какой tool нашёл что** + **какое reasoning LLM добавил**. Для compliance-отчётов — бесценно.

#### 4.5.4 Порядок работы внутри role (каноничный pattern)

Из `fragments/hybrid-review-workflow.md` (автоматически инжектится во все reviewer-роли):

```markdown
### Hybrid review workflow (ОБЯЗАТЕЛЬНО в этом порядке)

1. **First pass — static tools:** вызови все применимые deterministic tools из
   security-tools-mcp / code-analysis-mcp. Записать каждую finding через
   `palace-mcp.record_finding(source="static", static_confidence=1.0)`.

2. **Second pass — LLM reasoning поверх того что static tools не нашли:**
   прочитай ключевые entry-points (public methods on user-controlled inputs),
   architecture (через palace-mcp.get_architecture_summary), cross-file flows
   (через palace-serena). Ищи business-logic bugs, misuse patterns, выставление
   правил без проверки. Каждую LLM-finding записать с `source="llm",
   llm_confidence=<0.0..1.0>`.

3. **Merge pass:** если static нашёл что-то и LLM также подтвердил —
   `link_items` свяжи две findings, обновите одну до `source="hybrid"`.

4. **Never rely только на static.** Static — это baseline coverage, не exhaustive.
   Никогда не пропускай second pass "потому что static уже покрыл всё".
```

Это hard rule во всех reviewer-ролях — гарантия что hybrid action'ится, а не роль ограничивается только "что tool сказал".

### 4.6 Specialized extractors (ingest-time only)

Эти агенты запускаются один раз при ingest (и incrementally при update). Они не MCP-серверы, а **role-prompt'ы** для Paperclip-агентов, которые читают код и пишут в palace структурированные факты.

Roster v1:

| Role | Что пишет в palace |
|---|---|
| `architecture-extractor` | `:Module`, `:Layer`, `:DEPENDS_ON` edges |
| `ui-component-extractor` | `:UIComponent` (kind=button/screen/card/...), `:USED_BY` edges с counts |
| `api-extractor` | `:APIEndpoint` (method, path, request/response schema), `:CALLED_FROM` |
| `data-layer-extractor` | `:Model`, `:Repository`, `:DBTable`, `:PERSISTS_TO` |
| `dependency-analyzer` | `:ExternalLib`, `:USES_LIB` edges |

Активация конкретных role в конкретном репо — через `project.yaml` (§6).

### 4.7 Provisioners

**skills-distributor** — FastAPI service с двумя функциями:
1. Статическая раздача `/client/skills.tar.gz` и `/client/subagents.tar.gz` из volume `client-inventory`.
2. Команда `just install-skills` внутри сервера (для scenario A): копирует те же tarball'ы в локальный `~/.claude/` на хост-машине через volume mount.

**paperclip-provisioner** — one-shot Python job, **reconciler-style** (не upsert — у Paperclip нет идемпотентного PUT для agents).

Pre-reqs: `PAPERCLIP_URL`, `PAPERCLIP_API_KEY` (или JWT) в `.env`. Company уже существует — либо передаётся `PAPERCLIP_COMPANY_ID`, либо provisioner создаёт новую через `POST /api/companies`. Один gimle-instance → одна Paperclip company (все проекты в ней).

**Reconciliation loop:**

```python
for project in projects/*.yaml:
    desired_roles = resolve_roles(project, team_template)
    existing_agents = GET /api/companies/{cid}/agents
                      # filtered by name prefix "gimle:<project-slug>:" + role
    diff = compute_diff(desired_roles, existing_agents)

    for role in diff.to_create:
        # 1. Submit hire request (requires approval by default)
        hire = POST /api/companies/{cid}/agent-hires { ... see below ... }
        # → { agent: {id, status:"pending_approval"}, approval:{id, status:"pending"} | null }

        if hire.approval:
            if GIMLE_AUTO_APPROVE_HIRES=true:
                POST /api/approvals/{approvalId}/approve
                # (requires user api-key with board scope, опциональный)
            else:
                log("⏳ Agent {name} waiting for board approval: /approvals/{id}")
                continue  # пропускаем дальше, бэкгрaундом опрашиваем status

        # 2. Upload AGENTS.md bundle (managed mode)
        PUT /api/agents/{id}/instructions-bundle/file
          body: { path: "AGENTS.md",
                  content: render_role_prompt(role, project)}

        # 3. Skills sync through API (primary path)
        POST /api/agents/{id}/skills/sync
          body: { skills: role.plugins }

        # 4. Fallback: direct file write for plugin matrix that's not expressible via API
        #    (backup first to ~/.claude/.palace-backup/<ts>/)
        atomic_write(workspace_settings_path(agent.workspace_id),
                     merge_user_managed(existing, generated))

    for role in diff.to_update:
        PATCH /api/agents/{id} { title, role, icon, capabilities, adapterConfig, runtimeConfig }
        PUT /api/agents/{id}/instructions-bundle/file { ... }  # rewrite AGENTS.md

    for role in diff.to_delete:
        POST /api/agents/{id}/terminate
        # НЕ удаляем heartbeat_runs / comments / issues — audit trail
```

**Pending-approval background worker.** Если `GIMLE_AUTO_APPROVE_HIRES=false` (default) — provisioner пишет "awaiting approval" в лог и **не блокирует stack startup**. Отдельный background worker (в scheduler контейнере) поллит `GET /api/approvals?status=pending` каждые 60s; когда approval переходит в `approved` → запускается step 2+ для этого agent'а.

**Agent name convention (критичный hard rule — §Paperclip-operations Bug #1+#2):**
- Format: `<PascalCase role name>` без пробелов (`SecurityReviewer`, `UiComponentExtractor`, `ArchitectureExtractor`)
- Prefix не нужен — company isolation достаточна. Но при multi-project: `<project-slug>:<Role>` где `:` часть internal ID, в `name` field — только `Role` для корректного @-mention resolution
- Validation на загрузке `team-template.yaml` — regex `^[A-Z][a-zA-Z0-9]*$`, fail-fast если нарушено

**AGENTS.md template** рендерится из `roles/<role>.md` + `fragments/*.md` с автоматически inject'имым fragment'ом `@-mention-safety.md` (§7 team-template). Этот fragment содержит три правила handoff из §Paperclip-operations 3.4.

**AGENT_ROLE mapping.** Paperclip enum: `ceo, cto, cmo, cfo, engineer, designer, pm, qa, devops, researcher, general`. Наши extractors/reviewers мапятся так:

| Наш role | Paperclip agent_role |
|---|---|
| architecture-extractor, api-extractor, data-layer-extractor, ui-component-extractor, dependency-analyzer | `engineer` |
| security-reviewer, blockchain-reviewer, deadcode-hunter, duplication-detector | `qa` |
| report-writer | `researcher` |
| orchestrator (если делаем meta-coordinator) | `general` |

**adapterType mapping.** Наш `cli:` field → Paperclip `adapterType`:
`claude-code → claude_local`, `codex → codex_local`, `gemini → gemini_local`, `opencode → opencode_local`, `cursor → cursor`.

**Hire request body template:**
```json
{
  "name": "<PascalCaseRoleName>",
  "role": "engineer|qa|researcher|general",
  "title": "<role.display_name>",
  "icon": "<from /llms/agent-icons.txt>",
  "reportsTo": "<ceo-or-cto-agent-id — опционально>",
  "capabilities": "<from role.capabilities in team-template>",
  "adapterType": "claude_local",
  "adapterConfig": {
    "cwd": "<repo_path from project.yaml>",
    "model": "<role.model>",
    "instructionsFilePath": "AGENTS.md",
    "instructionsBundleMode": "managed"
  },
  "runtimeConfig": {
    "heartbeat": {"enabled": false, "wakeOnDemand": true, "maxConcurrentRuns": 1, "cooldownSec": 10}
  },
  "budgetMonthlyCents": "<role.budget_usd_per_month * 100>"
}
```

Примечание: `heartbeat.enabled=false` — мы не хотим, чтобы ingest-агенты просыпались по таймеру без задачи. Трigger — только по ручному wake из provisioner'а или scheduler'а.

---

**scheduler** — поведение зависит от `PAPERCLIP_MODE`:

**Case A — `PAPERCLIP_MODE=embedded` или `external` (profile `full`):**
Используем **Paperclip Routines API** — не пишем своего scheduler'а.

```python
for project in projects/*.yaml:
    routine = PUT /api/companies/{cid}/routines  # reconciled
      body: { name: "gimle:{project}:incremental-update",
              description: ...,
              task_template: "Run incremental ingest for project={project} based on
                              git HEAD since last run. Use tools: palace-mcp.record_*,
                              Serena. Assignee: ArchitectureExtractor."
            }
    PUT /api/routines/{id}/triggers
      body: { type: project.trigger.kind,  # cron | webhook | api
              schedule: project.trigger.schedule,
              secret: ... }
```

Paperclip routines сами триггерят issue creation + assign + wake-up. Наш scheduler sidecars только syncs routines declarations из `projects/*.yaml` → Paperclip.

**Case B — `PAPERCLIP_MODE=none` (profile `analyze`):**
Embedded scheduler в lite-orchestrator контейнере через APScheduler. Для каждого проекта:
- `trigger.kind: cron` → запускает по cron spec, POST /tasks в lite-orchestrator
- `trigger.kind: webhook` → FastAPI listens `POST /webhook/<project>/push`
- На срабатывании: `git fetch && git diff HEAD@{1} HEAD` → POST /tasks в lite-orchestrator с ролью `incremental-updater`

Обе ветки пишут результат в palace через те же `record_*` tools — data path идентичен, отличается только compute path.

### 4.8 Telemetry service

**Стек: SQLite в volume + FastAPI `/stats` endpoint.** Никакого Postgres/Prometheus в MVP.

Event schema:
```sql
CREATE TABLE palace_events (
  id TEXT PRIMARY KEY,                  -- ULID
  ts TIMESTAMPTZ NOT NULL,
  user TEXT NOT NULL,                   -- API key fingerprint
  session_id TEXT,                      -- Claude Code session if provided
  project TEXT,
  tool TEXT NOT NULL,
  args_json TEXT NOT NULL,              -- JSON, optionally hashed if TELEMETRY_HASH_ARGS=1
  response_bytes INT,
  response_tokens_est INT,
  latency_ms INT,
  avoided_tokens_est INT,               -- heuristic (see §8)
  model_hint TEXT,
  success BOOL NOT NULL,
  error TEXT
);
CREATE INDEX idx_events_ts ON palace_events(ts);
CREATE INDEX idx_events_user ON palace_events(user, ts);
CREATE INDEX idx_events_tool ON palace_events(tool, ts);
```

Commands (`just stats`):
- `just stats` — sliding window 24h/7d/30d breakdown.
- `just stats --user X` — per user.
- `just stats --tool X` — usage per tool.
- `just stats --explain` — прозрачная формула `avoided_tokens_est` с per-tool коэффициентами.
- `just stats --export csv|json` — для внешних dashboard'ов.

### 4.9 Client distribution endpoint

Встроен в skills-distributor FastAPI. Routes:

- `GET /install` — возвращает install.sh (server URL autoinjected в скрипт).
- `GET /client/skills.tar.gz` — текущий inventory.
- `GET /client/subagents.tar.gz`
- `GET /client/mcp-config.json` — готовая JSON config для `~/.claude/mcp.json` с правильным server URL.

Client `install.sh`:
1. Проверяет `~/.claude/` exists (иначе exit с инструкцией поставить Claude Code).
2. Qачает tarballs → распаковывает в `~/.claude/skills/` и `~/.claude/agents/`.
3. Merge'ит `mcp-config.json` в `~/.claude/mcp.json` (не затирает существующие entries).
4. Prints подтверждение + `claude mcp list` hint.

Идемпотентен — повторный запуск обновляет до последней версии.

### 4.10 lite-orchestrator

**Роль:** минимальный, но самодостаточный orchestrator для спавна задач/агентов когда Paperclip отсутствует (`PAPERCLIP_MODE=none`) или недоступен (`external` потеряло связность). Заменяет Paperclip **только** в части "кто какую задачу запустил, с каким бюджетом, какой result'ом" — без UI, без approval-gates, без cross-agent messaging.

**Tech stack:**
- Python 3.11 + FastAPI + asyncio + Pydantic
- SQLite таблица `orchestrator_tasks` (рядом с telemetry, тот же volume)
- Ничего другого (никакого Redis/Celery/RabbitMQ — overkill для single-host)

**API surface:**

REST:
- `POST /tasks` — enqueue task: `{role, project, input, budget_usd?, timeout_s?}` → возвращает `task_id`
- `GET /tasks/{id}` — статус (pending|running|done|failed|cancelled) + outputs + cost
- `GET /tasks?project=X&role=Y&status=running` — фильтрация
- `DELETE /tasks/{id}` — cancel running task (SIGTERM на sub-process)
- `GET /tasks/{id}/stream` — SSE stream logs/outputs в реальном времени

CLI (через Justfile):
- `just task-run <role> <project> [--input=...]` — синхронный запуск, выводит результат
- `just task-spawn <role> <project>` — async, возвращает task_id
- `just task-status <id>` / `just task-cancel <id>`
- `just task-list [--active]`

**Task lifecycle:**

```
POST /tasks
  ├─ resolve role из team-template.yaml → {cli, model, prompt_template, mcp_endpoints, budget}
  ├─ render prompt с переменными проекта
  ├─ spawn sub-process: `<cli> -p "<rendered_prompt>"` 
  │    (claude code / codex / gemini / opencode — определяется team-template)
  ├─ устанавливает env vars: ANTHROPIC_API_KEY, PALACE_MCP_URL и т.д.
  ├─ stream stdout+stderr в SQLite blob + SSE clients
  ├─ при exit: подсчёт tokens (parse from stdout или API call к provider), update cost
  ├─ enforce budget: если `spent >= budget_usd` — SIGTERM sub-process
  └─ финальный status → running → done|failed → event в telemetry
```

**Team-template совместимость.** Lite-orchestrator читает **тот же** `team-template.yaml` (§7) что и paperclip-provisioner. Одни и те же role manifests работают в обеих орбитах. При миграции с `analyze` → `full` (добавлении Paperclip) — provisioner просто переносит роли в Paperclip, lite-orchestrator автоматически становится fallback'ом.

**Budget enforcement — real.** В отличие от "декларативного" бюджета в Paperclip (где пользователь доверяет, что агент сам остановится) — lite-orchestrator считает токены по факту (subprocess stdout parse / API latency × model rate) и жёстко kill'ит при overshoot. Результат записывается с `killed_by_budget=true`, пишется warning в report.

**Parallelism.** Configurable через `LITE_ORCHESTRATOR_MAX_PARALLEL_TASKS` (default 3). Задачи сверх лимита — в очередь FIFO.

**Scheduler integration.** Scheduler (§4.7) при cron/webhook trigger не сам спавнит агентов — он **POST'ит в lite-orchestrator** (если `PAPERCLIP_MODE=none`) или в Paperclip REST (если `embedded/external`). Это унифицирует data flow: кто бы ни дирижировал, `:Finding`/`:Decision`/прочие записываются одинаково.

**Ограничения (явно):**
- Нет UI — только REST и CLI
- Нет approval-gates — запускает сразу
- Нет cross-agent messaging (если агент A хочет что-то передать B — через palace `record_*` tools)
- Нет long-running conversations — каждый task stateless, single-shot
- Нет mTLS между worker'ами — внутри docker network, auth через bearer token

Если пользователю нужна governance — ставит профиль `full` с Paperclip. Lite-orchestrator не пытается быть Paperclip'ом.

---

## 5. Data Model (Graphiti schema)

### 5.1 Namespace'ы (group_id в Graphiti)

- `project/<slug>` — per-project namespace (основной)
- `global/decisions` — cross-project архитектурные решения (опционально)
- `global/patterns` — переиспользуемые паттерны

Каждый `search_memory` по умолчанию scope'ится к текущему project (из `project` аргумента).

### 5.2 Entity types (core)

| Entity | Properties | Purpose |
|---|---|---|
| `:Project` | slug, name, language, framework, repo_url, root_path | Root-узел |
| `:Module` | name, path, kind (ui/data/domain/...) | Слой архитектуры |
| `:File` | path, hash, loc, last_ingest_ts | Исходный файл |
| `:Symbol` | name, kind (class/func/...), signature, location | Мост в Serena |
| `:UIComponent` | name, kind (button/screen/...), framework, path, variants, props | UI inventory |
| `:APIEndpoint` | method, path, request_schema, response_schema, auth_required | API inventory |
| `:Model` | name, fields (json), db_table? | Data model |
| `:Repository` | name, entity, storage_kind | Data access |
| `:ExternalLib` | name, version, category | 3rd-party |
| `:Finding` | severity, category, text, file, line, reviewer | Result of reviewer runs |
| `:Decision` | text, scope, tags[], author, decided_at | Architectural decision record |
| `:IterationNote` | iteration, text, tags[], created_at | Free-form notes |
| `:Iteration` | number, kind, from_commit_sha, to_commit_sha, commit_count, started_at, ended_at, label? | Marker ingest runs (не 1-commit-per-iteration, §5.2.1) |

### 5.2.1 Iteration lifecycle — "ingest = iteration"

Одна **Iteration** — это **одно ingest run**, не один commit. Диапазон коммитов захватывается через `from_commit_sha` / `to_commit_sha` / `commit_count`.

**Временная модель:**

```
Time →

 commits:    c1──c2──c3──c4──c5──c6──c7──c8──c9──c10
                  │                     │              │
                  ▼                     ▼              ▼
 ingests:    Iteration 1          Iteration 2     Iteration 3
             kind="full"          kind="incremental"  kind="incremental"
             from_commit=null     from_commit=c3   from_commit=c6
             to_commit=c3         to_commit=c6     to_commit=c10
             commit_count=3       commit_count=3   commit_count=4
             label="initial"      label="swap-v2"  label=null
             (полный review)      (user markred)   (scheduled nightly)
```

**Правила:**

- **Iteration 1 = `kind="full"`** — всегда. Ingest всего репо, `from_commit_sha=null`, `to_commit_sha=<HEAD at ingest start>`, `commit_count=<total commits in history>`. Точка отсчёта.

- **Iteration N (N > 1) = `kind="incremental"`** — всегда delta. `from_commit_sha = previous iteration's to_commit_sha`. Обрабатывает только файлы затронутые диапазоном коммитов.

- **Триггеры новой iteration:**
  - `just ingest <project>` руками — если iteration 1 не было, делает full; если была — делает incremental от последней до текущего HEAD
  - Scheduled cron (§11) — incremental от последней до HEAD, если новые коммиты появились (иначе no-op)
  - GitHub webhook on push — incremental
  - `just re-ingest <project> --full` — принудительно новая full iteration (например, после радикального refactor)

- **Idempotency:** если HEAD == previous `to_commit_sha` — incremental ingest no-op, iteration не создаётся.

- **Label** — optional, user-provided через `just ingest <project> --label "swap-v2 release"` или через `just mark-iteration <project> <iteration-number> "<label>"` post-hoc. Семантические milestones поверх техниче granularity.

- **Graph node updates:** узлы создаются/обновляются с attr `introduced_at_iteration` (для создания) и `last_seen_at_iteration` (для каждого incremental confirmation). Узлы НЕ в scope incremental iteration не трогаются. Это позволяет queries типа "что было актуально на iteration 5?" через фильтр `last_seen_at_iteration >= 5`.

- **Temporal invalidation:** если incremental iteration detect'ит что факт изменился (переименован, удалён, семантика поменялась) — предыдущий узел получает `valid_to = iteration.started_at`, создаётся новый с `valid_from = iteration.started_at`. Native Graphiti bi-temporal.

### 5.3 Edge types

| Edge | From → To | Cardinality |
|---|---|---|
| `:BELONGS_TO` | `:File` → `:Module` | N:1 |
| `:DEPENDS_ON` | `:Module` → `:Module` | N:M |
| `:DEFINED_IN` | `:Symbol` → `:File` | N:1 |
| `:USED_BY` | `:UIComponent` → `:File` (count property) | N:M |
| `:CALLED_FROM` | `:APIEndpoint` → `:File` | N:M |
| `:PERSISTS_TO` | `:Repository` → `:Model` | N:M |
| `:USES_LIB` | `:File` → `:ExternalLib` | N:M |
| `:CONCERNS` | `:Finding`/`:Decision`/`:IterationNote` → `:Module`/`:File`/`:Symbol` | N:M |
| `:INVALIDATED_BY` | `:Decision` → `:Decision` | N:1 (через Graphiti bi-temporal) |

### 5.4 Faceted classification — multi-axial KG

Чтобы один query типа "write a screen showing EVM token address" возвращал одновременно UI-компоненты, hex-utilities, API-методы возвращающие адрес, validators, константы и применимые архитектурные правила — мы классифицируем **каждый** code element по 4 ортогональным осям одновременно.

**Neo4j native multi-label:** один узел может нести любое подмножество меток:

| Axis | Labels |
|---|---|
| **Structural** (где в коде) | `:Module`, `:File`, `:Class`, `:Method`, `:Property`, `:Extension` |
| **Semantic kind** (чем является) | `:UIComponent`, `:APIEndpoint`, `:Utility`, `:Helper`, `:Validator`, `:Converter`, `:Constant`, `:TypeAlias`, `:Repository`, `:Model` |
| **Domain concept** (о чём) | **Hybrid taxonomy** (§5.4.1): base + dynamic. Базовые: `:HandlesHex`, `:HandlesData`, `:HandlesAddress`, `:HandlesCrypto`, `:HandlesChain`, `:HandlesToken`, `:HandlesAmount`, `:HandlesUnit`, `:HandlesTime`, `:HandlesCurrency`. LLM может добавлять новые при ingest → попадают в `dynamic_taxonomy.yaml`. |
| **Capability** (что умеет) | Расширяемый vocabulary. Базовые: `:Encodes`, `:Decodes`, `:Validates`, `:Formats`, `:Signs`, `:Hashes`, `:Parses`, `:Fetches`, `:Caches`, `:Transforms`, `:Renders`, `:Authenticates`, `:Authorizes`, `:Observes`, `:Subscribes`, `:Navigates`, `:Persists`, `:Synchronizes`. Расширяется по мере необходимости через `config/facet-taxonomy.yaml`. |

Пример узла метода `ByteArray.toHexString()`:
```
labels: [:Method :Extension :Utility :HandlesHex :HandlesData :Encodes]
properties: {name, signature, path, line, usage_count, last_used_iteration}
```

**Composite indexes** по парам (label, property) — O(log n) query по пересечениям осей.

### 5.4.1 Hybrid taxonomy для axis 3 (Domain concept)

Domain concepts не должны быть ни жёстко предопределены (негибко для новых проектов), ни полностью LLM-свободно generated (deteriorates consistency — один и тот же концепт получит 5 разных имён). Решение — **hybrid** с human-in-the-loop review loop.

**Три уровня:**

1. **Base taxonomy** (`config/facet-taxonomy.yaml`, коммитится в git):
   ```yaml
   domain_concepts:
     HandlesHex:
       description: "Operations on hexadecimal string representations"
       aliases: ["hex", "hex string", "hexadecimal"]
     HandlesAddress:
       description: "Blockchain address (EVM, Bitcoin, Ton, etc.) formatting/validation"
       aliases: ["address", "wallet address", "account address"]
     # ... 10-15 base concepts для mobile wallet stack
   capabilities:
     Encodes:
       description: "Converts from one representation to another (one-way semantic)"
     # ... 15-18 base capabilities
   ```

2. **Dynamic taxonomy** (`data/dynamic_taxonomy.yaml`, в persistent volume):
   - LLM extractor во время ingest'а, если встречает концепт которого нет в base **и** который встречается 3+ раз в коде — добавляет в dynamic_taxonomy
   - Каждая новая запись: `name`, `introduced_at_iteration`, `first_seen_file`, `example_usages`, `needs_review: true`
   - Default prefix: `:Handles*` для domain, `:*s` (Verbs) для capability
   - Similarity check при добавлении: если embedding нового концепта слишком близок существующему (cos-sim > 0.92) — НЕ создаётся новый, используется существующий + добавляется alias

3. **Review loop (weekly scheduled task)** `just review-taxonomy`:
   - Показывает user'у все dynamic concepts с `needs_review: true`
   - User может: **(a)** promote в base taxonomy, **(b)** merge с существующим базовым (как alias), **(c)** reject (удалить concept, re-tag узлы как `:Misc`), **(d)** rename
   - После review — `needs_review: false`, или concept исчезает
   - Alias-learning: если user merge'ит `HandlesHexadecimal → HandlesHex` — это записывается в `:ALIAS_OF` edge + `aliases:` list в base taxonomy

**Consistency guarantees:**
- При каждом ingest: первый шаг — прочитать `facet-taxonomy.yaml` + `dynamic_taxonomy.yaml`, дать extractor'у как known vocabulary.
- Extractor prompt: *"Используй только эти existing concepts. Если встречаешь что-то что ни один из них не описывает и встречается часто (≥3 раз в текущем batch'е) — добавь новый с префиксом `:Handles*`, иначе маппи в ближайший существующий."*
- Similarity check препятствует созданию `:HandlesHex` и `:HandlesHexadecimal` как разных концептов.

### 5.5 Capability edges для обратного индекса

Дополнительные edge-types:

| Edge | Из → В | Назначение |
|---|---|---|
| `:OPERATES_ON` | `:Method` → `:DomainConcept` | "этот метод работает с hex" |
| `:RETURNS` | `:Method` → `:DomainConcept`/`:Model` | тип возврата |
| `:ACCEPTS` | `:Method` → `:DomainConcept`/`:Model` | тип параметра |
| `:SIMILAR_TO` | `:UIComponent` ↔ `:UIComponent` | pre-computed по embedding cos-sim > 0.85 |
| `:APPLIES_TO` | `:Decision` → `:DomainConcept`/`:Module` | применимость правила |
| `:ALIAS_OF` | `:Alias` → `:DomainConcept` | "hex", "hexadecimal", "hex string" = один концепт |

### 5.6 Retrieval pipeline (faceted)

`palace-mcp.find_context_for_task(task_description)` — композитный tool:

```
Stage 1: Intent parsing (1 LLM call, Haiku, ~$0.001)
  → {domain_concepts[], capabilities_needed[], semantic_kinds_needed[]}

Stage 2: Vector search
  → top-K nodes по embedding similarity с task_description

Stage 3: Multi-axial intersection (parallel Cypher queries)
  for kind in semantic_kinds_needed:
    for concept in domain_concepts:
      MATCH (n) WHERE n:kind AND n:concept
      RETURN n ORDER BY usage_count DESC LIMIT 5

Stage 4: Graph expansion
  для топ-ranked — развернуть 1-2 hop edges :USED_BY, :SIMILAR_TO,
  :APPLIES_TO (decisions), :RETURNS/:ACCEPTS (call graph)

Stage 5: Group & render
  результат → JSON структурированный по facets
  (ui_building_blocks / utilities / api / constants / decisions / patterns)
```

Итоговый response: ~3-5K tokens, <500ms latency, Claude получает **grouped-by-purpose** картину вместо flat-списка.

### 5.7 Temporal model

Используем native Graphiti bi-temporal edges: `valid_from` / `valid_to` + `recorded_at`. Примеры запросов:

- "Что знали про модуль X до итерации N?" → фильтр по `recorded_at < iteration_N.started_at`.
- "Какие решения актуальны сейчас?" → фильтр `valid_to IS NULL`.
- "История архитектурных инверсий" → все `:Decision` с `INVALIDATED_BY` chains.

---

## 6. `project.yaml` schema

Декларативное описание таргет-репозитория. Валидируется через JSON Schema; загружается paperclip-provisioner + scheduler.

```yaml
# projects/unstoppable-android.yaml
slug: unstoppable-android
name: Unstoppable Wallet (Android)
repo:
  kind: local                # local | git
  path: /repos/unstoppable-wallet-android
  # OR:
  # url: https://github.com/horizontalsystems/unstoppable-wallet-android
  # token_env: GITHUB_TOKEN
  default_branch: master

language: kotlin
framework: android-compose
secondary_languages: [java]

tags:
  - mobile
  - blockchain
  - wallet

# Какие extractors активны на этом проекте
extractors:
  - architecture-extractor
  - ui-component-extractor
  - api-extractor
  - data-layer-extractor
  - dependency-analyzer

# Какие reviewers активны (code-analyzer MCPs)
reviewers:
  - security-reviewer
  - blockchain-reviewer
  - deadcode-hunter
  - duplication-detector

# Depth tuning (cost knob)
depth:
  structural: full            # full | shallow — карта символов
  review: hot-paths           # full | hot-paths | off — где гонять reviewers
  embeddings: yes             # да/нет — строить vector index

# Planned iterations marker
iteration:
  current: 1
  label: "initial"

# Scheduled updates
trigger:
  kind: cron                  # cron | webhook | manual
  schedule: "0 3 * * *"       # nightly at 03:00 UTC
  # OR: webhook: {provider: github, secret_env: GITHUB_WEBHOOK_SECRET}

# Budget caps (optional — forwarded to Paperclip team template)
budget:
  initial_ingest_usd: 50
  per_update_usd: 2
  model_policy:
    architecture: opus
    bulk_review: sonnet
    extractors: sonnet
    minor_passes: haiku
```

---

## 7. `team-template.yaml` schema

Шаблон команды для данного **класса** проектов (один template может использоваться для нескольких `project.yaml`). Структура одинаковая для Paperclip-based (`full`) и lite-orchestrator (`analyze`) путей — разница только в том, кто запускает агентов.

### 7.1 Role schema (полная)

```yaml
# teams/mobile-blockchain-default.yaml
name: Mobile Blockchain Default Team
applies_to_tags: [mobile, blockchain]

# Fragment'ы автоматически инжектятся во все generated AGENTS.md
auto_fragments:
  - "@-mention-safety"       # см. §7.3, критично для Paperclip handoff
  - "palace-record-discipline" # как и когда писать в palace через record_*

roles:
  - id: architecture-extractor
    # Paperclip-specific (только для paperclip-provisioner):
    paperclip_name: ArchitectureExtractor      # MUST match ^[A-Z][a-zA-Z0-9]*$ (§Paperclip-ops Bug #1)
    paperclip_role: engineer                   # enum: ceo|cto|cmo|cfo|engineer|designer|pm|qa|devops|researcher|general
    paperclip_icon: cpu                        # из /llms/agent-icons.txt
    paperclip_reports_to: CTO                  # optional agent name в той же company

    display_name: Architecture Extractor
    capabilities: |
      Maps modules, layers, and inter-module dependencies.
      Records :Module and :DEPENDS_ON edges in palace.

    # CLI / adapter selection
    cli: claude-code                           # claude-code | codex | gemini | opencode | cursor
    adapter_type: claude_local                 # auto-derived from cli; overridable
    model: claude-opus-4-6

    # MCP endpoints that agent has access to (reference §13.1 inventory + our palace)
    mcp_endpoints: [palace, serena, github, sequential-thinking]

    # Plugins enabled in ~/.paperclip/.../workspaces/<id>/.claude/settings.json
    plugins: [superpowers, voltagent-meta]     # per §13.5 matrix

    # Preferred subagents (when Claude Code is the CLI)
    subagent_preferences:
      - voltagent-qa-sec:architect-reviewer

    # Prompt template — rendered with {project.*} variables + auto_fragments injected
    prompt_template: |
      You are the Architecture Extractor for {project.name} ({project.slug}).
      Use Serena MCP for navigation and palace-mcp.record_* to persist findings.
      Map modules, layers, dependencies. Record as :Module and :DEPENDS_ON edges.
      Tags: {project.tags}.

    # Budget and runtime
    budget_usd_per_run: 5
    budget_monthly_usd: 100
    runtime:
      heartbeat_enabled: false                 # только on_demand wake от scheduler/provisioner
      wake_on_demand: true
      max_concurrent_runs: 1
      cooldown_sec: 10

  - id: ui-component-extractor
    paperclip_name: UiComponentExtractor
    paperclip_role: engineer
    paperclip_icon: palette
    display_name: UI Component Extractor
    capabilities: "Classifies UI components (buttons/screens/cards); counts usages; records :UIComponent + :USED_BY."
    cli: claude-code
    model: claude-sonnet-4-6
    mcp_endpoints: [palace, serena]
    plugins: [superpowers]
    prompt_template: |
      Extract UI components from {project.name}. For each @Composable (Kotlin) / View (Swift) /
      component (React/Vue/etc): classify kind={button|screen|card|input|layout|modal|other},
      framework={{project.framework}}, count usages via Serena `find_references`.
      Record as :UIComponent with :USED_BY edges.
    budget_usd_per_run: 3
    runtime: { heartbeat_enabled: false, wake_on_demand: true, max_concurrent_runs: 1 }

  - id: security-reviewer
    paperclip_name: SecurityReviewer
    paperclip_role: qa
    paperclip_icon: shield-check
    display_name: Security Reviewer
    capabilities: "Reviews code for OWASP/CWE vulnerabilities and security anti-patterns."
    cli: claude-code
    model: claude-opus-4-6            # Opus для security-critical
    mcp_endpoints: [palace, serena, security-reviewer-mcp, github]
    plugins: [superpowers, pr-review-toolkit, code-review, voltagent-qa-sec]
    subagent_preferences:
      - voltagent-qa-sec:security-auditor
      - voltagent-qa-sec:penetration-tester
    prompt_template: |
      Run security-reviewer-mcp against {project.name}. Focus: key storage, crypto usage,
      network requests, WebView configurations, deep link handling, input validation.
      Record findings as :Finding with severity ∈ {low, medium, high, critical}.
    budget_usd_per_run: 10

  # ... etc для blockchain-reviewer, deadcode-hunter, duplication-detector, etc.
```

### 7.2 Validation (на load)

`paperclip-provisioner` и `lite-orchestrator` валидируют `team-template.yaml` при старте через JSON Schema:
- `paperclip_name` — regex `^[A-Z][a-zA-Z0-9]*$` (hard fail — это корень Bug #1)
- `paperclip_role` — только enum values
- `cli` → `adapter_type` таблица маппинга должна совпадать
- `mcp_endpoints` — все endpoint names из списка должны быть зарегистрированы в compose
- `plugins` — все plugin names должны быть из `~/.claude/plugins/cache/` (detected at startup)
- `model` — валидный Claude/OpenAI/Gemini model ID

Fail-fast — если schema broken, стек не поднимается.

### 7.3 Auto-fragment `@-mention-safety.md`

Автоматически инжектится во все AGENTS.md (через `auto_fragments: ["@-mention-safety"]`). Его содержимое (на основе §Paperclip-operations 3.4):

```markdown
### @-упоминания: CamelCase без пробелов и всегда пробел после имени

Paperclip parser ломается на пробелах внутри имени агента и на любой пунктуации
сразу после `@Name`. Цепочка handoff молча останавливается — в логе никаких ошибок.

- Правильно:   `@CodeReviewer фикс готов`, `@iOSEngineer проверь билд`
- Неправильно: `@Code Reviewer ...`, `@CTO: нужен фикс`, `(@CodeReviewer)`

### Handoff: всегда @-упомяни следующего агента

Когда заканчиваешь фазу — обязательно `@NextAgent` в комментарии, **даже** если он
уже assignee. Разница endpoint'ов Paperclip:

- `POST /api/issues/{id}/comments` — будит assignee + всех @-упомянутых
- `PATCH /api/issues/{id}` с `comment` — будит ТОЛЬКО на assignee-change / status-from-backlog / @-mentions

Handoff-комментарий ВСЕГДА включает `@NextAgent` (CamelCase + пробел после).
Страхует оба пути, чтобы цепочка не остановилась молча.

### Ссылка на агента через markdown-link (опционально для 100% надёжности)

[Code Reviewer](agent://<agent-uuid>) — обрабатывается через `extractAgentMentionIds`,
пробелы и пунктуация в лейбле не ломают парсинг. Используй если имя сложное или ты не
уверен в токене.
```

Этот fragment **НЕ редактируется** пользователем в `fragments/` — он генерируется нашим builder'ом из данных `~/.paperclip/instances/default/companies/<cid>/agents` (список agent names живой). Регенерация при `just rebuild-prompts` или при каждом ingest.

### 7.4 Resolve flow (template → Paperclip agent)

```
team-template.yaml (roles)  +  project.yaml (reviewers, extractors list)
           │
           ▼
resolve_roles(project, template) → list[ResolvedRole]
  - filter: только те role.id, которые в project.reviewers + project.extractors
  - render prompt_template с project vars
  - inject auto_fragments
  - validate schema
           │
           ▼
paperclip-provisioner → Paperclip API (see §4.7 reconciliation loop)
   │     │
   │     └── создаёт/обновляет/удаляет Paperclip agents
   │
   └── lite-orchestrator (если PAPERCLIP_MODE=none) →
       регистрирует role в своём SQLite таске `orchestrator_roles`
       для последующих POST /tasks
```

---

## 8. Telemetry & ROI Measurement

### 8.1 Что записывается — см. §4.8 schema.

### 8.2 `avoided_tokens_est` формула

Прозрачная, документирована, пользователь может оспорить. Формула per-tool coefficient:

```python
AVOIDED_TOKENS_FORMULA = {
    "search_memory":          lambda res: 0.3 * total_file_bytes_matched(res) / 4,
    "find_ui_components":     lambda res: 0.25 * sum(c.file_size for c in res["components"]) / 4,
    "find_component_usage":   lambda res: 0.4 * sum(ref.file_size for ref in res["refs"]) / 4,
    "find_similar_component": lambda _: 20000,   # semantic search = ~20k raw read
    "find_api_contract":      lambda res: 3000 * len(res["endpoints"]),
    "find_screen":            lambda res: 15000,
    "get_layer_dependencies": lambda _: 15000,
    "get_iteration_notes":    lambda res: 2000 * len(res["notes"]),
    # record_* tools — no savings, это write.
}
```

`/` 4 — грубая конверсия bytes → tokens (1 token ≈ 4 bytes для кода в среднем).

Коэффициенты tunable через `config/telemetry.yaml` без релиза.

`just stats --explain` выводит эту формулу + per-tool вклад в общий saved tokens — **полная прозрачность**, явно помечает **"rough estimate based on file-size heuristics — actual savings may vary ±30%"**.

**Пользователь должен понимать** что avoided_tokens_est — оценка, не измерение. Абсолютные цифры приближённые; **trend reliable** (day-over-day сравнения работают, 30% bias одинаковый в обе стороны).

### 8.2.1 Калибровочный режим (opt-in)

Для users, кому нужны точные savings — `just calibrate` запускает controlled A/B:

```bash
just calibrate --project unstoppable-android --iterations 10
```

Workflow:
1. Выбираются 10 типовых задач из последних 100 палата-запросов (stratified по tool types).
2. Для каждой — **two runs** Claude с одним и тем же промптом:
   - Run A: **без palace-mcp** (MCP отключён). Claude делает grep/read файлов.
   - Run B: **с palace-mcp**. Claude use faceted tools.
3. Измеряется: total input + output tokens обоих runs. Разница (A − B) = **real avoided tokens** для этой задачи.
4. Новые коэффициенты для `AVOIDED_TOKENS_FORMULA` вычисляются через linear regression: `avoided_real = f(response_bytes, tool_type)`. Записываются в `data/calibration.yaml` с timestamp + sample size.
5. Дальше `just stats` использует **calibrated** коэффициенты вместо default heuristics. В `--explain` показывает *"calibrated on 2026-04-20, sample N=10, R²=0.73"*.

**Cost калибровки:** ~$20-30 на ran (каждая задача ×2 runs через Sonnet). Не делается автоматически — только по user command.

**Recalibration frequency:** рекомендуемая — раз в 3-6 месяцев или после значительных изменений в codebase/taxonomy. Автоматический prompt в `just stats`: *"Calibration is 4 months old — consider running `just calibrate`"*.

### 8.3 Dashboard поверх (optional)

Через compose profile `with-dashboard` добавляется **Metabase** pointed на SQLite. Out-of-scope для MVP.

### 8.4 Export — human-facing knowledge dump

`just export` — генерирует dump знаний палаты для человеческого чтения, передачи коллеге, архива. Отличается от backup (§4.1) тем, что backup — машинный snapshot для restore, export — читаемый артефакт.

**Параметры CLI:**

```bash
just export <project>                          # полный snapshot, markdown, все разделы
just export <project> --since=2026-04-01       # только delta с даты
just export <project> --since-iteration=5      # с конкретной итерации
just export <project> --format=markdown        # default
just export <project> --format=json            # machine-readable
just export <project> --format=zip             # markdown + json + attachments
just export <project> --summary                # краткая 1-2 стр. сводка вместо полного дампа
just export <project> --sections=ui,decisions  # только указанные разделы
just export --all                              # все registered projects разом
```

**Структура полного markdown export:**

```
exports/<project>/<timestamp>/
├── README.md               # metadata: iteration#, last_ingest_commit_sha, coverage %
├── architecture.md         # §modules + layers + mermaid dep-diagram
├── ui-catalogue.md         # все :UIComponent grouped by kind + usage counts
├── api-surface.md          # все :APIEndpoint с schemas
├── data-layer.md           # :Model, :Repository, :DBTable inventory
├── decisions.md            # все :Decision с timestamps — Linear-style feed
├── findings.md             # все :Finding grouped by severity + static/llm/hybrid source
├── dead-code.md            # hotspots из deadcode-hunter
├── duplication.md          # hotspots из duplication-detector
├── dependencies.md         # :ExternalLib + usage map + CVE findings
├── iterations-history.md   # timeline: когда какая итерация + что изменилось
└── diff-since-<date>.md    # если --since указан (delta-only view)
```

**Режимы:**

| Режим | Объём | Когда использовать |
|---|---|---|
| **Полный** (без флагов) | 20-50 стр. markdown для среднего репо | Монументальный audit, onboarding нового senior'а, архив итерации |
| **`--summary`** | 1-2 стр. (overview + top-10 decisions + top findings by severity) | Weekly digest команде, quick briefing для заинтересованного стейкхолдера |
| **`--since=<date>`** | Только изменения с даты | Monthly report "что сделали", delta audit перед релизом |
| **`--sections=...`** | Только указанные разделы | Focused export для конкретной задачи (напр. "покажи только UI inventory для дизайнера") |

**Что `--summary` выдаёт (компактный формат):**

```markdown
# Gimlé Palace Summary — unstoppable-wallet-android (iteration 14)

## Architecture at a glance
- 47 modules, 8 logical layers (ui / data / domain / ...)
- Deepest dep chain: 6 hops
- Top-3 most-depended-on modules: core-utils (23 depend), wallet-manager (18), network-kit (14)

## Key decisions (most recent 10)
- [2026-04-14] EVM addresses MUST be rendered in EIP-55 checksum format before display
- [2026-04-11] Biometric auth required for any private-key access path
- ... (дальше 8)

## Critical findings (severity=high, active)
- 2 open (SecurityReviewer 2026-04-13, BlockchainReviewer 2026-04-09)
  - HexEncoder uses platform-default charset → unicode edge case
  - Nonce in approve-tx handled in VM, should be in UseCase

## Stats
- UI components: 87 (32 screens, 24 buttons, 18 cards, 13 other)
- API endpoints: 42
- External libs: 23
- Dead code hotspots: 6
- Duplicates: 3 clusters
```

Генератор exports — отдельная role `report-writer` (§4.6), вызываемая через `just export` (напрямую из lite-orchestrator / Paperclip task). Использует `palace-mcp.get_architecture_summary`, `get_iteration_notes`, `find_decision_by_topic` и прочее — не пишет SQL/Cypher сам.

**Delta export** (`--since=<date>`) — incremental режим: report-writer получает `get_iteration_diff(from, to)`, только изменённые факты становятся контентом. 10-20× меньше чем full.

---

## 9. Security & Secrets

### 9.1 Secret surface

| Секрет | Где хранится |
|---|---|
| `ANTHROPIC_API_KEY` | `.env` (gitignored) или sops-encrypted `.env.sops.yaml` |
| `OPENAI_API_KEY` | same |
| `PAPERCLIP_API_KEY` | same (получается через `POST /api/agents/{id}/keys` — raw key возвращается **один раз**, сохранить в `.env` сразу; после потери — создать новый и ротировать) |
| `PAPERCLIP_AGENT_JWT_SECRET` | живёт в `~/.paperclip/instances/default/.env` на той же машине; наш stack читает через volume mount если нужен (для crafting JWT при manual wake-up через `curl`) — но штатно мы используем API keys, не JWT |
| `PAPERCLIP_LLM_APIKEY` | читается из `~/.paperclip/instances/default/config.json` → `llm.apiKey` (это **Paperclip-owned** секрет, мы его не трогаем, только читаем для sanity check что Paperclip может отдать LLM calls) |
| `GITHUB_TOKEN` (доступ к private репо) | `.env` |
| `NEO4J_PASSWORD` | `.env`, rotated через `just rotate-neo4j` |
| `TELEMETRY_HASH_SALT` | `.env` (для обезличивания args в логах) |

**Paperclip secrets не попадают в gimle's `.env`** — остаются под Paperclip'ом. Gimle держит только **ссылки на них** через path mount'ы и API keys.

### 9.2 Auth между client ↔ server

- `palace-mcp` при remote-connect требует `X-Palace-Token: <token>` header.
- Tokens management: `just mint-token <user>` генерирует JWT-like opaque token, записывает в `palace-tokens` SQLite table.
- Client installer пишет token в `~/.claude/mcp.json` как header.
- Revocation: `just revoke-token <user>`.

### 9.3 Privacy

- `TELEMETRY_HASH_ARGS=1` — hash'ирует `args_json` чтобы не логировать сам код/запросы.
- `TELEMETRY_RETENTION_DAYS=90` — автоматическое удаление старых events.

### 9.4 Network

- Все core сервисы — только на internal `paperclip-agent-net`.
- Наружу exposed только: palace-mcp HTTP (с auth), skills-distributor `/install`, `/stats` (опционально с basic auth).
- TLS — через reverse proxy (Caddy recommended) на front либо через Coolify-managed Traefik.

---

## 10. Ingest Pipeline

Команда: `just ingest <project-slug>` (full или incremental — autodetected по наличию previous `:Iteration`).

### 10.1 First-time (full) ingest — `:Iteration` kind=full

Триггерится когда для проекта нет предыдущих `:Iteration` узлов (первый запуск). **Полный deep ingest всех файлов**, без tiered shortcuts — точка отсчёта должна быть полноценной, от неё потом delta-обновления.

Workflow:

1. Validate `projects/<slug>.yaml`.
2. Clone/sync repo into server volume `repos/<slug>`. Запомнить `HEAD_SHA`.
3. Create `:Iteration` node: `{number: 1, kind: "full", from_commit_sha: null, to_commit_sha: <pending>, started_at: now(), label: <from flag or null>}`.
4. **Serena warm-up:** startup Serena с указанным репо, первичная индексация LSP (~20-120 сек в зависимости от размера).
5. **Load taxonomy:** читаем `config/facet-taxonomy.yaml` + `data/dynamic_taxonomy.yaml` — подаём extractor'у как known vocabulary.
6. **Paperclip task creation** (или lite-orchestrator в profile `analyze`): создаёт tasks для каждого extractor из team-template. Tasks runs параллельно с budget limits.
7. **Extractors** пишут в palace через palace-mcp `record_*` tools. Graphiti constructs KG. Каждый факт помечается `introduced_at_iteration: 1`, `last_seen_at_iteration: 1`.
8. **Reviewers pass** (если включены в `reviewers:` в project.yaml). Пишут `:Finding` узлы. Hybrid flow (§4.5.4): static tools first → LLM reasoning second.
9. **Taxonomy delta persist:** если LLM-extractor'ы создали новые domain concepts — append в `data/dynamic_taxonomy.yaml` с `needs_review: true`.
10. **Report generation:** `report-writer` агент читает palace + findings + generates **markdown-отчёт 10-20 страниц** в `reports/<slug>/iteration-01.md`. Содержимое (см. §8.4 для детальной структуры):
    - Architecture overview (с diagram в mermaid)
    - UI components catalogue
    - API surface
    - Dependencies + CVE findings
    - Critical findings (severity=high) — static + llm + hybrid
    - Non-critical findings
    - Dead code hotspots
    - Duplication hotspots
    - Recommendations
11. **Finalize Iteration:** update `:Iteration{1}` с `to_commit_sha: HEAD_SHA`, `commit_count: <total-in-history>`, `ended_at: now()`.
12. Telemetry записывает `ingest_completed` event с `kind="full"`, `iteration_number=1`, cost stats, latency.

Cost для типичного репо 30-300K LOC на cloud mode: **$5-50** (Sonnet). На Opus для критичных ролей: ×6-10.

### 10.2 Subsequent (incremental) ingest — `:Iteration` kind=incremental

Триггерится либо manually (`just ingest <project>`) либо scheduler (§11). Детектирует previous `:Iteration`, делает delta от её `to_commit_sha` до current HEAD.

Workflow:

1. Load last `:Iteration` (highest `number`).
2. `git fetch && HEAD_SHA = git rev-parse HEAD`.
3. Если `HEAD_SHA == last.to_commit_sha` → **no-op** (нет новых commits), exit. Iteration не создаётся.
4. Create `:Iteration{number: last.number + 1, kind: "incremental", from_commit_sha: last.to_commit_sha, to_commit_sha: <pending>, started_at: now()}`.
5. `changed_files = git diff --name-only last.to_commit_sha..HEAD`.
6. **Scope extractors только на changed_files** — не re-ingest всего репо. Serena refresh relevant LSP indexes.
7. Extractors пишут через palace-mcp `record_*`:
   - Новые факты: создаются узлы с `introduced_at_iteration: N`, `last_seen_at_iteration: N`.
   - Изменённые: старый узел получает `valid_to = iteration.started_at`, новый создаётся.
   - Удалённые (файл исчез): старый узел получает `valid_to = iteration.started_at` без нового.
   - Неизменённые факты из нетронутых файлов: просто update `last_seen_at_iteration: N` чтобы показать "всё ещё актуально".
8. Reviewers pass — только на changed_files + связанных через `:DEPENDS_ON` (blast radius ≤ 2 hops).
9. `report-writer` делает **delta report** — что изменилось в этой итерации (это `just export --since=<prev-iter-date>` эквивалент, автоматически).
10. Finalize Iteration: `to_commit_sha`, `commit_count`, `ended_at`.
11. Telemetry event `kind="incremental"`.

Cost: **$0.05-$0.50 per incremental update** — 10-100× дешевле full ingest.

### 10.3 Когда нужен force-full

`just ingest <project> --full` принудительно создаёт новую full iteration даже если есть предыдущие. Используй когда:
- Радикальный refactor (переименование 30%+ symbols, структурные изменения)
- Изменение `config/facet-taxonomy.yaml` (новые concepts, которые требуют re-classification)
- Подозрение на corruption incrementals (расхождение palace ↔ реальный код)

---

## 11. Scheduled Update Flow

Логика триггеров теперь разделена между Paperclip routines (`full` profile) и собственным scheduler'ом (`analyze`). Реализация и routing описаны в §4.7 (scheduler subsection). Здесь — только **pipeline logic**, одинаковая для обеих веток.

### 11.1 Incremental update pipeline (одинаково для обеих веток)

Logic per trigger fire:
```
fetch_latest(repo)
if head_sha == last_ingested_sha: return  # ничего нового
changed_files = git diff --name-only last_ingested_sha..HEAD
new_iteration = current + 1

# Ветка A (PAPERCLIP_MODE=embedded|external, profile=full):
#   scheduler синхронизировал Paperclip Routine; routine fires → issue created →
#   assigned to ArchitectureExtractor/... → agent wakes → читает issue →
#   использует palace-mcp.record_* tools

# Ветка B (PAPERCLIP_MODE=none, profile=analyze):
#   scheduler's APScheduler job → POST /tasks в lite-orchestrator с role=incremental-updater
#   → lite-orchestrator спавнит claude code -p "..." с нужным контекстом

# Далее — одинаковое:
run_incremental_extractors(changed_files, iteration=new_iteration)
run_incremental_reviewers(changed_files)
update_or_invalidate_graph_nodes(changed_files, iteration=new_iteration)
generate_delta_report(iteration=new_iteration)
update project.yaml with new iteration number (commit to git)
```

Incremental ingest в 10-100× дешевле полного (по количеству touched files).

### 11.2 Triggers — spec (одинаково для обеих веток)

В `project.yaml`:
```yaml
trigger:
  kind: cron      # cron | webhook | manual | api
  schedule: "0 3 * * *"
  # или:
  webhook:
    provider: github           # github | gitlab | gitea | generic
    secret_env: GITHUB_WEBHOOK_SECRET
```

`full` профиль: scheduler transformation `project.trigger` → Paperclip `POST /api/routines/:id/triggers` body.
`analyze` профиль: scheduler sets up APScheduler job или FastAPI `POST /webhook/:project/push` endpoint.

### 11.3 Invalidation vs update

- Если факт изменился (архитектурное решение, API signature) — новый `:Decision`/`:APIEndpoint` с `recorded_at = new_iteration`, предыдущий получает `valid_to`.
- Если факт "ушёл" (файл удалён) — `valid_to` без создания нового.
- Это native Graphiti bi-temporal, руками не трогаем.

---

## 12. Client Distribution & User Journey

### 12.1 Installer contract

`install.sh` (автогенерирован server'ом, подставлен server URL):

```bash
#!/usr/bin/env sh
set -eu
SERVER_URL="${1:-$DEFAULT_SERVER_URL}"
TOKEN="${2:-}"

test -d "$HOME/.claude" || { echo "Claude Code not installed"; exit 1; }

echo "Installing skills..."
mkdir -p "$HOME/.claude/skills" "$HOME/.claude/agents"
curl -fsSL "$SERVER_URL/client/skills.tar.gz" | tar -xz -C "$HOME/.claude/skills"
curl -fsSL "$SERVER_URL/client/subagents.tar.gz" | tar -xz -C "$HOME/.claude/agents"

echo "Configuring MCP..."
curl -fsSL "$SERVER_URL/client/mcp-config.json?token=$TOKEN" > /tmp/palace-mcp.json
# non-destructive merge into ~/.claude/mcp.json
python3 -c "import json,sys,os;p=os.path.expanduser('~/.claude/mcp.json');d=json.load(open(p)) if os.path.exists(p) else {};d.update(json.load(open('/tmp/palace-mcp.json')));json.dump(d,open(p,'w'),indent=2)"

echo "Done. Run 'claude mcp list' to verify."
```

### 12.2 Typical user session

1. User открывает Claude Code в каком-то клиентском проекте.
2. User пишет: "Напиши экран с отображением EVM адреса токена".
3. Claude Code видит доступные MCP tools (подключённые при install).
4. Claude call'ит composite `find_context_for_task("display EVM token address", project="unstoppable-android")` (§5.6).
5. palace-mcp запускает 5-stage faceted pipeline (Intent → Vector → Multi-axial intersection → Graph expansion → Grouped render).
6. Возвращается grouped JSON: `ui_building_blocks`, `utilities.hex_conversion`, `utilities.address_formatting`, `api_endpoints_returning_address`, `constants`, `decisions_applicable` (типа "всегда checksum формат"), `similar_code_patterns`.
7. Claude за **один MCP call** получает ≈3-5K tokens vs 100-200K grep-исследования — и строит решение с учётом существующих helpers, паттернов и декларированных правил.
8. По ходу работы — автоматические `record_decision(...)`/`record_finding(...)` через client palace-skill (§13.4), когда Claude принимает неочевидное решение или замечает паттерн.

### 12.3 Paperclip UI как дополнительный контрольный слой

- http://server:3100 — пользователь видит команду, approvals, budgets, traces всех agents runs.
- Может вручную поставить задачу: "security review PR #1234" → назначает security-reviewer агенту.
- Может посмотреть историю вызовов palace (которые также отражены в telemetry).

---

## 13. Existing Inventory — user's current Paperclip setup

Пользователь уже использует следующий inventory в `~/.paperclip/instances/default/workspaces/<workspace-id>/`. Наш стек встраивается в него, не ломая, через автоматическую установку (§13.5).

### 13.1 Global MCP servers (9 штук)

| Имя | Команда | Роль в нашем стеке |
|---|---|---|
| `filesystem` | `npx @modelcontextprotocol/server-filesystem /Users/Shared/Ios /Users/anton` | Доступ к локальным файлам — используется всеми агентами |
| `github` | `npx @modelcontextprotocol/server-github` | Git/GitHub API — для cron/webhook trigger, repo metadata, issues |
| `supabase` | `npx @supabase/mcp-server-supabase` | Опциональный backend для проектов, использующих Supabase |
| `magic` | `npx @21st-dev/magic` | 21st.dev UI generator — дополняет UXDesigner роль |
| `context7` | `npx @upstash/context7-mcp` | Docs для сторонних libs — дополняет reviewers знанием API |
| `playwright` | `npx @playwright/mcp@latest` | UI/E2E automation — для QAEngineer роль |
| `sequential-thinking` | `npx @modelcontextprotocol/server-sequential-thinking` | Мета-reasoning — для CTO/Architect ролей |
| `tavily` | `npx tavily-mcp@0.1.2` | Web search — для ResearchAgent роль |
| `serena` | `/Users/anton/.local/share/uv/tools/serena-agent/bin/serena ...` | Code navigation — **уже есть**, не ставим повторно |

**Инсайт:** Serena уже в inventory пользователя → наш серверный Serena-контейнер становится *опциональным* для scenario A (можно переиспользовать local Serena через MCP URL override). Для scenario C (remote server) — ставим наш serena-контейнер, т.к. клиент не может дать нам доступ к своей FS.

В статусе `needs-auth` были `claude.ai Gmail` / `claude.ai Google Calendar` — фактически не работают, не трогаем.

### 13.2 Skills — superpowers (14) + paperclip-specific (4)

superpowers — все 14 skill'ов нашего же brainstorming ecosystem:

```
brainstorming · dispatching-parallel-agents · executing-plans ·
finishing-a-development-branch · receiving-code-review · requesting-code-review ·
subagent-driven-development · systematic-debugging · test-driven-development ·
using-git-worktrees · using-superpowers · verification-before-completion ·
writing-plans · writing-skills
```

paperclip-specific (встроены в `@paperclipai/server`):
`paperclip · paperclip-create-agent · paperclip-create-plugin · para-memory-files`

**Вывод для нашего стека:** все эти skills уже у пользователя. Мы **НЕ** дублируем их в `client/skills/`. Вместо этого наша роль — дополнять palace-specific skills (см. §13.4).

### 13.3 Subagents — 31 по 4 плагинам

| Plugin | Count | Subagents |
|---|---|---|
| `superpowers` | 1 | `code-reviewer` |
| `pr-review-toolkit` | 6 | `code-reviewer`, `code-simplifier`, `comment-analyzer`, `pr-test-analyzer`, `silent-failure-hunter`, `type-design-analyzer` |
| `voltagent-meta` | 9 | `agent-organizer`, `context-manager`, `error-coordinator`, `it-ops-orchestrator`, `knowledge-synthesizer`, `multi-agent-coordinator`, `performance-monitor`, `task-distributor`, `workflow-orchestrator` |
| `voltagent-qa-sec` | 15 | `accessibility-tester`, `ad-security-reviewer`, `ai-writing-auditor`, `architect-reviewer`, `chaos-engineer`, `code-reviewer`, `compliance-auditor`, `debugger`, `error-detective`, `penetration-tester`, `performance-engineer`, `powershell-security-hardening`, `qa-expert`, `security-auditor`, `test-automator` |

**Mapping на наши reviewer-роли (§4.5, §4.6) — используем существующие subagents вместо изобретения своих:**

| Наш reviewer | Используемый subagent |
|---|---|
| `security-reviewer` | `voltagent-qa-sec:security-auditor` + `penetration-tester` |
| `architecture-extractor` | `voltagent-qa-sec:architect-reviewer` |
| `deadcode-hunter` | `pr-review-toolkit:code-simplifier` + custom prompt |
| `duplication-detector` | (собственный prompt через `code-reviewer`) |
| `blockchain-reviewer` | custom prompt поверх `voltagent-qa-sec:security-auditor` (adds chain-specific checks) |
| `ui-component-extractor` | custom prompt — нет прямого аналога |
| `api-extractor` | custom prompt |
| `dependency-analyzer` | custom prompt |
| `data-layer-extractor` | custom prompt |

### 13.4 Slash commands user'а

```
/code-review  → code-review plugin
/review-pr    → pr-review-toolkit
/brainstorm, /execute-plan, /write-plan  → superpowers
/superpowers:*  → все 14 skill-команд
/paperclip, /paperclip-create-agent, /paperclip-create-plugin, /para-memory-files  → paperclipai CLI
```

**Наш стек добавит `/palace-*` slash-command family:** `/palace-query`, `/palace-record`, `/palace-ingest-local`, `/palace-status`. Установка — через наш client installer.

### 13.5 Per-agent plugin enablement matrix (user's current)

Файл настройки: `~/.paperclip/instances/default/workspaces/<workspace-id>/.claude/settings.json`

Текущая матрица пользователя:

| Агент | superpowers | pr-review-toolkit | code-review | voltagent-qa-sec | voltagent-meta |
|---|---|---|---|---|---|
| CEO | ✅ | ❌ | ❌ | ❌ | ✅ |
| CTO | ✅ | ✅ | ❌ | ❌ | ✅ |
| CodeReviewer | ✅ | ✅ | ✅ | ✅ | ❌ |
| KMPEngineer | ✅ | ❌ | ❌ | ✅ | ❌ |
| iOSEngineer | ✅ | ❌ | ❌ | ❌ | ❌ |
| BackendEngineer | ✅ | ❌ | ❌ | ❌ | ❌ |
| QAEngineer | ✅ | ✅ | ❌ | ✅ | ❌ |
| UXDesigner | ✅ | ❌ | ❌ | ❌ | ❌ |
| ResearchAgent | ✅ | ❌ | ❌ | ❌ | ✅ |

Матрица — паттерн: `superpowers` у всех (universal skills), спец-плагины адресно. **Этот паттерн мы уважаем** — наш paperclip-provisioner НЕ включает все плагины для всех агентов, а берёт matrix из `team-template.yaml` (§13.6).

### 13.6 Расширение `team-template.yaml` — plugin matrix

В шаблон каждой роли добавляется явный список плагинов:

```yaml
roles:
  - id: security-reviewer
    display_name: Security Reviewer
    cli: claude-code
    model: claude-opus-4-6
    mcp_endpoints:
      - palace
      - serena
      - github
      - context7
      - sequential-thinking
    plugins:
      - superpowers
      - pr-review-toolkit
      - code-review
      - voltagent-qa-sec
    subagent_preference:
      - voltagent-qa-sec:security-auditor
      - voltagent-qa-sec:penetration-tester
    budget_usd_per_run: 10
    # ...
```

### 13.7 Automatic settings.json installation — API-primary + file fallback

Паперклип выставляет API для **part** нашей работы (plugins/skills sync через endpoint'ы). Но **некоторые аспекты** конфигурации Claude Code workspace'ов живут только в файле `settings.json` и нет эквивалентного API. Поэтому paperclip-provisioner использует **двухуровневый подход**:

**Primary path (API):** после создания agent'а в Paperclip (§4.7 reconciler) —
```python
POST /api/agents/{id}/skills/sync
  body: { skills: role.plugins_as_skill_refs }

PATCH /api/agents/{id}/configuration
  body: { mcp_endpoints: [...], adapterConfig.model, budgetMonthlyCents, ... }
```

Это official путь. Не требует filesystem access к `~/.paperclip/`, работает даже когда наш контейнер не mount'ит `~/.paperclip/` как volume (remote-Paperclip сценарий).

**Fallback path (direct file write):** для того, что нельзя выразить через API:
```python
workspace_id = GET /api/agents/{id}/configuration -> .adapterConfig.workspaceId
path = ~/.paperclip/instances/default/workspaces/{workspace_id}/.claude/settings.json
existing = json.load(path) if path.exists() else {}
backup = ~/.claude/.palace-backup/<ts>/settings-{workspace_id}.json
atomic_copy(path, backup)                # safety net
merged = merge_user_managed(existing, build_settings_json(role))
atomic_write(path, merged)               # temp + rename
```

File write требует volume mount `~/.paperclip/` в наш контейнер (делается только в scenario A/B — full self-host). В remote-connect (`external` Paperclip где мы только API-клиент) — **fallback невозможен**, мы ограничиваемся тем что API позволяет.

**Merge strategy.** При merge:
- Наши managed keys имеют префикс `palace_*` (для opaque values) и annotation `"# managed-by-gimle-palace": true` в root-level comments (если формат поддерживает).
- User-managed keys (без префикса, без annotation) — **никогда** не трогаются.
- При конфликте (user вручную редактировал наш `palace_*` key) — пропускаем с warning'ом, не перезаписываем. Пользователь должен либо откатить своё изменение, либо удалить managed key полностью (и regenerate через `just re-provision`).

**Rollback.** При любых проблемах — `just palace-restore --timestamp <ts>` восстанавливает из `~/.claude/.palace-backup/`.

### 13.8 File structure добавления к пользовательскому setup

```
~/.paperclip/instances/default/workspaces/<workspace-id>/
├── .claude/
│   ├── settings.json         ← генерируется нашим provisioner из team-template
│   ├── mcp.json              ← merged: user's 9 MCPs + наш palace-mcp
│   └── agents/               ← linked to central ~/.claude/agents + our additions
└── (остальное — paperclip-owned)

~/.claude/                    ← global inventory пользователя
├── skills/                   ← existing 14+4 skills (не трогаем) + наш palace-skills
├── agents/                   ← existing 31 subagents (не трогаем) + наш palace-specific
├── mcp.json                  ← existing 9 MCPs + наш palace-mcp (merge, non-destructive)
└── settings.json             ← existing — не трогаем
```

**Idempotency guarantee:** повторный запуск `just install-skills` / paperclip-provisioner:
- детектит существующие managed entries по префиксу `palace_` в JSON keys → обновляет in-place
- user-managed entries остаются нетронутыми
- atomic write via `temp + rename`
- backup предыдущего состояния в `~/.claude/.palace-backup/<timestamp>/` на случай rollback

---

## 14. Testing Strategy

### 14.1 Unit tests

- Per-tool тесты в `palace-mcp` с моковым Graphiti клиентом (pytest).
- Телеметрия: формула `avoided_tokens_est` covered тестами на известных фикстурах.
- Provisioner: JSON Schema validation тесты на `project.yaml`, `team-template.yaml`.

### 14.2 Integration tests

- `make test-integration` поднимает весь compose stack в test-profile (маленький Neo4j, маленький test-repo в `tests/fixtures/mini-repo/`).
- End-to-end: `just ingest mini-repo-android` → assert все expected nodes в графе → вызов palace-mcp tools → assert returns нужный JSON.

### 14.3 Provisioner tests

- mock Paperclip REST API (WireMock в контейнере).
- Idempotency test: run provisioner дважды → assert только 1 set of entities.

### 14.4 E2E smoke

- После `just setup`: script ждёт 2 минуты, проверяет:
  - Все healthchecks green
  - `curl /stats` отвечает
  - `curl /install` возвращает 200 + valid shell script
  - Тестовый MCP tool call через `palace-mcp-client` SDK

### 14.5 Load test (nice-to-have, post-MVP)

- Симулированные 100 concurrent MCP queries против палаты с 100K узлов.
- Target: P95 latency < 500ms.

---

## 15. Infrastructure Decisions — Rationale

Почему именно Docker Compose + Justfile:

- **Universal (Linux/macOS/любая machine с Docker):** в отличие от sh-installer который зависит от distro/OS.
- **Portable:** `git clone` + `cp .env` + `just setup` = работает везде.
- **Idempotent + clean teardown:** `docker compose down -v` полностью вычищает.
- **Version pinning:** image tags в compose.yml фиксируют версии всех сервисов.
- **Совместим с существующим Paperclip:** external network `paperclip-agent-net` уже знакома.
- **Можно позже поднять в K8s через `kompose`** если понадобится scale.

**Rejected:** K8s (overkill single-server), Ansible (нужен только для OS-level provisioning, которого нет), Nix (входной барьер), curl-to-sh installer (хрупкий, плохо обновляется).

**Profiles via Docker Compose `profiles:` keyword** — each service declares list of profiles оно принадлежит (`profiles: [review, analyze, full]`). Compose'у пробрасывается `COMPOSE_PROFILES=<active-profile>` из `.env`. Это нативный mechanism, не требующий override файлов (кроме override когда пользователь идёт по custom-пути).

**Interactive installer: gum → whiptail → bash fallback chain.** Хорошо деградирует: на голом сервере без tooling всё равно работает через `read`. На dev-машине с `brew install gum` — красивый UI. Installer не требует Python/Node — single shell script, максимальная portability.

---

## 16. Open Questions / Future Work

- **Multi-tenant на уровне данных:** сейчас namespace'ы по проекту, но auth per-user не привязан к данным (`palace_events.user` логируется, но все users видят все projects). Если понадобится — добавить `:Project` → `:Team` edge и filtering в palace-mcp.
- **Non-Claude CLIs:** skills/subagents concept специфичен Claude Code. Для Codex/Gemini/Cursor — только MCP endpoints + documentation how to add them. Hardcode-free; но auto-install не делаем.
- **Cost caps realtime:** сейчас budget declared в `project.yaml`, но enforcement — на Paperclip. Может потребоваться middleware в palace-mcp для hard-cutoff по telemetry.
- **RAG-mode:** сейчас palace — structured KG. Может имеет смысл иметь ещё один MCP tool `rag_search(query, project)` который возвращает raw code chunks с embeddings (не graph). Будущая итерация.
- **Diff-aware context window для Claude:** вместо `get_iteration_diff` сделать tool который возвращает semantically relevant diff (только relevant к текущему query).
- ~~**Paperclip REST API: idempotent PUT семантика.**~~ **CLOSED (2026-04-15):** подтверждено через operational dossier (§Paperclip-operations): PUT-upsert-нет, agents создаются через `POST /api/companies/:id/agent-hires` с approval flow. Provisioner реализован как **reconciler** (§4.7). Удаление — `POST /api/agents/:id/terminate` (soft), не `DELETE`.

- **Approval flow автоматизация.** Новые agents hire'ятся в `status: pending_approval` до board approval. Если `GIMLE_AUTO_APPROVE_HIRES=false` (default — безопаснее), `just setup --yes` ≠ полностью автоматический setup: на этапе creation'а agent'ов нужен manual approve через Paperclip UI. Варианты: (a) документировать как limitation, (b) предоставить auto-approve режим через user-level API key с board scope, (c) реализовать polling/wait pattern в installer с heartbeat'ом "⏳ waiting for approvals". Default: (a) + опциональный (b) через `--auto-approve` флаг installer'а.

- **Agent API key одноразовая выдача.** `POST /api/agents/:id/keys` возвращает raw key **один раз**. При потере — новый ключ + revoke старого. Влияние: provisioner'у нужно безопасно сохранить raw key в `.env` в момент creation. Если `.env` потерян / удалён — регенерация через `just rotate-keys`.

- **Migration path `analyze` → `full`.** Если user стартанул в `analyze` и потом хочет включить Paperclip — что делать с already-created lite-orchestrator tasks? Сейчас: reconciler не мигрирует, lite-orchestrator продолжает работать для исторических задач, новые идут в Paperclip. Возможно нужно явное `just migrate-to-paperclip` действие.

- **Paperclip heartbeat disabled vs enabled.** Мы hire'им agents с `heartbeat.enabled=false` (только on-demand wake). Плюс — agents не кушают budget в простое. Минус — если agent должен делать что-то периодически (например QAEngineer мониторить PR'ы) — heartbeat нужен. Пока пользователь не попросит recurring background behavior — остаёмся на on-demand.

- **Paperclip embedded Postgres vs наш Neo4j coexistence.** Embedded Paperclip слушает `54329` на localhost, наш Neo4j `7687` на docker network. Port-конфликтов нет. Но embedded Paperclip'а creds hardcoded (`paperclip/paperclip`). Если наш stack и Paperclip делят machine — docker network isolation достаточна.

- **На macOS: LaunchAgent для Paperclip не всегда зарегистрирован.** На `imac-ssh.ant013.work` launchd plist лежит но `launchctl print` возвращает "not found". При перезагрузке Paperclip сам не поднимется. Это user-side issue, но в `just doctor` можем детектить и warnить. В embedded-mode нашего compose — не проблема, docker сам управляет lifecycle.
- **Alias learning для domain concepts (§5.4 axis 3).** "hex" / "hex string" / "hexadecimal" — должно маппиться в один концепт. Runtime — детектится через embedding similarity; offline — через LLM pass на начальном ingest. Механизм тюнинга коэффициентов — open.
- **Facet taxonomy версионирование.** Domain concepts / capabilities (axes 3 и 4) — это evolving vocabulary. При расширении taxonomy старые `:Iteration` facts могут оказаться под-классифицированы. Нужен реиндексатор в scheduler: при изменении `facet-taxonomy.yaml` — triggers selective re-classification.
- **Cross-project decisions propagation:** если `:Decision` в репо A применим к репо B (напр. общий паттерн безопасности) — сейчас manual копирование. Хотелось бы автодетект через domain concepts overlap.

---

## 17. Glossary

- **Memory palace** — overall система: storage + MCPs + retrieval layer.
- **palace-mcp** — основной MCP-сервер, агент-facing surface.
- **Extractor** — ingest-time role agent, пишет структурированные факты в palace.
- **Reviewer** — ongoing analyzer MCP, пишет `:Finding` узлы.
- **Iteration** — snapshot знаний палаты на конкретный commit.
- **Paperclip** — control plane (external product), оркеструет команду.
- **lite-orchestrator** — наш thin orchestrator на Python/asyncio, замена Paperclip в профилях `review`/`analyze`.
- **Subagent** — Claude Code feature: specialized helper, запускается как delegated task.
- **Skill** — Claude Code feature: reusable prompt playbook, автоматически активируется триггерами.
- **Fragment** — reusable Markdown-блок в `paperclips/fragments/*.md`, инжектится через `<!-- @include -->` маркеры в role prompts.
- **Auto-fragment** — наш концепт: fragment который **автоматически** добавляется во все generated AGENTS.md (напр. `@-mention-safety`).
- **Paperclip heartbeat** — периодический wake агента по timer'у (interval в seconds). Не путать с health-check docker-сервисов.
- **Wake-up** (Paperclip) — событие, приводящее к запуску heartbeat_run для агента. 4 source'а: `timer`, `assignment`, `automation` (включая `@-mentions`), `on_demand`.
- **heartbeat_run** (Paperclip) — одна итерация работы агента: 1 запуск Claude/Codex/Gemini CLI с контекстом issue + bundle.
- **Managed bundle** (Paperclip) — режим AGENTS.md когда Paperclip владеет файлом (запись через `PUT /api/agents/:id/instructions-bundle/file`). Альтернатива — `external` (Paperclip только читает).
- **Execution lock** (Paperclip) — атомарный захват issue одним агентом. Пока один активно работает, wake'ы для других идут в `status=skipped reason=issue_execution_locked` (кроме `issue_comment_mentioned` — тот bypass'ит).
- **Approval flow** (Paperclip) — board approval required для hire нового агента, смены config'а, и пр. Gate'ится в `approvals` таблице; gimle-installer документирует ограничение для fully-automated setup.
- **Reconciler** (наш) — provisioner-паттерн: list existing → compute diff vs desired → create/update/terminate. Заменяет "upsert" когда нет PUT-семантики.

---

## 18. Implementation Phases (preview — detailed plan будет в writing-plans skill)

**Phase 0 — Schema & scaffolding**
- Finalize JSON schemas for `project.yaml`, `team-template.yaml`, agent-role manifests, `installer/profiles/*.yaml`.
- `docker-compose.yml` скелет с compose-profiles matrix (§3.5).
- `installer/setup.sh` с gum/whiptail/bash-fallback chain (§3.6).
- `Justfile` shell (`setup`, `ingest`, `update`, `status`, `stats`, `down`, `uninstall`).
- Neo4j + Graphiti up, smoke test на `profile=review` (минимальная конфигурация).

**Phase 1 — Core MCPs**
- palace-mcp с read tools (search, find_*).
- palace-mcp write tools (record_*, create_paperclip_issue).
- Serena MCP wired in.
- Telemetry service.

**Phase 2 — Extractors + Reviewers**
- architecture-extractor + ui-component-extractor (highest-value).
- security-reviewer + deadcode-hunter.
- Report-writer role.

**Phase 3 — Provisioners**
- paperclip-provisioner with idempotent Company/Agent creation.
- skills-distributor + client install.sh.
- scheduler (cron + webhook).

**Phase 4 — First real ingest**
- `just ingest unstoppable-android` на реальном репо.
- End-to-end валидация + отчёт.

**Phase 5 — Expand**
- Остальные Unstoppable репо (14 kit-библиотек).
- blockchain-reviewer, duplication-detector, dependency-analyzer.
- Dashboard (Metabase profile).

Каждая phase — отдельный implementation plan через writing-plans skill.
