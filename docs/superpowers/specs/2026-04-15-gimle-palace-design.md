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

### 4.1 Neo4j Community 5.x

- Docker image: `neo4j:5-community`
- Persistent volume: `neo4j-data`
- Vector index plugin встроен (для hybrid retrieval из Graphiti)
- Лицензия: GPL v3 — **приемлемо** т.к. мы не distribut'им стек как продукт, это self-host tooling
- Plan B: FalkorDB (SSPL, Redis-based) — drop-in замена для тех, кому GPL неприемлема; переключается через env-флаг `GRAPH_BACKEND=neo4j|falkordb`

### 4.2 Graphiti service

- Python 3.11 FastAPI wrapper над `graphiti-core` library (getzep/graphiti)
- Выставляет:
  - Internal gRPC/HTTP для palace-mcp
  - Official Graphiti MCP server v1.0 на отдельном порту (для Paperclip-агентов которым удобнее прямой MCP)
- Embedding model: configurable — `text-embedding-3-large` по умолчанию, переопределяется ENV
- Entity extraction LLM: configurable — Claude Sonnet по умолчанию (cost/quality оптимум)

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
| `list_projects()` | каталог проектов |
| `get_project_overview(project)` | high-level summary |

Exposed tools (write):

| Tool | Назначение |
|---|---|
| `record_decision(project, scope, text, tags?)` | архитектурное решение |
| `record_finding(project, scope, severity, text, tags?)` | баг/уязвимость/anti-pattern |
| `record_iteration_note(project, text, tags?)` | свободная заметка из текущей работы |
| `create_paperclip_issue(project, title, description, role_hint?)` | ставит задачу сотруднику Paperclip |

Все tools возвращают `{ok: bool, data?: T, error?: string, meta: {latency_ms, tokens_est, avoided_tokens_est, event_id}}`.

### 4.4 Serena MCP

Standalone контейнер поверх official image. Конфигурируется через volume mount путей анализируемых репозиториев. Запускается в режиме `--transport streamable-http` на порту в `paperclip-agent-net`.

Serena покрывает **"живую" code navigation** — то что должно быть точным в моменте, через LSP: find-references, go-to-definition, call hierarchies. В отличие от palace который содержит **синтезированные** знания, Serena даёт структурную истину текущего кода.

### 4.5 Code-analyzer MCP family

Модульно: по одному MCP-серверу на домен. Это **специализированные reviewers**, которые запускаются Paperclip-агентами при ingest и при scheduled updates; результаты их работы пишутся в palace через `record_*`.

Roster v1:

| MCP | Что делает | Базовые инструменты |
|---|---|---|
| `security-reviewer-mcp` | OWASP/CWE checks, secret scanning, injection surfaces | semgrep, trufflehog, ручные checklist-promts |
| `blockchain-reviewer-mcp` | crypto-specific invariants (reentrancy, signature verification, nonce handling, key storage) | ручные checklist + slither-like rules адаптированные под mobile Kotlin/Swift |
| `deadcode-hunter-mcp` | unused symbols, unreachable code | через Serena `find_references` — если 0 references → flag |
| `duplication-detector-mcp` | copy-paste, near-duplicates | jscpd / simian через tool-wrapping + semantic dedup через embeddings |
| `dependency-analyzer-mcp` | 3rd-party libs + usage map | парсинг build файлов + cross-ref через Serena |

Каждый — отдельный контейнер с единым interface: `analyze_file(path) → findings[]`.

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

**paperclip-provisioner** — one-shot Python job, стартует после всего остального. Логика:
1. Читает все `projects/*.yaml` + `teams/*.yaml`.
2. Для каждого проекта резолвит какие role нужны (из project.yaml `reviewers:` list).
3. Идемпотентно создаёт в Paperclip через REST API: Company per project, Agents per role, linked к MCP endpoints из нашего сервера.
4. Stable IDs — hash от `<project>:<role>` — чтобы re-run не создавал дубликатов (PUT семантика).
5. **Пишет `~/.paperclip/instances/default/workspaces/<workspace-id>/.claude/settings.json`** с plugin matrix из `team-template.yaml` (§13.6, §13.7). Merges with user-managed keys non-destructively; backup предыдущего в `~/.claude/.palace-backup/`.
6. **Пишет `~/.paperclip/instances/default/workspaces/<workspace-id>/.claude/mcp.json`** — merged MCP list: global user MCPs (§13.1) + наш palace-mcp + role-specific MCPs из `team-template.roles[].mcp_endpoints`.

