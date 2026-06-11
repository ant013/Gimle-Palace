# UNS-151 Blocked Wake Guard

**Status:** draft for operator review
**Date:** 2026-06-11
**Branch:** `feature/UNS-151-blocked-wake-guard-spec`
**Base:** `origin/develop@86cfaee8`

## Problem

`UNS-151` (`UAudit daily iOS version delta audit`) was blocked because two required
reviewer slots timed out:

- `uaudit-swift-audit-specialist`
- `uaudit-blockchain-auditor`

The issue then reopened into `in_progress` without a new Board decision or unblock
input. The wake was caused by the prior escalation/blocker comment path, not by a
changed audit precondition. `UWIInfraEngineer` correctly detected that no valid
unblock existed, confirmed the cursor was unchanged, and patched the issue back to
`blocked`.

This is unsafe because a blocked daily audit can be re-run after a service/comment
event. A re-run may waste agent budget, duplicate work, or accidentally advance the
cursor if a future agent misses the blocked contract.

## Assumptions

- The authoritative issue is Paperclip `UnstoppableAudit` issue `#151`,
  id `2fbec5c8-cba0-48e3-9997-36dd721e7cd2`.
- The current blocker is real until Board provides an explicit unblock decision,
  changes the required reviewer roster, or authorizes a partial audit.
- The daily audit cursor must not advance unless aggregation and Telegram delivery
  complete successfully.
- Do not rely on watchdog/recovery for the primary fix. UAudit must stay safe
  when watchdog is disabled, stale, misconfigured, or not covering the
  UnstoppableAudit company.
- Watchdog hardening is defense-in-depth only.

## Evidence

- Paperclip issue `#151` current state on 2026-06-11: `status=blocked`,
  `assigneeAgentId=339e9d3f-48c0-4348-a8da-5337e6f29491` (`UWIInfraEngineer`),
  `executionRunId=null`.
- Comment `5e4a219f-d344-412c-8962-e3698dc938a6` at
  `2026-06-11T11:19:29.752Z` recorded `@Board blocked` with missing required
  reviewer outputs.
- Comment `493530a3-2613-443d-95c9-6c5a1f4e62cc` at
  `2026-06-11T11:20:56.935Z` recorded that the wake had no new Board decision,
  no unblock input, no audit delivery, and no cursor advance.
- `paperclips/projects/uaudit/overlays/codex/UWIInfraEngineer.md` defines the
  daily audit cursor contract, but lacks an explicit resume guard for blocked
  issues woken by service/escalation comments.
- `services/watchdog/src/gimle_watchdog/detection.py` has recovery/escalation
  behavior that should not be the sole safety mechanism because watchdog is not
  a reliable enforcement substrate for this incident class.

## Scope

Implement a fail-closed guard for blocked daily audit issues:

1. UAudit infra-agent instructions must tell `UWIInfraEngineer` and
   `UWAInfraEngineer` to stop immediately on blocked daily audit resume unless
   the latest Board-authored input explicitly changes the blocker.
2. The daily audit routine must be fail-closed before repo checkout, subagent
   dispatch, aggregation, Telegram delivery, or cursor writes.
3. Watchdog recovery may be hardened, but the fix must remain correct if
   watchdog never runs.
4. Tests must cover the exact regression class: escalation/comment update does
   not restart blocked work; explicit Board unblock still can.

## Out Of Scope

- Fixing the underlying subagent timeouts.
- Changing the required four-reviewer daily audit contract.
- Advancing or editing `UNS-151` cursor/runtime artifacts.
- Reworking Paperclip server wake semantics globally.
- Treating watchdog as the source of truth for blocked-state enforcement.

## Affected Areas

- `paperclips/projects/uaudit/overlays/codex/UWIInfraEngineer.md`
- `paperclips/projects/uaudit/overlays/codex/UWAInfraEngineer.md`
- Snapshot/generated UAudit bundles if the project build requires them.
- Existing paperclip build/render tests for UAudit instructions.
- Optional defense-in-depth follow-up:
  `services/watchdog/src/gimle_watchdog/detection.py` and
  `services/watchdog/tests/test_detection.py`.

## Proposed Design

### UAudit Infra Agents

Add a daily-audit resume guard:

- If a daily audit issue is already `blocked`, read the latest comments before
  doing any repo/audit work.
- Continue only when the latest Board/operator input explicitly changes the
  blocker or authorizes a partial rerun.
- Otherwise comment that the blocker still stands, leave cursor unchanged, and
  patch back to `blocked`.

This codifies what `UWIInfraEngineer` manually did on `UNS-151`.

The guard must be placed before the existing daily-audit steps that read the
cursor, materialize the delta, dispatch subagents, aggregate findings, deliver
Telegram output, or write cursor state.

### Explicit Unblock Contract

The agent should require one of these Board/operator phrases in the newest
post-blocker input before resuming:

- `unblocked`
- `resume approved`
- `proceed`
- `partial audit approved`

The following are explicitly not unblock inputs:

- `@Board blocked`
- `watchdog escalation`
- `blocked`
- prior blocker summaries
- service comments that only reopen the issue into `in_progress`

### Watchdog Defense-In-Depth

If touched in this slice, watchdog must not auto-clear recovery/escalation state
based only on `updatedAt`. It may log or skip such candidates. This is not the
primary enforcement layer; the UAudit agent contract is.

## Acceptance Criteria

- A blocked daily audit issue with only a blocker/escalation/comment update does
  not start a new audit run.
- The same behavior holds with watchdog disabled or not deployed for
  UnstoppableAudit.
- The cursor is never advanced on blocked resume without explicit unblock input.
- UAudit generated/rendered instructions include the blocked resume guard for both
  iOS and Android infra engineers.
- Tests or snapshot checks prove the guard appears before daily-audit execution
  instructions.
- If watchdog is changed, watchdog tests prove escalation comments do not clear
  blocked recovery state.
- `UNS-151` remains `blocked` unless Board explicitly unblocks it.

## Verification Plan

- UAudit bundle/render test covering the added infra-agent instruction text, using
  the repo's existing paperclip build/test command if present.
- `bash paperclips/build.sh --project uaudit --target codex` if generated bundles
  are updated.
- If watchdog is touched: `uv run pytest services/watchdog/tests/test_detection.py`.
- Manual Paperclip API read of `UNS-151` after implementation to confirm status
  and cursor are unchanged.

## Open Questions

- Should Paperclip server later reject `blocked -> in_progress` transitions
  without an explicit unblock marker? This is stronger, but not required for the
  first fix because UAudit can be made fail-closed at the agent contract layer.
