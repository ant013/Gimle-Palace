# fullAudit: runtime control-plane connectivity and MCP preflight

## Context and problem

The fullAudit agents now start from the trusted Git checkout, but their runtime
environment receives `PAPERCLIP_API_URL=https://paperclip.ant013.work`.  In the
constrained execution shell that hostname cannot resolve, even though the same
iMac serves the authenticated Paperclip API on `http://127.0.0.1:3100`.

The runtime probe therefore cannot read heartbeat context or post a reply.
Its log also establishes that the current Codex run has `codebase-memory`, but
does not have the required `sequential-thinking` and Serena MCP endpoints.
Instructions and subagent TOMLs are present, yet that static fact is not a
runtime readiness guarantee.

## Assumptions

- The loopback Paperclip endpoint is the intended local control-plane route and
  authenticates the same board key as the public URL.
- A per-project host-local runtime URL may be supplied without placing a
  credential or absolute host path in a committed manifest.
- Required MCP availability is configured at the Codex/Paperclip runtime layer,
  not fabricated by the agent prompt.

## Scope

- Add a safe, explicit host-local configuration mechanism for a constrained
  project's control-plane URL, and reconcile it into existing agents' adapter
  environment without exposing credentials.
- Make fullAudit bootstrap/smoke fail before a roadmap issue when its required
  runtime MCP contract is unavailable.
- Configure the iMac fullAudit runtime with the verified loopback Paperclip
  endpoint and the required MCP set, then prove it with one isolated smoke
  probe.

## Non-goals

- Do not weaken sandboxing, enable bypass mode, or make the agent source
  checkout writable.
- Do not publish secrets, change unrelated companies, or modify the dirty
  primary Gimle checkout.
- Do not create the audit roadmap until the full runtime smoke passes.

## Affected areas

- `paperclips/projects/fullaudit/` runtime path example/assembly as needed
- `paperclips/scripts/bootstrap-project.sh` and focused tests
- iMac project-local Paperclip/Codex configuration

## Acceptance criteria

1. The fullAudit agent runtime can authenticate to the local control plane and
   comment/update a disposable probe without public-DNS dependence.
2. The effective agent configuration preserves constrained roots and `false`
   bypass, while containing no secret value.
3. `codebase-memory`, Serena, `context7`, GitHub, and `sequential-thinking` are
   verified as callable for the runtime, or the readiness gate reports exactly
   which service is unavailable and blocks roadmap launch.
4. The two read-only fullAudit subagent TOMLs remain installed and discoverable.
5. Bootstrap stays idempotent and focused tests, manifest validation, CI, and a
   single `smoke-test.sh fullaudit --cleanup-issues` pass.

## Verification plan

1. Run focused bootstrap/fullAudit tests, shell syntax checks, manifest
   validation, and CI.
2. Inspect redacted effective adapter config for all eight agents.
3. Run one controlled full smoke process, retain its log, and verify cleanup of
   only its disposable issue IDs.

## Open questions

- Which local registration mechanism is available for `sequential-thinking`
  and GitHub in the Paperclip-managed Codex runtime; determine this from the
  installed runtime configuration before changing it.
