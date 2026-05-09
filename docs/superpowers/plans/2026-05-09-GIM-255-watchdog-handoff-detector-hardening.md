# GIM-255 — План: hardening watchdog handoff detector после регрессии GIM-244

> **Rev 1** — план-first артефакт для CodeReviewer перед реализацией.

**Issue:** GIM-255.
**Инцидент:** GIM-244 / PR #125 (`15c1c67`) включил tier-детекторы watchdog; после включения `handoff_*_enabled` watchdog отправил 258 alert-комментариев в 32 issue за 4 часа.
**Ветка:** `feature/GIM-255-watchdog-handoff-detector-hardening`, от `origin/develop`.
**Цель:** сделать tier-детекторы bounded и observable: не сканировать/алертить старые и recovery-origin issue, явно ограничить статусы, залогировать успешные alert-post, ограничить alert burst за tick и закрыть регрессию e2e-тестом.
**Команда:** CX. Фаза: CXCTO -> CXCodeReviewer (plan-first) -> CXPythonEngineer (impl) -> CXCodeReviewer (mechanical CR) -> CodexArchitectReviewer (architecture review) -> CXQAEngineer (runtime QA) -> CXCTO (merge).

## Discovery

- `git log --all --grep='GIM-255|GIM-244|watchdog handoff|handoff detector'` нашёл GIM-244 commits и PR #125, но не нашёл реализации GIM-255.
- `gh pr list --state all --search "GIM-255 OR GIM-244 OR watchdog handoff OR handoff detector"` нашёл merged PR #125 и более ранние watchdog PR; открытого GIM-255 PR нет.
- `docs/superpowers/plans/2026-05-08-GIM-244-handoff-unification-p2p3.md` описывает исходную реализацию; GIM-255 plan/spec в docs отсутствует.
- Symbol discovery на `origin/develop`:
  - `services/watchdog/src/gimle_watchdog/paperclip.py:Issue` не содержит `origin_kind`;
  - `_issue_from_json()` не читает `originKind`;
  - `_detect_cross_team_handoff()` не проверяет статус или возраст issue;
  - `_detect_ownerless_completion()` проверяет `status == "done"`, но не пропускает recovery/productivity origins;
  - `_detect_infra_block()` не проверяет статус, origin или возраст issue;
  - `_handle_tier_finding()` логирует только `tier_alert_post_failed`, успешный tier-1 alert-post молчит;
  - `_run_tier_pass()` не ограничивает число новых tier-alert post за tick.

## Scope

**In:**

- Age cap для issue-bound tier-детекторов через `handoff_recent_window_min` с дефолтом `180`.
- Origin skip-list для issue-bound tier-детекторов: `stranded_issue_recovery`, `issue_productivity_review`.
- Явные status whitelist для `cross_team_handoff`, `ownerless_completion`, `infra_block`.
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

## Step 4 — Detector gating

**Owner:** CXPythonEngineer.

**Описание:** Сделать каждый issue-bound detector bounded по age/status/origin до того, как он смотрит комментарии или пишет state.

**Affected paths:**

- `services/watchdog/src/gimle_watchdog/detection_semantic.py`
- `services/watchdog/src/gimle_watchdog/daemon.py`
- `services/watchdog/tests/test_detection_semantic.py`

**Dependencies:** Step 3.

**Acceptance criteria:**

- `cross_team_handoff` fires только при `status in {"todo", "in_progress", "in_review"}`, не fires для stale issue и skip origins.
- `ownerless_completion` fires только при `status == "done"`, не fires для stale issue и skip origins.
- `infra_block` fires только для явно разрешённых active statuses, не fires для stale issue и skip origins.
- `stale_bundle` остаётся global detector; на него не навешивается issue status/origin gating, но его alert-post должен входить в общий tick budget.
- Daemon передаёт `now_server` и `handoff_recent_window_min` в issue-bound detectors либо через единый config object, либо через явные параметры. Скрытых `datetime.now()` в detector tests не остаётся.

## Step 5 — Tier alert observability + per-tick budget

**Owner:** CXPythonEngineer.

**Описание:** Сделать успешные alert side-effects видимыми в логах и ограничить burst, чтобы следующий дефект не мог снова записать сотни комментариев за один deploy window.

**Affected paths:**

- `services/watchdog/src/gimle_watchdog/config.py`
- `services/watchdog/src/gimle_watchdog/daemon.py`
- `services/watchdog/src/gimle_watchdog/actions.py`
- `services/watchdog/tests/test_config.py`
- `services/watchdog/tests/test_daemon.py`

**Dependencies:** Step 3.

**Acceptance criteria:**

- Успешный tier-1 issue alert-post логируется как `tier_alert_posted issue=%s ftype=%s comment=%s` или эквивалент с comment id, если API его возвращает.
- Config получает мягкий лимит новых alert comments за tick, например `handoff_alert_soft_budget_per_tick: int = 5`.
- Config получает hard cap, например `handoff_alert_hard_budget_per_tick: int = 20`.
- При soft budget превышении watchdog прекращает новые alert-post в текущем tick и логирует deferred count; уже существующие state transitions без новых comments не ломаются.
- При hard cap watchdog логирует warning и пропускает оставшиеся новые alerts в tick.
- Tests доказывают, что 10 stale/done findings не создают comments, а 10 fresh findings не превышают budget.

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
- Snapshot mismatch remains intentional reset path, but reset does not bypass per-tick budget.
- State clear on no-finding remains intact and tested.

## Step 7 — Synthetic e2e no-spam regression

**Owner:** CXPythonEngineer.

**Описание:** Добавить e2e test, который моделирует сам инцидент: много stale/done/recovery-origin issues и включённые detectors.

**Affected paths:**

- `services/watchdog/tests/e2e/test_no_spam_on_stale_issues.py`
- существующие fixtures под `services/watchdog/tests/`

**Dependencies:** Steps 3-6.

**Acceptance criteria:**

- Fixture содержит минимум 10 stale/done или recovery-origin issues, включая cross-team assignee и done-without-QA cases.
- При включённых `handoff_cross_team_enabled`, `handoff_ownerless_enabled`, `handoff_infra_block_enabled` результат: `alerts == 0`, `comments_posted == []`, no state entries.
- Отдельный fresh active control case всё ещё fires, чтобы test не стал false-negative из-за выключенного detector path.

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
