# Codex Watchdog Process Attribution

Date: 2026-09-01
Status: PROPOSED
Branch: `fix/codex-watchdog-process-detection`
Baseline: `81199ac82352e90493fff50d785554c5404382ec` (`origin/develop`)
Trigger: Glitcherry DX-004 / GLA-7 `NOT_READY`

## Goal

Teach the existing host watchdog to recognize a genuinely Paperclip-owned
`codex exec` subprocess and terminate it only after a fail-closed,
authoritative `company -> agent -> issue -> active run -> PID` correlation.
Existing hang thresholds, bounded `SIGTERM`/`SIGKILL`, wake limits, and recovery
semantics remain unchanged.

## Problem statement

The live watchdog recognizes only the Claude-oriented command markers
`append-system-prompt-file` and `paperclip-skills`. DX-004 proved that a live
Paperclip Codex run is launched as `/usr/local/bin/codex exec ...` and carries
the Paperclip company, agent, issue/task, run, and workspace identifiers in its
process environment. The current detector and the pre-kill PID-reuse guard
therefore ignore Codex runs completely.

Matching `codex exec` alone is unsafe because unrelated local Codex sessions can
have the same command shape. The remediation must combine a strict command
signature, a Paperclip parent-process check, sanitized process identity, and a
current Paperclip API correlation. Any missing, duplicated, stale, or
contradictory evidence must skip the signal.

## Assumptions

- The watchdog runs on the same host and user account as Paperclip.
- A Paperclip Codex child exposes the non-secret identity keys
  `PAPERCLIP_COMPANY_ID`, `PAPERCLIP_AGENT_ID`, `PAPERCLIP_TASK_ID`,
  `PAPERCLIP_RUN_ID`, and `PAPERCLIP_WORKSPACE_ID` in its environment.
- The process environment also contains secrets such as `PAPERCLIP_API_KEY`.
  The implementation must never log, return, persist, or snapshot the raw
  environment.
- The Paperclip issue API reports `assigneeAgentId` and `activeRunId` for a live
  run. The existing configured-company allowlist remains authoritative.
- macOS is the production host. Linux behavior remains supported or fails
  closed through a small platform adapter.
- DX-004, GLA-7, and its `NOT_READY` evidence remain immutable history. This
  change does not reopen, delete, or rewrite that issue.

## Scope

### In scope

- Recognize the executable/subcommand pair `codex exec` without substring-only
  matching.
- Retain the existing Claude command signature and behavior.
- Read only the allowlisted non-secret Paperclip identity fields for a Codex
  candidate; validate their UUID shape without exposing values in routine logs.
- Require the Codex candidate to be a child of a live `paperclipai run` process,
  not `launchd`, the watchdog, or an unrelated shell/process.
- Correlate exactly one candidate with a configured company, a current active
  issue in that company, its assigned agent, and its current `activeRunId`.
- Repeat the runtime signature, parent, identity, and API correlation immediately
  before signalling the exact PID so PID reuse or a completed/replaced run skips
  termination.
- Preserve the existing elapsed-time, CPU-idle, stream-idle, signal grace,
  maximum-actions-per-tick, and recovery limits.
- Make debug/status output report Claude and Codex candidates without printing
  identity values, environment values, credentials, or full commands.
- Add regression, negative-safety, daemon integration, and live-deploy canary
  coverage.

### Out of scope

- Broad `pkill`, process-name killing, shell globs, or killing every `codex exec`.
- Changing hang thresholds or shortening the 40+ minute production policy.
- Replacing Paperclip's runner, changing agent prompts/models, or changing the
  shared-worktree protocol.
- Product roadmap work, Android code, release/signing/publication, or automatic
  creation of a replacement diagnostic issue.
- Persisting process environments or API credentials as watchdog state/evidence.

## Proposed behavior

### Candidate discovery

Host process discovery includes PID, PPID, elapsed time, CPU time, and command.
Runtime signatures are explicit alternatives:

- Claude: the existing `append-system-prompt-file` plus `paperclip-skills`
  markers;
- Codex: executable basename `codex` followed by subcommand `exec`.

An arbitrary or manually launched `codex exec` is not actionable. A Codex
candidate also needs a direct `paperclipai run` parent and all five allowlisted
Paperclip identity fields. Missing or malformed identity produces no
`HangedProc` action.

### Authoritative correlation

Before kill eligibility, the daemon resolves the candidate's company only from
the configured company allowlist, loads active issues for that company, and
requires exactly one issue satisfying all of:

- issue id equals `PAPERCLIP_TASK_ID`;
- assignee id equals `PAPERCLIP_AGENT_ID`;
- active run id equals `PAPERCLIP_RUN_ID`;
- the assigned agent is a current agent of the same company;
- the issue remains in an active execution state.

Zero or multiple matches, API failure, stale run state, unknown company/agent,
or any parent/identity mismatch is fail-closed: log a reason code and send no
signal.

### Pre-signal guard

