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
  - `DaemonConfig.recovery_enabled` (default `False`);
  - `DaemonConfig.recovery_first_run_baseline_only` (default `True`);
  - `DaemonConfig.max_actions_per_tick` (default `1`);
  - `Thresholds.recover_max_age_min` (per-company; default `180`);
  - `HandoffConfig.handoff_recent_window_min` (default `180`);
  - `HandoffConfig.handoff_alert_enabled`, `handoff_cross_team_enabled`,
    `handoff_ownerless_enabled`, `handoff_infra_block_enabled`,
    `handoff_stale_bundle_enabled`, `handoff_auto_repair_enabled`, and the
    alert budget fields.
- `services/watchdog/src/gimle_watchdog/daemon.py`
  - `_run_recovery_pass()` returns immediately with `recovery_pass_disabled`
    when recovery is off;
  - `_tick()` constructs one `AlertPostBudget` and passes the same instance to
    `_run_handoff_pass(..., budget=budget)` and
    `_run_tier_pass(..., budget=budget)` — the "one shared budget" invariant
    is currently enforced only by this explicit pass-through (each pass
    default-constructs its own budget when `budget=None`).
- `services/watchdog/src/gimle_watchdog/detection.py`
  - recovery uses `list_active_issues`;
  - recovery respects `Thresholds.recover_max_age_min`.
- `services/watchdog/src/gimle_watchdog/paperclip.py` / `models.py`
  - `originKind` parses into `Issue.origin_kind: str | None`. Issue-bound
    semantic detectors consult it via
    `detection_semantic._issue_is_eligible` (which skips
    `origin_kind in SKIP_ORIGINS`). Recovery's age gate is independent —
    `detection.scan_died_mid_work` only compares
    `issue.updated_at` against `now - recover_max_age_min`.
- `services/watchdog/src/gimle_watchdog/__main__.py`
  - `_cmd_status` already exists but currently prints only:
    `Companies configured`, `paperclip-skills procs matching filter now`,
    `Active cooldowns`, `Active escalations`, `Permanent escalations`.

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
- Add a runbook for staged recovery re-enable. The canonical step ordering is
  defined once in §5.4 below and copied verbatim into `docs/runbooks/
  watchdog-operational-reenable.md`; this section MUST NOT restate the steps.
- Commit a cohort evidence fixture at
  `services/watchdog/tests/fixtures/gim255_cohort.json` with the schema:
  ```json
  {
    "paperclip_issue_ids": ["<uuid>", "<uuid>", "<32 entries>"],
    "issue_numbers": [244, 255, "<human-readable GIM-N numbers>"],
    "comment_ids": ["<uuid>", "<uuid>", "..."],
    "comment_markers": ["<optional body substring fingerprints>"],
    "posted_at_window": {"from": "2026-04-30T..Z", "to": "2026-04-30T..Z"},
    "author_agent_ids": ["<spam-detector agent uuid>", "..."]
  }
  ```
  Paperclip issue IDs and comment IDs are UUIDs (per paperclip.py data
  model); `issue_numbers` carries the human GIM-N labels. `comment_ids` is
  a flat list — UUIDs are non-monotonic, so a range is not well-defined.
  `comment_markers` is optional and only useful if message bodies share a
  fingerprint substring.

  **Scope of the fixture:** evidence for tests, dry-runs, and operator
  runbook only. It is NOT loaded by production watchdog code at runtime
  and is NOT a runtime ignore list. Production protection against a
  repeat of this incident is the GIM-255 hardening already in place
  (per-issue age gate `recover_max_age_min` / `handoff_recent_window_min`,
  `origin_kind` eligibility, `AlertPostBudget`, cooldown/escalation
  bookkeeping). The fixture exists so we can prove in CI that those
  general protections cover the historical cohort — not so we can
  hard-code GIM-244/GIM-255 IDs into production logic. Future spam
  clusters belong in new fixtures, not in this one; the fixture is
  frozen on incident exit.
