# UAudit: русские Telegram-summary и компактные итоговые отчёты

**Статус:** предложено к реализации
**Дата:** 2026-07-16
**Ветка:** `feature/uaudit-russian-audit-delivery`
**Базовый commit:** `796c60dea2ab0c59e9c5b5c046e955d82a2870e6` (`origin/develop`)

## 1. Цель

Сделать единым пользовательский результат UAudit для четырёх потоков:

- iOS PR-аудит;
- Android PR-аудит;
- iOS daily version-branch delta-аудит;
- Android daily version-branch delta-аудит.

Telegram должен сразу показывать короткий итог на русском языке и общее
количество найденных замечаний. Итоговый Markdown создаётся и прикладывается
только тогда, когда после дедупликации найдено хотя бы одно замечание. Сам
Markdown открывается сразу на замечаниях; служебные сведения находятся внизу.

## 2. Предпосылки и принятые решения

- `finding_count` — количество уникальных findings после существующей
  дедупликации. `limitations`, `methodology`, конфликты между агентами и
  `no_finding_areas` в это число не входят.
- Русифицируются пользовательские Telegram-summary и конечные файлы
  `audit.md` / `audit-final.md`.
- Внутренние JSON-контракты subagent-ов, машинные enum-значения severity и
  промежуточные stage-артефакты сохраняют текущий формат. Это ограничивает
  изменение границей агрегации и доставки.
- Для результата с findings Telegram получает один document message: поле
  `text` используется как подпись к приложенному `markdownContent`.
- Для результата без findings Telegram получает text-only summary без
  `markdownContent`; конечный MD не создаётся.
- Pinned Telegram plugin commit `c0423e45` поддерживает `text` как caption при
  одновременном `markdownContent` и ограничивает caption 1024 байтами. Изменение
  самого плагина не требуется.
- Успешный daily-аудит без findings остаётся успешно обработанным диапазоном.
  Cursor обновляется после успешной text-only доставки так же, как сейчас
  обновляется после успешной document-доставки.

## 3. Объём работ

### Входит в scope

- единый контракт агрегации для PR и daily-аудитов на обеих платформах;
- устойчивый машинный summary-артефакт;
- условное создание итогового Markdown;
- русский Telegram-summary как caption или text-only message;
- компактная русская структура итогового Markdown;
- согласованная retry/resume-семантика и daily cursor gate;
- обновление UAudit runbook, source-инструкций, generated bundles и тестов
  контрактов.

### Не входит в scope

- изменение `paperclip-plugin-telegram`;
- перевод внутренних subagent JSON и промежуточных `code.md`, `security.md`,
  `crypto.md`, `infra.md`, `research-context.md`, `qa-verify.md`;
- изменение набора audit-агентов, severity ladder или алгоритма дедупликации;
- изменение Telegram `fileRoutes`, chat ID, токенов или permission model;
- изменение логики поиска замечаний.

## 4. Архитектура

Граница ответственности остаётся прежней:

1. Coordinator/dispatcher агрегирует результаты и является единственным
   источником итогового количества findings.
2. Он атомарно записывает `delivery-summary.json`.
3. При `finding_count > 0` он дополнительно атомарно записывает компактный
   русский `audit.md` или `audit-final.md`.
4. Infra delivery-agent валидирует summary и выбирает ровно один режим:
   document с caption либо text-only.
5. Для daily-аудита cursor меняется только после подтверждённой успешной
   Telegram-доставки выбранного режима.

Infra не пересчитывает findings из Markdown. Это исключает расхождения между
iOS/Android и PR/daily потоками.

## 5. Контракт `delivery-summary.json`

Агрегатор создаёт в корне `$RUN` следующий внутренний артефакт:

