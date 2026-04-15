# Paperclip Operations — Medic

Reference doc собранный по результатам сессии траблшутинга 2026-04-15, когда multi-agent цепочка несколько раз молча останавливалась. Описывает **найденные баги**, **архитектуру промптов агентов**, **полный набор API endpoint'ов** и **способы управлять paperclip-инстансом через терминал/БД/API**, включая авторизацию и токены.

Стек paperclip на нашей инфраструктуре:
- **paperclipai** (npm, `2026.403.0`) — CLI + сервер
- **Node.js 20.20.2** (via nvm)
- **embedded-postgres 18.1.0-beta.16** — встроенный PostgreSQL, порт `54329`
- **LLM provider:** Claude (ключ в `config.json`)
- **Развёрнут на:** `imac-ssh.ant013.work` (Intel iMac, macOS Darwin 25.3.0)
- **Публичный URL:** `https://paperclip.ant013.work` (через Cloudflare tunnel)
- **Локальный HTTP:** `127.0.0.1:3100`
- **Автозапуск:** LaunchAgent `~/Library/LaunchAgents/com.paperclip.server.plist` (см. ниже — важный нюанс)

---

## 1. Архитектура: как paperclip будит агентов

### 1.1 Event-driven модель

Paperclip — это Linear-like таск-менеджер, где каждый "агент" — это живой Claude Code процесс. Агенты **не крутятся постоянно** — они запускаются по wake-up'ам.

Четыре источника wake-up'ов (`agent_wakeup_requests.source`):

| Source | Когда срабатывает |
|---|---|
| `timer` | По расписанию (`runtime_config.heartbeat.intervalSec`), обычно 4 часа |
| `assignment` | Issue переназначена на этого агента |
| `automation` | Коммент-mention, issue-comment-on-assignee, reopen и т.д. |
| `on_demand` | Ручной wake через UI или API |

Каждый wake → создаётся запись в `agent_wakeup_requests` (`status='queued'`) → шедулер создаёт `heartbeat_runs` строку → запускается процесс Claude Code с контекстом задачи → агент работает → `heartbeat_runs.status='succeeded'/'failed'` и `agent_wakeup_requests.status='completed'`.

### 1.2 Условия wake-up'а на issue update (`PATCH /api/issues/:id`)

Из исходников `@paperclipai/server/dist/routes/issues.js`:

```js
// CASE 1: Smена assignee → wake new assignee
if (assigneeChanged && issue.assigneeAgentId && issue.status !== "backlog") {
    wakeups.set(issue.assigneeAgentId, { source: "assignment", reason: "issue_assigned" });
}

// CASE 2: Status переходит backlog → non-backlog → wake current assignee
if (!assigneeChanged && statusChangedFromBacklog && issue.assigneeAgentId) {
    wakeups.set(issue.assigneeAgentId, { source: "automation", reason: "issue_status_changed" });
}

// CASE 3: @-упоминания в теле комментария → wake всех упомянутых
if (commentBody && comment) {
    const mentionedIds = await svc.findMentionedAgents(issue.companyId, commentBody);
    for (const mentionedId of mentionedIds) {
        if (actor.actorId !== mentionedId)
            wakeups.set(mentionedId, { source: "automation", reason: "issue_comment_mentioned" });
    }
}
```

**Критично:** `PATCH /api/issues/:id` с опциональным полем `comment` **НЕ будит assignee** автоматически на самом факте комментария. Только на смене assignee, переходе из backlog, или @-mention. См. секцию багов ниже.

### 1.3 Условия wake-up'а на comment creation (`POST /api/issues/:id/comments`)

Другой путь — через отдельный comment endpoint:

```js
const skipWake = selfComment || isClosed;

// Assignee wake (если issue не closed и не self-comment)
if (assigneeId && (reopened || !skipWake)) {
    wakeups.set(assigneeId, { source: "automation", reason: "issue_commented" });
}

// Плюс @-mention wake — так же как в PATCH
for (const mentionedId of mentionedIds) { ... }
```

**Различие с PATCH-with-comment:** здесь assignee будится **автоматически** на любом non-self комментарии к открытой issue.

### 1.4 Парсер @-упоминаний (`@paperclipai/server/dist/services/issues.js:findMentionedAgents`)

```js
const re = /\B@([^\s@,!?.]+)/g;
// ...
if (tokens.has(agent.name.toLowerCase())) resolved.add(agent.id);
```

Захватывает всё после `@` до одного из: whitespace, `@`, `,`, `!`, `?`, `.`. Сравнивает с `agent.name` в lowercase.

**Также есть explicit markdown-link формат** для 100% надёжности:
```markdown
[Code Reviewer](agent://<uuid>)
```
Обрабатывается через `extractAgentMentionIds` из `@paperclipai/shared` — пробелы в лейбле ок, пунктуация не мешает.

### 1.5 Execution lock

Каждая issue имеет `execution_run_id` + `execution_agent_name_key`. Пока один агент "держит" issue (в active run), wake-up'ы для другого агента на ту же issue идут в `status='skipped'` с `reason='issue_execution_locked'` (**кроме** `issue_comment_mentioned` — тот bypass'ит lock).

---

## 2. Структура промптов агентов

Source of truth — **`origin/develop:paperclips/dist/<role>.md`**. Каждая роль получается из:

```
roles/<role>.md (role-specific)  +  fragments/*.md (shared DRY blocks)
        │
        │  <!-- @include fragments/<name>.md -->  — expansion markers
        ▼
      build.sh (awk preprocessor)
        │
        ▼
    dist/<role>.md  ← закоммичено в git, видно в PR diff
        │
        │  (manual copy, through API или cp на сервере)
        ▼
~/.paperclip/instances/default/companies/<company-id>/agents/<agent-id>/instructions/AGENTS.md
```

