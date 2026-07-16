# UAudit: русские Telegram-summary и компактные итоговые отчёты

**Статус:** revision 2, предложено к реализации после согласования

**Дата:** 2026-07-16

**Ветка:** `feature/uaudit-russian-audit-delivery`

**Базовый commit:** `796c60dea2ab0c59e9c5b5c046e955d82a2870e6` (`origin/develop`)

**Review:** два независимых multi-agent прохода (UX/контракт, feasibility,
adversarial state)

## 1. Цель и критерий успеха

Сделать единым и русскоязычным пользовательский результат UAudit для четырёх
потоков:

- iOS PR-аудит;
- Android PR-аудит;
- iOS daily version-branch delta-аудит;
- Android daily version-branch delta-аудит.

Telegram сразу показывает короткий summary с общим количеством уникальных
замечаний и разбивкой по severity. Если полный аудит завершён без замечаний,
Telegram получает только text message, а итоговый Markdown физически
отсутствует. Если замечания есть либо аудит неполный, один Telegram document
содержит русский summary в caption и компактный русский Markdown, который после
короткой шапки сразу начинается с замечаний.

Успех означает, что число в Telegram воспроизводимо из машинных артефактов,
нулевой результат не скрывает неполное покрытие, сообщение всегда попадает в
UAudit route, а daily cursor меняется только после подтверждённой доставки.

## 2. Предпосылки и принятые решения

- `finding_count` — число уникальных findings после канонической дедупликации.
  Ограничения, методология, конфликты, `no_finding_areas` и сами результаты
  проверки в это число не входят.
- Пользовательские Telegram-summary и конечные `audit.md` / `audit-final.md`
  русифицируются. Машинные ключи и enum-значения остаются на английском;
  `title`, `evidence`, `impact` и `recommendation`, из которых строится отчёт,
  записываются по-русски уже в новом structured contract.
- Severity ladder не меняется: `Critical`, `Block`, `Important`,
  `Observation`.
- Полный нулевой результат и неполный нулевой результат различаются. Только
  `audit_status=complete` вместе с `finding_count=0` означает «отчёт не нужен».
  При `audit_status=partial` отчёт обязателен даже при нуле: иначе пользователь
  увидит ложный сигнал «проблем нет», хотя часть проверки не состоялась.
- При отсутствии matching receipt resume повторяет неоднозначную попытку. При
  справедливых retries это даёт **at-least-once retry semantics**, но не
  exactly-once: авария между успешным Telegram API-вызовом и записью receipt
  может привести к повторному сообщению.
- Pinned Telegram plugin `c0423e45` маршрутизирует через `fileRoutes` только
  вызовы с `markdownContent`. Text-only вызов сейчас уходит через legacy
  fallback. Поэтому безопасный нулевой режим требует минимального изменения
  плагина и нового pinned SHA.
- Исторические phase_f артефакты и baseline-файлы не переписываются.
- Bundle size gate для dispatcher остаётся `<=100` строк и `<=5200` байт.
  Инструкции сначала сокращаются; лимит нельзя повышать молча.

## 3. Объём работ

### Входит в scope

- общий машинный контракт findings для PR и daily-аудитов;
- structured sidecars для всех daily audit stages;
- каноническая дедупликация, severity counts, audit status и verdict;
- обязательный детерминированный runtime helper для schema validation,
  canonicalization, rendering, receipt validation и cursor compare-and-set;
- атомарная публикация `canonical-findings.json`, итогового MD и
  `delivery-summary.json`;
- русский Telegram-summary в document caption или text-only message;
- компактные русские шаблоны PR и daily отчётов;
- минимальное расширение Telegram plugin: одинаковый `fileRoutes` routing для
  route-aware document и text-only вызовов;
- pin нового plugin commit в Gimle-Palace;
- delivery receipt, безопасный resume и daily cursor gate;
- single-active-run lock для каждой daily routine;
- backward-compatible cutover для уже запущенных legacy runs;
- source-инструкции, generated UAudit bundles, runbook и тесты контрактов.

### Не входит в scope

- изменение логики поиска замечаний или состава audit-команды;
- перевод внутренних рассуждений и промежуточных human-readable stage MD;
- изменение UAudit chat/topic, `fileRoutes`, токенов и permission model;
- выдача Telegram action не-delivery агентам;
- добавление exactly-once/idempotency протокола в Telegram plugin;
- общий рефакторинг plugin routing за пределами описанного text-only случая;
- исправление существующего расхождения между runbook и infra overlays по
  чтению `auth.json`, если оно не блокирует этот контракт.

## 4. Репозитории и границы изменений

Изменение состоит из двух согласованных срезов.

### 4.1. Telegram plugin

Репозиторий: `ant013/paperclip-plugin-telegram`, текущий pin `c0423e45`.

Минимально ожидаются:

- `src/worker.ts` — route resolution для text-only вызовов с route context;
- `tests/send-to-telegram.test.ts` — позитивные, негативные и legacy cases;
- `README.md` — актуальный routing contract;
- manifest/version metadata только если этого требует принятый release flow.

Перед изменением plugin будет выполнен отдельный repository spec gate: fetch,
проверка его integration branch (ожидается `main`), отдельная ветка, spec-only
commit и согласование. Настоящий документ фиксирует межрепозиторный контракт, но
не заменяет обязательную spec в самом plugin repo.

