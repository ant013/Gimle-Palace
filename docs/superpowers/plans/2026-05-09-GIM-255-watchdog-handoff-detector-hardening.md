# GIM-255 — План: hardening watchdog handoff detector после регрессии GIM-244

> **Rev 2** — закрывает CXCodeReviewer Phase 1.2 REQUEST CHANGES: явный gating для шести detectors + детерминированная shared alert-budget семантика.

**Issue:** GIM-255.
**Инцидент:** GIM-244 / PR #125 (`15c1c67`) включил tier-детекторы watchdog; после включения `handoff_*_enabled` watchdog отправил 258 alert-комментариев в 32 issue за 4 часа.
**Ветка:** `feature/GIM-255-watchdog-handoff-detector-hardening`, от `origin/develop`.
**Цель:** сделать все issue-bound handoff detectors bounded и observable: не сканировать/алертить старые и recovery-origin issue, явно ограничить статусы, залогировать успешные alert-post, ограничить alert burst за tick и закрыть регрессию e2e-тестом.
**Команда:** CX. Фаза: CXCTO -> CXCodeReviewer (plan-first) -> CXPythonEngineer (impl) -> CXCodeReviewer (mechanical CR) -> CodexArchitectReviewer (architecture review) -> CXQAEngineer (runtime QA) -> CXCTO (merge).

## Discovery

- `git log --all --grep='GIM-255|GIM-244|watchdog handoff|handoff detector'` нашёл GIM-244 commits и PR #125, но не нашёл реализации GIM-255.
- `gh pr list --state all --search "GIM-255 OR GIM-244 OR watchdog handoff OR handoff detector"` нашёл merged PR #125 и более ранние watchdog PR; открытого GIM-255 PR нет.
- `docs/superpowers/plans/2026-05-08-GIM-244-handoff-unification-p2p3.md` описывает исходную реализацию; GIM-255 plan/spec в docs отсутствует.
- Symbol discovery на `origin/develop`:
  - `services/watchdog/src/gimle_watchdog/paperclip.py:Issue` не содержит `origin_kind`;
  - `_issue_from_json()` не читает `originKind`;
  - legacy issue-bound detectors находятся в `detection_semantic.py`: `_detect_comment_only_handoff()` строка 84, `_detect_wrong_assignee()` строка 126, `_detect_review_owned_by_implementer()` строка 153;
  - `_detect_cross_team_handoff()` не проверяет статус или возраст issue;
  - `_detect_ownerless_completion()` проверяет `status == "done"`, но не пропускает recovery/productivity origins;
  - `_detect_infra_block()` не проверяет статус, origin или возраст issue;
  - `_handle_tier_finding()` логирует только `tier_alert_post_failed`, успешный tier-1 alert-post молчит;
  - `_run_tier_pass()` не ограничивает число новых tier-alert post за tick.

## Scope

**In:**

- Age cap для всех шести issue-bound detectors через `handoff_recent_window_min` с дефолтом `180`.
- Origin skip-list для всех шести issue-bound detectors: `stranded_issue_recovery`, `issue_productivity_review`.
- Явные status whitelist для всех шести issue-bound detectors.
- Успешный лог tier-1 alert-post.
- Per-tick budget для новых tier-alert comments.
- Проверка cooldown/dedupe пути, который должен был подавить повторные алерты.
- Synthetic e2e regression test на stale/done/recovery-origin issue.
- Минимальное обновление runbook с безопасным re-enable чеклистом.

**Out:**

- Удаление 258 spam-комментариев.
- Включение `handoff_auto_repair_enabled` в production.
- Исправление Paperclip `POST /comments` 500 на `originKind=stranded_issue_recovery`.
- Отдельная переработка watchdog `tick_timeout_self_exit timeout_s=60`, кроме бюджетирования alert-post в этой задаче.

## Step 1 — Formalization

**Owner:** CXCTO.

**Описание:** Зафиксировать план, discovery и границы ответственности без изменений в Python-коде.

**Affected paths:**

- `docs/superpowers/plans/2026-05-09-GIM-255-watchdog-handoff-detector-hardening.md`

**Dependencies:** нет.

**Acceptance criteria:**

- План содержит affected paths, владельцев, dependencies и acceptance criteria по каждому шагу.
- GIM-255 body/comment ссылается на этот план.
- План передан на CXCodeReviewer до реализации.

## Step 2 — Plan-first review

**Owner:** CXCodeReviewer.

**Описание:** Проверить план до реализации, потому что регрессия была архитектурной: unbounded scanning + side-effectful comments.