### 2.1 Layout в `paperclips/`

```
paperclips/
├── README.md           # мини-руководство
├── build.sh            # awk-препроцессор roles+fragments → dist
├── fragments/          # shared атомарные правила
│   ├── git-workflow.md
│   ├── heartbeat-discipline.md   # ← наши три новые правила про @-mentions живут тут
│   ├── language.md
│   ├── pre-work-discovery.md
│   └── worktree-discipline.md
├── roles/              # role-specific + @include маркеры
│   ├── backend-engineer.md
│   ├── ceo.md
│   ├── code-reviewer.md
│   ├── cto.md
│   ├── ios-engineer.md
│   ├── kmp-engineer.md
│   ├── qa-engineer.md
│   ├── research-agent.md
│   └── ux-designer.md
└── dist/               # build artifact — generated from roles/+fragments/
    └── <9 файлов>      # идентичны по структуре roles/, но с раскрытыми include'ами
```

### 2.2 Синтаксис include'а

В `roles/<role>.md`:

```markdown
<!-- @include fragments/heartbeat-discipline.md -->
```

`build.sh` находит такие строки через awk, подставляет содержимое файла. Простой awk-препроцессор, без условий/переменных:

```bash
awk -v frag_dir="$FRAG_DIR" '
  /<!-- @include fragments\/.*\.md -->/ {
    match($0, /fragments\/[^ ]+\.md/)
    frag = substr($0, RSTART + 10, RLENGTH - 10)
    path = frag_dir "/" frag
    while ((getline line < path) > 0) print line
    close(path)
    next
  }
  { print }
' "$role_file" > "$out_file"
```

### 2.3 Процесс обновления