### 4.2. Gimle-Palace

Основные source-инструкции:

- `paperclips/projects/uaudit/overlays/codex/UWISwiftAuditor.md`;
- `paperclips/projects/uaudit/overlays/codex/UWAKotlinAuditor.md`;
- `paperclips/projects/uaudit/roles-codex/uwi-platform-dispatcher.md`;
- `paperclips/projects/uaudit/roles-codex/uwa-platform-dispatcher.md`;
- `paperclips/projects/uaudit/overlays/codex/UWIInfraEngineer.md`;
- `paperclips/projects/uaudit/overlays/codex/UWAInfraEngineer.md`;
- iOS/Android overlays `SecurityAuditor`, `CryptoAuditor`, `ResearchAgent` и
  `QAEngineer`;
- `docs/paperclip-operations/telegram-report-delivery.md`;
- `paperclips/scripts/versions.env` и тесты pin/install contract;
- `paperclips/projects/uaudit/runtime/uaudit_delivery_contract.py`;
- `paperclips/scripts/bootstrap-project.sh` и его тесты для атомарной установки
  helper в runtime workspace;
- `paperclips/scripts/install-paperclip.sh` и тесты reload/reinstall нового
  plugin pin;
- UAudit contract/fixture tests.

После source-изменений штатный builder обновляет соответствующие
`paperclips/dist/uaudit/codex/*.md` и
`paperclips/dist/uaudit.resolved-assembly.json`. Также отчётливо проверяются
размеры всех 14 затронутых agent bundles, хотя жёсткий byte gate сейчас есть
только у двух dispatcher bundles. Historical phase_f baseline не меняется.

## 5. Состояние аудита и правило «нет отчёта»

Каждый required stage имеет `audit_status`:

- `complete` — заявленный scope проверен;
- `partial` — результат полезен, но есть существенное ограничение покрытия;
- `blocked` — stage не может выдать пригодный результат.

Итоговый status определяется строго:

1. Любой отсутствующий, malformed или `blocked` required stage делает весь
   аудит `blocked`.
2. Если blocked stages нет, но хотя бы один required stage `partial` или имеет
   material limitation, весь аудит `partial`.
3. Только все required stages в `complete` без material limitations дают
   итоговый `complete`.

Для daily required stages: `code`, `security`, `crypto`, `infra`, `qa_verify`.
`research_context` становится required только если research path был вызван;
если research не требовался, dispatcher фиксирует причину пропуска, но не
снижает status.

Для iOS PR required slots:

- `uaudit-swift-audit-specialist`;
- `uaudit-bug-hunter`;
- `uaudit-security-auditor`;
- `uaudit-blockchain-auditor`.

Для Android первый slot заменяется на `uaudit-kotlin-audit-specialist`, ещё три
совпадают. Requested JSON каждого PR subagent расширяется `audit_status`,
`run_binding`, `limitations` и `block_reason` из раздела 6. Отсутствующий,
malformed или blocked slot блокирует весь PR run; complete/partial правила
полностью совпадают с daily.

Матрица публикации:

| Audit status | Findings | Telegram | Итоговый MD | Daily cursor |
|---|---:|---|---|---|
| `complete` | `0` | text-only | отсутствует | после receipt |
| `complete` | `>0` | caption + document | обязателен | после receipt |
| `partial` | любое число | caption + document с предупреждением | обязателен | только после receipt и approval |
| `blocked` | не публикуется | completion message не отправляется | не публикуется | не меняется |

Для partial daily operator/Board должен явно подтвердить продвижение cursor
комментарием `partial audit approved <summary-sha256>`. Infra проверяет stable
actor ID и human actor kind через Paperclip API против operator-owned allowlist
`{{paths.project_root}}/state/partial-approvers.json`. Approval без полного
digest текущего summary, от agent/service actor, от отсутствующего в allowlist
пользователя или для старого summary не принимается. Если API не возвращает
проверяемую identity, cursor остаётся blocked. Доставка отчёта может состояться
до approval, но issue, routine lock и cursor остаются незавершёнными.
Infra сохраняет полученные comment ID/text/actor metadata в
`$RUN/approval-comments.json`; helper валидирует этот bounded export и allowlist,
но сам не обращается к API.

## 6. Машинный контракт findings

### 6.1. Daily stage sidecars

Human-readable stage MD сохраняются. Рядом каждый stage атомарно пишет JSON:

- `code.findings.json`;
- `security.findings.json`;
- `crypto.findings.json`;
- `infra.findings.json`;
- `qa-verify.findings.json`;
- `research-context.findings.json`, только когда research вызван.

Schema каждого sidecar и PR subagent output:

```json
{
  "schema_version": 1,
  "run_binding": {
    "issue_identifier": "UNS-123",
    "platform": "ios",
    "audit_kind": "daily_delta",
    "generation_created_at": "2026-07-16T10:00:00Z",
    "source_ref": {
      "routine_id": "daily-ios-version-0.49",
      "branch": "version/0.49",
      "from_sha": "0123456789abcdef0123456789abcdef01234567",
      "to_sha": "89abcdef0123456789abcdef0123456789abcdef"
    },
    "input_digests": {
      "profile.json": "64-lowercase-hex",
      "commits.tsv": "64-lowercase-hex",
      "files.tsv": "64-lowercase-hex",
      "diff.patch": "64-lowercase-hex"
    }
  },
  "stage": "security",
  "source_agent": "UWISecurityAuditor",
  "audit_status": "complete",
  "findings": [
    {
      "severity": "Important",
      "file": "Sources/Wallet/Auth.swift",
      "line": 42,
      "area": null,
      "title": "Повторная авторизация не проверяется",
      "evidence": "Краткое проверяемое наблюдение",
      "impact": "Краткое следствие",
      "recommendation": "Одно конкретное действие",
      "needs_runtime_verification": false
    }
  ],
  "limitations": [
    {
      "text": "Runtime-сценарий не запускался",
      "material": false
    }
  ],
  "block_reason": null
}
```

Инварианты:

- unknown fields (`additionalProperties`) запрещены на каждом schema level;
- неизвестная `schema_version`, лишние enum-значения и неверные типы запрещены;
- `run_binding` после canonical JSON serialization совпадает по value/digest с
  `$RUN/run-context.json`; для PR `source_ref` содержит repo/PR URL/base/head и
  digests `pr.json`/`pr.diff`, для daily — routine/branch/FROM/TO и digests
  четырёх prepared inputs;
- `stage` и `source_agent` должны быть точной разрешённой парой из required
  PR-slot либо daily chain; подмена роли блокирует run;
- location задаётся либо парой `file` + положительный `line`, либо непустым
  `area`; одновременно оба варианта не используются;
- `file` — нормализованный POSIX path относительно audit repo, без абсолютного
  пути и `..`;
- `title`, `evidence`, `impact`, `recommendation` не содержат control characters;
- `title` после trim/collapse whitespace не длиннее 160 Unicode code points;
- `evidence + impact + recommendation` после whitespace normalization не
  превышают 120 слов, limitation text — 240 Unicode code points;
- report-facing prose fields записываются по-русски; path, identifiers и
  названия инструментов не переводятся;
- `limitations` не превращаются в findings; `material` является обязательным
  boolean, а не выводится агрегатором из текста;
- `complete` допускает только `material:false`, `partial` требует хотя бы одну
  `material:true`, `blocked` требует непустой `block_reason`;
- sidecar публикуется через temporary file + atomic `mv`, затем helper пишет
  `status/<stage>.done.json` с SHA-256 sidecar и run-binding digest. Пустые
  legacy `.done` не доказывают готовность v1 stage.

PR coordinators запрашивают эту envelope у четырёх required subagents и не
пересчитывают findings из Markdown. Неизменённый legacy PR JSON без status или
run binding считается malformed только для нового v1 handoff.

### 6.2. Каноническая дедупликация

Перед дедупликацией helper:

- file path приводится к POSIX relative form;
- `area` и `title` приводятся к Unicode NFC, затем проходят trim, collapse
  whitespace и Unicode `casefold()`;
- line сохраняется положительным integer;
- location key равен `file:line` либо `area:<normalized-area>`.

Dedup key: `(location_key, normalized_title)`.

При совпадении candidates сортируются по severity rank
`Critical > Block > Important > Observation`, затем по фиксированному порядку
required stages, `source_agent` и canonical raw finding bytes. Первый candidate
становится representative: его location/title/evidence/impact/recommendation
сохраняются без semantic merge. `source_agents` и `stages` объединяются как
лексикографически отсортированные уникальные массивы;
`needs_runtime_verification` равен `any(...)`.

Canonical envelope:

```json
{
  "schema_version": 1,
  "run_binding": {
    "issue_identifier": "UNS-123",
    "platform": "ios",
    "audit_kind": "daily_delta",
    "generation_created_at": "2026-07-16T10:00:00Z",
    "source_ref": {
      "routine_id": "daily-ios-version-0.49",
      "branch": "version/0.49",
      "from_sha": "0123456789abcdef0123456789abcdef01234567",
      "to_sha": "89abcdef0123456789abcdef0123456789abcdef"
    },
    "input_digests": {
      "profile.json": "64-lowercase-hex",
      "commits.tsv": "64-lowercase-hex",
      "files.tsv": "64-lowercase-hex",
      "diff.patch": "64-lowercase-hex"
    }
  },
  "audit_status": "complete",
  "findings": [
    {
      "dedup_key": {
        "location": "Sources/Wallet/Auth.swift:42",
        "title": "повторная авторизация не проверяется"
      },
      "severity": "Important",
      "file": "Sources/Wallet/Auth.swift",
      "line": 42,
      "area": null,
      "title": "Повторная авторизация не проверяется",
      "evidence": "Краткое проверяемое наблюдение",
      "impact": "Краткое следствие",
      "recommendation": "Одно конкретное действие",
      "source_agents": ["UWISecurityAuditor"],
      "stages": ["security"],
      "needs_runtime_verification": false
    }
  ],
  "limitations": [
    {
      "text": "Runtime-сценарий не запускался",
      "material": false,
      "source_agents": ["UWISecurityAuditor"],
      "stages": ["security"]
    }
  ]
}
```

Canonical findings сортируются по severity, location key и normalized title.
Limitations дедуплицируются по `(NFC/collapse/casefold text, material)`, их
sources объединяются и сортируются. JSON сериализуется UTF-8 через
`sort_keys=True`, `ensure_ascii=False`, separators `(',', ':')` и один конечный
LF. SHA-256 вычисляется по этим raw bytes. Unknown fields запрещены.