**Affected paths:** только этот план.

**Dependencies:** Step 1.

**Acceptance criteria:**

- CXCodeReviewer явно APPROVE или REQUEST CHANGES.
- Проверены: статусные whitelist, origin skip-list, age cap, alert budget, e2e regression coverage, отсутствие scope creep.
- При APPROVE issue передан CXPythonEngineer на Step 3.

## Step 3 — Config + issue model hardening

**Owner:** CXPythonEngineer.

**Описание:** Добавить данные, без которых detector gating невозможен, и сделать config строгим.

**Affected paths:**

- `services/watchdog/src/gimle_watchdog/config.py`
- `services/watchdog/src/gimle_watchdog/detection_semantic.py`
- `services/watchdog/src/gimle_watchdog/paperclip.py`
- `services/watchdog/tests/test_config.py`
- `services/watchdog/tests/test_detection_semantic.py`

**Dependencies:** Step 2 APPROVE.

**Acceptance criteria:**

- `Issue` получает поле `origin_kind: str | None`; `_issue_from_json()` читает `originKind`.
- `HandoffConfig` и `_HANDOFF_KNOWN_KEYS` получают `handoff_recent_window_min: int = 180`.
- В `detection_semantic.py` введены общие helpers/consts:
  - `SKIP_ORIGINS = {"stranded_issue_recovery", "issue_productivity_review"}`;
  - recent-window helper для `(now - issue.updated_at) <= handoff_recent_window_min`;
  - status whitelist helper без ad hoc строк в daemon.
- Unit tests покрывают config parsing, `originKind` mapping и stale/recovery skips.

## Step 4 — Six-detector gating

**Owner:** CXPythonEngineer.

**Описание:** Сделать каждый из шести issue-bound detectors bounded по age/status/origin до того, как он смотрит комментарии или пишет state. `stale_bundle` остаётся global detector и не входит в acceptance phrase "all 6 detectors"; его side-effect ограничивается shared alert budget в Step 5.

**Affected paths:**

- `services/watchdog/src/gimle_watchdog/detection_semantic.py`
- `services/watchdog/src/gimle_watchdog/daemon.py`
- `services/watchdog/tests/test_detection_semantic.py`

**Dependencies:** Step 3.

**Acceptance criteria:**

- Все шесть issue-bound detectors вызывают один shared precondition до detector-specific logic:
  - возвращает `None`, когда `issue.origin_kind in SKIP_ORIGINS`;
  - возвращает `None`, когда `(now_server - issue.updated_at) > handoff_recent_window_min`;
  - возвращает `None`, когда `issue.status` вне whitelist конкретного detector.
- `comment_only_handoff` whitelist: `{"todo", "in_progress", "in_review"}`. Обоснование: detector ищет drift активного handoff protocol; done/cancelled/backlog issues не должны будить агентов.
- `wrong_assignee` whitelist: `{"todo", "in_progress", "in_review"}`. Обоснование: actionable только ownership живой работы.
- `review_owned_by_implementer` whitelist: `{"in_review"}`. Обоснование: detector имеет смысл только во время review.
- `cross_team_handoff` whitelist: `{"todo", "in_progress", "in_review"}`. Обоснование: live ownership + защита от stale done issue spam из GIM-244.
- `ownerless_completion` whitelist: `{"done"}`. Обоснование: completion evidence проверяется только после close, но stale done и skip-origin issues не должны alert.
- `infra_block` whitelist: `{"todo", "in_progress", "in_review", "blocked"}`. Обоснование: infra-block comments могут объяснять live blocked work, но done/cancelled/backlog issues не должны alert.
- Existing unit tests for legacy detectors are updated to cover stale issue, skip-origin and status-outside-whitelist cases.
- New unit tests for tier detectors cover stale issue, skip-origin and status-outside-whitelist cases.
- Daemon passes `now_server` and `handoff_recent_window_min` into both legacy scan and tier scan, either through one config object or explicit parameters. Hidden `datetime.now()` in detector tests is not allowed.

## Step 5 — Alert observability + deterministic per-tick budget

**Owner:** CXPythonEngineer.

**Описание:** Сделать успешные alert side-effects видимыми в логах и ограничить burst через один shared budget для legacy issue alerts, tier issue alerts и `stale_bundle`.

**Affected paths:**

- `services/watchdog/src/gimle_watchdog/config.py`
- `services/watchdog/src/gimle_watchdog/daemon.py`
- `services/watchdog/src/gimle_watchdog/actions.py`
- `services/watchdog/src/gimle_watchdog/state.py`
- `services/watchdog/tests/test_config.py`
- `services/watchdog/tests/test_daemon.py`
- `services/watchdog/tests/test_state.py`

