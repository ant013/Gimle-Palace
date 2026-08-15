# fullAudit: reconcile configuration for previously hired agents

## Context and problem

`bootstrap-project.sh` reuses an agent whose ID is present in the project
bindings and exists in Paperclip.  That early reuse path skips construction and
submission of the current adapter configuration.  Consequently, a bootstrap
after a manifest change deploys fresh instructions but leaves an already hired
fullAudit agent running with its old `cwd` and sandbox roots.

The trusted-Git-cwd change therefore cannot take effect for the existing
fullAudit company until the agent configuration is reconciled with Paperclip.

## Assumptions

- Paperclip exposes an authenticated update endpoint for an existing agent
  compatible with the current `paperclip_hire_agent` payload, or the existing
  client helpers reveal the correct update method.
- Existing fullAudit agent IDs, hierarchy, identities, and budget must remain
  stable; this is an in-place configuration reconciliation, not a re-hire.
- The dedicated source checkout remains
  `/Users/Shared/Ios/full-audit-agent-source` and is a Git worktree without a
  `.env` file.

## Scope

- Update the bootstrap flow so it computes the desired configuration for every
  declared agent and updates existing Paperclip agents only when their managed
  configuration differs.
- Preserve the no-op behavior when all managed fields already match.
- Add focused tests for existing-agent reconciliation and the trusted fullAudit
  `cwd` / writable / read-only root contract.
- Re-bootstrap the existing company on iMac, inspect its effective API config,
  then rerun the full smoke probe.

## Non-goals

- Do not change fullAudit team roles, audit workflow, or report content.
- Do not delete or re-hire existing agents, rotate credentials, or alter the
  dirty primary iMac checkout.
- Do not create the audit roadmap issue until full smoke succeeds.

## Affected areas

- `paperclips/scripts/bootstrap-project.sh`
- Paperclip API helper(s) used by bootstrap
- `paperclips/tests/` focused bootstrap/fullAudit tests
- generated fullAudit assembly only if source manifest changes require it

## Acceptance criteria

1. Re-running bootstrap after a managed adapter change updates existing agents
   in place and preserves their IDs.
2. All fullAudit agents have
   `cwd=/Users/Shared/Ios/full-audit-agent-source`, that path is read-only, and
   no agent may write to it.
3. Per-agent workspaces/scratch remain writable; role-specific project output
   roots remain unchanged.
4. Bootstrap is idempotent: a subsequent unchanged run performs no managed
   config update.
5. The bootstrap unit/focused tests, manifest validation, shell syntax check,
   and CI pass.
6. A full iMac smoke test confirms instructions, MCP/subagent availability,
   constrained write policy, and trusted execution directory.

## Verification plan

1. Run the focused bootstrap and fullAudit tests plus manifest validation and
   `bash -n` locally.
2. Inspect the safely redacted effective Paperclip adapter fields for all eight
   agents after bootstrap.
3. Run `smoke-test.sh fullaudit --cleanup-issues` on iMac.
4. Merge only after required CI checks are green.

## Open questions

None; the exact HTTP verb/endpoint will be derived from the repository's
existing Paperclip API helpers before implementation.
