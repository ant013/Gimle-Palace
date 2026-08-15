# UAudit: непрерывный multi-app аудит release-веток, rebase и liveness

**Статус:** APPROVED — оператор подтвердил реализацию 2026-08-15 после выбора
availability-first решений для release/rebase/liveness и multi-app модели.
**База для реализации:** `origin/develop` `40a8529fb420c634d5971af6114ebaff158e95e8`.

## Цель

Не допускать пропуска ежедневных аудитов при release merge, hotfix в `master`,
delete/recreate/rebase `version/X.Y`, падении агента или stale generation для
любого подключённого приложения. При неясной истории предпочтительнее повторный
полный аудит, чем остановка или пропуск изменений. Cursor всегда меняется только
после валидного delivery receipt.

## Подтверждённый контекст

- Разработка идёт в `version/X.Y`; в конце спринта ветка merge-ится в `master`;
  следующая release-ветка может появиться позже.
- Android `version/0.50` сейчас удалена; последний cursor `f25df34…` является
  предком `master` `1f50b1…`. iOS `version/0.50` существует.
- Live schedules были active, но slots 9–13 августа получили `coalesced` из-за
  незавершённых generations. `skip_missed` не создаёт catch-up.
- Existing helper гарантирует receipt-before-cursor и strict lock-bound CAS, но
  не умеет stale-lock lifecycle, history transition или schedule liveness.
- Existing `forced_full` намеренно не меняет cursor; его нельзя выдавать за
  transition workflow.

## Инварианты

1. Direct remote refs — единственный источник SHA; `origin/*`, `FETCH_HEAD` и
   mirror refs не определяют audit range.
2. Повторный аудит разрешён. Silent cursor move или пропуск диапазона запрещён.
3. Русский Telegram report/receipt обязателен перед cursor transition.
4. Никакой recovery не удаляет lock directory напрямую и не крадёт active run.
5. Каждый automatic retry идемпотентен: один platform/routine recovery на slot.
6. Daily limits сохраняются; version/rebase recovery использует явный full mode.
7. Каждый persistent record, schedule, cursor, generation, lock, receipt и
   report принадлежит явному `app_id`; состояние одного приложения не может
   блокировать, дедуплицировать или продвигать другое.

## Multi-app модель

Принципы аудита для всех приложений одинаковы. Отличаются только зарегистрированные
параметры приложения и его платформ/репозиториев; логика release transition,
receipt-before-cursor, full recovery, liveness и Russian reporting не имеет
per-app исключений.

Ввести first-class таблицу/реестр `apps`:

| Поле | Назначение |
|---|---|
| `app_id` | Стабильный machine identifier, не выводится из URL или названия репозитория. |
| `display_name` | Имя для русских отчётов и Board. |
| `enabled` | Разрешает/останавливает schedules только этого приложения. |
| `platforms` | Явная конфигурация platform → repo, local path, release-branch policy и timezone. |
| `report_route` | Разрешённый delivery route приложения. |

Все рабочие таблицы/records получают обязательный `app_id` и compound identity:

| Область | Идентичность |
|---|---|
| Routine/schedule | `(app_id, routine_key)` |
| Platform state/cursor | `(app_id, platform)` |
| Generation/receipt/quarantine | `(app_id, routine_key, generation_id)` |
| Lock | `(app_id, stable_routine_key)` |
| Liveness slot/retry/dedup | `(app_id, routine_key, slot_id)` |
| Telegram/Board report | `app_id` + issue/generation evidence |

Файловые paths также app-scoped, например
`state/apps/<app_id>/<platform>/...`; migration для текущего UAudit создаёт
явный `app_id=unstoppable_wallet`. Запрещены global locks, cursors или dedup
keys без `app_id`.

## Durable platform state

Заменить одинокий cursor на один атомарно записываемый versioned platform-state
document на `(app_id, platform)`; оставить legacy cursor read-only evidence для
migration. Он хранит:

- `cursor_sha`, release line и selected branch/head;
- `master_anchor_sha` — HEAD master во время последнего verified release state;
- `master_audited_through_sha`;
- `release_base_master_sha`, previous release head и branch generation id;
- immutable manifest старой серии: SHA, parents, normalized patch-id;
- delivery receipt/summary digest и mode `release|bridge|transition|recovery`.

Subject коммита допустим только как операторская подсказка, не как identity.
Одна атомарная запись исключает рассинхронизацию ledger и cursor.

## Source state machine

Обозначения: `A` — предыдущий audited release SHA, `X` — сохранённый master
anchor, `Y` — current master HEAD, `B` — current/new release HEAD.

| Сценарий | Автоматическое действие |
|---|---|
| `A` — предок current release `B` | Обычный bounded daily `A..B`; receipt → cursor `B`. |
| `A == B` | No-change, без cursor mutation и без ложного report. |
| Release удалена, `A` — предок `Y`, новой version нет | Bridge audit `A..Y`; receipt → cursor `Y`, release line сохраняется. |
| `A` — предок `Y`, строго следующая version создана от `Y` | Один transition audit: `A..Y` плюс `Y..B`, без дублей; receipt → cursor `B`. |
| Hotfix `X..Y`, затем rebase current release: old `X..A`, new `Y..B` | Сопоставить series через range-diff/patch-id; аудировать `X..Y` и новые/изменённые патчи `Y..B`; receipt → cursor `B`. |
| Предыдущее сопоставление неоднозначно | Автоматический full recovery `X..Y` + весь `Y..B`, без daily limits; receipt → cursor `B`. |
| `A` не в master, но release `B` доступна и старая series отсутствует/непригодна | Автоматический full recovery release delta от доказуемой базы до `B`; receipt → cursor `B`. |
| Next release не содержит current master `Y` | Не ждать rebase: выполнить два независимых full recovery reports — master hotfix segment и release segment; хранить отдельный master progress, release cursor → `B` только после release receipt. |
| Remote/refs временно недоступны | Cursor не меняется; supervisor создаёт один retryable recovery с backoff и alert, не вечный lock. |

### Правила перехода на следующую версию

- Искать **строго следующую** release line (`0.50 → 0.51`), не highest
  available; пропуск `0.51` в пользу `0.52` требует отдельного recovery.
- Нельзя объединять master и version ranges, если `Y` не является предком `B`.
  В таком случае ждём следующей автоматической проверки/rebase либо создаём
  отдельные recovery generations, выбранные product policy.
- Если `A` отсутствует в master, master не используется на основании одного
  cursor. Для hotfix-rebase используется только сохранённая пара `X..Y` при
  доказанной ancestry `X ⊑ Y ⊑ B`.

### Rebase mapping

Перед каждым remote ref update resolver сохраняет старый source ref и series
manifest. Для `X..A` vs `Y..B`:

- one-to-one patch-equivalent commits считаются уже проверенными;
- новые/изменённые/unmatched patches включаются в audit;
- merge, empty, reordered или squash commits без доказуемого mapping делают
  mapping ambiguous и запускают full recovery, а не blocker.

## Transition workflow

Добавить отдельный `audit_kind=release_transition`, а не перегружать
`daily_delta` или `forced_full`. Immutable `source_ref` содержит selected
release, master anchors, mode и список именованных segments. Новый
`reconcile-transition` проверяет receipt и manifest, затем один раз атомарно
продвигает platform state/cursor. Daily limits в этом mode не применяются.

## Generation и stale-lock recovery

При bind создаётся immutable generation ledger:

`state/apps/<app_id>/generations/<stable-routine-key>/<generation-id>.json`

В нём: `app_id`, issue/execution IDs, creation/heartbeat times, run path, source
manifest, receipt state, retry count и artifact hashes. Lock key становится
стабильным внутри приложения для платформы (`<app_id>:uaudit-daily-android`), а
не зависит от `0.50`.

Recovery controller классифицирует run:

| Состояние | Действие |
|---|---|
| Matching receipt и cursor marker | Идемпотентно завершить workflow, снять lock. |
| Receipt есть, cursor отсутствует | Reconcile только cursor/workflow; Telegram не дублировать. |
| Нет receipt, run завершён/утрачен | Атомарно quarantine ledger+lock evidence, создать новый recovery от unchanged cursor. |
| Run активен и lease свежий | Не трогать; один queued health retry. |
| Артефакты противоречат | Quarantine с evidence, автоматический full recovery. |
| Partial или blocked terminal generation | Cursor не менять; quarantine generation и автоматически запустить full recovery от canonical cursor до current selected HEAD. |

Quarantine — атомарное перемещение в `state/quarantine/...`, не `rm`.

## Liveness supervisor

Отдельный periodic controller, не config reconciler. Каждые 5 минут он читает
все enabled routine records каждого приложения и валидирует schema. Green только
если для каждой `(app_id, routine_key)`:

- routine active, ровно один enabled expected trigger/cron/timezone;
- future `nextRunAt`, last trigger в допустимом окне;
- последнему expected slot соответствует terminal run/issue либо живой generation
  в пределах lease;
- нет stale Paperclip/filesystem lock и ledger согласован с issue/run.

`failed`/отсутствующий issue создаёт ровно один recovery issue; `coalesced`
исследует active generation. После первого пропуска — alert, затем capped
automatic backoff. Unknown API schema — visible retryable degradation, не green.

## Product decisions до реализации

## Выбранная availability-first политика

1. Любой terminal `blocked` или `partial` audit не удерживает платформу.
   Его cursor не продвигается, generation вместе с lock evidence quarantine-ится,
   а следующий автоматический запуск выполняет полный audit от canonical cursor
   до актуального selected HEAD. Human approval не является зависимостью для
   запуска следующего полного audit.
2. Если новая release ветка создана от старого master и не содержит current
   hotfix `Y`, не ждать rebase. Выпускать два независимых receipt-bound reports:
   master hotfix segment и release segment. `master_audited_through_sha` и
   release cursor ведутся раздельно, поэтому несвязанные истории не склеиваются.
3. Health supervisor проверяет состояние каждые 5 минут. Живой generation не
   трогается, пока обновляется heartbeat; terminal failure quarantine-ится сразу,
   потерянный generation — после трёх пропусков heartbeat (15 минут).
4. Если full recovery снова завершается partial/blocked, применяется тот же
   цикл quarantine + capped backoff + новый полный audit. Это не вечный lock и
   не ручная операция; cursor остаётся на последнем complete receipt.

## Тесты до кода

1. Normal/no-change/bridge/version-transition source resolver fixtures.
2. `X..A` vs `Y..B`: exact mapping, changed patch, merge/squash/ambiguous full
   recovery, missing historical objects.
3. Receipt-before-transition CAS, crash before cursor, crash after send,
   idempotent duplicate recovery.
4. Concurrent recovery: только один process quarantine/create выигрывает.
5. Active lock, dead lock, contradictory receipt/marker, partial P-1 A/B.
6. Live routine fixture: disabled/multiple trigger, stale next-run, failed run,
   coalesced live vs abandoned generation, unknown API schema, backoff.
7. Generated bundles/direct-fetch contract, helper schema and source/docs build.
8. Два приложения с одинаковой platform/branch/issue-like identifier: cursors,
   locks, retries, receipts, schedules и Telegram labels изолированы по `app_id`.
9. Migration текущего UAudit в `app_id=unstoppable_wallet` сохраняет cursor,
   receipt и active generation без cross-app default.

## Verification and deployment

Перед кодом: безопасно перенести implementation branch на `origin/develop` без
user-owned dirty files. После кода: narrow pytest, docs/bundle validators,
relevant full Paperclip suite, then staged deploy. Live proof: recovery iOS,
manual run Android+iOS, healthy future schedule slots and Russian receipts.
No secrets/raw diffs are written to artifacts, comments or reports.