1. Если правило **role-specific** → правь `roles/<role>.md`
2. Если **общее для нескольких ролей** → правь `fragments/<topic>.md`
3. Запусти: `./paperclips/build.sh`
4. Проверь `dist/` в git diff — это то что агенты увидят
5. Commit **roles/ + fragments/ + dist/** (dist коммитим тоже, видно в PR)
6. **Отдельный шаг:** копирование `dist/*.md` → live `AGENTS.md` в бандлах агентов. Обычно CEO делает это при hiring'е или вручную через API (см. §4.3).

### 2.4 Bundle modes

В `agents.adapter_config.instructionsBundleMode`:

- `managed` — paperclip владеет файлом; пишется через API `PUT /api/agents/:id/instructions-bundle/file` или прямо в `~/.paperclip/.../AGENTS.md`.
- `external` — путь указывает на файл вне paperclip'а (например в git checkout'е проекта). Paperclip только читает.

Все наши агенты сейчас в режиме `managed` — файл живёт в `~/.paperclip/instances/default/companies/7c094d21.../agents/<id>/instructions/AGENTS.md`. При прямом `cp dist/X.md → AGENTS.md` никакая DB-нотификация не нужна — paperclip читает файл при каждом run'е заново.

### 2.5 Hiring нового агента (CEO workflow)

Полная последовательность согласно `skills/paperclip-create-agent/SKILL.md`:

```bash
# 1. Identity check
curl -sS "$PAPERCLIP_API_URL/api/agents/me" -H "Authorization: Bearer $PAPERCLIP_API_KEY"

# 2. Discover adapter config docs
curl -sS "$PAPERCLIP_API_URL/llms/agent-configuration.txt" -H "Authorization: Bearer $PAPERCLIP_API_KEY"
curl -sS "$PAPERCLIP_API_URL/llms/agent-configuration/claude_local.txt" -H "Authorization: Bearer $PAPERCLIP_API_KEY"

# 3. Compare existing agents
curl -sS "$PAPERCLIP_API_URL/api/companies/$PAPERCLIP_COMPANY_ID/agent-configurations" -H "Authorization: Bearer $PAPERCLIP_API_KEY"

# 4. Discover icons
curl -sS "$PAPERCLIP_API_URL/llms/agent-icons.txt" -H "Authorization: Bearer $PAPERCLIP_API_KEY"

# 5. Submit hire request
curl -sS -X POST "$PAPERCLIP_API_URL/api/companies/$PAPERCLIP_COMPANY_ID/agent-hires" \
  -H "Authorization: Bearer $PAPERCLIP_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "NewRole",
    "role": "engineer",
    "title": "New Role Description",
    "icon": "cpu",
    "reportsTo": "<ceo-or-cto-agent-id>",
    "capabilities": "Owns X, delivers Y",
    "adapterType": "claude_local",
    "adapterConfig": {
      "cwd": "/Users/Shared/Ios/Medic",
      "model": "claude-sonnet-4-6",
      "promptTemplate": "<минимальный inline prompt или пусто>",
      "instructionsFilePath": "AGENTS.md",
      "instructionsBundleMode": "managed"
    },
    "runtimeConfig": {
      "heartbeat": {
        "enabled": true,
        "intervalSec": 14400,
        "wakeOnDemand": true,
        "maxConcurrentRuns": 1,
        "cooldownSec": 10
      }
    },
    "budgetMonthlyCents": 0,
    "sourceIssueId": "<originating-issue-uuid>"
  }'
```

Ответ:
```json
{
  "agent": { "id": "uuid", "status": "pending_approval" },
  "approval": { "id": "uuid", "type": "hire_agent", "status": "pending" }
}
```

**Approval flow:** по умолчанию hire требует board-approve. Когда board (пользователь) нажимает approve в UI → `agent.status: pending_approval → idle`. Если company disabled approval requirement — агент сразу `idle`, `approval` в ответе `null`.

После approve CEO загружает AGENTS.md:

```bash
curl -sS -X PUT "$PAPERCLIP_API_URL/api/agents/<new-agent-id>/instructions-bundle/file" \
  -H "Authorization: Bearer $PAPERCLIP_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "path": "AGENTS.md",
    "content": "<полный content из paperclips/dist/<role>.md>"
  }'
```

### 2.6 AGENT_ROLES enum (константы paperclip)

Разрешённые значения `agent.role`:

```
ceo, cto, cmo, cfo, engineer, designer, pm, qa, devops, researcher, general
```

### 2.7 AGENT_ADAPTER_TYPES enum

```
process, http, claude_local, codex_local, gemini_local, opencode_local,
pi_local, cursor, openclaw_gateway, hermes_local
```

У нас все агенты — `claude_local` (запускают локальный Claude Code через `claude` CLI).

---

## 3. Найденные баги (и фиксы)

В ходе сессии нашли **три** баги в паре «@-mention parsing + wake routing» — все три независимы, каждый отдельно останавливал цепочку.

### 3.1 Bug #1: Regex не поддерживает пробелы в имени агента

**Симптом:** агенты писали `@Code Reviewer ...` — никто не просыпался, цепочка вставала. В логе никаких ошибок, просто тишина.

**Root cause:**
```js
const re = /\B@([^\s@,!?.]+)/g;
```
Регулярка останавливается на whitespace. Token `Code` (без "Reviewer") → нет агента с именем `"Code"` → wake-up не ставится.

**Fix:** Переименовали всех 9 агентов в CamelCase без пробелов:

| Было | Стало |
|---|---|
| Backend Engineer | BackendEngineer |
| Code Reviewer | CodeReviewer |
| KMP Engineer | KMPEngineer |
| QA Engineer | QAEngineer |
| Research Agent | ResearchAgent |
| UX Designer | UXDesigner |
| iOS Engineer | iOSEngineer |
| CEO / CTO | (уже 1 слово) |

**Что изменили:**
- `UPDATE agents SET name = ... WHERE id = ...` × 7, транзакция с guard'ом `status='idle'`
- Во всех `paperclips/roles/*.md` и `paperclips/dist/*.md` — sed-замена
- 9 live `AGENTS.md` перекопированы из нового `dist/`
- Git commit `a5c4caec` в `develop`, merged в phase-k

### 3.2 Bug #2: Regex пропускает пунктуацию в токен имени

**Симптом:** после fix #1 агенты писали `@CTO: нужен фикс` — CTO не просыпался.

**Root cause:** список исключений в regex'е `[^\s@,!?.]` покрывает только `,`, `!`, `?`, `.`. НЕ покрывает `:`, `;`, `)`, `]`, `"`, `'`, `/`, и пр. Написал `@CTO:` → токен `cto:` → `agents.name` — `cto`, нет match'а.

Подтверждение прямой симуляцией:
```js
const body = "@CTO: нужен 1-line fix";
const re = /\B@([^\s@,!?.]+)/g;
// captured: ['cto:']
// matches: []  ← никто не будется
```

**Fix:** Добавили правило в `fragments/heartbeat-discipline.md`:

> ### @-упоминания: всегда пробел после имени
> Парсер paperclip'а ломается, если сразу после `@AgentName` идёт двоеточие, точка-с-запятой, скобка или кавычка. Токен захватывает знак в имя, упоминание не резолвится, wake-up для агента не ставится — цепочка молча останавливается.
>
> **Правильно:** `@CTO нужен фикс`, `@iOSEngineer проверь билд`
> **Неправильно:** `@CTO: нужен фикс`, `@iOSEngineer;`, `(@CodeReviewer)`

Commit `f2f78d3e` в develop, merged в phase-k.

### 3.3 Bug #3: PATCH vs POST wake asymmetry

**Симптом:** после fix #1 и #2 агенты всё равно вставали. iOSEngineer fix'ил баг, PATCH'ил STA-24 со статусом todo и комментарием «fix ready for review» — CodeReviewer не просыпался.

**Root cause:** `PATCH /api/issues/:id` с опциональным полем `comment` **не делает assignee-wake автоматически**, только на:
1. Смене assignee
2. Переходе из backlog
3. @-mention в теле комментария

А `POST /api/issues/:id/comments` (отдельный endpoint) будит assignee на любом non-self комменте к открытой issue.

iOSEngineer использовал PATCH + comment без @-mention → ни одно из 3 условий PATCH-wake не сработало → wake-up не создан → CodeReviewer спит.

**Fix:** Добавили второе правило в `fragments/heartbeat-discipline.md`:

> ### Handoff: всегда @-упомянуть следующего агента
> Когда заканчиваешь свою фазу и передаёшь дальше — обязательно @-упомяни следующего агента в комментарии, даже если он уже assignee.
>
> Важное отличие endpoint'ов:
> - `POST /api/issues/{id}/comments` — будит assignee + всех @-упомянутых
> - `PATCH /api/issues/{id}` с полем `comment` — будит **ТОЛЬКО** на assignee-change / status-from-backlog / @-mentions
>
> Правило: handoff-комментарий всегда включает `@NextAgent` (с пробелом после имени). Страхует оба пути.

Commit `db8f20e0` в develop, merged в phase-k как `7f5e5a7b`.

### 3.4 Сводка: что теперь гарантирует handoff

Правильный handoff-комментарий должен одновременно:
1. Использовать имя агента **без пробелов** (BackendEngineer, не "Backend Engineer")
2. Иметь **пробел после имени** перед любой пунктуацией (`@CodeReviewer фикс готов`, не `@CodeReviewer:`)
3. Содержать **`@NextAgent`** в теле даже если он уже assignee (страхует PATCH-vs-POST разницу)

Эти три правила сейчас записаны в `paperclips/fragments/heartbeat-discipline.md` и попадают во все 9 ролей через `<!-- @include -->`.

---

## 4. API commands reference

Base URL: `https://paperclip.ant013.work` (production) / `http://127.0.0.1:3100` (direct на сервере).

Company ID (наш): `7c094d21-a02d-4554-8f35-730bf25ea492`

### 4.1 Agents

| Endpoint | Описание |
|---|---|
| `GET /api/agents/me` | Текущий agent по JWT |
| `GET /api/agents/:id` | Детали агента |
| `GET /api/agents/:id/configuration` | Полный adapter config |
| `PATCH /api/agents/:id` | Обновить (name, title, role, icon, capabilities, adapter*, budget) |
| `PATCH /api/agents/:id/permissions` | canCreateAgents, canAssignTasks |
| `POST /api/agents/:id/wakeup` | Ручной wake (source: timer/assignment/on_demand/automation) |
| `POST /api/agents/:id/heartbeat/invoke` | Принудительно создать run |
| `POST /api/agents/:id/pause` | Пауза — не будет реагировать на wake'ы |
| `POST /api/agents/:id/resume` | Снять паузу |
| `POST /api/agents/:id/terminate` | Уволить |
| `POST /api/agents/:id/keys` | Сгенерировать API key для агента |
| `GET /api/agents/:id/config-revisions` | История конфигов |
| `POST /api/agents/:id/config-revisions/:revId/rollback` | Откатить конфиг |
| `POST /api/agents/:id/runtime-state/reset-session` | Сбросить Claude CLI session |

### 4.2 Agent instruction bundle (AGENTS.md и прочие файлы)

| Endpoint | Описание |
|---|---|
| `PATCH /api/agents/:id/instructions-bundle` | Переключить mode (managed/external) |
| `PATCH /api/agents/:id/instructions-path` | Установить путь до AGENTS.md (относительный или абсолютный) |
| `PUT /api/agents/:id/instructions-bundle/file` | Upsert отдельного файла в bundle. Body: `{path, content, clearLegacyPromptTemplate?}` |
| `DELETE /api/agents/:id/instructions-bundle/file?path=X` | Удалить файл из bundle |

### 4.3 Agent hiring (через approval flow)

| Endpoint | Описание |
|---|---|
| `POST /api/companies/:companyId/agent-hires` | Подать hire-request (даёт approval) |
| `POST /api/companies/:companyId/agents` | Прямое создание (если разрешено) |
| `GET /api/approvals/:approvalId` | Статус approval'а |
| `POST /api/approvals/:approvalId/comments` | Комментарий на approval'е |
| `POST /api/approvals/:approvalId/request-revision` | (board) попросить ревизию |
| `POST /api/approvals/:approvalId/resubmit` | (requester) пересдать |
| `GET /api/approvals/:approvalId/issues` | Связанные issue |

### 4.4 Issues + comments + checkout

| Endpoint | Описание |
|---|---|
| `GET /api/issues/:id` | Детали issue |
| `GET /api/issues/:id/heartbeat-context` | Компактный контекст для heartbeat |
| `PATCH /api/issues/:id` | Update (status, assignee, priority, parent, title, description + optional `comment`). **ВАЖНО:** см. §3.3 про wake asymmetry |
| `POST /api/issues/:id/comments` | Добавить комментарий (будит assignee + @-mentions) |
| `GET /api/issues/:id/comments` | Список комментариев |
| `GET /api/issues/:id/comments?after=<id>&order=asc` | Delta-опрос после определённого комментария |
| `POST /api/issues/:id/checkout` | Захватить execution lock для работы над issue |
| `POST /api/issues/:id/release` | Отпустить lock |
| `DELETE /api/issues/:id` | Удалить |
| `GET /api/companies/:companyId/issues?q=<search>&assigneeAgentId=<id>&status=<st>` | Поиск/фильтр |
| `POST /api/companies/:companyId/issues` | Создать issue (с `parentId` для subtask) |

### 4.5 Issue documents (plan, etc.)

| Endpoint | Описание |
|---|---|
| `PUT /api/issues/:id/documents/:key` | Upsert документа (`plan`, `spec` и т.д.). Body: `{title, format:"markdown", body, baseRevisionId}` |
| `GET /api/issues/:id/documents` | Список документов |
| `GET /api/issues/:id/documents/:key` | Получить |
| `GET /api/issues/:id/documents/:key/revisions` | История |

### 4.6 Attachments

| Endpoint | Описание |
|---|---|
| `POST /api/companies/:companyId/issues/:issueId/attachments` | multipart upload (field=file) |
| `GET /api/issues/:id/attachments` | Список |
| `GET /api/attachments/:id/content` | Скачать |
| `DELETE /api/attachments/:id` | Удалить |

### 4.7 Company skills + plugin config

| Endpoint | Описание |
|---|---|
| `GET /api/companies/:companyId/skills` | Установленные skills |
| `POST /api/companies/:companyId/skills/import` | Импорт skill'а |
| `POST /api/companies/:companyId/skills/scan-projects` | Auto-discover из project workspace'ов |
| `POST /api/agents/:id/skills/sync` | Синхронизировать assigned skills на агенте |

### 4.8 Routines (recurring tasks)

| Endpoint | Описание |
|---|---|
| `POST /api/companies/:companyId/routines` | Создать routine |
| `GET /api/companies/:companyId/routines` | Список |
| `GET /api/routines/:id` | Детали |
| `PATCH /api/routines/:id` | Update |
| `POST /api/routines/:id/triggers` | Добавить trigger (schedule/webhook/api) |
| `PATCH /api/routine-triggers/:id` | Update trigger |
| `DELETE /api/routine-triggers/:id` | Удалить trigger |
| `POST /api/routines/:id/run` | Ручной запуск |
| `GET /api/routines/:id/runs` | История запусков |
| `POST /api/routine-triggers/public/:publicId/fire` | Внешний webhook |

### 4.9 Company import/export

| Endpoint | Описание |
|---|---|
| `POST /api/companies/:companyId/imports/preview` | Preview импорт (CEO-safe) |
| `POST /api/companies/:companyId/imports/apply` | Применить |
| `POST /api/companies/:companyId/exports/preview` | Preview export |
| `POST /api/companies/:companyId/exports` | Сгенерировать export package |

### 4.10 Dashboard + meta

| Endpoint | Описание |
|---|---|
| `GET /api/companies/:companyId/dashboard` | Агрегированный дашборд |
| `GET /api/companies/:companyId/agents` | Список всех агентов |
| `GET /api/heartbeat-runs/:runId/log?offset=X&limitBytes=Y` | Поток логов run'а (используется UI для live-tail) |
| `GET /llms/agent-configuration.txt` | Текстовый референс для агентов |
| `GET /llms/agent-configuration/:adapterType.txt` | Adapter-specific config |
| `GET /llms/agent-icons.txt` | Список разрешённых icon values |

---

## 5. Доступ и авторизация

### 5.1 SSH на сервер

```bash
ssh imac-ssh.ant013.work
# пароль: <в секрет-хранилище>
```

Путь до репо на сервере: `/Users/Shared/Ios/Medic`

### 5.2 Embedded PostgreSQL (прямой SQL)

```
host=127.0.0.1
port=54329
user=paperclip
password=paperclip
database=paperclip
```

Дефолтные креды — это hardcoded в `@paperclipai/server/dist/index.js`, не секрет (только на localhost слушает).

Нет нативного `psql` — можно через node:
```bash
/Users/anton/.nvm/versions/node/v20.20.2/bin/node -e '
const {Client}=require("/Users/anton/.npm/_npx/43414d9b790239bb/node_modules/pg");
(async()=>{
  const c=new Client({host:"127.0.0.1",port:54329,user:"paperclip",password:"paperclip",database:"paperclip"});
  await c.connect();
  const r = await c.query("SELECT name, status FROM agents WHERE company_id=$1", ["7c094d21-a02d-4554-8f35-730bf25ea492"]);
  console.log(r.rows);
  await c.end();
})()
'
```

### 5.3 `.env` файл paperclip'а

`/Users/anton/.paperclip/instances/default/.env` содержит:

```
PAPERCLIP_AGENT_JWT_SECRET=<64-hex-string — secret для подписи агентских JWT>
```

Опциональные переменные:
- `PAPERCLIP_AGENT_JWT_TTL_SECONDS` (default 48h)
- `PAPERCLIP_AGENT_JWT_ISSUER` (default `"paperclip"`)
- `PAPERCLIP_AGENT_JWT_AUDIENCE` (default `"paperclip-api"`)

### 5.4 Агентский JWT (HS256)

Формат (из `@paperclipai/server/dist/agent-auth-jwt.js`):

```js
header = { alg: "HS256", typ: "JWT" }
claims = {
  sub: "<agent_id>",
  company_id: "<company_id>",
  adapter_type: "claude_local",
  run_id: "<heartbeat_run uuid>",    // обязательно, должен существовать в heartbeat_runs
  iat: <unix_sec>,
  exp: <unix_sec>,
  iss: "paperclip",
  aud: "paperclip-api"
}
```

Signing: `HMAC-SHA256(PAPERCLIP_AGENT_JWT_SECRET, `${base64url(header)}.${base64url(claims)}`).base64url`

**Секрет берётся как UTF-8 string напрямую, НЕ hex-декодируется** (несмотря на hex-like формат value).

Пример crafting'а и использования:

```js
const crypto = require("crypto");
const fs = require("fs");
const secret = fs.readFileSync("/Users/anton/.paperclip/instances/default/.env","utf8")
  .match(/PAPERCLIP_AGENT_JWT_SECRET=(\S+)/)[1];

const now = Math.floor(Date.now()/1000);
const claims = {
  sub: "<agent-id>",
  company_id: "7c094d21-a02d-4554-8f35-730bf25ea492",
  adapter_type: "claude_local",
  run_id: "<recent-heartbeat_run-uuid>",
  iat: now,
  exp: now + 3600,
  iss: "paperclip",
  aud: "paperclip-api"
};
const header = { alg: "HS256", typ: "JWT" };
const b64u = o => Buffer.from(JSON.stringify(o),"utf8").toString("base64url");
const signingInput = b64u(header) + "." + b64u(claims);
const sig = crypto.createHmac("sha256", secret).update(signingInput).digest("base64url");
const jwt = signingInput + "." + sig;

// Use:
const req = http.request({
  hostname: "127.0.0.1", port: 3100,
  path: "/api/issues/<id>/comments", method: "POST",
  headers: {
    "Authorization": "Bearer " + jwt,
    "X-Paperclip-Run-Id": "<same-run_id-as-claim>",
    "Content-Type": "application/json"
  }
}, res => { /* ... */ });
```

### 5.5 Agent API keys (persistent tokens)

Таблица `agent_api_keys`: `id, agent_id, company_id, name, key_hash, last_used_at, revoked_at, created_at`.

**Raw key НЕ хранится** — только hash (bcrypt/scrypt/argon-style). Получить существующий ключ без его raw-значения невозможно.

Создать новый ключ:
```bash
curl -X POST "http://127.0.0.1:3100/api/agents/<agent-id>/keys" \
  -H "Authorization: Bearer <valid-jwt-or-existing-api-key>" \
  -H "Content-Type: application/json" \
  -d '{"name": "admin-ops"}'
