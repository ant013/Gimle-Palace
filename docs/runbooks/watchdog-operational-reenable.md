# Watchdog operational re-enable

Canonical source: [docs/superpowers/specs/2026-05-13-watchdog-operational-coverage-reenable.md](/Users/Shared/Ios/worktrees/cx/Gimle-Palace/docs/superpowers/specs/2026-05-13-watchdog-operational-coverage-reenable.md)

When to use: taking `gimle-watchdog` from observe-only into mechanical recovery and later bounded detector alerting.

## Phase 1 - Observe-only precheck (recovery OFF)

- Set `recovery_enabled: false`.
- Keep all `handoff_*_enabled` detector flags false.
- Run `gimle-watchdog status` and verify:
  - `Effective mode: observe-only`
  - company inventory reconciliation output is present and non-degraded.
- Confirm cohort harness is green:
  - `uv run pytest services/watchdog/tests/e2e/test_gim255_cohort_isolation.py -v`

## Phase 2 - Baseline tick (recovery ON, no wake)

- Set `recovery_enabled: true`.
- Keep `recovery_first_run_baseline_only: true`.
- Keep all handoff detector flags false.
- Run one daemon tick and verify no outbound writes in logs except posture/health.

## Phase 3 - Controlled recovery (one wake per tick)

- Keep `max_actions_per_tick: 1`.
- Keep detector flags false.
- Run a limited window and verify:
  - only release/PATCH recovery operations are performed;
  - no comment posting paths are executed.

## Phase 4 - Scale mechanical recovery

- Only after Phase 3 evidence is stable, raise `max_actions_per_tick` cautiously.
- Keep detector flags false while scaling recovery.
- Roll back immediately if stale-lock or churn symptoms appear.

## Phase 5 - Bounded alert re-enable

- Enable exactly one detector flag at a time.
- Before enabling each detector in production, run:
  - `uv run pytest services/watchdog/tests/e2e/test_gim255_cohort_isolation.py -k <flag_name> -v`
- Verify alert volume stays within `handoff_alert_soft_budget_per_tick` and `handoff_alert_hard_budget_per_tick`.

## Phase 6 - Auto-repair stays off

- Keep `handoff_auto_repair_enabled: false` in production configs for this slice.
- Any proposal to enable auto-repair requires a separate Board decision and follow-up spec.

## Rollback

- Set `recovery_enabled: false`.
- Set all `handoff_*_enabled` flags false.
- Restart watchdog service.
- Re-run `gimle-watchdog status` and verify `Effective mode: observe-only`.
