# UNS-137 Android Daily Audit Recovery

## Status

Draft for review.

Grounded in `develop` at commit
`7e887c847725d692ce3de884a665076734f566ae` and the live `UNS-137`
investigation performed on 2026-06-08.

## Problem

`UNS-137` (`UAudit daily Android version delta audit`) is blocked for the
second observed Android daily-audit failure pattern. The immediate failure is
not an Android repository failure and not a missing Codex subagent registry
entry. The `UWAInfraEngineer` executor reached a valid forward Android delta,
spawned the required reviewer roster, collected completion from three reviewers,
and blocked because `uaudit-bug-hunter` was interrupted before final output.

The current architecture treats every mandatory reviewer timeout as a whole-run
failure, does not reliably preserve partial reviewer artifacts on the failed
run, and then lets Paperclip comment/resume behavior reopen the blocked issue
repeatedly. There is also routine configuration drift: the repo-owned UAudit
daily routine config points Android at
`/Users/Shared/UnstoppableAudit/state/android-version-audit.json`, while the
live routine and `UNS-137` still reference the older
`/Users/Shared/UnstoppableAudit/artifacts/UWAInfraEngineer/cursor.json` path.

The result is that Android does not receive a valid daily audit, and each retry
can repeat the same fragile four-agent fanout failure.

## Goal

Produce a valid Android daily version-delta audit for `UNS-137` and harden the
UAudit daily executor path so one late reviewer can be recovered deterministically
instead of blocking the whole Android audit team again.

The target architecture is:

```text
Routine config
  -> routine reconciliation
  -> platform CTO decision gate
  -> infra immutable audit packet
  -> durable reviewer supervisor
  -> audit aggregation
  -> Telegram/report delivery
  -> cursor advance

On reviewer timeout:
  durable completed outputs
  -> missing-reviewer recovery packet
  -> targeted rerun only for missing reviewers
  -> aggregate once required roster is complete
```

## Assumptions

- `UNS-137` must remain blocked until the full required Android reviewer roster
  has produced usable output for the exact immutable delta.
- The `UNS-137` delta is:
  - `FROM=8974878fee8a2cb6ff0ed12156ea66d724f2fd50`
  - `TO=f12a546fd2831e36f84468359e2c70c9b7e4d6ff`
- The required Android roster remains:
  - `uaudit-kotlin-audit-specialist`
  - `uaudit-bug-hunter`
  - `uaudit-security-auditor`
  - `uaudit-blockchain-auditor`
- The legacy Android cursor currently used by the live issue is
  `/Users/Shared/UnstoppableAudit/artifacts/UWAInfraEngineer/cursor.json`.
- The repo-owned target cursor path in
  `paperclips/projects/uaudit/daily-version-branch-routines.yaml` is
  `/Users/Shared/UnstoppableAudit/state/android-version-audit.json`.
- Cursor migration is a policy decision because the Android routine has
  `initialization_allowed: false`; implementation must not silently initialize
  or advance a new cursor path without explicit operator/AUCEO approval.
- Paperclip issue comments should not reopen a blocked routine execution unless
  an explicit unblock/resume signal is present.

## Scope

### 1. UNS-137 Operational Recovery

Recover the blocked Android audit without changing the delta:

- Read the existing `UNS-137` run packet from
  `/Users/Shared/UnstoppableAudit/runs/UNS-137-audit`.
- Preserve any existing evidence under the run directory.
- Run or assign only the missing reviewer work for
  `uaudit-bug-hunter` against the exact `FROM..TO` delta.
- Persist the missing reviewer output as a structured artifact under the
  `UNS-137` run directory.
- Reconstruct or re-run any completed reviewer outputs only if the prior output
  cannot be recovered from live session logs or existing artifacts.
- Aggregate the full roster only after all four reviewer outputs exist.
- Deliver the Android audit report through the existing UAudit delivery path.
- Advance the active Android cursor only after delivery succeeds.

### 2. Durable Reviewer Supervisor

Change the infra executor contract and implementation so completed reviewer
results are durable before the executor waits for or closes any remaining
reviewers:

- Persist each reviewer output immediately when a `wait_agent` result completes.
- Store reviewer status independently from aggregate status:
  `running`, `completed`, `timed_out`, `interrupted`, `invalid_output`.
- If one reviewer times out, keep completed reviewer JSON on disk and write a
  recovery manifest naming only the missing reviewers.
- Do not close already completed agents after their output has been collected.
- If a reviewer is interrupted, record the child session id and interruption
  reason when available.

### 3. Targeted Missing-Reviewer Recovery

Add a deterministic recovery lane:

- A blocked daily audit with a recovery manifest can resume by spawning only the
  missing required reviewers.
