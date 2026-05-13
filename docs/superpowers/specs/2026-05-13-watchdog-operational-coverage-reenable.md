---
slug: watchdog-operational-coverage-reenable
status: proposed
branch: docs/watchdog-operational-coverage-spec
base: origin/develop@69ce650
date: 2026-05-13
owner: CX/Codex
related:
  - GIM-244
  - GIM-255
  - PBUG-5
  - PBUG-8
  - PBUG-9
---

# Watchdog operational coverage, recovery re-enable, and status visibility

## 1. Context

Watchdog was put into an effectively read-only posture after the GIM-244 /
GIM-255 incident. The immediate reason was correct: tier handoff detectors
posted 258 alert comments across 32 issues in roughly 4 hours, so side effects
had to stop until the detectors were bounded.

GIM-255 then landed the important safety work:

- issue-bound detectors have age/status/origin gates;
- `originKind` is parsed into `Issue.origin_kind`;
- `handoff_recent_window_min` defaults to 180;
- mechanical recovery has `recover_max_age_min` and must use the same
  3-hour default boundary unless an explicit per-company override is approved;
- `AlertPostBudget` applies one shared soft/hard per-tick budget;
- successful alert posts are observable;
- no-spam e2e coverage exists for stale/recovery-origin issues.

Separate in-review recovery work also landed:

- recovery scans active issues through `list_active_issues`;
- `trigger_respawn` preserves status during `release+PATCH`;
- first-run baseline mode can seed cooldowns without waking old work.

The remaining problem is operational, not detector math. Live watchdog logs
sampled on 2026-05-13 showed:

```json
{"message": "tick_start companies=1"}
{"message": "recovery_pass_disabled"}
{"message": "tick_end actions=0"}
```

At the same time, Paperclip `server.log` showed process bugs across multiple
companies and projects. In particular:

- PBUG-5: stale execution locks reject legitimate later agent comments/PATCHes
  with 403;
- PBUG-6: bad Paperclip write payload shapes lose evidence with 400;
- PBUG-8: mass `/issues/<TOKEN>` 404 noise makes WARN logs hard to use;
- PBUG-9: watchdog covers one company and has recovery disabled, so
  non-covered companies do not self-heal.

The 258 spam comments are kept as incident audit trail. This spec assumes
deleting them is not a viable recovery path and does not include comment
cleanup.

Those old comments must also be operationally inert: watchdog must not treat
the historical GIM-244/GIM-255 spam-alert comments as fresh evidence, wake
signals, ownerless-completion evidence gaps, infra-block markers, or reasons
to re-alert. The safe behavior is to identify the incident cohort and ignore
those comments/issues during re-enable validation unless an operator
explicitly selects one as a fresh control case.

## 2. Goal

Make watchdog safe to move out of read-only mode for mechanical recovery while
making its coverage and side-effect posture visible enough that operators can
trust it.

Success means an operator can answer, from `gimle-watchdog status` and logs:

- which companies are covered;
- whether recovery is enabled;
- whether first-run baseline mode is still pending;
- which handoff/tier detectors are enabled;
- whether auto-repair is disabled;
- what per-tick alert budgets are active;
- whether the last tick had recovery actions, alert posts, deferrals, or
  failures.

It also means production can re-enable mechanical recovery for all live
companies without re-enabling unbounded alerting or auto-repair.

## 3. Existing implementation to preserve

Do not re-implement GIM-255. The following already exists and must remain the
foundation:

- `services/watchdog/src/gimle_watchdog/config.py`
  - `DaemonConfig.recovery_enabled`;
  - `DaemonConfig.recovery_first_run_baseline_only`;
  - `DaemonConfig.max_actions_per_tick`;
  - handoff flags and alert budget fields.
- `services/watchdog/src/gimle_watchdog/daemon.py`
  - `_run_recovery_pass()` returns immediately with `recovery_pass_disabled`
    when recovery is off;
  - one `AlertPostBudget` is shared by legacy and tier alert paths in `_tick()`.
- `services/watchdog/src/gimle_watchdog/detection.py`
  - recovery uses `list_active_issues`;
  - recovery respects `recover_max_age_min`.
- `services/watchdog/src/gimle_watchdog/__main__.py`
  - `status` already exists but currently reports only company count, process
    filter matches, cooldowns, escalations, and permanent escalations.

## 4. Scope

### In

- Define a clear operational mode vocabulary:
  - **observe-only**: no recovery, no alert comments, no auto-repair;
  - **alert-only**: may post bounded detector alerts, no recovery repairs;
  - **recovery-only**: mechanical release/PATCH recovery enabled, handoff
    comments/auto-repair disabled;
  - **full watchdog**: recovery and bounded alerts enabled; auto-repair still
    requires a separate Board decision.