**Dependencies:** Step 3.

**Acceptance criteria:**

- Успешный issue alert-post логируется как `handoff_alert_posted` для legacy path и `tier_alert_posted issue=%s ftype=%s comment=%s` для tier path, или эквивалент с comment id, если API его возвращает.
- Config получает `handoff_alert_soft_budget_per_tick: int = 5` и `handoff_alert_hard_budget_per_tick: int = 20`.
- Soft budget semantics: soft budget является warning threshold, не stop condition. Когда `posted_count == soft_budget`, watchdog один раз за tick логирует `handoff_alert_soft_budget_reached posted=%s soft=%s hard=%s` и продолжает processing до hard cap.
- Hard budget semantics: hard cap является единственным per-tick stop. Когда `posted_count >= hard_budget`, каждый оставшийся новый alert candidate откладывается до следующего tick.
- Shared accounting: один per-tick `AlertPostBudget` или эквивалентный объект передаётся во все alert paths, которые могут писать comments:
  - legacy `_run_handoff_pass()` issue alerts;
  - tier `_handle_tier_finding()` tier-1 issue alerts;
  - `stale_bundle` board alert path.
- State semantics заданы явно:
  - budget расходуется только непосредственно перед попыткой `post_issue_comment`;
  - `state.record_handoff_alert()` вызывается только после успешного comment post;
  - если budget отклоняет/defer: handoff state entry не записывается, tier promotion не происходит, watchdog логирует `handoff_alert_deferred_budget issue=%s ftype=%s posted=%s hard=%s`;
  - если comment post бросает exception: handoff state entry не записывается, текущий failure log сохраняется;
  - existing active alerts можно оценивать для no-comment transitions, но любой transition, который пишет новый comment, сначала резервирует budget.
- Детерминированный порядок: в каждом tick обрабатывать companies в config order, issues в API order после de-dupe, detectors в текущем precedence order, затем `stale_bundle` последним. Tests могут assert budget results against this order.
- Tests доказывают:
  - 10 stale/done/recovery findings create 0 comments and 0 state entries.
  - при soft=5 и hard=8, 10 fresh new findings пишут ровно 8 comments, один раз логируют soft threshold, defer 2 без state entries и повторяют deferred candidates на следующем tick;
  - `stale_bundle` consumes the same budget and is deferred if the hard cap is already exhausted by issue alerts.

## Step 6 — Cooldown/dedupe regression check

**Owner:** CXPythonEngineer.

**Описание:** Проверить и закрепить, что state-machine snapshot + `handoff_alert_cooldown_min` реально подавляет повторные alert comments для той же finding snapshot.

**Affected paths:**

- `services/watchdog/src/gimle_watchdog/daemon.py`
- `services/watchdog/src/gimle_watchdog/state.py`
- `services/watchdog/tests/test_daemon.py`
- `services/watchdog/tests/test_state.py`

**Dependencies:** Step 5.

**Acceptance criteria:**

- Test reproduces two consecutive ticks with identical finding snapshot and asserts one comment, not two.
- Snapshot mismatch remains intentional reset path, but any reset that would post a new alert comment must reserve shared budget first.
- State clear on no-finding remains intact and tested.

## Step 7 — Synthetic e2e no-spam regression

**Owner:** CXPythonEngineer.

**Описание:** Добавить e2e test, который моделирует сам инцидент: много stale/done/recovery-origin issues и включённые detectors.

**Affected paths:**

- `services/watchdog/tests/e2e/test_no_spam_on_stale_issues.py`
- существующие fixtures под `services/watchdog/tests/`

**Dependencies:** Steps 3-6.

**Acceptance criteria:**

- Fixture содержит минимум 10 stale/done или recovery-origin issues, включая cases для всех шести issue-bound detectors:
  - comment-only handoff marker on stale active issue;
  - wrong assignee on stale active issue;
  - review owned by implementer on stale review issue;
  - cross-team assignee on stale active issue;
  - done-without-QA on recovery-origin issue;
  - infra-block marker on stale blocked/done issue.
- При включённых legacy `handoff_alert_enabled` и tier flags `handoff_cross_team_enabled`, `handoff_ownerless_enabled`, `handoff_infra_block_enabled` результат: `alerts == 0`, `comments_posted == []`, no state entries.
- Отдельные fresh active control cases для legacy и tier paths всё ещё fire, чтобы test не стал false-negative из-за выключенного detector path.

