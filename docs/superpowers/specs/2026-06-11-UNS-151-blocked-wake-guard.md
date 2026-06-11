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
- Existing watchdog recovery is allowed to wake stale live work, but must not treat
  service-generated comments or escalation comments as a valid unblock for
  `blocked` issues.

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
- `services/watchdog/src/gimle_watchdog/detection.py` currently auto-clears
  recovery escalation when `issue.updated_at > escalated_at`, without checking
  whether the update is an actual unblock.
- `paperclips/projects/uaudit/overlays/codex/UWIInfraEngineer.md` defines the
  daily audit cursor contract, but lacks an explicit resume guard for blocked
  issues woken by service/escalation comments.

## Scope

Implement a fail-closed guard for blocked daily audit issues:

1. Watchdog recovery must not wake or auto-unescalate a blocked issue unless the
   update is explicitly attributable to a real operator unblock.
2. UAudit infra-agent instructions must tell `UWIInfraEngineer` and
   `UWAInfraEngineer` to stop immediately on blocked daily audit resume unless
   the latest Board-authored input explicitly changes the blocker.
3. Tests must cover the exact regression class: escalation/comment update does
   not restart blocked work; explicit Board unblock still can.

## Out Of Scope

- Fixing the underlying subagent timeouts.
- Changing the required four-reviewer daily audit contract.
- Advancing or editing `UNS-151` cursor/runtime artifacts.
- Reworking Paperclip server wake semantics globally.

## Affected Areas

- `services/watchdog/src/gimle_watchdog/detection.py`
- `services/watchdog/tests/test_detection.py`
- `paperclips/projects/uaudit/overlays/codex/UWIInfraEngineer.md`
- `paperclips/projects/uaudit/overlays/codex/UWAInfraEngineer.md`
- Snapshot/generated UAudit bundles if the project build requires them.

## Proposed Design

### Watchdog

Keep the existing `blocked` skip as the primary recovery guard. Tighten escalation
clearing so service-generated comments and watchdog/escalation comments cannot
implicitly clear a blocked or escalated recovery state.

The implementation should introduce a small predicate with tests, for example:

- explicit unblock: Board/operator comment contains a recognized unblock phrase
  such as `unblocked`, `resume approved`, `proceed`, or `partial audit approved`;
- not explicit unblock: comments containing `@Board blocked`, `watchdog escalation`,
  `blocked`, or service-generated escalation markers.

If reliable comment context is not available in the recovery pass, the safer first
slice is to remove the `issue.updated_at > escalated_at` auto-clear for blocked
or escalation-marked issues and require manual `gimle-watchdog unescalate`.

### UAudit Infra Agents

Add a daily-audit resume guard:

- If a daily audit issue is already `blocked`, read the latest comments before
  doing any repo/audit work.
- Continue only when the latest Board/operator input explicitly changes the
  blocker or authorizes a partial rerun.
- Otherwise comment that the blocker still stands, leave cursor unchanged, and
  patch back to `blocked`.

This codifies what `UWIInfraEngineer` manually did on `UNS-151`.

## Acceptance Criteria

- A blocked daily audit issue with only a blocker/escalation/comment update does
  not start a new audit run.
- The cursor is never advanced on blocked resume without explicit unblock input.
- Watchdog tests prove escalation comments do not clear blocked recovery state.
- UAudit generated/rendered instructions include the blocked resume guard for both
  iOS and Android infra engineers.
- `UNS-151` remains `blocked` unless Board explicitly unblocks it.

## Verification Plan

- `uv run pytest services/watchdog/tests/test_detection.py`
- UAudit bundle/render test covering the added infra-agent instruction text, using
  the repo's existing paperclip build/test command if present.
- `bash paperclips/build.sh --project uaudit --target codex` if generated bundles
  are updated.
- Manual Paperclip API read of `UNS-151` after implementation to confirm status
  and cursor are unchanged.

## Open Questions

- What exact Board/operator phrases should count as explicit unblock? Proposed
  initial allowlist: `unblocked`, `resume approved`, `proceed`, and
  `partial audit approved`.
- Should this guard live only in watchdog + agent instructions, or should the
  Paperclip server reject `blocked -> in_progress` transitions without an
  explicit unblock marker?