- Add tests for the new status output and posture warnings.
- Document that the 258 spam comments remain as audit trail.
- Document that watchdog must ignore issue-bound findings on issues older than
  3 hours. `stale_bundle` is the only global detector exempt from the
  per-issue age gate because it is not issue-bound; the exemption applies to
  the age gate ONLY. Production cohort isolation comes from the same general
  protections (cooldowns, budgets, age gates on the issues `stale_bundle`
  surfaces), not from a runtime fixture lookup.

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

Add a pure helper `describe_effective_mode(cfg: Config) -> EffectiveMode`,
used by CLI and logs.

Classification is a **total function** over the boolean triplet
`(recovery, any_alert, auto_repair)` with `unsafe-auto-repair` as a strictly
dominant overlay. The truth table is exhaustive:

| `recovery_enabled` | `any_alert_path_on` | `handoff_auto_repair_enabled` | Mode |
|---|---|---|---|
| any | any | `true` | `unsafe-auto-repair` |
| `false` | `false` | `false` | `observe-only` |
| `false` | `true` | `false` | `alert-only` |
| `true` | `false` | `false` | `recovery-only` |
| `true` | `true` | `false` | `full-watchdog` |

Define two module-level constants in `config.py`:

```python
ALERT_FLAG_NAMES: Final[frozenset[str]] = frozenset({
    "handoff_alert_enabled",
    "handoff_cross_team_enabled",
    "handoff_ownerless_enabled",
    "handoff_infra_block_enabled",
    "handoff_stale_bundle_enabled",
})
AUTO_REPAIR_FLAG_NAME: Final[str] = "handoff_auto_repair_enabled"
```

`any_alert_path_on` is the OR of all `ALERT_FLAG_NAMES` values on the
config. `describe_effective_mode` MUST `raise ConfigError` if it encounters
a `handoff_*_enabled` field on `HandoffConfig` that is neither in
`ALERT_FLAG_NAMES` nor equal to `AUTO_REPAIR_FLAG_NAME`. Future non-alert
guard flags (e.g. an opt-in `handoff_dry_run_enabled`) MUST be added to one
of these constants explicitly. This fails fast on the "default-off new
detector flipped on by typo'd YAML" regression class without rejecting
unrelated future guards.

§7 must include a partition-completeness property test that enumerates the
2³ = 8 combinations of `(recovery, any_alert, auto_repair)` and asserts each
maps to exactly one mode.

`unsafe-auto-repair` MUST be printed prominently in both `status` output and
the `watchdog_posture` log event because Board has not approved production
auto-repair.

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

Status MUST NOT call mutating Paperclip endpoints. If it checks live company
health, it uses read-only GETs only.

**Authoritative live company inventory source (was open question Q1):**
the Paperclip API list-companies GET is the source of truth for which
companies *exist*. The watchdog config file is the *coverage assertion* —
which existing companies the operator chose to cover.

Implementation: add a new read-only method
`PaperclipClient.list_companies()` that issues a GET against the
Paperclip companies endpoint and returns companies with
`archived=false` (or whatever the live-status discriminator is — the
implementer must confirm against the Paperclip schema and document the
filter). Archived and test companies are explicitly excluded so they do
not produce false `live_but_unconfigured` warnings.

`status` reads local config AND calls `list_companies()`, then reconciles
the **active** set:

- companies in config AND active-live → printed normally with `recover_max_age_min`;
- companies in config but NOT in active-live → warning
  `configured_but_missing=<company_id>` (may indicate company was archived
  or deleted);
- companies active-live but NOT in config → warning
  `live_but_unconfigured=<company_id> name=<name>` — this is the structural
  catch for PBUG-9 (one company covered, others not).

**API-failure behavior:**

- If the `/api/companies` GET fails (timeout, 5xx, JSON parse error), `status`
  prints `company_inventory=unreachable reason=<short>` and exits with code 2.
- An explicit `gimle-watchdog status --allow-degraded` suppresses the non-zero
  exit but still prints the unreachable line; it never silently downgrades to
  "all OK".
- For per-company health GETs (if any), each prints
  `company_health=unreachable(<reason>)` rather than being omitted.