- Recovery must verify that `FROM`, `TO`, branch, repo, cursor path, and roster
  match the original run manifest.
- Recovery must not recompute the delta from the current branch head.
- Recovery must not advance the cursor until the original roster is complete.
- Repeated recovery attempts should update the same run directory, not create
  unrelated audit directories for the same immutable delta.

### 4. Routine Cursor Drift Guard

Fix or explicitly gate the Android routine cursor mismatch:

- Routine reconciliation must detect when a live routine body/description
  references a cursor path that differs from
  `daily-version-branch-routines.yaml`.
- The reconciliation path must match live routines by stable routine identity
  such as configured title/body marker when the live Paperclip API exposes UUID
  routine ids instead of config ids.
- The reconciler must either update the routine body to the configured cursor
  path or fail loudly with an actionable drift report.
- It must not silently create
  `/Users/Shared/UnstoppableAudit/state/android-version-audit.json` for Android
  while `initialization_allowed: false`.
- If operator approval chooses migration, provide a one-shot cursor migration
  command that copies the last successful old cursor value to the new state path
  with explicit evidence.

### 5. Blocked-Issue Reopen Guard

Prevent the `UNS-137` churn pattern:

- A normal comment on a blocked routine-execution issue must not reopen it.
- A blocked issue should wake/reopen only on an explicit unblock signal, direct
  assignment change, or supported Paperclip state transition.
- Repeated "still blocked" comments from the same executor must not create a
  `blocked -> in_progress/todo -> blocked` loop.
- Add a regression test that models the `UNS-137` comment/resume loop.

## Affected Files And Areas

Expected areas, subject to implementation discovery:

- `paperclips/projects/uaudit/daily-version-branch-routines.yaml`
- `paperclips/projects/uaudit/overlays/codex/UWAInfraEngineer.md`
- `paperclips/projects/uaudit/overlays/codex/UWIInfraEngineer.md`
- `paperclips/scripts/reconcile_uaudit_routines.py`
- UAudit role/bundle validation tests under `paperclips/tests/`
- Paperclip issue wake/reopen handling in the server/runtime code path
- Existing UAudit docs/runbooks for daily routine operation and recovery

Implementation should keep changes surgical. If the Paperclip wake/reopen code
is outside this repository or not locally available, this slice must document the
external patch required and still harden the local UAudit executor/reconciler
pieces that are available here.

## Non-Goals

- Changing the Android audit reviewer roster.
- Waiving `uaudit-bug-hunter` for `UNS-137`.
- Advancing the Android cursor before report delivery.
- Replacing the UAudit daily dispatcher model.
- Refactoring unrelated Paperclip issue lifecycle behavior.
- Force-pushing or mutating `develop`/`main`.

## Acceptance Criteria

- `UNS-137` has a complete Android audit artifact for the exact
  `8974878f..f12a546f` delta.
- The audit includes structured output from all four required Android reviewers.
- The Android team receives the delivered daily audit report through the
  existing UAudit delivery channel.
- The active Android cursor is advanced only after successful delivery and cites
  `UNS-137`.
- If a mandatory reviewer times out in a future daily audit, completed reviewer
  outputs remain on disk and the run contains a missing-reviewer recovery
  manifest.
- A recovery run can execute only missing reviewers for the original immutable
  delta.
- Routine reconciliation detects the Android cursor path drift between live
  Paperclip routine state and repo config.
- Blocked routine-execution comments do not repeatedly reopen the issue without
  an explicit unblock signal.

## Verification Plan

- Re-run or recover `UNS-137` on the iMac using the exact recorded delta and
  verify all four reviewer artifacts exist under the run directory.
- Verify the final Android report artifact cites the exact `FROM`, `TO`, branch,
  repo, required roster, and cursor path used.
- Verify the active Android cursor file changed only after delivery succeeds.
- Run targeted tests for UAudit routine reconciliation and bundle validation.
- Run targeted tests for Paperclip blocked issue reopen behavior if that code is
  in this repo.
- Run the narrow local lint/test gates required for touched Python/Paperclip
  files before pushing implementation.

## Open Questions

- Should Android cursor state migrate from
  `/Users/Shared/UnstoppableAudit/artifacts/UWAInfraEngineer/cursor.json` to
  `/Users/Shared/UnstoppableAudit/state/android-version-audit.json` immediately,
  or should the live routine intentionally remain on the legacy path until a
  separate AUCEO-approved migration issue?
- Is the Paperclip issue wake/reopen implementation in this repository for this
  slice, or does it require a coordinated patch in an external runtime?
- Should missing-reviewer recovery be executed by `UWAInfraEngineer` directly,
  or should it create a child issue assigned to the missing reviewer role for a
  cleaner audit trail?