Результат атомарно публикуется в `$RUN/canonical-findings.json`.

`finding_count = len(canonical.findings)`. Severity counts вычисляются только из
этого списка, поэтому их сумма обязана совпадать с `finding_count`.

### 6.3. Verdict и русские labels

| Machine severity | Русский label |
|---|---|
| `Critical` | `Критические` |
| `Block` | `Блокирующие` |
| `Important` | `Важные` |
| `Observation` | `Наблюдения` |

Verdict:

- есть `Critical` или `Block` → `block` / «блокирует принятие»;
- иначе есть `Important` → `request_changes` / «требуются изменения»;
- иначе при `audit_status=partial` → `inconclusive` /
  «вердикт не вынесен: проверка неполная»;
- иначе → `approve` / «можно принимать».

`audit_status` показывается отдельно от verdict. Partial audit никогда не
называется «чистым» или полностью завершённым; даже при найденных Important или
Block итог дополнительно говорит о неполном покрытии.

### 6.4. Детерминированный runtime helper

Contract реализуется одним stdlib-only Python helper:
`paperclips/projects/uaudit/runtime/uaudit_delivery_contract.py`. Во время
`bootstrap-project.sh uaudit` его bytes атомарно копируются в
`{{paths.team_workspace_root}}/.uaudit-tools/uaudit_delivery_contract.py`,
проверяются по SHA-256 и делаются read-only. Runtime roles используют только
этот deployed path; несовпадение install manifest блокирует v1 run.

Фиксированный CLI:

- `bind-context` — читает authoritative PR/daily intake, вычисляет input digests
  и атомарно пишет `$RUN/run-context.json` до первого audit stage; context
  получает `generation_created_at` один раз, а повторный вызов только валидирует
  существующий immutable context;
- `validate-stage` — валидирует sidecar, run binding, role/stage pair и пишет
  digest-bound stage marker;
- `aggregate` — валидирует полный required input set, выполняет canonicalization,
  определяет status/counts/verdict, рендерит русский text/report и публикует
  summary последним;
- `verify-payload` — перед send повторно проверяет summary, digests, run/handoff
  binding и expected route mode;
- `record-delivery` — принимает сохранённый raw plugin response, проверяет его и
  атомарно создаёт receipt;
- `reconcile-daily` — проверяет receipt/approval/lock и выполняет cursor CAS.

Helper не вызывает Telegram, GitHub или Paperclip API и не читает credentials.
Agents только готовят входы и выполняют внешние actions; count, verdict, bytes,
digests и cursor transition не вычисляются свободным LLM-текстом. Это также
позволяет не помещать полный алгоритм в почти заполненные dispatcher bundles.

## 7. Контракт `delivery-summary.json`

Aggregator публикует `$RUN/delivery-summary.json` последним, как commit record
готового delivery payload. Пример PR:

```json
{
  "schema_version": 1,
  "issue_identifier": "UNS-123",
  "platform": "ios",
  "audit_kind": "pr",
  "audit_status": "complete",
  "run_binding_sha256": "64-lowercase-hex",
  "source_ref": {
    "repo": "unstoppable-wallet-ios",
    "pr_url": "https://github.com/org/repo/pull/456",
    "base_sha": "0123456789abcdef0123456789abcdef01234567",
    "head_sha": "89abcdef0123456789abcdef0123456789abcdef"
  },
  "finding_count": 4,
  "severity_counts": {
    "critical": 0,
    "block": 1,
    "important": 2,
    "observation": 1
  },
  "verdict": "block",
  "material_limitations": [],
  "telegram_text": {
    "file": "telegram-summary.txt",
    "sha256": "64-lowercase-hex"
  },
  "findings": {
    "file": "canonical-findings.json",
    "sha256": "64-lowercase-hex"
  },
  "report": {
    "file": "audit.md",
    "sha256": "64-lowercase-hex"
  },
  "created_at": "2026-07-16T10:00:00Z"
}
```

Для `daily_delta` `source_ref` вместо PR-полей содержит обязательные
`routine_id`, `branch`, `from_sha`, `to_sha`. Для complete zero `report` равен
`null`; canonical findings file всё равно существует и содержит пустой список.
`telegram-summary.txt` существует во всех delivery cases и содержит ровно те
UTF-8 bytes с одним конечным LF, которые Infra передаёт как `text`.
`material_limitations` — стабильный массив текстов всех canonical limitations с
`material:true`; `created_at` равен immutable `generation_created_at` из binding.

Строгая валидация требует:

- все перечисленные поля, `additionalProperties:false` на каждом уровне и
  только поддерживаемую `schema_version`;
- `platform: ios|android`, `audit_kind: pr|daily_delta`,
  `audit_status: complete|partial`;
- `verdict: approve|request_changes|block|inconclusive` и точное соответствие
  status/severity mapping из раздела 6;
- неотрицательные integer counts и все четыре severity keys;
- `finding_count == sum(severity_counts)` и совпадение с canonical file;
- SHA-256 в lowercase hex и совпадение digest каждого указанного файла;
- совпадение `run_binding_sha256` с canonical file, всеми sidecars и
  `$RUN/run-context.json`;