This explicit failure surfacing is load-bearing: silent skip would
re-introduce the PBUG-9 invisibility the spec exists to fix.

### 5.3 Tick/startup logs

Two distinct structured events.

**`watchdog_starting`** — emitted as the first line `main()` writes, **before
any config load or Paperclip GET**. If the daemon crashes during
company-loading (PBUG-9 territory), this event still survives in the
operator-captured stderr stream.

**Pre-load logging gap (honest about reality):** `logger.setup_logging(cfg.logging)`
runs inside `_cmd_run`/`_cmd_tick` AFTER `load_config(...)`. Anything emitted
through the `logging` module before that point reaches only the root logger,
which has no file handler configured yet — so it does NOT land in the daemon's
rotating log file. Two compatible delivery mechanisms must both fire so the
event survives every failure mode:

1. Direct `print(json.dumps({...}), file=sys.stderr, flush=True)`. launchd
   (`StandardErrorPath`) and systemd (`journald`) capture stderr by default,
   so the event is durably recorded regardless of Python logging state.
2. `log.info("watchdog_starting", extra={...})` through the `watchdog.cli`
   logger. Once `setup_logging` runs, subsequent ticks' file-bound logs are
   consistent with this event's namespace.

Required fields on BOTH delivery paths:

- `event`: `"watchdog_starting"`;
- `pid`;
- `version` (package version; `"unknown"` if `__version__` is not yet exported);
- `config_path` (best-effort scan of argv);
- `argv` (token list; no secrets in current argv set).

**`watchdog_posture`** — emitted at first tick start and at every subsequent
tick start, after companies are loaded. Fields:

- `event`: `"watchdog_posture"`;
- `mode` (one of the five enum values from §5.1);
- `company_count`;
- `company_names` (list of human names);
- `company_ids` (list of UUIDs);
- `configured_but_missing` (list of company IDs from reconciliation);
- `live_but_unconfigured` (list of company IDs from reconciliation);
- `recovery_enabled`;
- `recovery_baseline_completed`;
- `max_actions_per_tick`;
- `handoff_recent_window_min`;
- `recover_max_age_min_per_company` (map `{company_id: minutes}`);
- `handoff_alert_enabled`;
- `handoff_cross_team_enabled`;
- `handoff_ownerless_enabled`;
- `handoff_infra_block_enabled`;
- `handoff_stale_bundle_enabled`;
- `handoff_auto_repair_enabled`;
- `alert_budget_soft`;
- `alert_budget_hard`.

Keep existing `tick_start companies=%d` log line for backward compatibility,
but it is no longer the diagnostic — `watchdog_starting` + `watchdog_posture`
are.

### 5.4 Staged recovery re-enable

This is the canonical step ordering. `docs/runbooks/
watchdog-operational-reenable.md` copies it verbatim; §4 In does not
duplicate it.

1. **Observe-only precheck (recovery OFF)**
   - `recovery_enabled: false`;
   - all `handoff_*_enabled` flags false;
   - `gimle-watchdog status` shows mode=`observe-only`, all expected
     companies present, `configured_but_missing=[]`, `live_but_unconfigured=[]`;
   - status shows `handoff_recent_window_min=180` and each company
     `recover_max_age_min=180`;
   - **observe-only side-effect smoke:** run one live tick on the iMac
     against production Paperclip and verify zero outbound writes — no
     `wake_result`, no `*_alert_posted`, no `auto_repair_*` events. This
     proves the mode contract holds end-to-end (it does NOT prove cohort
     isolation; cohort isolation is proved separately by the CI tests
     in §7).
2. **Baseline tick (recovery ON, no wake)**
   - set `recovery_enabled: true`;
   - keep `recovery_first_run_baseline_only: true`;
   - keep `max_actions_per_tick: 1`;
   - verify `recovery_baseline_seeded` appears, but no wake actions happen;
   - verify issues older than 3 hours produce no recovery actions.