# Response содержит raw key ОДИН раз, сохрани
```

Использование API key в запросах: тот же header `Authorization: Bearer <raw-key>`.

### 5.6 User auth (Better-auth session)

UI пользователя работает через Better-auth session cookie:
```
Cookie: __Secure-better-auth.session_token=<...>
```
Видно в server.log запросах, не передаётся через API программно — это UI-only path.

### 5.7 Другие секреты на сервере

- **Anthropic API key** (для LLM): `/Users/anton/.paperclip/instances/default/config.json` → `llm.apiKey`
- **Cloudflare tunnel config**: `~/Library/LaunchAgents/com.cloudflare.*.plist`

---

## 6. Управление paperclip через терминал

### 6.1 Состояние сервера

```bash
# Процесс жив?
ps aux | grep paperclipai | grep -v grep

# Автозапуск
launchctl print gui/$(id -u)/com.paperclip.server 2>&1 | head -20
cat ~/Library/LaunchAgents/com.paperclip.server.plist

# Логи
tail -50 /Users/anton/.paperclip/instances/default/logs/server.log
tail -50 /Users/anton/paperclip/logs/paperclip.log
```

**ВНИМАНИЕ:** на нашем сервере LaunchAgent plist лежит, но **не зарегистрирован в launchd** (`launchctl print` возвращает "Could not find service"). Paperclip сейчас запускается вручную через терминал — видно по именам лог-файлов `paperclip.signup-disable.log`, `paperclip.auth-enable.log` и т.д. После перезагрузки iMac paperclip сам не поднимется.

Регистрация автозапуска (после ручной остановки текущего процесса):
```bash
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.paperclip.server.plist
```

### 6.2 Запуск вручную

```bash
cd /Users/anton/paperclip
source ~/.nvm/nvm.sh
npx paperclipai run
```

### 6.3 CLI команды paperclipai

Из `paperclipai/dist/index.js`, доступны как подкоманды:

```bash
npx paperclipai <command>
```

Основные (видно по `commander` registrations):
- `run` — запустить сервер
- `heartbeat-run --agent-id <uuid>` — вручную invoke heartbeat (вызывает `POST /api/agents/:id/wakeup`)
- `company import <path-or-url>` — импорт company package (agents + projects + issues)
- `company export` — экспорт
- `configure` — onboarding / изменить настройки
- `doctor` — диагностика

CLI читает `~/.paperclip-cli.toml` для `api_base` + `api_key` при работе через HTTP.

### 6.4 Ключевые пути на диске

```
~/paperclip/                                    # рабочая дир для launchd
  logs/                                         # stdout/stderr paperclipai
    paperclip.log
    paperclip.error.log
    paperclip.startup.log
    paperclip.signup-disable.log                # следы ручных запусков с разными флагами
    paperclip.auth-enable.log