**scheduler** — APScheduler внутри контейнера. Для каждого проекта из `projects/*.yaml`:
- Если `trigger: cron` → запускает по cron spec.
- Если `trigger: webhook` → слушает `POST /webhook/<project>/push` (GitHub/GitLab webhook).
- На срабатывании: `git fetch && git diff --name-only HEAD@{1} HEAD` → запускает incremental re-ingest только по затронутым файлам (Paperclip task).

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
| `:Iteration` | number, started_at, ended_at, commit_sha | Marker итераций |

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
| **Domain concept** (о чём) | `:HandlesHex`, `:HandlesData`, `:HandlesAddress`, `:HandlesCrypto`, `:HandlesChain`, `:HandlesToken`, `:HandlesAmount`, `:HandlesUnit`, `:HandlesTime`, `:HandlesCurrency` |
| **Capability** (что умеет) | `:Encodes`, `:Decodes`, `:Validates`, `:Formats`, `:Signs`, `:Hashes`, `:Parses`, `:Fetches`, `:Caches`, `:Transforms`, `:Renders` |

Пример узла метода `ByteArray.toHexString()`:
```
labels: [:Method :Extension :Utility :HandlesHex :HandlesData :Encodes]
properties: {name, signature, path, line, usage_count, last_used_iteration}
```

**Composite indexes** по парам (label, property) — O(log n) query по пересечениям осей.

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

Шаблон команды в Paperclip для данного **класса** проектов (т.е. один template может использоваться для нескольких project.yaml).

```yaml
# teams/mobile-blockchain-default.yaml
name: Mobile Blockchain Default Team
applies_to_tags: [mobile, blockchain]

roles:
  - id: architect
    display_name: Architecture Extractor
    prompt_template: |
      You are an architecture extractor. Using Serena MCP for navigation and palace-mcp
      for recording, map modules, layers, and dependencies in {project.name}. Record
      as :Module and :DEPENDS_ON. Use tags: [{project.tags}].
    cli: claude-code          # claude-code | codex | gemini | opencode
    model: claude-opus-4-6
    mcp_endpoints: [palace, serena]
    budget_usd_per_run: 5

  - id: ui-extractor
    display_name: UI Component Extractor
    prompt_template: |
      Extract UI components (buttons, screens, cards) from {project.name}. Classify by
      `kind`. Count usages via Serena `find_references`. Record as :UIComponent with
      :USED_BY edges.
    cli: claude-code
    model: claude-sonnet-4-6
    mcp_endpoints: [palace, serena]
    budget_usd_per_run: 3

  - id: security-reviewer
    display_name: Security Reviewer
    prompt_template: |
      Run security-reviewer-mcp against {project.name}. Focus on: key storage,
      crypto usage, network requests, WebView configurations, deep link handling.
      Record findings as :Finding with severity.
    cli: claude-code
    model: claude-opus-4-6    # Opus for security
    mcp_endpoints: [palace, serena, security-reviewer]
    budget_usd_per_run: 10

  # ... etc для blockchain-reviewer, deadcode-hunter, etc.
```

Paperclip-provisioner при запуске резолвит `project.yaml.reviewers` + `project.yaml.extractors` через template matching и создаёт соответствующие Agents в Paperclip.

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

`just stats --explain` выводит эту формулу + per-tool вклад в общий saved tokens — полная прозрачность.

### 8.3 Dashboard поверх (optional)

Через compose profile `with-dashboard` добавляется **Metabase** pointed на SQLite. Out-of-scope для MVP.

---

## 9. Security & Secrets

### 9.1 Secret surface

