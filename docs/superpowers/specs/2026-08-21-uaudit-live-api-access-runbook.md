# UAudit: live Paperclip API access in the iMac operations runbook

**Status:** review requested

**Base:** `origin/develop` at `14c52e1110cbe9cfe59f20ac09010b646ac9dd04`.

## Goal

Make the UAudit live-operations runbook lead an operator to the proven
read-only Paperclip control-plane access path when SSH to iMac is unavailable,
without treating a local development checkout as live audit evidence.

## Assumptions

- `/Users/ant013/Android/Gimle-Palace-claude/.env` is the approved local
  operator credential source described by `API.md`; its values must never be
  printed, copied, or committed.
- The Paperclip API is supplementary orchestration evidence. iMac UAudit
  artifacts remain authoritative for run artefacts, cursors, locks, and
  delivery receipts when SSH is available.
- The runbook currently exists on `origin/docs/uaudit-imac-operations` and is
  not yet present on `origin/develop`; this change must preserve its existing
  iMac-first and secret-safe rules when it is carried into the new branch.

## Scope

- Document a staged access procedure: SSH batch preflight first; then, on an
  SSH authentication failure, source the approved operator `.env` without
  echoing it, verify `/api/cli-auth/me`, and use company-scoped Paperclip API
  reads.
- Include a minimal, redacted routine/issue inspection example for the
  `UnstoppableAudit` company, and direct readers to `API.md` for endpoint and
  authentication details.
- State the evidence boundary: API state may explain scheduling, issue status,
  locks and execution ownership, but cannot replace the iMac artifact
  inspection when filesystem evidence is required.
- Add a concise failure outcome for missing or invalid operator credentials.

## Non-scope

- No changes to Paperclip routines, issues, API authorization, iMac SSH keys,
  runtime paths, audit cursors, locks, or delivery behaviour.
- No credential migration or new secret storage.
- No automated repair, approval, release, deployment, or audit launch command
  in the read-only diagnostic flow.

## Affected areas

- `docs/paperclip-operations/uaudit-imac-operations.md` (carried from the
  existing documentation branch, then updated).
- `API.md` is referenced, not modified, unless its existing contract proves
  insufficient during implementation.

## Acceptance criteria

1. The runbook makes SSH the preferred source for live UAudit artifacts.
2. After an SSH authentication failure, it names the approved operator env
   file and shows a command form that does not print a key or token.
3. It verifies an API key with `/api/cli-auth/me` before further reads and
   identifies `UnstoppableAudit` from the authenticated company list rather
   than hard-coding undocumented assumptions.
4. It distinguishes the Paperclip control-plane diagnosis from iMac filesystem
   evidence and tells the operator what conclusion is safe from each.
5. It contains no actual credentials, unredacted environment output, or
   state-mutating API request.

## Verification plan

1. Review every command for read-only HTTP methods and absence of secret
   expansion in output.
2. Check referenced paths against `API.md` and the existing operations
   runbook.
3. Use a shell syntax check for fenced shell examples where applicable and run
   the repository documentation validator if it covers this path.
4. Inspect `git diff --check` and the rendered Markdown diff for clarity.

## Open questions

- None. If the API credential location changes, update `API.md` first and
  revise this runbook to reference that authoritative contract.