~/.paperclip/
  instances/default/
    .env                                        # PAPERCLIP_AGENT_JWT_SECRET
    config.json                                 # server/auth/storage/llm/db config
    companies/
      <company-id>/
        agents/
          <agent-id>/
            instructions/
              AGENTS.md                         # live bundle — что агент читает при старте
              <other files>
    data/
      backups/                                  # pg_dump hourly, retention 30 days
      storage/                                  # file uploads
      run-logs/<company>/<agent>/
        <run-id>.ndjson                         # raw Claude Code session logs
    db/                                         # embedded PostgreSQL data dir
      postmaster.pid
      pg_hba.conf
      postgresql.conf
    logs/
      server.log                                # paperclip server (HTTP, DB, scheduler)
    secrets/
      master.key                                # local_encrypted secrets provider
    workspaces/<workspace-id>/
      .claude/settings.json                     # per-workspace plugin enablement

/Users/Shared/Ios/Medic/                        # main Medic repo (agent cwd)
  paperclips/
    roles/     fragments/     dist/     build.sh     README.md

~/.claude/                                      # Claude Code user config
  settings.json                                 # enabled plugins list
  plugins/
    cache/
      claude-plugins-official/{superpowers, pr-review-toolkit, code-review}/
      voltagent-subagents/{voltagent-qa-sec, voltagent-meta}/
  commands/                                     # user-defined slash commands

