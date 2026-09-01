# Watchdog nested active-run parsing

Date: 2026-09-02

Baseline SHA: `ab71842f52833e849c8bfb0499adbe67eabc540b`

Branch: `fix/watchdog-nested-active-run`

Status: APPROVED FOR IMPLEMENTATION by the Human Engineering Lead through the
existing authorization to repair, merge, deploy, and rerun the Glitcherry
watchdog qualification.

## Problem

The deployed watchdog now discovers detached no-TTY Codex processes, but the
Glitcherry DX-005-R1 live qualification stopped at its pre-signal guard. The
detector selected the exact attributed process and the guard returned
`no_exact_active_run` even though:

- the issue API reported the same `executionRunId` as the process identity;
- the heartbeat-run API reported that run as `running`; and
- the issue-list response included the live run as nested `activeRun.id`.

`_issue_from_json` currently reads only a top-level `activeRunId`. The current
Paperclip issue-list contract exposes a nested `activeRun` object instead, so
`Issue.active_run_id` becomes `None` and the exact-run guard fails closed.

## Assumptions

- `activeRun.id` is the authoritative active-run identifier in the current
  Paperclip issue-list response.
- A missing or malformed nested object must continue to fail closed.
- Keeping support for a top-level `activeRunId` is cheap and preserves
  compatibility with older fixtures or deployments.
- No watchdog threshold, action budget, signal policy, or Paperclip issue state
  should change as part of this fix.

## Scope

- Parse the active run from `activeRun.id` when present.
- Retain the existing top-level `activeRunId` fallback.
- Add regression coverage using the observed issue-list JSON shape.
- Verify that the exact Codex correlation accepts the parsed nested run and that
  missing/mismatched active-run evidence still fails closed.

## Out of scope

- Changing hang thresholds, cadence, or recovery mode.
- Weakening company, agent, issue, run, parent-process, or PID correlation.
- Changing Paperclip server responses.
- Retrying or rewriting GLA-8, GLA-9, GLA-10, or GLA-11 evidence.
- Starting product work or TP-01.

## Affected areas

- `services/watchdog/src/gimle_watchdog/paperclip.py`
  - normalize the current nested active-run response into `Issue.active_run_id`.
- `services/watchdog/tests/test_paperclip.py`
  - prove parsing of the real nested shape and backward-compatible fallback.
- `services/watchdog/tests/test_daemon.py`
  - only if needed to connect the parsed response to the existing exact-run
    correlation behavior; avoid duplicate unit coverage.

## Acceptance criteria

1. A response with `activeRun: {"id": "run-1", "status": "running"}` produces
   `Issue.active_run_id == "run-1"`.
2. A response with only top-level `activeRunId` continues to parse that value.
3. A missing, null, non-object, or object-without-id `activeRun` does not invent
   an active run.
4. The existing exact Codex guard still requires matching company, agent, issue,
   active run, active issue status, process parent, and process identity.
5. No production configuration or threshold changes.

## Verification plan

1. Add the regression test first and demonstrate failure against the baseline.
2. Run the focused Paperclip parser and Codex correlation tests.
3. Run all watchdog tests except the environment-dependent live Paperclip test.
4. Run Ruff check, Ruff format check, mypy, and `git diff --check`.
5. Push one implementation PR to `develop`, wait for required CI, squash-merge,
   deploy the exact merge SHA, and verify one live watchdog process.

## Risks and rollback

- Risk: treating a stale `activeRun` object as live. Mitigation: consume only an
  explicit non-empty string `id`; the existing guard still checks all other
  identity fields and active issue status.
- Risk: schema drift between Paperclip versions. Mitigation: keep the legacy
  top-level fallback and tests for both forms.
- Rollback: revert the single merge commit and redeploy the prior known SHA. No
  state migration or configuration rollback is required.

## Open questions

None. The live response, failure log, and existing guard contract make the
required normalization unambiguous.
