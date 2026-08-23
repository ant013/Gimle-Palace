# UAudit runtime-tool visibility recovery

## Goal

Make each UAudit execution observe the exact manifest-verified delivery helper and
release resolver that deployment reports, then safely resume the currently blocked
Android and iOS recovery executions.

## Evidence and assumptions

- Deploy on host `ant013` installed both files under
  `/Users/Shared/UnstoppableAudit/runs/.uaudit-tools` and verified their manifests.
- The Paperclip run transcript for `UNS-568` executes through `codex_local` on a
  distinct runtime host (`anton`) and observes the same absolute path without the
  resolver. It is a cross-host filesystem boundary, not a cursor or routine-lock
  failure.
- `UNS-568`, `UNS-569`, and child `UNS-570` are blocked; no cursor, lock, Git range,
  or Telegram delivery was mutated by these failed attempts.

## Scope

- Add a runtime-host publication/attestation step for the two UAudit tools.
- Make the deploy path fail before routine work if the execution environment cannot
  read and verify the published manifest-bound tools.
- Add an operator recovery command that attests the execution host, then wakes the
  existing blocked issues exactly once.
- Add tests covering host-vs-execution visibility mismatch, manifest mismatch, and
  successful attest-and-wake flow.

## Non-scope

- No manual cursor or lock deletion, range construction, or Telegram sending.
- No copying tools from an audit agent, weakening manifests, or assuming two hosts
  share an absolute path.
- No routine schedule rewrite or global Paperclip service restart.

## Design

The existing bootstrap installer remains the source-generation and manifest
authority. A new execution-environment publisher uses the Paperclip runtime's
supported workspace/host transport to atomically stage both immutable files and
manifests where `codex_local` actually executes. It writes a bounded attestation
containing execution-host identity, tool digests, and deploy SHA.

`imac-agents-deploy.sh` runs this attestation after prompt deployment and before
declaring success. A mismatch or unavailable execution host fails closed and leaves
routines untouched. Recovery consumes only a fresh successful attestation, posts one
evidence comment to each already-blocked issue, and waits for its normal wake; it
never creates a replacement routine run.

## Analog delta matrix

| Slice | Primary analog / invariant | Required delta | Failure handling | Verification |
| --- | --- | --- | --- | --- |
| Tool install | `install_uaudit_delivery_helper` atomic manifest install | Publish to the actual execution host, not only the deploy host | Missing/foreign host or digest mismatch blocks | host-mismatch fixture and manifest test |
| Deploy lifecycle | `imac-agents-deploy.sh` pinned worktree + bootstrap handoff | Require execution-host attestation before deploy success | No routine reconciliation/recovery on failed attestation | shell/integration test |
| Recovery | receipt-led daily recovery rules | One comment/wake for existing blocked issues after attestation | No cursor/lock/Telegram mutation; duplicate wake prohibited | API fixture + live readback |

## Acceptance criteria

1. A deployment cannot succeed until a `codex_local` execution reads and verifies
   both installed tool manifests from its own filesystem.
2. A host-only installation reproduces a deterministic failure without touching a
   routine, cursor, lock, or Telegram.
3. A successful attestation records the execution host identity and both SHA-256
   values without secrets.
4. Recovery re-wakes only `UNS-568` and `UNS-569` once after successful attestation;
   it creates no additional routine executions.
5. The next scheduled Android/iOS slots complete with a Telegram receipt or a
   explicit durable blocker report.

## Verification plan

- Narrow tests for publisher/attestation parsing and manifest mismatch.
- Shell syntax and bootstrap/deploy structural tests.
- Project build and CI.
- Production evidence: execution-host attestation, issue run transcript showing both
  tools present, terminal status of `UNS-568`/`UNS-569`, and next-run health.

## Open question

The supported Paperclip transport/API for publishing an immutable runtime asset to
the remote `codex_local` host must be identified from the active server contract;
the implementation must not substitute SSH or an agent-side copy without that
contract.
