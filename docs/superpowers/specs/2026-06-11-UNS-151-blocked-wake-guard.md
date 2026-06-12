# UNS-151 Daily Audit Staged Routing Recovery

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

This exposed the deeper root cause: iOS daily audit was routed through the stale
direct-subagent model (`UWIInfraEngineer` -> `uaudit-*` local Codex subagents)
instead of the staged Paperclip-agent chain that has actually completed Android
daily audits.

The working Android model uses real Paperclip agents:

1. `UWACTO` performs Stage 1 intake/profiling.
2. `UWAKotlinAuditor` writes `code.md`.
3. `UWASecurityAuditor` writes `security.md`.
4. `UWACryptoAuditor` writes `crypto.md`.
5. `UWAInfraEngineer` writes `infra.md`.
6. `UWAResearchAgent` writes `research-context.md` when needed.
7. `UWAQAEngineer` writes `qa-verify.md`.
8. `UWACTO` aggregates `audit-final.md`.
9. `UWAInfraEngineer` performs Telegram delivery and cursor advance.

`UNS-151` instead sent all review work to `UWIInfraEngineer`, which attempted
the local subagent fanout and blocked on missing/timed-out `uaudit-*` outputs.

## Assumptions

- The authoritative issue is Paperclip `UnstoppableAudit` issue `#151`,
  id `2fbec5c8-cba0-48e3-9997-36dd721e7cd2`.
- The current blocker is real until Board provides an explicit unblock decision,
  changes the required reviewer roster, or authorizes a partial audit.
- The daily audit cursor must not advance unless aggregation and Telegram delivery
  complete successfully.
- Do not rely on watchdog/recovery for the primary fix.
- The daily iOS/Android audit path should use staged Paperclip agents, not local
  `uaudit-*` subagents, for real-delta routine audits.
- `UWIInfraEngineer`/`UWAInfraEngineer` remain responsible for infra-owned audit
  stages and final delivery/cursor work, not for coordinating every reviewer.

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
- `paperclips/projects/uaudit/roles-codex/uwi-platform-dispatcher.md` dispatches
  real deltas directly to `UWIInfraEngineer` with `mode=audit_delta` and a
  `required_subagents` roster.
- Successful Android examples (`UNS-62`, `UNS-65`) show a staged Paperclip-agent
  flow with `code.md`, `infra.md`, optional `research-context.md`, optional
  `qa-verify.md`, CTO aggregation, then infra delivery.
- `services/watchdog/src/gimle_watchdog/detection.py` has recovery/escalation
  behavior that should not be the sole safety mechanism because watchdog is not
  a reliable enforcement substrate for this incident class.

## Scope

Implement staged Paperclip-agent routing for daily delta audits and keep the
blocked-resume guard:

1. `UWICTO` must route iOS real-delta work through staged Paperclip agents:
   `UWISwiftAuditor` -> `UWISecurityAuditor` -> `UWICryptoAuditor` ->
   `UWIInfraEngineer` -> optional `UWIResearchAgent` -> `UWIQAEngineer` ->
   `UWICTO` aggregate -> `UWIInfraEngineer` deliver.
2. `UWACTO`/Android docs should keep matching staged-chain semantics.
3. `UWIInfraEngineer` and `UWAInfraEngineer` must not coordinate full
   `uaudit-*` local subagent fanout for real-delta daily audits.
4. UAudit infra-agent instructions must stop immediately on blocked daily audit
   resume unless the latest Board-authored input explicitly changes the blocker.
5. Watchdog recovery may be hardened, but the fix must remain correct if
   watchdog never runs.
6. Tests must cover the exact regression class: escalation/comment update does
   not restart blocked work; explicit Board unblock still can.

## Out Of Scope

- Fixing the underlying subagent timeouts.
- Installing or debugging local Codex `uaudit-*` subagents.
- Advancing or editing `UNS-151` cursor/runtime artifacts.
- Reworking Paperclip server wake semantics globally.
- Treating watchdog as the source of truth for blocked-state enforcement.

## Affected Areas