- Expand `gimle-watchdog status` so it reports the effective mode and
  coverage for every configured company.
- Add structured startup/tick log fields for operational posture:
  - company IDs/names;
  - recovery enabled/disabled;
  - first-run baseline pending/completed;
  - max actions per tick;
  - recover max age per company;
  - handoff detector flags;
  - alert budget;
  - auto-repair enabled/disabled.
- Add warnings when watchdog is operationally inert:
  - no companies configured;
  - recovery disabled and all handoff detector flags disabled;
  - recovery disabled while active companies exist and no maintenance marker
    is configured;
  - auto-repair enabled without an explicit `allow_auto_repair: true` style
    guard, if such guard is added in implementation.
- Add a runbook for staged recovery re-enable:
  1. confirm GIM-255 hardening is deployed;
  2. put all live company IDs into config;
  3. run observe-only status;
  4. confirm both `handoff_recent_window_min` and every company
     `recover_max_age_min` are `180` minutes unless there is a documented
     override;
  5. load the known GIM-255 spam cohort / comment markers into the re-enable
     checklist and verify they produce zero new actions;
  6. enable mechanical recovery with first-run baseline;
  7. verify baseline seeds cooldowns but takes no action;
  8. run one tick with `max_actions_per_tick=1`;
  9. scale gradually;
  10. keep `handoff_auto_repair_enabled=false`;
  11. enable handoff/tier alert flags one at a time only after recovery is
     stable.
- Add tests for the new status output and posture warnings.
- Document that the 258 spam comments remain as audit trail.
- Document that watchdog must ignore issue-bound findings on issues older than
  3 hours. `stale_bundle` is the only global detector exempt from this rule
  because it is not issue-bound.

### Out

- Deleting the 258 spam comments.
- Enabling `handoff_auto_repair_enabled` in production.
- New semantic detectors.
- Paperclip server stale-lock cleanup.
- Fixing PBUG-6 write payload helpers.
- Fixing PBUG-8 markdown/autolink 404 noise.
- Editing live iMac `~/.paperclip/watchdog-config.yaml` in this repository
  change. The code/runbook must make the live edit safe, but the operator
  applies live config.

## 5. Proposed behavior

### 5.1 Effective mode calculation

Add a pure helper, for example `describe_effective_mode(cfg: Config)`, used by
CLI and logs.

Rules:

- `observe-only` when:
  - `daemon.recovery_enabled == false`;
  - all `handoff_*_enabled` detector flags are false;
  - `handoff_alert_enabled == false`;
  - `handoff_auto_repair_enabled == false`.
- `alert-only` when detector/alert flags can post comments but recovery and
  auto-repair are disabled.
- `recovery-only` when mechanical recovery is enabled and all handoff alert
  and tier detector flags are disabled.
- `full-watchdog` when recovery and any bounded detector alert path are
  enabled.
- `unsafe-auto-repair` when `handoff_auto_repair_enabled == true`; status must
  print this loudly because Board has not approved production auto-repair.

### 5.2 `gimle-watchdog status`

Extend status output from current:

```text
Companies configured: 1
paperclip-skills procs matching filter now: N
Active cooldowns: N
Active escalations: N
Permanent escalations: N
```

to include:

```text
Effective mode: recovery-only
Recovery enabled: true
First-run baseline: pending
Max actions per tick: 1
Configured companies:
  - Gimle (9d8f432c-...) recover_max_age_min=180
  - Trading (...) recover_max_age_min=180
  - UAudit (...) recover_max_age_min=180
Handoff alerts: disabled
Tier detectors: cross_team=false ownerless=false infra_block=false stale_bundle=false
Auto repair: disabled
Alert budget: soft=5 hard=20
Active cooldowns: N
Active escalations: N
Permanent escalations: N
Warnings:
  - recovery disabled while active companies are configured
```

Status should not call mutating Paperclip endpoints. If it checks live company
health, it must use read-only GETs and tolerate API failures.

### 5.3 Tick/startup logs

At daemon startup and every tick start, log one structured event:

- `watchdog_posture`;
- `mode`;
- `company_count`;
- `company_names`;
- `recovery_enabled`;
- `recovery_baseline_completed`;
- `max_actions_per_tick`;
- `handoff_alert_enabled`;
- tier detector flags;
- `handoff_auto_repair_enabled`;
- alert soft/hard budgets.

Keep existing `tick_start companies=%d`, but add enough structured fields to
diagnose PBUG-9 without reading config manually.

### 5.4 Staged recovery re-enable

The runbook must explicitly separate mechanical recovery from alerting:

1. **Observe-only precheck**
   - `recovery_enabled: false`;
   - all handoff flags false;
   - `gimle-watchdog status` shows all expected companies.
   - status shows `handoff_recent_window_min=180` and each company
     `recover_max_age_min=180`.
   - status/runbook names the known GIM-255 incident cohort so operators do
     not use old spammed issues as fresh controls.
2. **Baseline tick**
   - set `recovery_enabled: true`;
   - keep `recovery_first_run_baseline_only: true`;
   - keep `max_actions_per_tick: 1`;
   - verify `recovery_baseline_seeded` appears, but no wake actions happen.
   - verify issues older than 3 hours produce no recovery actions.
   - verify the known 258 spam-comment cohort produces no alert comments, no
     recovery actions, and no new state entries.
3. **Controlled recovery**
   - run one normal tick;
   - verify at most one `wake_result`;
   - inspect issue IDs touched.
4. **Scale mechanical recovery**
   - increase `max_actions_per_tick` only after clean evidence.
5. **Bounded alert re-enable**
   - enable at most one detector flag at a time;
   - verify `handoff_alert_posted` / `tier_alert_posted` volume;
   - verify no alerts on the known 32-issue GIM-255 cohort.
6. **Auto-repair remains off**
   - `handoff_auto_repair_enabled: false` unless a separate Board-approved
     spec enables it.

## 6. Affected files

Expected implementation files:

- `services/watchdog/src/gimle_watchdog/__main__.py`
- `services/watchdog/src/gimle_watchdog/config.py`
- `services/watchdog/src/gimle_watchdog/daemon.py`
- `services/watchdog/tests/test_cli.py`
- `services/watchdog/tests/test_daemon.py`
- `docs/runbooks/watchdog-operational-reenable.md`
- `docs/runbooks/watchdog-handoff-alerts.md` if linking to the new runbook is
  cleaner than duplicating content.

This spec file:

- `docs/superpowers/specs/2026-05-13-watchdog-operational-coverage-reenable.md`

## 7. Acceptance criteria

- `gimle-watchdog status` prints effective mode, recovery settings, first-run
  baseline state, max actions per tick, company names/IDs, handoff flags,
  auto-repair state, alert budgets, `handoff_recent_window_min`,
  per-company `recover_max_age_min`, cooldown counts, escalation counts, and
  warnings.
- Status output clearly distinguishes observe-only, alert-only,
  recovery-only, full-watchdog, and unsafe-auto-repair.
- Daemon logs a structured `watchdog_posture` event at startup or first tick
  and at each tick start.
- If recovery is disabled while companies are configured, status and logs make
  that visible; this must catch the PBUG-9 state.
- New tests cover:
  - observe-only mode;
  - recovery-only mode;
  - alert-only mode;
  - unsafe auto-repair warning;
  - multiple company status rendering;
  - posture log fields.
- New or existing tests prove issue-bound watchdog paths ignore issues older
  than 3 hours:
  - mechanical recovery skips stale active issues via `recover_max_age_min`;
  - legacy handoff detectors skip stale issues via `handoff_recent_window_min`;
  - tier issue-bound detectors skip stale issues via `handoff_recent_window_min`.
- Re-enable smoke explicitly proves the known GIM-255 32-issue / 258-comment
  cohort produces zero new alert comments, recovery actions, or new state
  entries.
- Runbook gives exact staged re-enable steps and explicitly says the 258 spam
  comments remain as audit trail and must be ignored by watchdog during
  re-enable validation.
- No production auto-repair is enabled.
- No new detector posts comments beyond existing GIM-255 bounded paths.

## 8. Verification plan

- `uv run ruff check services/watchdog/`
- `uv run mypy services/watchdog/src/`
- `uv run pytest services/watchdog/tests/test_cli.py services/watchdog/tests/test_daemon.py -v`
- If implementation touches posture helpers outside CLI/daemon, run full
  watchdog tests:
  `uv run pytest services/watchdog/ -v`
- Manual smoke on iMac after merge:
  - `gimle-watchdog status`;
  - verify all live company IDs are listed;
  - verify effective mode before and after config change;
  - run one baseline tick and confirm no wake side effects;
  - run one controlled recovery tick with `max_actions_per_tick=1`.

## 9. Open questions

- What is the authoritative live company inventory source: static YAML,
  Paperclip API, or a repo-maintained manifest?
- Should status perform live Paperclip GET checks, or remain purely local
  config/state inspection?
- Do we want an explicit `maintenance_read_only_until` / `recovery_disabled_reason`
  config field so a temporary read-only posture is visible and expires?
- Should prolonged `recovery_pass_disabled` become a watchdog alert to Board,
  or only a local status warning?