```json
{
  "schema_version": 1,
  "issue_identifier": "UNS-123",
  "platform": "ios",
  "audit_kind": "pr",
  "subject": "unstoppable-wallet-ios#456",
  "finding_count": 4,
  "severity_counts": {
    "critical": 0,
    "block": 1,
    "important": 2,
    "observation": 1
  },
  "verdict": "request_changes",
  "report_file": "audit.md"
}
```

Допустимые значения:

- `platform`: `ios | android`;
- `audit_kind`: `pr | daily_delta`;
- `verdict`: `approve | request_changes | block`;
- `report_file`: `audit.md | audit-final.md | null`.

Инварианты:

- `finding_count == sum(severity_counts.values())`;
- `finding_count == 0` требует `report_file == null`;
- `finding_count > 0` требует непустой `report_file` и существующий файл;
- summary записывается через временный файл и атомарный `mv`;
- completed/handoff markers ставятся только после валидации summary.

## 6. Telegram-summary

### Есть замечания

Telegram action вызывается с `text`, `markdownContent` и
`markdownFileName`. Поле `text` становится caption того же MD-документа.

Пример:

```text
Аудит iOS PR #456 завершён
Найдено замечаний: 4
Блокирующих: 1 · Важных: 2 · Наблюдений: 1
Вердикт: требуются изменения
```

### Замечаний нет

Telegram action вызывается только с `text`; `markdownContent` и
`markdownFileName` отсутствуют.

```text
Аудит Android PR #456 завершён
Замечаний не найдено: 0
Итоговый отчёт не формировался
```

Шаблон должен оставаться заметно короче лимита caption в 1024 байта. Raw diff,
секреты, абсолютные локальные пути и полные report bytes в caption не попадают.

## 7. Структура итогового Markdown

Итоговый файл создаётся только при `finding_count > 0`:

```markdown
# Аудит PR #456

Найдено замечаний: 4
Вердикт: требуются изменения

## Найденные проблемы

### 1. Блокирующее: краткий заголовок

`path/to/File.swift:42`

Что не так и к чему это приводит.

**Рекомендация:** минимальное исправление.

## Ограничения проверки

Только ограничения, влияющие на доверие к результату.

## Техническая информация

PR/диапазон, base/head SHA, автор, координатор, roster и методология.
```

Правила компактности:

- после заголовка и двух строк summary сразу идут findings;
- top-level metadata до findings отсутствует;
- один finding содержит заголовок, `file:line`, суть/влияние и рекомендацию;
- confidence, false-positive risk, runtime-verification flag и source-agent
  остаются во внутренних JSON; при необходимости source attribution можно
  указать компактно в нижней технической секции;
- пустые необязательные разделы не рендерятся;
- конфликты между агентами и ограничения добавляются только при наличии;
- methodology и provenance объединяются в короткую нижнюю секцию
  «Техническая информация».

## 8. Потоки данных

### PR-аудит

1. Swift/Kotlin coordinator получает четыре subagent JSON.
2. Валидирует их и выполняет текущую дедупликацию `(file, line, title)`.
3. Вычисляет severity counts, `finding_count` и verdict.
4. Записывает `delivery-summary.json`.
5. При ненулевом результате пишет русский `audit.md`; при нулевом не создаёт
   итоговый MD.
6. Передаёт issue соответствующему InfraEngineer.
7. Infra отправляет caption + document либо text-only summary.

### Daily delta-аудит

1. Platform dispatcher агрегирует stage-артефакты после QA/CTO gate.
2. Вычисляет единый summary и пишет `delivery-summary.json`.
3. При ненулевом результате пишет русский `audit-final.md`; при нулевом не
   создаёт итоговый MD.
4. Передаёт issue InfraEngineer в `mode=daily_delivery`.
5. Infra отправляет выбранный Telegram-режим.
6. Только после `ok:true` атомарно обновляет cursor и закрывает issue.

## 9. Ошибки, повторы и безопасность

- Отсутствующий или невалидный `delivery-summary.json` блокирует доставку.
- Несовпадение `finding_count` и суммы severity counts блокирует доставку.
- Ненулевой count без указанного/существующего MD блокирует доставку.
- Нулевой count с указанным `report_file` считается нарушением контракта и
  блокирует доставку до исправления агрегатором.
