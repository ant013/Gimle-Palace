# UAudit: lifecycle веток релиза и восстановление ежедневных аудитов

**Статус:** draft для review  
**Основание:** `origin/develop` `40a8529fb420c634d5971af6114ebaff158e95e8`; рабочий worktree `fix/uaudit-version-0.50-migration` содержит несвязанные незакоммиченные изменения и не является базой для реализации без предварительного обновления.

## Цель

Ежедневный аудит Android и iOS должен непрерывно отслеживать актуальную
релизную линию: существующую `version/X.Y`, временно `master` между удалением
закрытой линии и созданием следующей, а также безопасно переживать пересоздание
ветки после rebase. Ни один диапазон не должен тихо исчезать, а delivery/cursor
остаются receipt-bound.

## Зафиксированные правила продукта

- Разработка идёт в `version/X.Y`; в конце спринта она merge-ится в `master`.
- Следующая `version/X.(Y+1)` создаётся от `master` позднее и может отсутствовать
  несколько дней.
- После hotfix в `master` активную local `version/X.Y` могут rebase-нуть на
  `master`, удалить удалённую ветку и опубликовать её заново с новыми SHA.
- `master` используется только как bridge, а не как постоянная замена release
  branch.

## Scope

1. Repository-owned source resolver для обеих платформ.
2. Immutable evidence о выборе source и контролируемый переход после history
   rewrite.
3. Recovery stale iOS daily generation без прямого изменения cursor.
4. Проверка live liveness routine: active state, future next-run и отсутствие
   незавершённого generation lock.
5. Тесты, generated UAudit bundles, документация и безопасный deploy/recovery
   runbook.

Не входит: изменение Telegram destination/формата, увеличение daily limits,
удаление исторических артефактов или автоматический `git push --force`.

## Наблюдения и инварианты

- На 2026-08-15 Android не имеет публичных `version/0.50` или `version/0.51`;
  iOS имеет `version/0.50` `63379839b9677d1ec77135240f73c37f3ff0326a`.
- Current `source_ref` содержит только `routine_id, branch, from_sha, to_sha`,
  а cursor CAS принимает только exact FROM/TO. Это защищает от пропуска,
  но не описывает rebase transition.
- `reconcile_uaudit_routines.py` сейчас меняет только assignee и description;
  schedule liveness не является частью его контракта.
- Matching receipt, immutable run binding и successful helper reconciliation
  остаются обязательными перед cursor advance. Повторная доставка допустима,
  тихий cursor reset — нет.

## Проектирование

### 1. Разрешение source

Добавить узкий repository-owned resolver, вызываемый dispatcher до no-op,
range и lock checks. Он получает refs только через direct remote fetch/ls-remote
и записывает в intake выбранную точную ветку и SHA.

Порядок выбора для каждой платформы:

1. Найти все публичные `version/<major>.<minor>` refs; выбрать наибольшую
   семантическую версию, не ниже настроенной release line.
2. Если подходящей `version/*` нет, использовать `master` как `bridge` и
   включить это в immutable source evidence и операторский комментарий.
3. Если `master` также недоступен, block с exact remote evidence; не брать
   локальный `origin/*`, `FETCH_HEAD` или старый mirror ref.
4. Если version ref появляется после bridge, перейти на неё только после
   проверки ancestry/transition ниже.

В нормальном ancestor случае daily range остаётся ограниченным действующими
30 commits/300 files/3000 lines. Превышение создаёт существующий явный
full-range путь; daily limits не расширяются.

### 2. Source transition и rebase

Ввести отдельный state ledger рядом с cursor, не меняя exact cursor schema.
Он хранит последний verified source mode/branch/head и immutable receipt/run
reference. Resolver классифицирует переход как `normal`, `bridge`,
`version-advance` или `history-rewrite`.

- Для `normal`, `bridge` и `version-advance` cursor должен быть ancestor
  выбранного HEAD; обычный receipt-led daily flow остаётся без изменений.
- Для `history-rewrite` запрещены обычный no-op и cursor CAS. Создаётся
  отдельная recovery generation с сохранёнными old/new refs, merge-base и
  range-diff/patch-equivalence evidence. Она повторно аудирует необходимый
  полный диапазон, а не предполагает совпадение SHA.
- Новый helper command применяет transition только после валидного full-range
  delivery receipt, completed workflow и complete evidence manifest. Он
  атомарно обновляет ledger и cursor; конфликт или неполная equivalence оставляет
  lock/cursor без изменений и создаёт Board blocker.

