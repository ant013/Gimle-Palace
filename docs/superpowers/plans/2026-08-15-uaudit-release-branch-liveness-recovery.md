# План реализации UAudit: release transition, liveness и multi-app

Основание: спецификация
`docs/superpowers/specs/2026-08-15-uaudit-release-branch-liveness-recovery.md`,
утверждённая на ветке `fix/uaudit-version-0.50-migration` от
`origin/develop` `40a8529fb420c634d5971af6114ebaff158e95e8`.

## Последовательность изменений

1. Ввести единый app-scoped runtime state: реестр приложения, versioned platform
   state, stable routine key, generation ledger и quarantine paths. Мигратор
   создаёт `unstoppable_wallet`, переносит только проверяемые legacy cursor и
   не удаляет исходные evidence files.
2. Добавить чистый source resolver. Он получает remote refs напрямую,
   выбирает ежедневный, bridge, transition или recovery range, строит
   patch-id/range-diff mapping при rebase и выбирает full recovery при любой
   недоказуемой эквивалентности. Resolver не пишет cursor и не отправляет
   сообщения.
3. Расширить delivery contract отдельным `release_transition` audit kind,
   multi-segment source manifest и `reconcile-transition`. Единственная
   атомарная операция после receipt продвигает app/platform state. Старый
   `forced_full` сохраняет запрет cursor mutation.
4. Заменить version-dependent lock identity на `(app_id, stable_routine_key)`;
   при bind записывать ledger с heartbeat. Добавить quarantine/recovery команду:
   receipt без cursor только reconcile-ится; stale/partial/blocked generation
   quarantine-ится и создаёт один full recovery от canonical cursor.
5. Расширить routine configuration и dispatcher contracts явным `app_id`,
   разрешённым route и новой transition/recovery dispatch path. Пересобрать
   generated UAudit bundles из source.
6. Добавить liveness supervisor с пяти-минутным schedule scan. Он не меняет
   healthy active generation, требует три пропущенных heartbeat перед lost-run
   recovery и дедуплицирует recovery по `(app_id, routine_key, slot_id)`.
7. Выполнить совместимую миграцию текущего UAudit и staged deployment: сначала
   tests/build, затем native service restart, dry-run, ручной iOS/Android proof
   и проверка будущего schedule slot. Внешние mutation выполняются только после
   merged/reviewed source.

## Delta matrix

| Slice | Текущий аналог | Изменение | Нельзя нарушать |
|---|---|---|---|
| Daily intake | `daily_delta` + direct upstream dispatcher | source resolver и `release_transition` | authoritative remote refs, daily bounds |
| Delivery | `reconcile_daily` | transition CAS over state document | receipt before cursor, immutable receipt |
| Locking | lock metadata in `bind_context` | app-scoped stable locks + ledger/quarantine | active generation never stolen |
| Runtime config | daily routine YAML/reconciler | app registry + scoped records | no cross-app state or route reuse |
| Operations | routine schedules/reconciler | independent five-minute liveness controller | reconciler stays non-executing/no schedule rewrite |

## Test plan

- Unit fixtures: normal/no-change/bridge/next-version/rebase exact and
  ambiguous mappings; current master absent from next release emits two reports.
- Delivery: transition receipt CAS, duplicate replay, crash before/after cursor,
  `forced_full` still cannot advance state.
- Recovery: partial/blocked/dead/contradictory generation quarantine; active
  lease is retained; concurrent recovery elects one winner.
- Isolation: two applications with overlapping branches/routine names cannot
  share cursor, lock, receipt, retry or Telegram identity.
- Supervisor: expected schedule, stale next run, coalesced active vs abandoned
  generation, unknown API payload and capped retry/backoff.
- Integration: dispatcher source/generated bundle consistency; existing daily
  receipt contract regressions; native deploy smoke only after PR merge.

## Completion criteria

No missing release/ref/history scenario can leave a permanent daily blocker.
Every successful state advance is receipt-bound and Russian report facing.
Any ambiguity produces an automatic full audit/retry rather than a silent skip.
