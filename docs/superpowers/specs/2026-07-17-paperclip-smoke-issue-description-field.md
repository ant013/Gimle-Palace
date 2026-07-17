# Paperclip Smoke Issue Description Field

**Status:** approved implementation follow-up to
`2026-07-17-paperclip-thorchain-team.md`

**Branch:** `fix/paperclip-smoke-issue-description`

## Problem

The first live ThorChainKit runtime-probe pass proved that the smoke harness
creates disposable issues with a `body` property. Paperclip's create-issue
contract accepts the task text as `description`, so the unknown property is
dropped and the assigned agent receives an issue with no instructions. The
agent runs succeed, but marker validation fails because the replies describe an
empty task rather than answering the intended probe.

## Assumptions

- The pinned Paperclip `2026.618.0` create-issue API remains authoritative for
  the live deployment.
- Both per-role probes and the end-to-end handoff probe use the same issue
  creation contract and must be corrected together.
- No agent prompt, authority boundary, or production product code needs to
  change for this defect.

## Scope

- Change disposable smoke issue payloads from `body: $q` to
  `description: $q` in `paperclips/scripts/lib/_smoke_probes.sh`.
- Add a regression assertion to
  `paperclips/tests/test_phase_c_smoke_probes.py` covering every smoke issue
  creation payload.
- Re-run focused Phase C tests, shell validation, and the live ThorChainKit
  smoke with exact-ID cleanup.

## Out of Scope

- Paperclip server upgrades or schema changes.
- Agent role/prompt changes unless a correctly delivered probe exposes a
  separate role-contract defect.
- Unstoppable company retirement.

## Acceptance Criteria

1. Every smoke issue creation payload sends the probe text as `description`.
2. No smoke issue creation payload sends probe text as the unsupported `body`
   property.
3. A newly created live probe issue exposes the exact question through its
   `description` field.
4. Full ThorChainKit smoke reaches real agent responses and cleans up only the
   disposable issue IDs created by that run.
5. Focused Phase C tests, `bash -n`, and ShellCheck remain green.

## Verification Plan

1. Add the regression assertion and prove it fails against the current code.
2. Apply the two-field correction and prove the focused test passes.
3. Run all Phase C tests with the repository virtual environment on `PATH`.
4. Run `bash -n` and `shellcheck -x -P paperclips/scripts` for the changed
   library.
5. Run `smoke-test.sh thorchain --cleanup-issues` against the pinned local
   Paperclip server and inspect live issue descriptions and final cleanup.

## Open Questions

None. The live reproduction and pinned API schema identify a single contract
mismatch with no architectural choice.