3. **Controlled recovery (one wake per tick)**
   - turn `recovery_first_run_baseline_only: false`;
   - run one normal tick;
   - verify at most one `wake_result`;
   - inspect the issue ID touched and confirm it is recent legitimate work
     (newer than 3 hours, not on the historical cohort list — operator
     check against the fixture, not a runtime gate).
4. **Scale mechanical recovery**
   - **PBUG-5 gate:** do NOT raise `max_actions_per_tick` above 1 while
     PBUG-5 (stale execution lock → 403 on legitimate later
     comments/PATCHes) is unfixed. Mechanical recovery's release+PATCH path
     is exactly the surface PBUG-5 breaks; under load every locked issue
     becomes a recurring failed-action loop that burns the tick budget on
     cohort-adjacent victims and masks legitimate recoveries with log
     noise. Hold `max_actions_per_tick=1` until PBUG-5 ships.
   - After PBUG-5 ships: increase `max_actions_per_tick` by one step per
     clean evidence cycle.
5. **Bounded alert re-enable**
   - enable at most one detector flag at a time;
   - before flipping a flag in production, confirm the §7 CI cohort harness
     for that specific detector is green;
   - after flipping, verify `handoff_alert_posted` / `tier_alert_posted`
     volume against the `AlertPostBudget` over a one-tick window.
6. **Auto-repair remains off**
   - `handoff_auto_repair_enabled: false` unless a separate Board-approved
     spec enables it. Until then `status` reports `unsafe-auto-repair` for
     any config that turns this on.

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

### Status + posture surface

- `gimle-watchdog status` prints effective mode, recovery settings, first-run
  baseline state, max actions per tick, company names/IDs, handoff flags,
  auto-repair state, alert budgets, `handoff_recent_window_min`,
  per-company `recover_max_age_min`, cooldown counts, escalation counts,
  `configured_but_missing` and `live_but_unconfigured` reconciliation
  warnings, and the `unsafe-auto-repair` banner when applicable.
- Status output clearly distinguishes the five §5.1 modes: observe-only,
  alert-only, recovery-only, full-watchdog, unsafe-auto-repair.
- Daemon emits a structured `watchdog_starting` event before any config
  load (see §5.3 for the minimal pre-load fallback path), AND a
  `watchdog_posture` event at first tick, AND at each subsequent tick
  start, with the full field set defined in §5.3.
- If recovery is disabled while live companies exist, both status output and
  `watchdog_posture` log surface `live_but_unconfigured` and/or the
  "recovery disabled while active companies are configured" warning. This
  is the structural PBUG-9 catch.

### Mode classifier coverage (not echo tests)

- A unit test of `describe_effective_mode` enumerates all 2³ = 8 combinations
  of `(recovery_enabled, any_alert_path_on, handoff_auto_repair_enabled)`
  and asserts each maps to exactly one of the five enum values. The test
  fails if any combination raises `ConfigError` or returns a value outside
  the enum.
- For EACH of the five modes, a daemon-level test sets the matching config,
  runs one tick against a synthetic fixture, and asserts BOTH:
  - `describe_effective_mode(cfg)` returns the expected enum value;
  - the observable side-effect counters for that tick match the mode
    contract — e.g. `observe-only` ⇒ 0 outbound Paperclip writes / 0
    `wake_result` / 0 `*_alert_posted` / 0 `auto_repair_*` events;
    `recovery-only` ⇒ may emit `wake_result` events but 0 `*_alert_posted`;
    `alert-only` ⇒ may emit `*_alert_posted` but 0 `wake_result`.
- A regression test asserts `_run_handoff_pass` and `_run_tier_pass` receive
  the same `AlertPostBudget` instance from `_tick()` (object identity
  check), proving the "one shared budget per tick" invariant survives
  refactor.

### Stale-issue age gates

- Mechanical recovery skips stale active issues via `recover_max_age_min`;
- legacy handoff detectors skip stale issues via `handoff_recent_window_min`;
- tier issue-bound detectors skip stale issues via `handoff_recent_window_min`;
- `stale_bundle` is exempt from the per-issue age gate (it is global, not
  issue-bound). Its cohort isolation is proved by the §7 "Cohort isolation"
  CI harness below, not by a runtime carve-out.

