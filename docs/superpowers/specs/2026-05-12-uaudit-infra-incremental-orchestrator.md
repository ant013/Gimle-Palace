# UAudit Daily Version-Branch Delta Audit

## Goal

Replace manual incremental PR audit orchestration with two scheduled UAudit
infra routines:

- iOS: `UWIInfraEngineer`, daily at 18:00.
- Android: `UWAInfraEngineer`, daily at 18:10.

Each infra agent owns the full cycle in one Paperclip issue: detect new commits
on the configured version branch, enrich codebase context, run four UAudit
Codex subagents in parallel, aggregate a Markdown audit report, deliver it to
Telegram, and update the audit cursor only after delivery succeeds.

## Assumptions

- UAudit Codex subagents are already installed and smoke-tested:
  `uaudit-swift-audit-specialist`, `uaudit-kotlin-audit-specialist`,
  `uaudit-bug-hunter`, `uaudit-security-auditor`,
  `uaudit-blockchain-auditor`.
- `UWIInfraEngineer` and `UWAInfraEngineer` already have runtime
  `PAPERCLIP_API_KEY` and `PAPERCLIP_API_URL` for Telegram delivery.
- Paperclip routines can create scheduled issues assigned to a specific agent.
- The target release branches are:
  - iOS: `version/0.49`
  - Android: `version/0.49`
- The shared repos are:
  - iOS: `/Users/Shared/UnstoppableAudit/repos/ios/unstoppable-wallet-ios`
  - Android:
    `/Users/Shared/UnstoppableAudit/repos/android/unstoppable-wallet-android`

## Scope

- Update UAudit Codex infra overlays:
  - `paperclips/projects/uaudit/overlays/codex/UWIInfraEngineer.md`
  - `paperclips/projects/uaudit/overlays/codex/UWAInfraEngineer.md`
- Keep the old "prepared audit.md delivery" path for backward compatibility.
- Update generated UAudit Codex dist via `paperclips/build.sh`.
- Document the routine/cursor contract.
- Deploy updated infra bundles to Paperclip.
- Create or reconcile two Paperclip routines for the daily iOS/Android delta
  audit.
- Trigger Android PR #9195 manually by making the Android version-branch delta
  routine run once after deploy, if that PR is present in the version branch.

## Out Of Scope

- Changing the Telegram plugin.
- Replacing Paperclip routines with our own scheduler.
- Adding tester/QA agents to the delta audit.
- Updating cursors before successful Telegram delivery.
- Full repo audit mode.

## Delta Contract

Each infra role stores its cursor under:

- iOS:
  `/Users/Shared/UnstoppableAudit/state/ios-version-audit.json`
- Android:
  `/Users/Shared/UnstoppableAudit/state/android-version-audit.json`

Cursor shape:

```json
{
  "platform": "ios | android",
  "branch": "version/0.49",
  "last_successfully_audited_sha": "<sha>",
  "last_successful_issue": "UNS-<N>",
  "last_successful_at": "<UTC ISO-8601>"
}
```

The cursor is the source of truth. Do not use local branch position as proof
that commits were audited.

For each scheduled issue:

1. Fetch the remote version branch.
2. Resolve:
   - `from = cursor.last_successfully_audited_sha`
   - `to = remote version branch HEAD`
3. If `from == to`, comment `No new commits`, write a no-op marker, and mark
   the issue `done`.
4. If new commits exist, check size limits:
   - more than 30 commits blocks the run with a split-required comment;
   - more than 3000 changed diff lines blocks the run with a split-required
     comment.
5. Checkout the repo at `to`.
6. Save artifacts under
   `/Users/Shared/UnstoppableAudit/runs/UNS-<N>-audit/`:
   - `commits.json`
   - `files.json`
   - `diff.patch`
   - `subagents/*.json`
   - `audit.md`
7. Refresh/enrich codebase-memory for the repo after checkout and before
   subagent fanout.
8. Start four required subagents in parallel with explicit
   `spawn_agent.agent_type`.
9. Aggregate one English `audit.md` covering the whole commit delta.
10. Send the report through the Telegram plugin with `issueIdentifier`, not
    `chatId`.
11. Only after Telegram returns `ok:true`, update the cursor to `to` and mark
    the issue `done`.

If any step after diff creation fails, leave the cursor unchanged.

## Required Subagents

iOS:

- `uaudit-swift-audit-specialist`
- `uaudit-bug-hunter`
- `uaudit-security-auditor`
- `uaudit-blockchain-auditor`

Android:

- `uaudit-kotlin-audit-specialist`
- `uaudit-bug-hunter`
- `uaudit-security-auditor`
- `uaudit-blockchain-auditor`

Default/generic Codex agents are forbidden. Missing subagent, malformed JSON, or
generic fallback blocks the run.

## Routine Contract

Paperclip routines should create visible UAudit issues with:

- `projectId`: `64871690-2f2d-4fbd-a30d-975e6bbccec9`
- `projectWorkspaceId`: `3ba77e45-88be-41f0-bdcd-b7558de3a16b`
- status: `todo`
- priority: `high`
- iOS assignee: `UWIInfraEngineer`
  (`339e9d3f-48c0-4348-a8da-5337e6f29491`)
- Android assignee: `UWAInfraEngineer`
  (`5f0709f8-0b05-43e7-8711-6df618b95f69`)

The issue body must include the platform, branch, repo root, cursor path, and a
clear phrase such as `UAudit daily version-branch delta audit`.

## Affected Files

- `paperclips/projects/uaudit/overlays/codex/UWIInfraEngineer.md`
- `paperclips/projects/uaudit/overlays/codex/UWAInfraEngineer.md`
- `paperclips/dist/uaudit/**`
- `docs/paperclip-operations/telegram-report-delivery.md`

## Acceptance Criteria

- `UWIInfraEngineer` and `UWAInfraEngineer` instructions define the daily
  version-branch delta path.
- Infra instructions use four exact UAudit subagents per platform.
- Infra instructions require codebase-memory refresh before fanout.
- Cursor update happens only after successful Telegram delivery.
- No-op runs close cleanly without updating cursor.
- Oversized deltas block instead of producing partial reports.
- UAudit Codex build and instruction validation pass.
- Updated infra bundles are deployed to live Paperclip.
- Two Paperclip routines are created or reconciled.

## Verification Plan

- `./paperclips/build.sh --project uaudit --target codex`
- `python3 paperclips/scripts/validate_instructions.py --repo-root .`
- `uv run python -m pytest paperclips/tests/test_validate_instructions.py`
- Deploy `UWIInfraEngineer` and `UWAInfraEngineer` through
  `paperclips/scripts/deploy_project_agents.py --project uaudit --target codex --api`.
- Verify live infra bundles compare OK.
- Create/reconcile routines and verify they are visible through Paperclip API.
- Manually trigger or create the first Android delta issue for PR #9195 after
  deploy.
