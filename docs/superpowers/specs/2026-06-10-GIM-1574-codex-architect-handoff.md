# GIM-1574 Codex Architect Handoff Guard

Grounded at `e4e8fd674ad09ea370dc43196551932e4065afa0`.

## Assumptions

- The GIM-1574 walker must use Codex/CX agents only.
- `OpusArchitectReviewer` is not allowed for this walker because its adapter is
  `claude_local`.
- `CodexArchitectReviewer` is the intended Codex-side adversarial reviewer.

## Scope

- Clarify Codex/CX review handoff instructions so CX mechanical review hands
  off to `CodexArchitectReviewer`, not `OpusArchitectReviewer`.
- Keep the change limited to Paperclip role/fragments and prompt safeguards.
- Do not change service runtime code or existing issue data models.

## Affected Areas

- `paperclips/roles-codex/cx-code-reviewer.md`
- `paperclips/fragments/shared/fragments/code-review/adversarial.md`
- Related prompt snapshot/tests if required by existing test coverage.

## Acceptance Criteria

- Codex-side CodeReviewer instructions explicitly name
  `CodexArchitectReviewer` as the Phase 3.2 handoff target.
- Instructions explicitly prohibit `OpusArchitectReviewer` handoff from CX/Codex
  roles when Claude is disabled.
- Shared adversarial-review wording is target-neutral or clearly maps Codex
  targets to `CodexArchitectReviewer`.
- Local prompt validation or the narrowest relevant tests pass.

## Verification Plan

- Search role/fragments for stale `OpusArchitectReviewer only` wording.
- Run the relevant Paperclip prompt/role tests or validation script if present.
- If no focused test exists, run a shell search proving the Codex role path no
  longer contains an Opus-only handoff instruction.

## Open Questions

- None for this urgent guard. Longer-term Paperclip should enforce adapter-type
  constraints at assignment time so a Codex-only walker cannot wake a
  `claude_local` agent.