~/.claude.json                                  # MCP servers config (mcpServers dict)
```

### 6.5 Типовые диагностические запросы

```sql
-- Все агенты + статусы
SELECT name, status, last_heartbeat_at, pause_reason FROM agents
  WHERE company_id = '<company-id>' ORDER BY name;

-- Wake-ups за последний час
SELECT a.name, w.source, w.reason, w.status, w.requested_at
FROM agent_wakeup_requests w
JOIN agents a ON a.id = w.agent_id
WHERE w.company_id = '<company-id>'
  AND w.requested_at > NOW() - INTERVAL '1 hour'
ORDER BY w.requested_at DESC;

-- Heartbeat runs за час
SELECT a.name, hr.status, hr.started_at, hr.finished_at, hr.error_code
FROM heartbeat_runs hr
JOIN agents a ON a.id = hr.agent_id
WHERE hr.company_id = '<company-id>'
  AND hr.started_at > NOW() - INTERVAL '1 hour'
ORDER BY hr.started_at DESC;

-- Активные issue с assignee
SELECT identifier, status, title, assignee_agent_id, execution_run_id
FROM issues
WHERE company_id = '<company-id>'
  AND status NOT IN ('done','cancelled','backlog')
ORDER BY updated_at DESC LIMIT 20;

-- Issue execution locks (кто держит)
SELECT identifier, execution_run_id, execution_agent_name_key, execution_locked_at
FROM issues WHERE execution_run_id IS NOT NULL;