- immutable 40-hex source SHA и валидную привязку к текущему issue/run;
- точное совпадение issue, platform, kind, PR head/base либо daily
  routine/FROM/TO с handoff parameters;
- `report=null` только при `complete + zero`;
- `report.file=audit.md` только для PR и `audit-final.md` только для daily;
- существующий report для positive или partial результата;
- `telegram_text.file=telegram-summary.txt` и размер менее 900 UTF-8 bytes.

Subject/caption выводится из validated `source_ref`, а не принимается как
свободная строка. Новые строки, control characters и непроверенные local paths
в пользовательский текст не попадают.

Generation preflight выполняется до любых удалений:

1. Matching receipt запрещает regeneration; coordinator не меняет artifacts и
   передаёт управление Infra для reconciliation.
2. Conflicting receipt блокирует run.
3. Валидный summary без receipt является immutable generation: при отсутствии
   `status/handoff.done` повторяется только assignment/handoff, при наличии
   marker coordinator выходит.
4. Невалидный существующий summary блокирует run; его нельзя молча заменить.
5. `status/handoff.done` без валидного summary блокирует run.
6. Только при отсутствии summary, receipt и handoff marker разрешено
   начать/возобновить aggregation attempt.

Порядок разрешённого aggregation attempt:

1. Удалить только stale `status/aggregate.done` и незакоммиченные payload
   artifacts предыдущей незавершённой попытки. Никогда не удалять receipt,
   `status/telegram.done`, cursor/workflow markers или `handoff.done`.
2. Проверить все digest-bound required inputs и сформировать canonical findings
   во временном файле.
3. Сформировать и атомарно опубликовать `telegram-summary.txt`.
4. Для positive/partial результата сформировать report во временном файле,
   валидировать и атомарно переименовать. Для complete zero удалить и проверить
   физическое отсутствие **обоих** известных paths: `audit.md` и
   `audit-final.md`.
5. Вычислить digests уже опубликованных text/canonical/report files.
6. Записать, провалидировать и атомарно переименовать `delivery-summary.json`
   **последним**, затем поставить `status/aggregate.done`, получить успешный
   ответ assignment API и только после него поставить `status/handoff.done`.

После публикации summary text/canonical/report/summary immutable. Correction
создаёт новый issue/run generation, а не перезаписывает доставленный payload.
Malformed/blocked входы не дают публиковать новый summary и completion payload.

## 8. Telegram routing contract

### 8.1. Минимальное изменение plugin

Route-aware считается вызов, содержащий хотя бы один routing context field,
поддерживаемый plugin (`projectKey`, `issueIdentifier` или `issueId`). Для него
plugin применяет одну и ту же `fileRoutes` resolution независимо от наличия
`markdownContent`.

- Однозначный match разрешает document или text-only send.
- Unknown, ambiguous, invalid или конфликтующие route inputs завершаются
  ошибкой без fallback и без отправки.
- Отдельный conflict case: `projectKey` не согласуется с route, найденным по
  `issueIdentifier` или resolved `issueId`; explicit project key не может
  замаскировать конфликт.
- Вызов без route context сохраняет существующий `legacy_fallback`; это
  обеспечивает backward compatibility для других consumers.
- Успешный UAudit text-only ответ содержит минимум `ok:true`, `mode:"message"`,
  `routeSource:"file_route"`, `routeName:"UAudit"`, `issueIdentifier` и
  `messageId`.
- Document behavior и caption limit 1024 UTF-8 bytes не меняются.

После plugin tests новый полный 40-hex immutable commit pin записывается в
`paperclips/scripts/versions.env`. Install/pin tests требуют точного ожидаемого
SHA, а не только валидной длины. Поскольку pin host-global, rollout включает
полный plugin suite для всех consumers, backup/rollback, принудительный
reinstall/reload worker даже при уже существующем plugin ID и проверку реально
загруженного SHA. Complete-zero production path включается только после canary
route-aware text-only smoke.

### 8.2. Delivery modes

При `complete + zero` Infra вызывает action с `text` и route context, но без
`markdownContent`/`markdownFileName`; принимает только
`mode=message`, `routeSource=file_route`, `routeName=UAudit`.

При positive или partial результате Infra передаёт `text`,
`markdownContent`, `markdownFileName` и route context одним вызовом; принимает
только `mode=document`, `routeSource=file_route`, `routeName=UAudit`.

`chatId`, raw bot token, URL и `filePath` в agent instructions не добавляются.

## 9. Русский Telegram-summary

Caption/text строится детерминированно и должен быть короче 900 UTF-8 bytes,
оставляя запас до plugin limit. Он всегда содержит status, общее число и все
четыре severity counts в фиксированном порядке.

Полный PR с findings:

```text
Аудит iOS PR #456 завершён
Найдено замечаний: 4
Критические: 0 · Блокирующие: 1 · Важные: 2 · Наблюдения: 1
Вердикт: блокирует принятие
```

Полный PR без findings:

```text
Аудит Android PR #456 завершён
Найдено замечаний: 0
Критические: 0 · Блокирующие: 0 · Важные: 0 · Наблюдения: 0
Вердикт: можно принимать
Итоговый отчёт не формировался
```

Полный daily с findings:

```text
Аудит iOS version/0.49 a1b2c3d..e4f5a6b завершён
Найдено замечаний: 2
Критические: 0 · Блокирующие: 0 · Важные: 1 · Наблюдения: 1
Вердикт: требуются изменения
```