Таким образом удаление/пересоздание ветки может дать повторный аудит, но не
может скрыть коммиты или перенести cursor на непроверенную историю.

### 3. iOS stale generation

Добавить recovery command/runbook, который сначала классифицирует старый lock:
terminal receipt-led generation возобновляется существующим reconciliation;
незавершённая или противоречивая generation quarantines с неизменным cursor и
полным evidence. Новый run получает lock только после quarantine marker и
никакой агент не удаляет lock directory напрямую. Для текущего iOS состояния
это разблокирует full-range recovery от `d8280fe...` до актуального selected
HEAD и доставляет русский отчёт по v1 contract.

### 4. Liveness routine

Расширить reconciler read-only liveness check для обеих live routines. До
`--apply` он должен получить и показать: enabled/active state, future next-run,
последний execution outcome и active generation/lock. API contract будет
зафиксирован отдельной fixture после безопасного live GET; отсутствие нужных
полей или невозможность проверить их завершает команду blocker, а не "green".

После repair оба routine активируются только после одного успешного manual run
каждый, отсутствующих active locks и будущих next-run timestamps.

## Затрагиваемые области

- `paperclips/projects/uaudit/daily-version-branch-routines.yaml`
- platform dispatcher role sources и rendered `paperclips/dist/uaudit/codex/`
- `paperclips/projects/uaudit/runtime/uaudit_delivery_contract.py` и новый
  source-transition/resolution utility
- `paperclips/scripts/reconcile_uaudit_routines.py`
- `paperclips/tests/test_uaudit_delivery_contract.py`,
  `paperclips/tests/test_uaudit_dispatcher_bundles.py`, docs/runbook

## Delta matrix и тесты до кода

| Slice | Базовый аналог | Новый delta | Риск | Проверка |
|---|---|---|---|---|
| Source selection | Platform dispatcher + direct remote fetch contract | Semver version discovery, temporary master bridge и recorded source mode | Высокий | Fake `ls-remote`: version exists, no version, new version appears, remote unavailable |
| Rewrite transition | `reconcile_daily` receipt/CAS | Ledger + evidence-bound recovery; no SHA reset on non-ancestor | Высокий | ancestor, non-ancestor, incomplete equivalence, receipt conflict, idempotent resume |
| iOS stale generation | Existing lock/CAS validation | Quarantine/resume protocol, no direct lock deletion | Высокий | valid terminal resume, incomplete run, conflicting artifacts, next run gets lock only after quarantine |
| Routine liveness | Revision-safe reconciler + partial-apply tests | Validate live schedule/execution state, fail closed on unknown schema | Высокий | active/future run green; inactive/past/missing-field/409 fail; rerun converges |

## Acceptance criteria

1. Каждый run пишет selected branch/mode/SHA в immutable evidence; локальные
   refs не могут определять HEAD.
2. Между version branches Android/iOS audit использует `master` только как
   explicitly labelled bridge и возвращается на newest `version/*`.
3. Rebase/delete/recreate не приводит к silent cursor movement; переход
   возможен только после полного receipt-bound recovery evidence.
4. iOS stale `UNS-538` не блокирует новый audit после подтверждённой quarantine
   или resume, а cursor меняется только helper-ом.
5. Reconciler выдаёт non-zero/blocker при inactive routine, отсутствии future
   next run, active stale generation или неизвестном API liveness schema.
6. Оба platform daily runners проходят manual proof и отправляют русские v1
   отчёты; schedules затем имеют future next-run.
7. Узкие unit tests, docs validator, bundle build и relevant full tests зелёные;
   generated output согласован с source.

## Verification и deploy

1. Сначала targeted pytest для source resolver, helper transition, reconciler
   и bundles; затем `python3 paperclips/scripts/validate_uaudit_docs.py` и
   `paperclips/validate-codex-target.sh`.
2. Run full relevant Paperclip tests и review diff against this matrix.
3. После PR approval: deploy rendered agents/source по approved runbook,
   read-only routine liveness check, repair iOS, manual Android/iOS proof,
   then enable routines.
4. На каждом live step сохранить redacted issue/receipt/lock evidence; никаких
   токенов, raw diffs или manual cursor writes.

## Open execution gates

- Перед реализацией нужен read-only live API probe, чтобы зафиксировать точные
  schedule/next-run/execution поля; текущий iMac недоступен.
- Базовый worktree надо безопасно обновить до `origin/develop` без включения
  существующих user-owned dirty файлов.
- Эта спецификация требует явного approval перед implementation/deploy.