-- Последние комментарии с @-mentions
SELECT i.identifier, a.name AS author, ic.body, ic.created_at
FROM issue_comments ic
JOIN issues i ON i.id = ic.issue_id
LEFT JOIN agents a ON a.id = ic.author_agent_id
WHERE i.company_id = '<company-id>'
  AND ic.body LIKE '%@%'
ORDER BY ic.created_at DESC LIMIT 20;

-- Pending approvals
SELECT type, status, created_at, id FROM approvals
WHERE company_id = '<company-id>'
  AND status IN ('pending','revision_requested')
ORDER BY created_at DESC;
```

### 6.6 Парсинг run logs

Каждый run создаёт NDJSON в `~/.paperclip/instances/default/data/run-logs/<company>/<agent>/<run-id>.ndjson`.

Формат: каждая строка — `{"ts":"...", "stream":"stdout|stderr", "chunk":"<json-string-of-claude-event>"}`.

Внутри `chunk` — события Claude Code: `system.init`, `assistant`, `user`, `tool_use`, `tool_result`, `result` (финальный).

Последняя строка — `type:"result"` с `subtype:"success"`, `terminal_reason:"completed"`, `total_cost_usd`, и итоговый текст в `result.result`.

Чтобы вытащить все tool_use Bash commands из run'а:
```bash
python3 -c "
import json
for line in open('<run-id>.ndjson'):
    try:
        o = json.loads(line)
        inner = json.loads(o.get('chunk',''))
        if inner.get('type')=='assistant':
            for c in inner.get('message',{}).get('content',[]):
                if c.get('type')=='tool_use' and c.get('name')=='Bash':
                    print(c.get('input',{}).get('command','')[:500])
                    print('---')
    except: pass
"
```

### 6.7 Ручной wake агента

**Через API (правильный путь):**
```bash
curl -X POST "http://127.0.0.1:3100/api/agents/<agent-id>/wakeup" \
  -H "Authorization: Bearer <jwt-or-api-key>" \
  -H "Content-Type: application/json" \
  -d '{"source":"on_demand","triggerDetail":"manual","reason":"manual unblock"}'
```

**Через direct SQL (НЕ РЕКОМЕНДУЕТСЯ):** INSERT в `agent_wakeup_requests` напрямую не даст эффекта — шедулер поллит `heartbeat_runs`, а он создаётся через `enqueueWakeup()` в `services/heartbeat.js` которая делает много бизнес-логики (budget check, execution lock, session resolution). Прямой SQL-insert минует всю эту логику.

### 6.8 Публичный URL и cloudflared

Публичный URL `https://paperclip.ant013.work` работает через cloudflared tunnel (LaunchAgent'ы `com.cloudflare.cloudflared.plist` + `com.cloudflare.tunnel.plist`). Логи туннеля в `/Users/anton/paperclip/logs/cloudflared.{log,error.log}`.

### 6.9 Backup

Встроенный pg_dump каждый час (`config.json` → `database.backup.intervalMinutes: 60`), retention 30 дней:
```
~/.paperclip/instances/default/data/backups/paperclip-YYYYMMDD-HHMMSS.sql
```

Восстановление — через стандартный `psql < backup.sql` (потребуется внешний psql — установить через `brew install libpq` и использовать `/opt/homebrew/opt/libpq/bin/psql` на Apple Silicon, или `/usr/local/opt/libpq/bin/psql` на Intel).

---

## 7. MCP + плагины (per-agent)

### 7.1 MCP servers (9, общие в `~/.claude.json`)

| Имя | Command |
|---|---|
| filesystem | `npx @modelcontextprotocol/server-filesystem /Users/Shared/Ios /Users/anton` |
| github | `npx @modelcontextprotocol/server-github` |
| supabase | `npx @supabase/mcp-server-supabase` |
| magic | `npx @21st-dev/magic` |
| context7 | `npx @upstash/context7-mcp` |
| playwright | `npx @playwright/mcp@latest` |
| sequential-thinking | `npx @modelcontextprotocol/server-sequential-thinking` |
| tavily | `npx tavily-mcp@0.1.2` |
| serena | `serena start-mcp-server --context=claude-code --project /Users/Shared/Ios/Medic` |

### 7.2 Плагины + per-workspace overrides

5 плагинов глобально включены в `~/.claude/settings.json`. Per-workspace `settings.json` в `~/.paperclip/instances/default/workspaces/<id>/.claude/settings.json` оверрайдит.

Текущая матрица:

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

### 7.3 Skills (14 из superpowers)

```
brainstorming, dispatching-parallel-agents, executing-plans,
finishing-a-development-branch, receiving-code-review, requesting-code-review,
subagent-driven-development, systematic-debugging, test-driven-development,
using-git-worktrees, using-superpowers, verification-before-completion,
writing-plans, writing-skills
```

Плюс paperclip-специфичные (из `@paperclipai/server`): `paperclip`, `paperclip-create-agent`, `paperclip-create-plugin`, `para-memory-files`.

### 7.4 Subagents (31, по 4 плагинам)

- **superpowers (1):** `code-reviewer`
- **pr-review-toolkit (6):** `code-reviewer, code-simplifier, comment-analyzer, pr-test-analyzer, silent-failure-hunter, type-design-analyzer`
- **voltagent-meta (9):** `agent-organizer, context-manager, error-coordinator, it-ops-orchestrator, knowledge-synthesizer, multi-agent-coordinator, performance-monitor, task-distributor, workflow-orchestrator`
- **voltagent-qa-sec (15):** `accessibility-tester, ad-security-reviewer, ai-writing-auditor, architect-reviewer, chaos-engineer, code-reviewer, compliance-auditor, debugger, error-detective, penetration-tester, performance-engineer, powershell-security-hardening, qa-expert, security-auditor, test-automator`