### Cohort isolation (data-backed, not by-absence)

- `services/watchdog/tests/fixtures/gim255_cohort.json` is committed with the
  schema in §4 (paperclip_issue_ids, issue_numbers, comment_ids,
  comment_markers, posted_at_window, author_agent_ids).
- A CI cohort harness loads that fixture into an in-memory Paperclip
  mock and, for EACH detector individually with its `handoff_*_enabled`
  flag set to `true` and a mocked write-sink, runs one tick and asserts
  zero calls to `post_issue_comment` and zero wake-action emissions
  against any cohort issue. Detectors tested: each entry in
  `ALERT_FLAG_NAMES` plus the recovery code path plus `stale_bundle`
  (global).
- This is a CI test (`tests/e2e/test_gim255_cohort_isolation.py` or
  similar), not a manual checklist item. It proves the GIM-255 general
  hardening (age gates, `origin_kind` eligibility, budgets, cooldowns)
  covers the historical cohort. The fixture is never loaded by
  production code.

### Post-comment-path registry

- A module-level `POST_COMMENT_PATHS: Final[frozenset[str]]` enumerates the
  bounded callsites that may call `paperclip.PaperclipClient.post_issue_comment`.
- A test asserts every `post_issue_comment` callsite reachable in
  `services/watchdog/src/` is registered in `POST_COMMENT_PATHS`.
- Adding a new callsite requires updating the registry AND the test.
  A full spec amendment is only required when introducing a new *class*
  of side-effect channel (e.g. posting to a non-issue Paperclip endpoint,
  or to an external service like Telegram/Slack).
- This enforces "No new detector posts comments beyond existing GIM-255
  bounded paths" mechanically rather than by reviewer vigilance.

### Operational invariants

- The runbook at `docs/runbooks/watchdog-operational-reenable.md` carries
  the same phase ordering as §5.4 and links back to this spec for canonical
  semantics. On any conflict, the spec wins; the runbook is treated as
  derivative documentation, not as a separate source of truth. The runbook
  explicitly says the 258 spam comments remain as audit trail and watchdog
  ignores them during re-enable validation via the general protections, not
  via runtime cohort lookups.
- No production auto-repair is enabled; `handoff_auto_repair_enabled=false`
  in any shipped config.
- The runbook explicitly holds `max_actions_per_tick=1` until PBUG-5 ships.

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

## 9. Resolved decisions and explicit followups

### Resolved inline by §5.2 (previously open)

- **Authoritative live company inventory:** Paperclip API
  `/api/companies` GET. Watchdog config is the *coverage assertion*, not the
  inventory. Reconciliation produces `configured_but_missing` and
  `live_but_unconfigured` warnings.
- **Live GET vs local-only:** `status` does perform read-only Paperclip GETs.
  On failure it prints `company_inventory=unreachable` and exits non-zero
  unless `--allow-degraded` is set; it never silently downgrades.

### Followups — explicitly NOT in this spec

- `maintenance_read_only_until` / `recovery_disabled_reason` config fields so
  a temporary read-only posture is visible and auto-expires. Defer to a
  followup spec; not blocking re-enable because the `watchdog_posture` log
  + `status` already make the current posture visible.
- Promoting prolonged `recovery_pass_disabled` to a Board alert. Defer to a
  followup spec; today the local status warning is sufficient because the
  operator is on the hook to read it.
- Splitting "operational visibility" and "mechanical recovery re-enable" into
  two specs / two PRs. Architect review flagged this as a clean cut; if the
  implementer hits a coupling issue, raise it before phase 3.

### Open (must answer before phase 1 implementation)

- The literal contents of `services/watchdog/tests/fixtures/gim255_cohort.json`
  — the 32 Paperclip issue UUIDs, their GIM-N numbers, the list of spam
  comment UUIDs, the posted-at time window, and the spam-detector agent
  UUID. Operator commits the cohort fixture from incident evidence;
  implementer cannot guess these values.