Полный daily без findings:

```text
Аудит Android version/0.49 a1b2c3d..e4f5a6b завершён
Найдено замечаний: 0
Критические: 0 · Блокирующие: 0 · Важные: 0 · Наблюдения: 0
Вердикт: можно принимать
Итоговый отчёт не формировался
```

Partial daily:

```text
Аудит iOS version/0.49 a1b2c3d..e4f5a6b выполнен частично
Найдено замечаний: 0
Критические: 0 · Блокирующие: 0 · Важные: 0 · Наблюдения: 0
Вердикт не вынесен: проверка неполная
Покрытие неполное — ограничения указаны в отчёте
```

Для daily обязательны platform, validated branch и короткий `FROM..TO`; для PR
— platform и номер из validated PR URL. Полные SHA, raw diff, secrets,
абсолютные пути и длинные limitations в caption не попадают.

## 10. Компактный итоговый Markdown

PR template:

```markdown
# Аудит iOS PR #456

- Найдено замечаний: 4
- Вердикт: блокирует принятие

## Замечания

### 1. Блокирующее — краткий заголовок

`Sources/Wallet/Auth.swift:42`

Короткие evidence и impact.

**Что сделать:** одно конкретное действие.

## Ограничения

Только material limitations, влияющие на доверие к результату.

## Техническая информация

Issue, repo/platform, PR URL или branch/range, immutable SHA, scope и время.
```

Daily template начинается так же, но с validated branch/range:

```markdown
# Аудит изменений iOS version/0.49

- Диапазон: `a1b2c3d..e4f5a6b`
- Найдено замечаний: 2
- Вердикт: требуются изменения

## Замечания
```

Правила:

- точный порядок complete: title → summary bullets → `## Замечания`;
- точный порядок partial: title → summary bullets → строка
  `> Проверка выполнена частично` → `## Замечания`;
- порядок findings: `Critical`, `Block`, `Important`, `Observation`, затем
  стабильный location/title order;
- каждый finding содержит severity/title, `file:line` либо понятную область,
  evidence + impact и одну actionable recommendation;
- тело finding не длиннее 120 слов; служебные JSON-поля не печатаются;
- `needs_runtime_verification=true` показывается одной короткой строкой, потому
  что влияет на решение;
- пустые optional sections не рендерятся;
- no-finding areas, конфликты и нематериальные детали не раздувают верх отчёта;
- metadata находятся только внизу.

Нижняя техническая секция сохраняет минимум: issue identifier, repo/platform,
PR URL или daily branch/range, base/head либо FROM/TO SHA, generated time, diff
scope/counts, methodology/source traceability и Android variant impact, когда
применимо. Подробные material limitations находятся только в разделе
`## Ограничения` и не дублируются в metadata.

Complete zero MD не создаётся. Partial zero MD содержит предупреждение,
ограничения и техническую информацию, а `## Замечания` явно говорит, что в
проверенной части замечаний не найдено.

## 11. Delivery state, resume и cursor

Coordinator `handoff.done` означает только готовность handoff и не подтверждает
Telegram delivery. Новый handoff обязательно содержит
`delivery_contract=uaudit-delivery/v1` и фиксированный путь
`$RUN/delivery-summary.json`.

После валидного успешного Telegram response Infra атомарно пишет
`$RUN/delivery-result.json`:

```json
{
  "schema_version": 1,
  "summary_sha256": "64-lowercase-hex",
  "run_binding_sha256": "64-lowercase-hex",
  "mode": "document",
  "route_source": "file_route",
  "route_name": "UAudit",
  "message_id": 123,
  "telegram_text_sha256": "64-lowercase-hex",
  "report_sha256": "64-lowercase-hex",
  "delivered_at": "2026-07-16T10:01:00Z"
}
```

В strict receipt schema `report_sha256` — 64-hex string для document mode и
JSON `null` для message mode.

Затем Infra ставит `$RUN/status/telegram.done`. Receipt означает только
«Telegram подтвердил payload» и никогда не означает, что cursor, comment или
issue status уже завершены.

Resume rules:

- matching receipt при любом наборе markers → не отправлять повторно, а
  последовательно reconcile недостающие cursor, comment и issue transitions;
- receipt с другим summary/report digest, route или mode → block, не отправлять;
- `telegram.done` без receipt, `cursor.done` без matching cursor/receipt или
  `workflow.done` без выполненных prerequisites считаются stale state и
  блокируют run;
- нет receipt и terminal markers → resume может повторить send; duplicates
  допустимы в известном crash window;
- Telegram error или неожиданный response не создаёт receipt/marker и не меняет
  cursor;
- no-op разрешён только когда matching receipt, требуемый cursor state,
  подтверждённый Board comment/status и `$RUN/status/workflow.done` согласованы.

V1 использует разные terminal markers:

- `status/telegram.done` — matching receipt записан;
- `status/cursor.done` — daily cursor CAS применён или подтверждён как уже
  применённый той же generation;
- `status/workflow.done` — required comment и issue status подтверждены Board
  API; для PR это первый terminal marker после Telegram.

`status/delivery.done` не используется новым контрактом. Crash после любого
marker безопасно возобновляет следующие шаги; наличие receipt всегда запрещает
resend.