- Ошибка Telegram не ставит delivery/handoff done marker и не обновляет daily
  cursor.
- При duplicate wake валидный summary является источником выбора режима;
  второй Telegram message после подтверждённого delivery marker не отправляется.
- Используется существующий `issueIdentifier`/`fileRoutes` контракт; `chatId`,
  raw bot token, URL и `filePath` не добавляются.
- Caption остаётся обычным коротким текстом, чтобы не зависеть от корректности
  MarkdownV2 escaping.

## 10. Затрагиваемые области

Ожидаемые source-файлы:

- `paperclips/projects/uaudit/overlays/codex/UWISwiftAuditor.md`;
- `paperclips/projects/uaudit/overlays/codex/UWAKotlinAuditor.md`;
- `paperclips/projects/uaudit/roles-codex/uwi-platform-dispatcher.md`;
- `paperclips/projects/uaudit/roles-codex/uwa-platform-dispatcher.md`;
- `paperclips/projects/uaudit/overlays/codex/UWIInfraEngineer.md`;
- `paperclips/projects/uaudit/overlays/codex/UWAInfraEngineer.md`;
- `docs/paperclip-operations/telegram-report-delivery.md`.

Generated output обновляется штатным builder-ом только для изменившихся UAudit
bundles. Тестовые изменения ожидаются в существующих UAudit bundle/contract
тестах; новый helper или runtime service не планируется.

## 11. Acceptance criteria

1. Все четыре потока формируют конечный пользовательский результат на русском.
2. Telegram-summary содержит точное число уникальных findings.
3. При findings > 0 summary является caption того же MD-документа.
4. При findings == 0 конечный MD отсутствует, а Telegram получает text-only
   summary с числом `0`.
5. PR и daily потоки используют одинаковые правила подсчёта и отображения.
6. Daily cursor обновляется после успешной text-only или document-доставки и
   никогда не обновляется после ошибки доставки.
7. Итоговый MD после заголовка/summary сразу показывает findings; metadata и
   methodology находятся внизу.
8. Один finding не содержит служебный JSON-набор полей и сохраняет только
   location, суть/влияние и actionable recommendation.
9. Internal subagent JSON и severity enum остаются обратно совместимыми.
10. Generated UAudit bundles проходят существующие size и instruction gates.
11. Ни один не-delivery agent не получает права самостоятельно вызывать
    Telegram action.

## 12. План проверки

- Добавить/обновить targeted tests, которые проверяют generated bundles для
  iOS/Android coordinator, dispatcher и InfraEngineer.
- Проверить две матрицы для каждого audit kind: `finding_count > 0` и
  `finding_count == 0`.
- Проверить инварианты summary: сумма severity, conditional `report_file`,
  отсутствие document-параметров при нуле.
- Проверить русский порядок разделов и отсутствие metadata перед findings.
- Проверить daily cursor gate для обоих Telegram-режимов.
- Выполнить:

```bash
python3 paperclips/scripts/build_project_compat.py --project uaudit --target codex --inventory check
python3 -m pytest paperclips/tests/test_uaudit_dispatcher_bundles.py
python3 paperclips/scripts/validate_uaudit_docs.py
python3 paperclips/scripts/validate_instructions.py --repo-root .
./paperclips/validate-codex-target.sh
```

- Перед live deploy выполнить UAudit deploy dry-run. Реальную отправку в
  Telegram проводить только в разрешённом оператором smoke/QA этапе.

## 13. Открытые вопросы

Открытых продуктовых вопросов нет. Если при реализации выяснится, что текущий
bundle builder не позволяет выразить одинаковую валидацию summary без
дублирования инструкций, это считается новым архитектурным решением и требует
отдельного согласования, а не скрытого добавления runtime helper-а.