Immediately before `SIGTERM`, re-read the exact PID and require the same runtime
signature, PPID, and Paperclip identity, then repeat the live API correlation.
If the process survives the existing grace period, the existing bounded
`SIGKILL` behavior may run only for that same revalidated PID. Recovery continues
through the current same-issue wake path; no new issue is created by the
watchdog.

## Affected files and areas

- `services/watchdog/src/gimle_watchdog/detection.py`
  - runtime signatures, PID/PPID discovery, sanitized Codex identity extraction.
- `services/watchdog/src/gimle_watchdog/actions.py`
  - runtime-aware pre-signal PID-reuse/identity guard.
- `services/watchdog/src/gimle_watchdog/daemon.py`
  - configured-company and active-run correlation before a kill action.
- `services/watchdog/src/gimle_watchdog/paperclip.py`
  - only if a narrow read-only helper or additional existing issue field is
    required for the correlation; no new mutating endpoint.
- `services/watchdog/src/gimle_watchdog/__main__.py`
  - safe per-runtime status/debug counts and wording.
- `services/watchdog/tests/test_detection.py`
- `services/watchdog/tests/test_actions.py`
- `services/watchdog/tests/test_daemon.py`
- `services/watchdog/tests/test_cli.py`
- `services/watchdog/tests/test_integration.py`
  - positive Codex coverage and fail-closed negative cases.
- Watchdog operator documentation only if a command/output contract changes.

No Paperclip role bundle, Glitcherry roadmap, or product repository file belongs
to this implementation branch.

## Acceptance criteria

1. A sufficiently old/idle Paperclip-owned `codex exec` fixture with a valid
   Paperclip parent and complete identity can become a hang candidate.
2. An otherwise identical unrelated `codex exec` without the complete identity
   is never a hang candidate and is never signalled.
3. A candidate with an unknown company, wrong agent, wrong issue, stale/different
   active run, missing workspace id, duplicate API match, or unavailable API is
   skipped with a non-secret reason code.
4. Existing Claude-shaped detection and kill tests remain green.
5. The exact PID is revalidated immediately before signalling; changed command,
   parent, identity, issue owner, or active run returns a skip result.
6. No code path logs or stores `PAPERCLIP_API_KEY`, a raw environment dump, a wake
   payload, or a full command containing environment data.
7. Existing hang thresholds, grace period, action budget, cooldowns, and
   same-issue recovery behavior are byte-for-byte or behaviorally unchanged.
8. Status/debug output distinguishes Claude and Codex recognition and remains
   safe to paste into issue evidence.
9. Focused unit/integration tests, the full watchdog suite, Ruff, format check,
   mypy, and `git diff --check` pass before merge.
10. After merge/deploy, a read-only canary recognizes a live Paperclip Codex run
    as attributable but does not kill it while it is young/active.
11. A later, separately human-authorized diagnostic may test bounded termination
    and same-issue recovery. This implementation does not silently rewrite or
    replace completed GLA-7.

## Verification plan

### Before implementation

- Reproduce the current failure with a test containing the live command shape:
  `codex exec --json ...`; prove the existing detector returns no candidate.
- Add negative fixtures first for an unrelated Codex session and each incomplete
  or mismatched Paperclip identity.

### Local implementation checks

From `services/watchdog`:

```bash
uv run pytest tests/test_detection.py tests/test_actions.py tests/test_daemon.py \
  tests/test_cli.py tests/test_integration.py
uv run pytest
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
uv run mypy src/
```

From the repository root:

```bash
git diff --check
```

### Deployment checks

- Update the iMac checkout only from the merged `origin/develop` SHA and restart
  the tracked watchdog launchd service using the established deploy/runbook.
- Verify one watchdog process, the expected deployed SHA/posture, and no duplicate
  wake or child issue.
- Run status/debug in read-only mode while a known young Codex run exists; record
  only boolean/count/reason evidence, never identifiers or environment values.
- Do not perform fault injection until a separate human-owned requalification
  slice explicitly authorizes the exact run and PID.

## Risks and rollback

- **False positive against a user's Codex session.** Prevented by the parent,
  complete identity, configured-company, live issue/agent/run, and pre-signal
  revalidation gates.
- **Secret exposure through `ps eww`.** Prevented by allowlisted field extraction
  and a prohibition on raw output logging/testing snapshots.
- **Paperclip schema or launcher drift.** Missing fields or changed signatures
  fail closed and surface a reason code instead of broadening process matching.
- **Claude regression.** Existing Claude fixtures and full watchdog suite are
  mandatory.
- **Deployment regression.** Roll back the watchdog service to baseline SHA
  `81199ac82352e90493fff50d785554c5404382ec` and restart; GLA-7 remains the
  truthful `NOT_READY` record.

## Open questions for review

- Whether the existing `Issue` model already provides all correlation fields or
  needs a narrow `projectWorkspaceId` addition. Workspace environment presence is
  mandatory either way; workspace API equality is optional unless the API exposes
  it reliably.
- Whether the Claude path should adopt the same API correlation in this change or
  remain behaviorally unchanged to keep the remediation surgical. Default:
  preserve Claude behavior and require the new authoritative correlation for
  Codex only.
