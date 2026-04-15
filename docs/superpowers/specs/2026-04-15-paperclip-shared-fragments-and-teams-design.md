# Paperclip Shared Fragments + Team Composition — Design Specification

**Document date:** 2026-04-15
**Status:** Draft · awaiting user review
**Author:** brainstorming session (Claude Opus 4.6 + Anton Stavnichiy)
**Related:**
- `2026-04-15-paperclip-operations.md` — runbook по инфраструктуре Paperclip на iMac
- `2026-04-15-gimle-palace-design.md` — дизайн самого Gimle-Palace продукта (control plane для team)
- `Medic/docs/paperclip-operations.md` (equivalent в Medic репо)

**Repos (created 2026-04-15):**
- [`github.com/ant013/paperclip-shared-fragments`](https://github.com/ant013/paperclip-shared-fragments) — shared fragments + templates + research + tooling (public, 1 commit scaffold)
- [`github.com/ant013/Gimle-Palace`](https://github.com/ant013/Gimle-Palace) — memory palace продукт + его paperclip-команда (public, 13 commits, spec complete)

---

## 1. Контекст и проблема

### 1.1 Ситуация

У нас уже работает Paperclip AI на `imac-ssh.ant013.work` (`paperclip.ant013.work` публично), там три компании:

| Company | ID | Команда | Статус |
|---|---|---|---|
| Medic (old) | `1593f659...` | 0 агентов | archived |
| **Medic (active)** | `7c094d21-a02d-4554-8f35-730bf25ea492` | 9 агентов (CEO, CTO, 3 инженера, reviewer, QA, research, designer) | active, работает |
| **Gimle** | `9d8f432c-ff7d-4e3a-bbe3-3cd355f73b64` | 1 агент (CEO), пусто | active, ждёт наполнения |

Medic-команда была собрана в спешке. За одну сессию нашли и починили три бага paperclip-механики @-mention handoff'а (см. §6 в `paperclip-operations.md`), и написали дисциплинарные правила в `Medic/paperclips/fragments/heartbeat-discipline.md`.

### 1.2 Проблема

**Paperclip-механика универсальна.** Правила про @-mention format, wake-up triggers, worktree discipline, PATCH vs POST wake asymmetry — не имеют отношения к домену проекта. Но сейчас они живут только в `/Users/Shared/Ios/Medic/paperclips/fragments/` (server canonical — локальная копия у Anton'а отстаёт до старого плоского `agents/` layout). Как только Gimle-команда начнёт работать, надо либо:

- **Скопировать** fragments из Medic в Gimle — гарантированно разойдётся при следующем baga-фиксе, реальные инциденты будут.
- **Сделать symlink** — не travel'ится в git, доступно только на iMac.
- **Вынести в submodule** — правильное решение, один source of truth, все проекты подтягивают.

Параллельно мы заметили что **роль-templates** (CEO, CTO, engineer, reviewer, etc.) тоже содержат много повторяющегося — patterns типа "CEO hires new agents via paperclip-create-agent skill", "CTO never codes", "Reviewer uses CRITICAL/WARNING/NOTE format". Сейчас это разбросано по индивидуальным role-файлам Medic. При создании Gimle-команды мы снова либо скопируем, либо вынесем.

**Дополнительный константин** — выявленный в этой же сессии — **размер AGENTS.md напрямую бьёт по токен-бюджету каждого wake'а**. Значит стратегия "@-include всё подряд" недопустима. Надо per-role селективное включение + hard token budget.

### 1.3 Цели документа

Зафиксировать:
1. Архитектуру нового `paperclip-shared-fragments` репо.
2. Классификацию: что выносится в shared, что остаётся project-local.
3. Token-budget политику с hard лимитами.
4. Team composition для Gimle (11 ролей) и reserve для будущего (Unstoppable Wallet).
5. Research-процесс на обогащение templates из community-плагинов + domain-refs.
6. Bootstrap flow нового проекта и migration flow существующего (Medic).

### 1.4 Не-цели

- Не переписываем paperclip — апстрим фиксы для @-mention regex отдельная задача.
- Не делаем полный инструментарий для любого agent-framework (Letta/AutoGen/AutoGPT) — фокус на Paperclip AI.
- Не проектируем сам Gimle-Palace продукт — у него свой spec `2026-04-15-gimle-palace-design.md`.

---

## 2. Архитектура

### 2.1 Структура репозиториев

```
┌──────────────────────────────────────────────────────────────┐
│  github.com/ant013/paperclip-shared-fragments                │
│  (single source of truth)                                     │
│                                                                │
│  ├── fragments/          — atomic @include blocks              │
│  ├── templates/          — role skeletons                      │
│  │   ├── management/     — CEO, CTO                            │
│  │   ├── engineers/      — 9 engineering archetypes            │
│  │   ├── quality/        — 6 reviewer personalities + QA       │
│  │   └── support/        — research, UX, technical writer      │
│  ├── research/           — per-role domain best practices      │
│  │   └── role-patterns/                                        │
│  ├── build.sh            — awk preprocessor (include resolver) │
│  ├── bootstrap-new-project.sh                                  │
│  ├── CONVENTIONS.md      — token budget + include rules        │
│  └── README.md                                                 │
└──────────────────────────────────────────────────────────────┘
           │
           │ git submodule
           ├────────────────────────────────┐
           ▼                                ▼
┌───────────────────────────┐   ┌───────────────────────────┐
│  Medic/paperclips/        │   │  Gimle-Palace/paperclips/ │
│                           │   │                           │
│  fragments/               │   │  fragments/               │
│   ├── shared/ [submodule] │   │   ├── shared/ [submodule] │
│   └── local/              │   │   └── local/              │
│      └── <medic-specific> │   │      └── <gimle-specific> │
│  roles/                   │   │  roles/                   │
│   ├── ceo.md              │   │   ├── ceo.md              │
│   ├── cto.md              │   │   ├── cto.md              │
│   └── ...                 │   │   └── ...                 │
│  dist/                    │   │  dist/                    │
│  build.sh → shared/.../   │   │  build.sh → shared/.../   │
└───────────────────────────┘   └───────────────────────────┘
```

### 2.2 Роли путей

| Путь | Кто владеет | Что там |
|---|---|---|
| `paperclip-shared-fragments/` | Anton (root) | Универсальное: paperclip-механика, шаблоны ролей, research |
| `<project>/paperclips/fragments/shared/` | submodule | read-only, синкается с shared репо |
| `<project>/paperclips/fragments/local/` | проект | Проект-специфичные fragments (которые не universal) |
| `<project>/paperclips/roles/` | проект | Роли проекта (копии templates + правка) |
| `<project>/paperclips/dist/` | build.sh | Скомпилированный output для AGENTS.md |
| `~/.paperclip/.../companies/<c>/agents/<a>/instructions/AGENTS.md` | paperclip | Live bundle — что агент реально читает |

### 2.3 Build pipeline

```
  local/*.md   shared/*.md    roles/*.md
       \          |          /
        \         |         /
         v        v        v
      ┌──────────────────────┐
      │     build.sh (awk)    │
      │  resolves @include    │
      │  markers in roles/    │
      └──────────────────────┘
                 │
                 ▼
            dist/*.md  ─── manual copy / API PUT ───▶  live AGENTS.md
```

Синтаксис @include:
```markdown
<!-- @include fragments/shared/heartbeat-discipline.md -->
<!-- @include fragments/local/medic-specific-testing.md -->
```

build.sh (расширенная версия текущей, резолвит оба пути):
```bash
for role_file in roles/*.md; do
  awk -v frag_dir="$SCRIPT_DIR" '
    /<!-- @include fragments\/.*\.md -->/ {
      match($0, /fragments\/[^ ]+\.md/)
      path = frag_dir "/" substr($0, RSTART, RLENGTH)
      while ((getline line < path) > 0) print line
      close(path); next
    }
    { print }
  ' "$role_file" > "dist/$(basename $role_file)"
done
```

---

## 3. Классификация: что выносить, что оставлять

Пять категорий, решение для каждой.

### 3.1 Категория A — чистые shared fragments (existing)

Уже в `Medic/paperclips/fragments/`. Переносятся **как есть** в `shared/fragments/`:

| Fragment | Размер | Что внутри | Shared? |
|---|---|---|---|
| `heartbeat-discipline.md` | ~1200 tok | Три-шаговый wake-check + запрет memory-между-сессиями + три anti-@-mention правила (rename / punctuation / handoff) | **100%** |
| `worktree-discipline.md` | ~200 tok | Paperclip worktree поведение | **100%** |
| `pre-work-discovery.md` | ~300 tok | Методология "не дубликат ли фича": git log / gh pr list / serena / docs / issues | **100%** |
| `language.md` | ~80 tok | Русский в UI, английский в коде | **100%** (user-preference) |
| `git-workflow.md` | ~200 tok | Feature branch, PR в develop, no force push, rebase pre-PR | **95%** — «develop» одна строка специфична, но почти всегда верна |

### 3.2 Категория B — новые shared fragments (извлекаем из ролей)

Извлекаются из существующих `Medic/paperclips/roles/*.md`, новые файлы в `shared/fragments/`:

| Новый fragment | Откуда извлечь | Размер target | Что содержит |
|---|---|---|---|
| `ceo-hiring-workflow.md` | ceo.md L70-85 | ~400 tok | 6-шаговая процедура найма (create-agent skill → read dist → write AGENTS.md → chainOfCommand → первая задача) |
| `cto-no-code-ban.md` | cto.md L10-25 | ~300 tok | "CTO не редактирует, не коммитит, не запускает gradle/npm. Write-tools запрещены" |
| `escalation-blocked.md` | cto.md L27-35 | ~200 tok | Паттерн "нет свободного инженера → blocked → @Board → жди" |
| `adversarial-review.md` | code-reviewer.md L11-17 | ~300 tok | Red Team mindset: assume broken, конкретика не "looks good", CLAUDE.md mечанически, без поблажек |
| `review-report-format.md` | code-reviewer.md L82-99 | ~250 tok | Markdown шаблон: Summary / Findings (CRITICAL/WARNING/NOTE) / Compliance / Verdict |
| `qa-skeptic.md` | qa-engineer.md L10-16 | ~200 tok | "Не доверяй проверяй, edge cases, cross-platform, regression first" |
| `edge-cases-matrix-base.md` | qa-engineer.md L33-43 | ~300 tok | Универсальные категории edge cases (strings/numbers/dates/collections/offline/concurrent/auth) |
| `research-output-format.md` | research-agent.md L47-66 | ~300 tok | Markdown Research-отчёт (Контекст / Findings / Сравнение / Рекомендация / Источники) |
| `research-principles.md` | research-agent.md L20-26 | ~200 tok | "Факты не мнения, с источниками, версионность, actionable" |
| `verification-gates.md` | cto.md L45-53 | ~200 tok | Паттерн "задача не закрыта без CodeReviewer + QA + build sign-off" |

**Итого:** 15 fragments (5 existing + 10 new), общий footprint ~3000-4000 tokens если роль включает всё. Реально роль не включает всё — только нужное (см. §4).

### 3.3 Категория C — role templates

Живут в `shared/templates/`. Скелеты с placeholder'ами. **Копируются** в проект-ные `<project>/paperclips/roles/` при bootstrap'е и правятся под проект.

Структура:

```
templates/
├── management/
│   ├── ceo.md                     ← shared — hiring workflow + Board-interface
│   └── cto.md                     ← shared — no-code-ban + delegation + verification-gates
├── engineers/
│   ├── engineer-generic.md        ← универсальный каркас (paths / MCP / subagents / @includes)
│   ├── kmp-engineer.md            ← KMP shared + Android Compose (Medic-flavored)
│   ├── ios-engineer.md            ← SwiftUI + bridges + XCFramework (Medic-flavored)
│   ├── backend-engineer.md        ← Supabase/Postgres/Edge Functions (Medic-flavored)
│   ├── python-engineer.md         ← NEW — FastAPI/asyncio/pytest (Gimle)
│   ├── mcp-engineer.md            ← NEW — MCP protocol specialist (Gimle)
│   ├── infra-engineer.md          ← NEW — Docker/compose/justfile/networking
│   ├── blockchain-engineer.md     ← NEW — wallet-client + smart-contract patterns
│   └── mobile-developer.md        ← NEW — RN/Flutter/native generalist (альтернатива KMP+iOS split)
├── quality/
│   ├── code-reviewer.md           ← coordinator generalist
│   ├── bug-hunter.md              ← NEW — correctness/edge/silent-failures
│   ├── security-auditor.md        ← NEW — attack surface + per-project plugin matrix
│   ├── privacy-auditor.md         ← NEW — PII/GDPR/HIPAA
│   ├── performance-engineer.md    ← NEW — metrics + leaks (memory/coroutine/cpu)
│   ├── architecture-reviewer.md   ← NEW — macro design cross-PR
│   └── qa-engineer.md             ← test methodology
└── support/
    ├── research-agent.md
    ├── ux-designer.md
    └── technical-writer.md        ← NEW — product docs / install guides / runbooks
```

**Итого:** 21 template (2 management + 9 engineers + 7 quality + 3 support). На старте все существовать не обязаны — создаём по мере появления первого потребителя. Medic сейчас использует 9, Gimle будет использовать 11, пересечение — 5 (ceo, cto, code-reviewer, qa-engineer, research-agent).

### 3.4 Категория D — project-specific (остаётся локально)

**НЕ** переносятся в shared. Живут в `<project>/paperclips/roles/<role>.md` или `<project>/paperclips/fragments/local/`:

- Product knowledge (CEO знает Kit/PillBox для Medic, Graphiti/MCP для Gimle)
- Roadmap, метрики, KPI
- Delegation map (какие роли есть в проекте)
- Paths в зоне ответственности (/shared/commonMain/..., /server/supabase/...)
- CLAUDE.md compliance checklist (опирается на проектный CLAUDE.md)
- Конкретные MCP/Subagents/Skills комбинации (Medic: supabase+figma; Gimle: neo4j+graphiti)
- Figma-ссылки, Linear-prefix, repo-URL

### 3.5 Категория E — инфраструктура репо

| Файл | Назначение |
|---|---|
| `build.sh` | awk-препроцессор (shared + local path resolution) |
| `bootstrap-new-project.sh` | Scaffold нового проекта: создать `paperclips/{roles,fragments/local,dist}`, добавить submodule, скопировать стартовые templates, первый commit |
| `README.md` | Главный layout, consumers, how to use |
| `CONVENTIONS.md` | Token budget policy + selective @include правила + code style |

---

## 4. Token-budget discipline

Критическая метрика — размер `AGENTS.md` влияет на каждый wake агента.

### 4.1 Hard limits

| Артефакт | Бюджет (tokens) | Способ контроля |
|---|---|---|
| Один fragment | ≤500 (large), ≤1200 (heartbeat-discipline только) | Tables>prose, без filler'ов, ссылки вместо inline-checklists |
| Role body (без fragments) | ≤2000 | Только role-specific, без общих дисциплин |
| Полный AGENTS.md (body + fragments) | **≤8000** | Селективный @include (см. §4.2) |
| Research нотсы | без лимита | **НЕ** грузятся в AGENTS.md, читаются по запросу |
| Template skeletons | ≤2000 | Это scaffold, не финал |

### 4.2 Селективный @include mapping

**Не все fragments всем ролям.** Таблица максимальной селективности:

| Роль | Обязательные @include | Запрещённые (НЕ включать) |
|---|---|---|
| CEO | heartbeat, language, git-workflow, ceo-hiring-workflow, pre-work-discovery | worktree (не редактирует), adversarial-review (делегирует reviewer'ам), research-* |
| CTO | heartbeat, language, git-workflow, pre-work, cto-no-code-ban, escalation, verification-gates | worktree (не коммитит), adversarial-review (делегирует reviewer'ам) |
| Engineer (любой) | heartbeat, language, git-workflow, pre-work, worktree, escalation | adversarial-review, research-*, ceo-hiring, cto-no-code-ban |
| Reviewer (любой) | heartbeat, language, git-workflow, adversarial-review, review-report-format | pre-work (чужая работа), worktree, escalation, research-* |
| QAEngineer | heartbeat, language, git-workflow, worktree, qa-skeptic, edge-cases-matrix-base | adversarial-review (делает reviewer), cto-no-code-ban |
| BugHunter | heartbeat, language, git-workflow, adversarial-review, review-report-format, qa-skeptic, edge-cases-matrix-base | worktree (чужой worktree), pre-work |
| ResearchAgent | heartbeat, language, git-workflow, research-principles, research-output-format | worktree, pre-work, adversarial, verification-gates |
| TechnicalWriter | heartbeat, language, git-workflow | всё остальное не нужно |
| UXDesigner | heartbeat, language, git-workflow | всё остальное не нужно |

**Пример реального расчёта для CTO (измерено):** role body 1182 + fragments (heartbeat 1323 + language 53 + git-workflow 191 + pre-work 204 + worktree 225) = **3178 tokens теоретически**. Живой AGENTS.md = 3085 tokens (очень близко, разница — вариативность tokenization на границах склейки). **В бюджет 8000 — 61% headroom.**

**Расчёт для Reviewer (5 fragments, новые + существующие):**
- role body (code-reviewer current) 1485 + heartbeat 1323 + language 53 + git-workflow 191 + adversarial-review ~300 (новый B) + review-report-format ~250 (новый B) = **~3600 tokens**

**BugHunter (7 fragments)** ~ 2000 body + 1323+53+191+300+250+200+300 = **~4617 tokens** — всё ещё в бюджет.

**Худший случай — CEO** после migration: 1484 body + 53+191+400 (ceo-hiring-workflow новый) + 1323 (heartbeat) = **~3451 tokens**. В бюджет.

### 4.3 On-demand content (НЕ в AGENTS.md)

Большие вещи вынесены "на полку":

| Content | Где живёт | Когда читается |
|---|---|---|
| Research-нотсы per role | `shared/research/role-patterns/<role>.md` | Агент сам читает через filesystem MCP когда углубляется |
| Full OWASP Top 10 / CWE entries | URL-ссылки в fragment'е | По запросу через context7 / tavily MCP |
| Большие примеры кода | URL в репо или `docs/examples/` | По запросу |
| Compliance полные checklists (HIPAA, GDPR) | URL | По запросу |
| Domain deep-dumps (blockchain RPC patterns) | `shared/research/role-patterns/blockchain-engineer.md` | Blockchain-engineer читает когда нужно |

### 4.4 Мониторинг бюджета

В `CONVENTIONS.md` зафиксировать:
- pre-commit hook в shared репо: `wc -w fragments/*.md` — если > лимит, fail
- `build.sh` при сборке проверяет размер `dist/*.md`, warn если > 8000 tok
- Периодический аудит (раз в месяц): `ls -la ~/.paperclip/.../AGENTS.md` + tokencount

---

## 5. Research-процесс (обогащение templates)

Templates из головы = отражают только текущий опыт автора. Нужен systematic research на community-wisdom + domain-best-practices.

### 5.1 Три фазы

**Фаза 1 — Mining existing plugins** (быстро, высокий сигнал)

**Два корпуса на сервере imac-ssh.ant013.work** (user: `anton`):

| # | Путь | Content | Размер |
|---|---|---|---|
| A | `~/.claude/plugins/marketplaces/voltagent-subagents/categories/*/agents/*.md` | 10 мета-плагинов, 150 agents — `voltagent-core-dev` (11), `voltagent-lang` (29), `voltagent-infra` (16), `voltagent-qa-sec` (15), `voltagent-domains` (12), `voltagent-meta` (9), `voltagent-data-ai`, `voltagent-biz`, `voltagent-dev-exp`, `voltagent-research` | ~150 prompt files |
| B | `~/claude-agents/plugins/*/{agents,skills}/*.md` | Seth Hobson's claude-code-workflows — 76 плагинов, 182 agents, 147 skills — включая `blockchain-web3`, `frontend-mobile-security`, `comprehensive-review`, `llm-application-dev`, `reverse-engineering`, etc. | ~330 prompt files |

**Итого корпус для mining'а:** ~480 готовых community-промптов.

Процесс:
1. Читаем `plugin.json` + `agents/*.md` + `skills/*.md` из обоих корпусов
2. Для каждого плагина извлекаем: name, category, MCP-конвенции, ключевые правила роли, output-форматы, anti-patterns
3. Deliverable: `shared/research/plugin-prompt-mining.md` — таблица «плагин → роль → ключевые правила / MCP / skills / anti-patterns», сгруппированная по category (security / engineer / review / domain / …)
4. Оценка: ~3-4 часа работы параллельных subagent'ов, результат = high-density reference для фазы 2

**Фаза 2 — Per-role deep research** (параллельно)

Спавним 10 параллельных research-задач через `superpowers:dispatching-parallel-agents`, по одной на крупную роль. Каждая produce:

`shared/research/role-patterns/<role>.md`:
- TL;DR — что роль делает
- Domain knowledge — 5-10 ключевых концепций с источниками
- Checklist that this role uses механически
- Common pitfalls / blind spots
- Output format (пример реального отчёта)
- Tooling recommendations (MCP + subagents + skills + external refs)
- Escalation triggers

Приоритетные 10 ролей:
1. `security-auditor` (OWASP ASVS, Top 10, Mobile Top 10, SANS Top 25)
2. `privacy-auditor` (GDPR articles 5/25/32, HIPAA Security Rule, NIST Privacy Framework)
3. `performance-engineer` (Brendan Gregg USE method, Google SRE book, profiling methodologies)
4. `bug-hunter` (Chaos engineering, property-based testing, silent failure patterns)
5. `architecture-reviewer` (C4 model, ADR template, SOLID/DDD references)
6. `code-reviewer` (Code review best practices, Google engineering practices)
7. `blockchain-engineer` (BIP-32/39/44, EIP-712, SLIP-0010, SWC registry, wallet-client patterns)
8. `mcp-engineer` (MCP spec modelcontextprotocol.io, tool-design patterns, Anthropic agent docs)
9. `python-engineer` (FastAPI best practices, Hypothesis, pytest fixtures, asyncio pitfalls)
10. `infra-engineer` (Docker compose v2 spec, 12-factor app, Justfile patterns, healthcheck design)

Остальные 9 ролей (ceo, cto, kmp, ios, backend, qa, research, ux, technical-writer, mobile-developer) — light research, 1 на каждую, можно сделать inline во время написания template'а.

**Фаза 3 — Synthesis → templates**

После фаз 1+2:
- Plugin mining reference
- 10 deep research-нотсов

Пишем templates. Каждый опирается на mining + research-ноты. Templates становятся обоснованными («потому что OWASP ASVS §X», «по паттерну Y в community plugin Z»), не из головы.

Deliverable: 21 `templates/*.md` (по §3.3 подпапкам: management/2, engineers/9, quality/7, support/3).

### 5.2 Где хранятся research-нотсы

В `shared/research/role-patterns/` — рядом с templates, не в проектах. Потому что research → informs → templates — единый source of truth.

Research **не грузится в AGENTS.md** (см. §4.3). Агент читает по запросу через filesystem MCP:
```
# SecurityAuditor в своём run'е, если нужно углубиться:
Read shared/research/role-patterns/security-auditor.md
```

### 5.3 Триггер обновления research

- Новый bug в paperclip-механике → обновить `shared/fragments/heartbeat-discipline.md` (уже работает)
- Новая роль → сначала research, потом template
- Major version плагина изменился → retrigger mining
- Новая OWASP Top 10 версия / HIPAA update → частичное обновление security/privacy research

---

## 6. Team composition

### 6.1 Medic — существующая команда (9 ролей)

Без изменений. После migration'а (см. §8) роли продолжают работать, только fragments идут из submodule.

| Role | Template источник | Agent ID |
|---|---|---|
| CEO | `management/ceo.md` | `419d56ec...` |
| CTO | `management/cto.md` | `780ec10f...` |
| KMPEngineer | `engineers/kmp-engineer.md` | `1222c2f7...` |
| iOSEngineer | `engineers/ios-engineer.md` | `c47eb69e...` |
| BackendEngineer | `engineers/backend-engineer.md` | `cdf1455f...` |
| CodeReviewer | `quality/code-reviewer.md` | `cf52c981...` |
| QAEngineer | `quality/qa-engineer.md` | `1f65199b...` |
| ResearchAgent | `support/research-agent.md` | `5085cd02...` |
| UXDesigner | `support/ux-designer.md` | `20b806a1...` |

### 6.2 Gimle — новая команда (11 ролей)

Новая компания `9d8f432c...`. CEO уже нанят (default при создании company). Остальные 10 — нанимаются CEO'м через `paperclip-create-agent` skill.

| # | Role (в paperclip) | Template | Ответственность |
|---|---|---|---|
| 1 | CEO | `management/ceo.md` | Board-interface, приоритизация, hiring, roadmap |
| 2 | CTO | `management/cto.md` | Техническая стратегия, decomposition, verification-gates (не пишет код) |
| 3 | **BlockchainEngineer** | `engineers/blockchain-engineer.md` | Wallet-client architecture expertise; advises MCP-analyzer design for crypto code |
| 4 | PythonEngineer | `engineers/python-engineer.md` | Graphiti service, extractors, telemetry, lite-orchestrator, scheduler |
| 5 | MCPEngineer | `engineers/mcp-engineer.md` | palace-mcp, code-analyzer MCPs, Serena integration, client distribution |
| 6 | InfraEngineer | `engineers/infra-engineer.md` | Docker Compose, Justfile, install scripts, networking, secrets, healthchecks |
| 7 | CodeReviewer | `quality/code-reviewer.md` | Coordinator generalist — synthesizes review from other specialists |
| 8 | **SecurityAuditor** (enhanced) | `quality/security-auditor.md` + `blockchain-web3` + `frontend-mobile-security` plugins | Wallet attack surface + MCP exposure surface + secrets/supply chain |
| 9 | QAEngineer | `quality/qa-engineer.md` | Integration tests across docker profiles (review/analyze/full), pytest+testcontainers, Unstoppable real-repo test |
| 10 | TechnicalWriter | `support/technical-writer.md` | README, install guides (per profile × topology), operational runbooks, demo scripts |
| 11 | ResearchAgent | `support/research-agent.md` | Graphiti/mem0/Letta landscape evolution, MCP spec updates, blockchain-client patterns research |

**Опциональное расширение** (добавить если один CodeReviewer не справляется):
- BugHunter, PerformanceEngineer, ArchitectureReviewer, PrivacyAuditor — от review team full

### 6.3 Gimle — что НЕ берём (vs Medic)

- KMPEngineer, iOSEngineer, BackendEngineer (mobile) — нет мобилок, нет Supabase
- UXDesigner — нет UI (только CLI и MCP; control plane UI делает Paperclip)
- PrivacyAuditor — внутренний dev-инструмент, PII отсутствует

### 6.4 Резерв — будущие команды

**Unstoppable Wallet** (если решим вынести в свою paperclip-компанию):
- management: CEO, CTO
- engineers: KMPEngineer, iOSEngineer, **BlockchainEngineer**
- quality: CodeReviewer, SecurityAuditor (с blockchain+mobile плагинами), QAEngineer
- support: ResearchAgent, UXDesigner

Все templates **уже будут** в shared репо — новой работы ноль, только hiring.

**Новые проекты** (не-mobile, не-memory-palace): берут нужный subset existing templates + возможно новые domain-specific templates (data-engineer, ml-engineer и пр.) — добавим когда понадобится.

### 6.5 Per-project plugin activation

**Два источника специалистов** на сервере:

**A. Voltagent subagents marketplace** (уже зарегистрирован в `~/.claude/settings.json`) — 10 мета-плагинов, ~150 агентов суммарно. Для enable — добавить флаг в per-workspace settings.json. **Marketplace уже на месте, никаких extra steps.**

| Voltagent плагин | Агенты (выбранные) | Для каких ролей |
|---|---|---|
| `voltagent-meta` ✅ уже enabled | agent-organizer, multi-agent-coordinator, workflow-orchestrator, error-coordinator + 5 | CEO, CTO, CodeReviewer (координация) |
| `voltagent-qa-sec` ✅ уже enabled | security-auditor, penetration-tester, code-reviewer, debugger, compliance-auditor, test-automator, performance-engineer, architect-reviewer + 7 | CodeReviewer, SecurityAuditor, QAEngineer |
| `voltagent-domains` 🔵 **enable для Gimle** | **blockchain-developer**, fintech-engineer, mobile-app-developer, embedded-systems, game-developer, iot-engineer, payment-integration, quant-analyst, risk-manager + 3 | BlockchainEngineer (primary), SecurityAuditor |
| `voltagent-lang` 🔵 **enable для Gimle + Medic** | python-pro, fastapi-developer, kotlin-specialist, swift-expert, typescript-pro, rust-engineer, expo-react-native-expert, flutter-expert + 21 | Все engineers — каждый берёт свой язык |
| `voltagent-core-dev` 🔵 enable где нужно | backend-developer, frontend-developer, fullstack-developer, mobile-developer, api-designer, microservices-architect, graphql-architect, websocket-engineer + 3 | PythonEngineer, MCPEngineer, backend roles |
| `voltagent-infra` 🔵 **enable для Gimle** | docker-expert, devops-engineer, kubernetes-specialist, platform-engineer, sre-engineer, terraform-engineer, network-engineer, cloud-architect, database-administrator, security-engineer + 6 | InfraEngineer (primary) |
| `voltagent-data-ai` 🔵 enable для Gimle | (data engineering, ML, LLM specialists) | ResearchAgent (для ML/LLM tracks) |
| `voltagent-dev-exp` 🔵 enable для TechnicalWriter | (CLI tools, documentation, README generation) | TechnicalWriter (primary) |
| `voltagent-research` 🔵 enable для ResearchAgent | (market research, competitive, scientific literature) | ResearchAgent (primary) |
| `voltagent-biz` ⚪ опционально | (product, legal, licensing) | Возможно CEO для regulatory research |

**Enable действие** в `~/.paperclip/instances/default/workspaces/<ws-id>/.claude/settings.json`:
```json
{
  "enabledPlugins": {
    "superpowers@claude-plugins-official": true,
    "voltagent-meta@voltagent-subagents": true,
    "voltagent-qa-sec@voltagent-subagents": true,
    "voltagent-domains@voltagent-subagents": true,
    "voltagent-lang@voltagent-subagents": true,
    "voltagent-infra@voltagent-subagents": true
  }
}
```

**B. Seth Hobson's claude-code-workflows** (~/claude-agents/ — 76 плагинов, 182 агента, 147 skills). **НЕ зарегистрирован** как marketplace сейчас. Содержит более узкие специализации которых нет в voltagent:

| Seth plugin | Что даёт уникального | Когда нужен |
|---|---|---|
| `blockchain-web3` | blockchain-developer + **4 skills** (solidity-security, web3-testing, defi-protocol-templates, nft-standards) | Если нужны Solidity/Web3 skill-ориентированные workflows поверх voltagent-domains |
| `frontend-mobile-security` | **mobile-security-coder**, frontend-security-coder | Wallet/fintech mobile apps — специфичное hardening. Voltagent'овский SecurityAuditor generalist, не покрывает mobile-key-storage deeply |
| `comprehensive-review` | Три-agent review set (architect-review + code-reviewer + security-auditor) — готовый workflow | Если хочется дополнительной review perspective поверх нашей 6-reviewer team |
| `llm-application-dev` | Специфика для LLM-heavy apps | Gimle (MCP + Graphiti — LLM-centric) |
| `reverse-engineering` | Для анализа foreign/minified кода | BlockchainEngineer / SecurityAuditor анализирующий чужие контракты |

**Использование B:**
- **Для research mining** (Фаза 1 §5.1) — читаем файлы напрямую через filesystem MCP, НЕ требуется marketplace registration. ~200 промпт-файлов для изучения.
- **Для enable в paperclip** — добавить в `~/.claude/settings.json` → `extraKnownMarketplaces` Seth'овский GitHub repo (`wshobson/claude-code-workflows` или аналогичный) **отдельным Phase 1.5**. Это opt-in — делаем когда реально нужен mobile-security-coder или solidity-security skill.

### 6.6 Декларативный template-driven plugin activation

В каждом role template (например `quality/security-auditor.md`) секция **"Per-project plugin matrix"** перечисляет какие voltagent плагины нужно enable'ить под контекст проекта. При bootstrap'е нового проекта скрипт читает эту секцию и генерирует корректный workspace settings.json автоматически.

Пример в `security-auditor.md`:
```markdown
## Plugin matrix (activate per project type)

| Project type | Required voltagent plugins | Optional Seth plugins |
|---|---|---|
| Blockchain / wallet | voltagent-domains, voltagent-qa-sec | blockchain-web3, frontend-mobile-security |
| Mobile (native/RN) | voltagent-lang, voltagent-qa-sec | frontend-mobile-security |
| Health / PII | voltagent-qa-sec, voltagent-biz | — (GDPR/HIPAA через context7 MCP) |
| Fintech / payments | voltagent-domains, voltagent-qa-sec | — |
| Pure backend / API | voltagent-core-dev, voltagent-qa-sec | backend-api-security |
```

---

## 7. Bootstrap flow нового проекта

Сценарий: Anton хочет начать проект X.

### 7.1 Предусловие

- `paperclip-shared-fragments` существует и stable
- Paperclip инстанс запущен на iMac
- Проектный git-репо уже создан (напр. `ant013/project-x`)

### 7.2 Шаги

```bash
# 1. Клонируем проектный репо
git clone git@github.com:ant013/project-x.git
cd project-x

# 2. Скачиваем bootstrap скрипт из shared репо
curl -fsSL https://raw.githubusercontent.com/ant013/paperclip-shared-fragments/main/bootstrap-new-project.sh > /tmp/bootstrap.sh
bash /tmp/bootstrap.sh

# Что делает bootstrap.sh:
#   a) git submodule add git@github.com:ant013/paperclip-shared-fragments.git paperclips/fragments/shared
#   b) mkdir -p paperclips/{roles,fragments/local,dist}
#   c) cp paperclips/fragments/shared/build.sh paperclips/build.sh
#   d) Copies starter templates: ceo.md + cto.md to paperclips/roles/
#   e) Creates paperclips/README.md pointing to shared
#   f) git add paperclips/ .gitmodules && git commit -m "chore: paperclip team bootstrap"

# 3. Правим роли
$EDITOR paperclips/roles/ceo.md   # заполняем product knowledge, roadmap, delegation map
$EDITOR paperclips/roles/cto.md   # заполняем tech stack, delegation map, verification commands

# 4. Добавляем нужные domain роли (копируем templates)
cp paperclips/fragments/shared/templates/engineers/python-engineer.md paperclips/roles/
cp paperclips/fragments/shared/templates/quality/code-reviewer.md paperclips/roles/
# ... и так для всех нужных ролей

# 5. Собираем dist/
./paperclips/build.sh

# 6. Commit и push
git add paperclips/
git commit -m "feat: paperclip roles — initial team v1"
git push

# 7. На iMac — создаём paperclip company и нанимаем через CEO
# (или создаём пустую company в UI, наполняем через UI или API)
```

### 7.3 Первый найм

На сервере через CEO агента (paperclip-create-agent skill):

```bash
# CEO получает issue "set up engineering team"
# CEO для каждой роли:
#   - читает ~/.paperclip/.../roles/<role>.md через filesystem MCP (или из dist/)
#   - POST /api/companies/<cid>/agent-hires
#   - Board approves (или company disable approval)
#   - CEO PUT /api/agents/<id>/instructions-bundle/file {path: "AGENTS.md", content: <dist file>}
```

---

## 8. Migration flow существующего проекта (Medic)

Medic уже имеет собственные `Medic/paperclips/fragments/*.md` и работающую команду. Нужно перенести без downtime.

### 8.1 Шаги миграции

```bash
# 1. Создаём shared репо
cd /tmp
git clone git@github.com:ant013/paperclip-shared-fragments.git
cd paperclip-shared-fragments

# 2. Копируем Medic-существующие fragments, они все Категория A
mkdir -p fragments
cp /path/to/Medic/paperclips/fragments/*.md fragments/

# 3. Извлекаем Категория B из Medic/paperclips/roles/*.md (см. §3.2) в shared/fragments/
# Для каждого extract: ceo-hiring-workflow, cto-no-code-ban, escalation-blocked, etc.
# Используем edits tools, aim размеры из §3.2

# 3a. В соответствующих Medic roles УДАЛЯЕМ извлечённый текст и заменяем на @include marker.
# Пример: в Medic/paperclips/roles/cto.md блок "Что ты НЕ делаешь (hard ban)" (L10-25)
# заменяем на строку: <!-- @include fragments/shared/cto-no-code-ban.md -->
# Без этого шага будет дубликат: текст и в fragment'е shared, и в Medic role inline.
# Полный set извлечений — по §3.2 таблице.

# 4. Копируем templates — используем Medic/roles/*.md как basis, удаляем Medic-specific
mkdir -p templates/{management,engineers,quality,support}
# ceo.md template = Medic/roles/ceo.md минус product/roadmap/метрики + placeholders
# cto.md template = Medic/roles/cto.md минус delegation map + placeholders
# engineer templates: kmp/ios/backend — Medic-flavored, но с placeholders для paths
# ... и т.д.

# 5. build.sh, CONVENTIONS.md, README.md, bootstrap-new-project.sh
cp build-updated.sh build.sh
# ... напишем CONVENTIONS.md, README.md

# 6. Первый commit
git add .
git commit -m "chore: initial import from Medic"
git push

# 7. Migrate Medic на submodule
cd /path/to/Medic
git rm -r paperclips/fragments
git submodule add git@github.com:ant013/paperclip-shared-fragments.git paperclips/fragments/shared
mkdir -p paperclips/fragments/local
# Перемещаем Medic-local fragments (если будут появляться)
# Обновляем paperclips/build.sh на новую версию (shared + local resolution)
cp paperclips/fragments/shared/build.sh paperclips/build.sh
# Обновляем @include paths в roles/*.md
# Было: <!-- @include fragments/heartbeat-discipline.md -->
# Станет: <!-- @include fragments/shared/heartbeat-discipline.md -->
sed -i '' 's|@include fragments/|@include fragments/shared/|g' paperclips/roles/*.md
./paperclips/build.sh
git add paperclips/
git commit -m "refactor(paperclips): migrate fragments to shared submodule"
git push origin develop

# 8. Обновляем live AGENTS.md на сервере
# На сервере — cp paperclips/dist/<role>.md → ~/.paperclip/.../AGENTS.md (см. paperclip-operations.md §8.4)
```

### 8.2 Тестирование после миграции

После migration — smoke тест цепочки:
1. Board пишет comment на любую issue Medic с `@CTO проверь что всё ок после миграции`
2. CTO просыпается, читает AGENTS.md (уже из нового source), выполняет задачу
3. Проверяем `agent_wakeup_requests` — wake fired, source=automation
4. Если агент работает нормально — migration успешна

### 8.3 Rollback plan

Если что-то сломается:
```bash
cd /path/to/Medic
git revert <migration-commit>
git push
# Обновить live AGENTS.md back to old versions (из dist pre-migration)
```

Submodule можно удалить: `git rm paperclips/fragments/shared && mv paperclips/fragments/local/* paperclips/fragments/ && ...`

---

## 9. Execution plan (последовательность действий)

**Фаза 0 — setup** ✅ DONE 2026-04-15
1. ✅ `github.com/ant013/paperclip-shared-fragments` создан (1 commit scaffold)
2. ✅ `github.com/ant013/Gimle-Palace` создан (13 commits, spec committed)
3. ✅ URL зафиксированы в заголовке документа

**Фаза 1 — research** (через subagents в Claude Code session'е)
1. Mining existing plugins — **два корпуса** (voltagent ~150 prompts + Seth ~330 prompts) → `shared/research/plugin-prompt-mining.md`
2. Параллельно — 10 deep research задач → `shared/research/role-patterns/<role>.md`

**Фаза 2 — shared репо initial content** (после research)
1. Написать 15 fragments (A+B) — используя Medic fragments + research inputs
2. Написать 21 template (4 подпапки) — используя research + Medic roles как basis
3. build.sh (hardened: `set -euo pipefail`, file-exists check, nested include up to 2 levels, exit on size breach) + bootstrap-new-project.sh (idempotency check: refuses if `paperclips/` exists без `--force`) + deploy.sh (atomic copy to live AGENTS.md via `.tmp` + rename) + drift-check.sh + CONVENTIONS.md + README.md
4. **Tokeniser** в CONVENTIONS.md — скрипт measure.sh вокруг Anthropic `count_tokens` API (ключ из `~/.paperclip/instances/default/config.json`)
5. **Versioning** — semver теги (`v0.1.0`, `v0.2.0`...), CHANGELOG.md, breaking-change policy (breaking = major bump, consumer обязан read CHANGELOG перед update)
6. **Branch protection** — GitHub Settings → Branches → protect `main` (require PR, no force-push), CODEOWNERS = `* @ant013`
7. Push, tag `v0.1.0`

**Фаза 3 — Medic migration**
1. Добавить submodule в Medic
2. Обновить build.sh + @include paths в roles + **заменить inline-content на @include маркеры** (Категория B extractions, §8.1 шаг 3a)
3. Перемерить полученные AGENTS.md реальным `count_tokens` — убедиться что ≤8000
4. `deploy.sh` на сервере — atomic обновление 9 live AGENTS.md
5. Smoke test (Board comment на любую issue, проверить цепочку CodeReviewer → handoff chain)

**Фаза 4 — Gimle bootstrap**
1. bootstrap-new-project.sh в Gimle-Palace репо
2. Правим ceo.md, cto.md под Gimle domain
3. Добавляем 9 ролей из templates (копируем + правим)
4. **Enable voltagent plugins** для Gimle workspaces: domains, lang, infra, core-dev, data-ai, dev-exp в per-workspace settings.json (см. §6.5)
5. build.sh → dist/, деплой через deploy.sh
6. На сервере: CEO нанимает команду через paperclip-create-agent
7. Назначаем первую issue (напр. «setup docker compose structure per spec»)

**Фаза 5 — Unstoppable / другие проекты** (когда решим)
- Создаём новую paperclip company
- bootstrap + templates + enable plugins (всё уже готово)
- hiring команды

---

## 10. Open questions / future work

### 10.1 Решено по ходу reality-check

- ✅ **Имена репо:** `paperclip-shared-fragments` + `Gimle-Palace` (Public, main protected)
- ✅ **Research scope:** 10 priority deep-research tasks (§5.1)
- ✅ **Plugin marketplace:** никакого нового marketplace не нужно. Voltagent уже зарегистрирован, просто enable 6 дополнительных плагинов (§6.5 matrix). Seth's Hobson 76 плагинов — опциональный secondary source, подключение отдельным шагом Phase 1.5 если потребуется.
- ✅ **Tokeniser:** Anthropic `count_tokens` API (пример скрипта в §12 и в CONVENTIONS.md shared репо). Реальные измерения — в §12.
- ✅ **Versioning:** semver + CHANGELOG в Phase 2 deliverable (было в «решить позже», перенесено в P0).
- ✅ **Live deployment atomicity:** deploy.sh с `.tmp` + rename, drift-check.sh, idempotent bootstrap — всё в Phase 2 deliverable (§9).
- ✅ **Branch protection:** GitHub protect-main + CODEOWNERS в Phase 2 (§9).
- ✅ **Submodule vs альтернативы:** при 2 consumer'ах + один maintainer — submodule OK. Trade-off задокументирован: bug-fix требует N explicit `git submodule update --remote && commit && deploy` (N = число consumer'ов). Пересмотреть при N≥3 или появлении второго maintainer'а. Альтернативы (git subtree / vendir / Renovate-PR / tarball) сравнить на §10.2 checkpoint когда одно из этих условий наступит.
- ✅ **Multi-host paperclip:** явно out-of-scope MVP. Single-host (imac-ssh.ant013.work) assumption зафиксирован. Multi-host — future work если появится потребность.

### 10.2 Решить по мере работы (не блокер MVP)

- **Pre-commit hook** для token-budget control в shared репо (запускает measure.sh на изменённых fragments, fail если > лимит) — писать когда будет первый случай «забыли померить»
- **Nested @include** — сейчас build.sh резолвит только один уровень. Если fragment'у потребуется включать другой fragment — расширять build.sh (до 2 уровней глубины, cycle detection)
- **Selective-include matrix scalability** — §4.2 таблица 9×10. При >30 ролей перейти на tag-based (`<!-- audience: engineer,reviewer -->` в fragments) или per-role `includes.txt`
- **Subagent разговорник** — как Reviewer-coordinator (CodeReviewer) эффективно merge'ит 6 параллельных review-отчётов в один verdict. Базовый паттерн в `review-report-format.md`, уточнить на первой реальной большой PR-ревизии
- **Shared test harness** — unit-test fragments/templates: «fragment X ≤ N tok», «template Y компилируется без awk-ошибок», «все @include пути existуют» — после первого рефакторинга fragments
- **CI pipeline для live deployment** — сейчас manual deploy.sh. Future: GitHub Actions на push в shared `main` → auto-PR к consumer'ам через Renovate + merge → SSH к серверу → deploy.sh. Нужен только когда multi-host или второй maintainer
- **CHANGELOG автоматизация** — `semantic-release` или ручной CHANGELOG. Пока ручной ок (мало commits, один maintainer)

### 10.3 Upstream (для сообщества)

- Pull request в Paperclip: regex fix для @-mention (расширить exclusion set или использовать explicit markdown-link mentions)
- Pull request: унифицировать PATCH vs POST wake-логику
- Блог-пост / опенсорс-anon: "Running multiple paperclip companies on one instance" с нашими learnings

---

## 11. Acceptance criteria

Разделено на **приёмку spec'а** (документ) и **DoD проекта** (реализация). Это разные вехи.

### 11.1 Spec review acceptance

Spec готов к переходу в imлементацию когда:

1. Документ написан, committed, обсуждён с Board (Anton)
2. Reality-check пройден: все пути, размеры, plugin-имена соответствуют серверной реальности (см. §12)
3. Нет placeholder'ов (TBD / TODO / `{{...}}`) в content-секциях
4. Validation strategy зафиксирована (§13) — как не выкатывать всю архитектуру без доказательства работоспособности базы

### 11.2 Project Definition of Done

Имплементация считается завершённой когда:

1. **`paperclip-shared-fragments` репо** на GitHub содержит:
   - Минимум: 5 fragments (категория A), 1 сборочный build.sh, 1 tag `v0.1.0`, README.md
   - Полный scope (после успешного слайса): 15 fragments (5 A + 10 B), ≥6 templates (минимум CEO, CTO, один engineer, CodeReviewer, QA, один support), hardened tooling (build.sh + bootstrap-new-project.sh + deploy.sh + drift-check.sh + measure.sh), CHANGELOG.md, CONVENTIONS.md, branch protection + CODEOWNERS
2. **Medic успешно мигрирован** на submodule, chain работает без downtime — smoke test: Board comment на любую открытую issue → wake fired → agent run succeeded → handoff chain не порван
3. **Gimle company** имеет 6+ нанятых агентов, первая реальная issue выполнена end-to-end (от Board → CEO → CTO → engineer → review → done)
4. **Token-budget compliance:** `measure.sh` показывает все AGENTS.md ≤ 8000 tokens (baseline CTO Medic = 3085 tok)
5. **Research нотсы** для 10 приоритетных ролей (§5.1) в `shared/research/role-patterns/` — но **только если спек расширился до полного scope**. Slice-only DoD их не требует.
6. **Documentation** обновлена: `docs/paperclip-operations.md` в Medic и Gimle-Palace дополнены секцией про submodule workflow + deploy/drift workflow

---

## 12. Appendix: размерный аудит existing Medic (measured)

**Методика** — Anthropic `POST /v1/messages/count_tokens` endpoint (официальный Claude tokeniser). Скрипт измерения будет в `CONVENTIONS.md` shared репо. `wc -l / -w / -c` — для sanity, не для бюджета.

**Источник файлов** — `/Users/Shared/Ios/Medic/paperclips/` на сервере `imac-ssh.ant013.work` (canonical). Локальная копия у Anton'а отстаёт.

| File | Lines | Bytes | **Tokens (measured)** |
|---|---|---|---|
| `fragments/heartbeat-discipline.md` | 52 | 5100 | **1323** |
| `fragments/git-workflow.md` | 8 | 718 | **191** |
| `fragments/worktree-discipline.md` | 9 | 887 | **225** |
| `fragments/pre-work-discovery.md` | 11 | 826 | **204** |
| `fragments/language.md` | 3 | 199 | **53** |
| `roles/ceo.md` | 94 | 5591 | **1484** |
| `roles/cto.md` | 66 | 4371 | **1182** |
| `roles/kmp-engineer.md` | 36 | 1839 | **539** |
| `roles/ios-engineer.md` | 39 | 2069 | **605** |
| `roles/backend-engineer.md` | 46 | 2270 | **665** |
| `roles/code-reviewer.md` | 101 | 5522 | **1485** |
| `roles/qa-engineer.md` | 62 | 3467 | **1011** |
| `roles/research-agent.md` | 71 | 3523 | **923** |
| `roles/ux-designer.md` | 53 | 2967 | **842** |

**Reassembled AGENTS.md (role + fragments через build.sh) — live bundle CTO:** `3085 tokens` (11864 bytes, 144 lines).

**Ratio:** ~0.26 tok/byte для Russian-heavy Markdown с inline code fences. Не использовать `wc -w × 1.3` — погрешность ±40%.

### 12.1 Соответствие §4.1 hard limits

Все измеренные файлы **укладываются** в лимиты:

| Лимит | Реальный максимум в Medic | Запас |
|---|---|---|
| Role body ≤ 2000 tok | 1485 (code-reviewer) | 26% |
| Full AGENTS.md ≤ 8000 tok | 3085 (CTO assembled) | 61% |
| Fragment ≤ 1200 tok (heartbeat), ≤ 500 tok (others) | 1323 (heartbeat — marginal над 1200), 225 (next largest) | heartbeat чуть over — либо поднять лимит до 1500 tok, либо сократить 3 наших новых @-mention правила |

**Вывод:** никакого принудительного compress'а при migration не требуется. Лимиты реалистичны и **не противоречат** замерам. Единственное — heartbeat-discipline чуть over «500 tok для fragments»; решение: явно определить его как исключение в `CONVENTIONS.md` («heartbeat-discipline разрешён до 1500 — содержит три критичных paperclip-fix-правила, компактнее не сжать без потери сигнала»).

### 12.2 Source of truth — сервер

**Важно для всех путей в §3.1, §3.2, §8:** canonical source — `/Users/Shared/Ios/Medic/paperclips/` **на сервере iMac** (user: `anton`). Локальная копия у разработчика (`/Users/ant013/Android/Medic/paperclips/`) отстаёт — там остался плоский `agents/` layout из предыдущей сессии. Migration fragments category B (§3.2) и size measurements (§12) относятся к server-версии.

---

## 13. Validation strategy: narrow slice first

Спек описывает ~60 артефактов (15 fragments + 21 template + 10 research notes + tooling) как prerequisite продакшена. Но **ни один базовый assumption не валидирован**:

- Submodule workflow реально работает с build.sh?
- Extraction fragment → @include эквивалентна inline-контенту по поведению агента?
- Paperclip корректно подхватывает новые AGENTS.md после deploy.sh?

**Правило:** не расширяем scope до тех пор, пока самый узкий слайс не доказан.

### 13.1 Slice #1 — submodule viability (первый слайс)

**Гипотеза:** «submodule с существующими 5 Medic fragments, без extraction и новых templates, сохраняет работу существующей Medic-команды».

**Scope (1 день):**

1. В `paperclip-shared-fragments` репо положить **только 5 существующих Medic fragments (категория A)**: `heartbeat-discipline.md`, `git-workflow.md`, `worktree-discipline.md`, `pre-work-discovery.md`, `language.md`. Без правок содержимого.
2. Скопировать текущий Medic `build.sh` as-is + README-stub. Tag `v0.0.1`.
3. В Medic (на сервере, `/Users/Shared/Ios/Medic/`):
   - `git submodule add git@github.com:ant013/paperclip-shared-fragments.git paperclips/fragments/shared`
   - `git rm -r paperclips/fragments/*.md` (удаляем локальные копии)
   - `sed -i 's|@include fragments/|@include fragments/shared/|g' paperclips/roles/*.md` (обновляем @include пути)
   - `./paperclips/build.sh` → rebuild dist
   - Commit + push на develop
4. На сервере — atomic deploy: `cp` всех 9 dist/*.md в live AGENTS.md через `.tmp + mv` (draft deploy.sh сценарий)
5. **Smoke test:** Board пишет коммент `@CTO проверь текущее состояние projeкта` на любую открытую issue Medic. Ждём wake → run → response.

**Проверяется (ожидаемо все ✅):**
- Submodule workflow технически работает
- `build.sh` с путём `fragments/shared/` резолвит корректно
- Deploy всех 9 файлов не ломает консистентность
- Paperclip подхватывает новые AGENTS.md без перезапуска (мы это уже наблюдали когда делали rename fix, но здесь явная верификация)
- Chain `Board → CTO → handoff` работает так же как до миграции

**Критерии отказа:**
- Submodule не клонируется при deploy / клонирование требует creds которые агенты не имеют
- `build.sh` ищет старый путь `fragments/` вместо `fragments/shared/` и ломает сборку
- Agent reads AGENTS.md и видит broken @include markers (сырой текст)
- Chain molча обрывается после миграции

### 13.2 Slice #2 — один extraction (после успеха #1)

**Гипотеза:** «извлечение одного куска role'и в новый fragment + @include обратно даёт идентичное поведение агента».

**Scope (1-2 часа):**
- Извлечь `cto-no-code-ban` блок из `cto.md` (самый короткий и чёткий — L10-25)
- Положить в `shared/fragments/cto-no-code-ban.md`, `v0.0.2` tag
- В Medic: заменить inline L10-25 в cto.md на `<!-- @include fragments/shared/cto-no-code-ban.md -->`, rebuild, redeploy
- Smoke test: измерить diff размеров AGENTS.md (должен быть нейтральным), назначить CTO issue которая обычно триггерит no-code-ban поведение, наблюдать что CTO остаётся дисциплинированным (не пишет код)

### 13.3 Slice #3 — один template + один hire (после успеха #2)

**Гипотеза:** «template → role → hired agent → assigned issue → executed» работает end-to-end для новой компании.

**Scope (4-8 часов):**
- Написать ОДИН template (`templates/engineers/python-engineer.md`) на основе research mining'а НЕСКОЛЬКИХ релевантных plugins (не 10 параллельных deep-research, а минимально обоснованная версия)
- В Gimle-Palace: скопировать → заполнить Gimle-specific → build.sh → deploy
- CEO Gimle нанимает PythonEngineer через `paperclip-create-agent` skill
- Board назначает PythonEngineer'у простую issue («create empty `services/palace-mcp/` directory structure with Dockerfile stub»)
- Observe: issue выполняется, commit появляется, handoff назад к CEO работает

### 13.4 Только после трёх успешных слайсов — расширение scope

Когда #1+#2+#3 зелёные — **тогда** запускаем:
- Полный extraction категории B (9 оставшихся fragments)
- Остальные templates (по мере того как нанимается новая роль)
- Research mining (когда реально нужен — например, security-auditor template требует OWASP-knowledge)
- Gimle team complete hiring

### 13.5 Что это НЕ значит

Это не «спек неверен» — большинство его решений остаются. Это — **порядок реализации**. Спек описывает **целевое состояние**. Slice-first описывает **путь туда**: сначала минимальный risk, потом инкремент.

Если слайс #1 провалится — значит submodule подход ошибочен, и мы переписываем §2 (архитектуру) до того как написали 20 templates. Это дешёвый провал.

Если слайс #1 зелёный — мы **знаем** что фундамент стоит, и можем строить на нём без страха.

### 13.6 Что с gimle-palace-design spec'ом

`2026-04-15-gimle-palace-design.md` (2873 строки, продуктовый дизайн самого palace) **не проходил** reality-check в этой сессии. Он описывает what-to-build, не how-to-deliver, поэтому прямого пересечения с team spec'ом нет. Но там тоже могут быть выдуманные facts про серверную инфраструктуру. **Отдельная задача для отдельной сессии** — не блокер для team-slice.

---

_Документ составлен на основе сессии brainstorming 2026-04-15. Reality-check пройден. По мере bootstrap'а репо — обновлять, добавлять findings из research._
