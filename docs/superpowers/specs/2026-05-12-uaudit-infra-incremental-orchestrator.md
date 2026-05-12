# UAudit Infra Incremental PR Orchestrator

## Goal

Move incremental PR audit orchestration from Swift/Kotlin auditor roles into the
UAudit infra roles so one Paperclip wake owns the full path:

1. prepare PR checkout, diff, and metadata;
2. refresh codebase-memory context for the PR head;
3. run three required UAudit Codex subagents in parallel;
4. aggregate one English `audit.md`;
5. send the report to Telegram;
6. close the issue.

This removes the current coordinator-to-infra handoff delay while preserving the
explicit subagent contract.

## Assumptions

- UAudit Codex subagents are already installed and smoke-tested:
  `uaudit-swift-audit-specialist`, `uaudit-kotlin-audit-specialist`,
  `uaudit-security-auditor`, `uaudit-blockchain-auditor`.
- `UWIInfraEngineer` and `UWAInfraEngineer` already have runtime
  `PAPERCLIP_API_KEY` and `PAPERCLIP_API_URL` for Telegram delivery.
- Paperclip runtime can run `gh`, `git`, and the codebase-memory MCP/indexer
  against `/Users/Shared/UnstoppableAudit/repos/*`.
- New incremental audit issues can be assigned directly to infra roles.

## Scope

- Update UAudit Codex infra overlays:
  - `paperclips/projects/uaudit/overlays/codex/UWIInfraEngineer.md`
  - `paperclips/projects/uaudit/overlays/codex/UWAInfraEngineer.md`
- Update Swift/Kotlin auditor overlays so PR audit issues are no longer their
  default coordinator path; they remain available as subagent/domain roles.
- Update generated UAudit Codex dist via `paperclips/build.sh`.
- Update docs/runbook text for assigning new incremental audit issues directly
  to infra.
- Deploy updated UAudit Codex infra/auditor bundles to Paperclip.
- Create a real Android audit issue for
  `https://github.com/horizontalsystems/unstoppable-wallet-android/pull/9195`
  assigned to `UWAInfraEngineer`.

## Out Of Scope

- Changing the Telegram plugin.
- Changing Paperclip issue scheduling.
- Adding new test agents.
- Reintroducing QA/tester agents for this flow.
- Full repo audit mode; this spec is only for PR incremental audit.

## New Infra Contract

When `UWIInfraEngineer` sees an iOS PR URL, it owns the full flow using:

- `uaudit-swift-audit-specialist`
- `uaudit-security-auditor`
- `uaudit-blockchain-auditor`

When `UWAInfraEngineer` sees an Android PR URL, it owns the full flow using:

- `uaudit-kotlin-audit-specialist`
- `uaudit-security-auditor`
- `uaudit-blockchain-auditor`

`uaudit-bug-hunter` is removed from the default incremental path to keep the
fast path at three subagents. It remains available for separate bug-hunt modes.

The infra role must:

- derive `$RUN=/Users/Shared/UnstoppableAudit/runs/UNS-<N>-audit`;
- fetch PR metadata to `$RUN/pr.json`;
- fetch full PR diff to `$RUN/pr.diff`;
- checkout/fetch the PR head in the platform repo;
- refresh/enrich codebase-memory for the platform repo after checkout;
- start the three required subagents in parallel with explicit
  `spawn_agent.agent_type`;
- reject default/generic subagent fallback;
- require JSON outputs with the existing finding schema;
- write `$RUN/audit.md`;
- send `audit.md` through the Telegram plugin using `issueIdentifier`, not
  `chatId`;
- comment the artifact path, delivery message id, and status;
- mark the issue `done`.

## Affected Files

- `paperclips/projects/uaudit/overlays/codex/UWIInfraEngineer.md`
- `paperclips/projects/uaudit/overlays/codex/UWAInfraEngineer.md`
- `paperclips/projects/uaudit/overlays/codex/UWISwiftAuditor.md`
- `paperclips/projects/uaudit/overlays/codex/UWAKotlinAuditor.md`
- `paperclips/dist/uaudit/**`
- `docs/paperclip-operations/telegram-report-delivery.md`
- `docs/runbooks/deploy-checklist.md` if needed

## Acceptance Criteria

- New iOS incremental PR issue can be assigned directly to `UWIInfraEngineer`.
- New Android incremental PR issue can be assigned directly to
  `UWAInfraEngineer`.
- Infra instructions clearly require three explicit subagents and forbid
  default/generic fallback.
- Infra instructions include checkout plus codebase-memory refresh before
  subagent fanout.
- Infra writes `audit.md` and sends it to Telegram in the same issue lifecycle.
- Swift/Kotlin auditor instructions no longer claim to own the default
  incremental PR coordinator path.
- UAudit Codex build and instruction validation pass.
- Updated bundles are deployed to live Paperclip.
- Android PR #9195 issue is created and starts under `UWAInfraEngineer`.

## Verification Plan

- `./paperclips/build.sh --project uaudit --target codex`
- `python3 paperclips/scripts/validate_instructions.py --repo-root .`
- `uv run python -m pytest paperclips/tests/test_validate_instructions.py`
- Deploy changed UAudit Codex agents through
  `paperclips/scripts/deploy_project_agents.py --project uaudit --target codex --api`.
- Create Android PR #9195 issue assigned to `UWAInfraEngineer`.
- Verify the issue is visible and moves to `in_progress`.

## Open Questions

- Whether infra should continue to support the old "prepared audit.md only"
  delivery path. Default answer: yes, keep it for backward compatibility, but
  PR URLs take the new orchestrator path.