- `paperclips/projects/uaudit/overlays/codex/UWIInfraEngineer.md`
- `paperclips/projects/uaudit/overlays/codex/UWAInfraEngineer.md`
- `paperclips/projects/uaudit/roles-codex/uwi-platform-dispatcher.md`
- `paperclips/projects/uaudit/roles-codex/uwa-platform-dispatcher.md`
- `paperclips/projects/uaudit/daily-version-branch-routines.yaml`
- Snapshot/generated UAudit bundles if the project build requires them.
- Existing paperclip build/render tests for UAudit instructions.
- Optional defense-in-depth follow-up:
  `services/watchdog/src/gimle_watchdog/detection.py` and
  `services/watchdog/tests/test_detection.py`.

## Proposed Design

### Daily Audit Stages

The daily real-delta route should mirror the working Android `UNS-65` pattern.

Stage outputs:

- Stage 1 intake/profiler: dispatcher/CTO writes `$RUN` intake artifacts and
  `profile.json`.
- Stage 2 code audit: platform code auditor writes `$RUN/code.md` and
  `$RUN/code.done`.
- Stage 2 security audit: platform security auditor writes `$RUN/security.md`
  and `$RUN/security.done`.
- Stage 2 crypto audit: platform crypto auditor writes `$RUN/crypto.md` and
  `$RUN/crypto.done`.
- Stage 2 infra audit: infra engineer writes `$RUN/infra.md` and
  `$RUN/infra.done`.
- Stage 3 research context: research agent writes `$RUN/research-context.md` and
  `$RUN/research.done` when Critical/Block findings or profile require it.
- Stage 4 QA: QA agent writes `$RUN/qa-verify.md` and `$RUN/qa.done`.
- Stage 5 aggregate: CTO writes `$RUN/audit-final.md`.
- Stage 6 delivery: infra engineer sends Telegram and advances cursor only after
  success.

For iOS the concrete chain is:

- `UWICTO`
- `UWISwiftAuditor`
- `UWISecurityAuditor`
- `UWICryptoAuditor`
- `UWIInfraEngineer`
- `UWIResearchAgent`
- `UWIQAEngineer`
- `UWICTO`
- `UWIInfraEngineer`

### Infra Agents

Add a daily-audit resume guard:

- If a daily audit issue is already `blocked`, read the latest comments before
  doing any repo/audit work.
- Continue only when the latest Board/operator input explicitly changes the
  blocker or authorizes a partial rerun.
- Otherwise comment that the blocker still stands, leave cursor unchanged, and
  patch back to `blocked`.

This codifies what `UWIInfraEngineer` manually did on `UNS-151`.

The guard must be placed before repo/audit work, Telegram delivery, or cursor
state writes.

Remove or supersede the direct `Required subagents for mode=audit_delta` blocks
from infra executor docs for real-delta daily audits. If retained for a separate
smoke/fallback path, the text must explicitly say it is not the daily
Paperclip-chain route.

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
- iOS real-delta handoff from `UWICTO` assigns Stage 2 code work to
  `UWISwiftAuditor`, not `UWIInfraEngineer` subagent fanout.
- Infra executor docs no longer require `uaudit-swift-audit-specialist` or
  `uaudit-blockchain-auditor` local subagent JSON for the daily real-delta route.
- The cursor is never advanced on blocked resume without explicit unblock input.
- UAudit generated/rendered instructions include the blocked resume guard for both
  iOS and Android infra engineers.
- Tests or snapshot checks prove dispatcher/infra instructions name the staged
  Paperclip chain and do not require `uaudit-*` subagent fanout for daily deltas.
- If watchdog is changed, watchdog tests prove escalation comments do not clear
  blocked recovery state.
- `UNS-151` remains `blocked` unless Board explicitly unblocks it.

## Verification Plan

- UAudit bundle/render test covering the added infra-agent instruction text, using
  the repo's existing paperclip build/test command if present.
- `bash paperclips/build.sh --project uaudit --target codex` if generated bundles
  are updated.
- Targeted grep/snapshot assertions:
  - `UWICTO` daily route mentions `UWISwiftAuditor`.
  - `UWIInfraEngineer` daily route does not contain `Required subagents for
    mode=audit_delta`.
  - Android dispatcher/infra docs keep the staged-chain contract.
- If watchdog is touched: `uv run pytest services/watchdog/tests/test_detection.py`.
- Manual Paperclip API read of `UNS-151` after implementation to confirm status
  and cursor are unchanged.

## Open Questions

- Should Paperclip server later reject `blocked -> in_progress` transitions
  without an explicit unblock marker? This is stronger, but not required for the
  first fix because UAudit can be made fail-closed at the agent contract layer.