### 11.1. Single-active daily run

После определения непустого delta и до Stage 1 dispatcher атомарно захватывает
`{{paths.project_root}}/state/locks/<routine_id>.lock` через `mkdir`. Сначала
внутри записываются issue identifier, FROM и TO; после Stage 1 `bind-context`
добавляет run-binding digest атомарной заменой lock metadata до первого audit
stage.

- Та же issue/generation может resume lock.
- Другая issue для этой routine блокируется и не начинает overlapping range.
- Partial run удерживает lock до approval и cursor reconciliation.
- Blocked/crashed lock нельзя steal по времени; его снимает оператор после
  проверки либо Infra после успешного workflow completion.

### 11.2. Cursor compare-and-set

`reconcile-daily` запускается только с matching receipt, matching routine lock и,
для partial, валидным human approval. Он читает cursor и применяет:

1. `cursor.last_successfully_audited_sha == FROM` → атомарно записать `TO` в это
   поле, `last_successful_issue`, `last_successful_at`,
   `last_delivery_summary_sha256` и `last_telegram_message_id`, затем поставить
   `cursor.done`.
2. `cursor.last_successfully_audited_sha == TO` и metadata совпадают с теми же
   summary/receipt → считать CAS уже применённым и поставить отсутствующий
   `cursor.done`.
3. Любое другое значение либо `TO` с другой metadata → block. Нельзя откатывать,
   переписывать более новый cursor или освобождать routine lock.

После `cursor.done` Infra создаёт/проверяет итоговый comment, переводит issue в
целевой status, ставит `workflow.done` и только затем освобождает routine lock.
Ошибка cursor/comment/status не вызывает повторный Telegram send при matching
receipt.

## 12. Cutover и совместимость

- Handoff с `delivery_contract=uaudit-delivery/v1` обязан иметь валидный
  `delivery-summary.json`; иначе доставка блокируется.
- До rollout оператор фиксирует точный allowlist существующих in-flight runs в
  `{{paths.project_root}}/state/legacy-delivery-allowlist.json`: issue/run path,
  audit kind и ожидаемый report SHA-256.
- Unversioned handoff разрешает старый document-only path только при точном
  allowlist match и совпадении report digest. Любой другой unversioned handoff
  после cutover fail-closed.
- Summary при отсутствующем v1 marker, v1 marker без summary и отсутствие обоих
  у не-allowlisted run считаются malformed, а не legacy/zero.
- После доставки каждой allowlisted generation запись удаляется оператором;
  после опустошения allowlist legacy fallback выключается и получает sunset.
- Rollout order: plugin full suite → новый pin → forced reinstall/reload +
  loaded-SHA proof → Gimle helper/source/bundles/tests → dry-run → разрешённый
  оператором document canary → route-aware complete-zero canary. До последнего
  шага complete-zero production path не включается.

## 13. Обработка ошибок и безопасность

- Unknown schema version, malformed sidecar, count mismatch, digest mismatch,
  stale report, run-binding mismatch или неожиданный Telegram route блокируют
  completion.
- Complete zero считается готовым только после удаления `audit.md` и
  `audit-final.md`; старый MD нельзя приложить или оставить как результат
  текущего run.
- Report публикуется раньше summary, поэтому новый summary не может указывать на
  частично записанный файл.
- User-controlled title/location не может добавлять новые caption lines,
  абсолютные paths или traversal segments.
- Telegram action получает только уже провалидированный bounded summary и
  report bytes; raw diff и секреты не отправляются.
- Неожиданная двусмысленность route закрывается ошибкой, а не default chat.
- Agent не заявляет exactly-once и не скрывает возможный duplicate после
  process crash.
- Stage marker без matching sidecar/run-binding digest и summary без matching
  immutable generation считаются stale и не возобновляют workflow.
- Routine lock, cursor CAS и human approver allowlist являются fail-closed
  boundaries; агент не может их обходить по текстовой инструкции в issue.

## 14. Acceptance criteria

1. Все четыре потока выдают русские Telegram-summary и, когда требуется,
   русские компактные MD.
2. Stdlib helper детерминированно формирует raw canonical/text/report/summary
   bytes; повтор на тех же fixtures даёт те же SHA-256.
3. `finding_count` воспроизводится из canonical findings и равен сумме всех
   четырёх severity counts.
4. PR и daily count строятся только из schema-valid, role-valid и run-bound
   structured inputs, не из Markdown.
5. Каноническая дедупликация одинакова для PR и daily, выбирает максимальную
   severity и deterministic representative без semantic merge.
6. Только `complete + zero` не создаёт MD; оба известных report paths физически
   отсутствуют.
7. Partial результат всегда явно помечен, не получает `approve` и всегда имеет
   report, даже при нуле.
8. Blocked/malformed run не отправляет completion message и не меняет cursor.
9. Positive/partial summary является caption того же MD document; complete zero
   отправляется text-only.
10. Оба режима подтверждают `file_route`, route `UAudit` и ожидаемый `mode`.
11. Route-aware text-only plugin вызов fail-closed при unknown, ambiguous и
    conflicting input;
    no-context legacy behavior не меняется.
12. Caption содержит total и все severity counts и занимает менее 900 UTF-8
    bytes на максимальных fixture values.