### 7.5 Slash-commands

| Command | Источник |
|---|---|
| `/code-review` | code-review plugin |
| `/review-pr` | pr-review-toolkit |
| `/brainstorm`, `/execute-plan`, `/write-plan` | superpowers |
| `/superpowers:*` (14) | superpowers skills |
| `/paperclip`, `/paperclip-create-agent`, `/paperclip-create-plugin`, `/para-memory-files` | paperclipai |

---

## 8. Типовые траблшут-сценарии

### 8.1 «Цепочка остановилась после шага X»

1. `SELECT ... FROM agent_wakeup_requests WHERE requested_at > NOW() - INTERVAL '1 hour'` — есть ли вообще wake-ups после X?
2. Если **нет** — handoff сломан. Проверь последний комментарий агента X:
   - Есть ли `@NextAgent` с пробелом? (Bugs #1, #2)
   - Использовал PATCH с comment или POST /comments? (Bug #3)
   - Менялся ли assignee?
3. Если **есть, но `status=skipped`** — `reason` расскажет почему (budget, heartbeat.disabled, wakeOnDemand.disabled, issue_execution_locked, issue_execution_issue_not_found)
4. Если **есть `status=queued` но давно** — шедулер не забрал. Проверь что paperclip процесс жив (`ps aux`) и `server.log` на ошибки.

### 8.2 «Агент получил wake но сразу завершился»

Смотри run log в `~/.paperclip/instances/default/data/run-logs/<company>/<agent>/<run-id>.ndjson`. Финальная запись — `type:"result"`. Если `terminal_reason:"completed"` + `stop_reason:"end_turn"` и короткий `result` — агент "idle exit". Это OK если нет назначений (см. fragment `heartbeat-discipline.md` правило 1), это проблема если задание было.

### 8.3 «UI показывает wrong state»

UI поллит API (`GET /issues/...`, `GET /heartbeat-runs/.../log`). Если direct SQL UPDATE — UI может увидеть изменение сразу на след polling cycle (~2s). Но server-side caches могут запаздывать при нестандартных путях (мы видели это когда `INSERT agent_wakeup_requests` напрямую — у нас не было запущенного `heartbeat_run`, scheduler не увидел).

### 8.4 «Нужно принудительно перезагрузить инструкции агента»

`cp /Users/Shared/Ios/Medic/paperclips/dist/<role>.md /Users/anton/.paperclip/instances/default/companies/<company>/agents/<agent-id>/instructions/AGENTS.md`

Или через API:
```bash
curl -X PUT "http://127.0.0.1:3100/api/agents/<id>/instructions-bundle/file" \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d "{\"path\":\"AGENTS.md\",\"content\":$(jq -Rs . < dist/<role>.md)}"
```

Paperclip читает файл заново при каждом run'е — перезапуск сервера не нужен.

### 8.5 «Восстановить сломанную цепочку без агентов»

Post а user-comment в UI на соответствующую issue с `@<NextAgent>` (имя без пробелов, пробел после). Это единственный чистый путь — board может писать без JWT (cookie-auth) и без execution lock.

---

## 9. Mapping: workspace UUID ↔ agent

| Agent | Agent UUID | Workspace UUID |
|---|---|---|
| BackendEngineer | `cdf1455f-0873-465a-b1d5-a581272c608e` | same |
| CEO | `419d56ec-e3da-47bc-bce9-2979f100d8b9` | same |
| CodeReviewer | `cf52c981-165e-4239-a2bb-f590be87de79` | same |
| CTO | `780ec10f-f42b-415e-9b38-e89b08510806` | same |
| iOSEngineer | `c47eb69e-5e77-46f8-922f-d862b682dbee` | same |
| KMPEngineer | `1222c2f7-cee8-43b3-8c7d-1ecc5a980b99` | same |
| QAEngineer | `1f65199b-4f8e-4d92-9c44-4a2ea0a2bd40` | same |
| ResearchAgent | `5085cd02-2b61-48c4-9115-79824c45473f` | same |
| UXDesigner | `20b806a1-1618-4bf9-ae6d-fae4226c5e61` | same |

Company ID: `7c094d21-a02d-4554-8f35-730bf25ea492`
Project ID: `2a87ab6b-fe11-495d-af01-0eb9abbc2baa` (Medic)

---

## 10. Что можно улучшить дальше (upstream)

1. **Regex fix в парсере @-mentions** — в `@paperclipai/server/dist/services/issues.js:findMentionedAgents` заменить `/\B@([^\s@,!?.]+)/g` на что-то более liberal (например `/\B@([\w-]+)/g` или trim punctuation после capture). Pull request в апстрим, либо локальный patch в `node_modules` после каждого `npx` upgrade.

2. **Унифицировать PATCH и POST wake-up логику** — чтобы `PATCH /issues` с comment полем также будил assignee, как `POST /comments`. Сейчас это скрытая асимметрия, ловит всех кто читает SKILL.md reference.

3. **Написать paperclip plugin** через `paperclip-create-plugin` skill для автоматических smoke-тестов handoff цепочек (создать issue → assign → комментировать → проверить wake появился → assert chain continues).

4. **Зарегистрировать LaunchAgent в launchd** — сейчас сервер запущен вручную, при перезагрузке iMac он не поднимется. Команда в §6.1.

---

_Документ собран по результатам сессии 2026-04-15. При расхождениях с кодом paperclip'а — **код истина**; обновляй этот док по мере новых находок._