| Секрет | Где хранится |
|---|---|
| `ANTHROPIC_API_KEY` | `.env` (gitignored) или sops-encrypted `.env.sops.yaml` |
| `OPENAI_API_KEY` | same |
| `PAPERCLIP_API_KEY` | same |
| `GITHUB_TOKEN` (доступ к private репо) | same |
| `NEO4J_PASSWORD` | `.env`, rotated через `just rotate-neo4j` |
| `TELEMETRY_HASH_SALT` | `.env` (для обезличивания args в логах) |

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

## 10. Ingest Pipeline (first-time)

Команда: `just ingest <project-slug>`.

Workflow:

1. Validate `projects/<slug>.yaml`.
2. Clone/sync repo into server volume `repos/<slug>`.
3. **Serena warm-up:** startup Serena с указанным репо, первичная индексация LSP (~20-120 сек в зависимости от размера).
4. **Paperclip task creation:** создаёт tasks для каждого extractor из team-template. Tasks runs в параллель с budget limits.
5. Extractors пишут в palace через palace-mcp `record_*` tools. Graphiti constructs KG.
6. **Reviewers pass** (опционально, если включены в `reviewers:`). Пишут `:Finding` узлы.
7. **Report generation:** последний Paperclip task — `report-writer` агент читает palace + findings + generates **markdown-отчёт 10-20 страниц** в `reports/<slug>/<iteration>.md`. Содержимое:
   - Architecture overview (с diagram в mermaid)
   - UI components catalogue
   - API surface
   - Dependencies
   - Critical findings (severity=high)
   - Non-critical findings
   - Dead code hotspots
   - Duplication hotspots
   - Recommendations
8. `:Iteration` node создаётся/обновляется с commit_sha + ended_at.
9. Telemetry записывает `ingest_completed` event.

Idempotency: повторный `just ingest` на том же commit SHA → no-op (детектируется через `:Iteration.commit_sha`).

---

## 11. Scheduled Update Flow

Команда `scheduler` внутри контейнера. Два источника триггеров:

### 11.1 Cron-режим

Для каждого `projects/*.yaml` с `trigger.kind: cron` — APScheduler job.

Logic per job:
```
fetch_latest(repo)
if head_sha == last_ingested_sha: return  # ничего нового
changed_files = git diff --name-only last_ingested_sha..HEAD
new_iteration = current + 1
run_incremental_extractors(changed_files, iteration=new_iteration)
run_incremental_reviewers(changed_files)
update_or_invalidate_graph_nodes(changed_files, iteration=new_iteration)
generate_delta_report(iteration=new_iteration)
update project.yaml with new iteration number (commit to git)
```

Incremental ingest в 10-100× дешевле полного (по количеству touched files).

### 11.2 Webhook-режим

`POST /webhook/<project>/push` принимает GitHub/GitLab payload, verifies secret, enqueues same incremental pipeline.

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

### 13.7 Automatic settings.json installation

**paperclip-provisioner** (§4.7) расширяется: после создания Agent'а в Paperclip он также пишет `~/.paperclip/instances/default/workspaces/<workspace-id>/.claude/settings.json` с plugin matrix из `team-template.yaml`.

Алгоритм:
```
for project in projects/*.yaml:
  company = paperclip.put_company(project.slug)
  for role in resolve_roles(project, team_template):
    agent = paperclip.put_agent(company, role)
    workspace_id = agent.workspace_id
    path = ~/.paperclip/instances/default/workspaces/{workspace_id}/.claude/settings.json
    settings = build_settings_json(role)   # plugins enabled, mcp_endpoints, subagent prefs
    atomic_write(path, settings)            # write via temp + rename for idempotency
```

Чтобы команды разных агентов не конфликтовали — каждый settings.json генерируется свежим, но **мы сохраняем user overrides** через механизм: перед перезаписью читаем существующий файл, merge'им наши managed keys с user-managed keys (user-managed область помечена комментарием `# managed by user, do not touch`).

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
- **Paperclip REST API: idempotent PUT семантика.** Наш provisioner предполагает что Paperclip поддерживает upsert по stable IDs. Если в реальности только POST/create — нужен reconciler cycle (list → diff → create/update/delete) вместо голого PUT. Проверить при первой интеграции.
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
- **Subagent** — Claude Code feature: specialized helper, запускается как delegated task.
- **Skill** — Claude Code feature: reusable prompt playbook, автоматически активируется триггерами.

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