## Step 8 — Runbook update

**Owner:** CXTechnicalWriter, либо CXPythonEngineer если writer недоступен на момент handoff.

**Описание:** Зафиксировать безопасный порядок повторного включения handoff detectors после hardening.

**Affected paths:**

- `docs/runbooks/watchdog-handoff-alerts.md`

**Dependencies:** Steps 3-7.

**Acceptance criteria:**

- Runbook содержит re-enable checklist:
  - сначала enable одного detector flag в staging/local;
  - проверить `tier_alert_posted` volume;
  - проверить отсутствие alerts на 32 known-spammed issue;
  - включать production flags по одному;
  - rollback: вернуть все `handoff_*_enabled: false` и restart watchdog.
- Runbook явно говорит, что `handoff_auto_repair_enabled` остаётся `false`, пока Board отдельно не решит иначе.

## Step 9 — Implementation verification

**Owner:** CXPythonEngineer.

**Описание:** Локально доказать корректность Python slice перед review.

**Affected paths:** все paths из Steps 3-8.

**Dependencies:** Steps 3-8.

**Acceptance criteria:**

- `uv run ruff check services/watchdog/`
- `uv run mypy services/watchdog/src/`
- `uv run pytest services/watchdog/ -v`
- Push branch to origin.
- Handoff comment to CXCodeReviewer includes branch, commit SHA and command output summary.

## Step 10 — Mechanical code review

**Owner:** CXCodeReviewer.

**Описание:** Проверить реализацию как regression hardening, не как feature expansion.

**Affected paths:** все changed paths.

**Dependencies:** Step 9.

**Acceptance criteria:**

- Reviewer verifies all issue-bound detectors share age/status/origin gating.
- Reviewer verifies successful alert-post logging exists.
- Reviewer verifies budget applies to new alert comments and cannot be bypassed by stale bundle path.
- Reviewer verifies e2e incident fixture would have prevented GIM-244 spam.
- APPROVE -> CodexArchitectReviewer; REQUEST CHANGES -> CXPythonEngineer.

## Step 11 — Architecture review

**Owner:** CodexArchitectReviewer.

**Описание:** Проверить failure-mode архитектуру: bounded side effects, observability, rollout safety.

**Affected paths:** all changed paths.

**Dependencies:** Step 10 APPROVE.

**Acceptance criteria:**

- Architecture reviewer confirms no detector can post unbounded comments across closed/stale/recovery issue sets.
- Reviewer confirms config defaults keep new behavior safe when detectors are disabled.
- Reviewer confirms no cross-team UUID routing regression introduced.
- APPROVE -> CXQAEngineer.

## Step 12 — Runtime QA

**Owner:** CXQAEngineer.

**Описание:** Проверить не только unit/e2e tests, но и runtime behavior с watchdog config, похожим на incident window.

**Affected paths:** runtime + test artifacts.

**Dependencies:** Step 11 APPROVE.

**Acceptance criteria:**

- `uv run ruff check services/watchdog/` green.
- `uv run mypy services/watchdog/src/` green.
- `uv run pytest services/watchdog/ -v` green.
- Runtime smoke с включёнными detector flags и synthetic stale issue set показывает 0 alert comments.
- Smoke с fresh active control issue показывает 1 bounded alert и `tier_alert_posted` log.
- QA comment follows Phase 4.1 evidence format and hands to CXCTO.

## Step 13 — Merge + post-merge queue

**Owner:** CXCTO.

**Описание:** Merge only after review + QA evidence, then decide whether follow-up tickets are needed for out-of-scope operator decisions.

**Affected paths:** PR only; issue thread.

**Dependencies:** Step 12 QA PASS.

**Acceptance criteria:**

- Before claiming merge blocker, paste:
  - `gh pr view --json mergeStateStatus,mergeable,statusCheckRollup,reviewDecision,headRefOid`;
  - check-runs for head SHA;
  - develop branch protection status.
- Squash-merge to `develop` only if required gates are green.
- Mark GIM-255 done with merge SHA.
- If Board chooses comment cleanup, auto-repair enablement, or tick-timeout work, create separate follow-up issue(s); otherwise leave those out of GIM-255.

## Open Board Decisions

- Delete 258 spam comments or keep incident audit trail?
- After hardening, keep `handoff_auto_repair_enabled: false` or schedule a separate auto-repair enablement slice?
- Treat watchdog tick timeout as a separate blocker or defer until after detector re-enable smoke?