13. MD после title/summary и optional partial warning сразу показывает findings;
    обязательные metadata
    находятся внизу; тело каждого finding не превышает 120 слов.
14. `delivery-summary.json` публикуется последним, привязан к current run/input
    digests и после публикации immutable.
15. Matching receipt предотвращает resend после crash на последующих шагах;
    документация честно фиксирует оставшееся duplicate window.
16. Resume с receipt всегда reconcile Telegram/cursor/workflow states и не
    превращает промежуточный marker в ошибочный no-op.
17. Daily cursor меняется только compare-and-set после matching receipt/lock, а
    partial cursor — ещё и после digest-bound approval от allowlisted human.
18. Для одной routine существует не более одной активной generation; overlapping
    range не стартует.
19. Legacy document runs работают только по exact pre-rollout allowlist; любой
    malformed/unversioned новый handoff fail-closed.
20. Новый полный plugin SHA закреплён, принудительно загружен runtime worker и
    проверен pin/install/reload proof.
21. Generated bundles соответствуют source и проходят существующие size и
    instruction gates без скрытого повышения лимитов.
22. Runtime helper устанавливается с проверяемым digest; agents не реализуют
    собственные варианты canonicalization/cursor CAS.
23. Только InfraEngineer обладает delivery action; chat ID/token/filePath не
    появляются в audit instructions.

## 15. План проверки

### Plugin tests

- route-aware text-only success с `mode=message`, `file_route`, `UAudit`;
- unknown, ambiguous, invalid и conflicting route contexts fail-closed;
- конфликт `projectKey` против `issueIdentifier` и resolved `issueId`;
- no-context text-only сохраняет `legacy_fallback`;
- document routing и caption limit не регрессируют;
- полный plugin unit test suite проходит до создания нового pin;
- reinstall/reload test подтверждает, что existing plugin ID не сохраняет старый
  worker, а rollback возвращает предыдущий SHA.

В plugin repo выполняются `npm ci`, `npm run typecheck` и `npm test`.

### Gimle fixture/contract tests

- strict schema/additionalProperties, stage-role pairs и unknown-version
  rejection;
- sidecar/canonical run binding и input digest mismatch;
- PR/daily canonicalization, dedup и highest-severity winner;
- deterministic representative, JSON bytes и repeatable SHA;
- missing/malformed/blocked/partial stage propagation;
- typed material limitations и PR/daily status consistency;
- exact total/severity counts и verdict mapping, включая partial
  `inconclusive`;
- complete zero, positive, partial zero и partial positive payloads;
- stale report deletion, report presence и SHA mismatch;
- issue/platform/kind/PR SHA/daily range binding mismatch;
- summary-last contract и fixed report names;
- Russian caption template, ordering и `<900 UTF-8 bytes`;
- report order, bottom metadata и per-finding compactness;
- response mode/route validation;
- receipt/telegram/cursor/workflow crash matrix;
- cursor CAS: FROM, matching TO, conflicting TO и newer cursor;
- single-active routine lock и partial wait;
- allowlisted human approval identity и rejected agent identity;
- exact legacy allowlist, malformed handoff и sunset;
- exact 40-hex plugin pin/install/reload contract;
- helper install digest и missing/tampered helper failure.

Static bundle assertions проверяют wiring, но не считаются доказательством
runtime behavior. Fixture tests напрямую исполняют тот же
`uaudit_delivery_contract.py`, который устанавливается в runtime; отдельной
test-only реализации schema/state machine не создаётся.

Обязательные Gimle commands:

```bash
python3 paperclips/scripts/build_project_compat.py --project uaudit --target codex --inventory check
python3 -m pytest paperclips/tests/test_uaudit_dispatcher_bundles.py
python3 -m pytest paperclips/tests/test_uaudit_delivery_contract.py
python3 -m pytest paperclips/tests -k 'uaudit and (delivery or summary or telegram or pin)'
python3 paperclips/scripts/validate_uaudit_docs.py
python3 paperclips/scripts/validate_instructions.py --repo-root .
./paperclips/validate-codex-target.sh
```

Для dispatcher сначала удаляются повторы и сжимаются формулировки. Если
полезный контракт не помещается в текущие `100 lines / 5200 bytes`, реализация
останавливается для отдельного решения; тестовый gate не повышается автоматически.

Live Telegram smoke выполняется только с явного разрешения оператора и включает
document case, complete-zero message case, loaded plugin SHA proof и проверку
UAudit route. Runbook обновляется так, чтобы оба режима считались штатными и
содержал rollback нового plugin pin/helper.

## 16. Открытые вопросы и stop conditions

Открытых продуктовых вопросов после review нет: приняты fail-closed routing,
run-bound structured inputs, deterministic helper, partial-report rule,
at-least-once retry semantics, single-active routine и сохранение текущего
bundle gate.

Новая остановка и согласование требуются, если:

- plugin repo использует другой integration/release flow, чем обнаруженный;
- stdlib helper нельзя атомарно установить в общий runtime path без расширения
  permission model;
- dispatcher нельзя безопасно уместить в существующий size gate;
- Paperclip API не предоставляет stable human actor identity для partial
  approval: delivery допустима, но cursor остаётся blocked до нового решения;
- plugin canary обнаруживает регрессию другого route-aware text-only consumer;
- изменение требует chat/topic/token/permission migration.
