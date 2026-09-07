# Glitcherry internal review status

Date: 2026-09-07  
Baseline: `3824e6ea1b78fbf4fd0f9a9d5abb2cfd72f52b94`  
Branch: `fix/glitcherry-internal-review-status`

## Goal

Keep Glitcherry's multi-phase work inside one non-terminal slice issue without
triggering Paperclip's terminal review/approval policy. Internal spec, plan, and
code-review handoffs remain `in_progress`; CTO alone marks the slice `done` after
merge and cleanup.

## Assumptions

- The controller, exact assignee, shared execution workspace, branch, and HEAD
  remain the authority for internal phase routing.
- Paperclip's `in_review` status is protected by `invalid_issue_disposition` and
  requires a real terminal review path.
- A Paperclip execution-policy review stage completes the issue when approved;
  it therefore does not model the pre-integration code-review phase.
- Existing role-to-role handoffs are serialized and do not require a second
  status vocabulary.

## Scope

- Explicitly keep all internal CTO/implementer/reviewer handoffs in
  `in_progress` while changing only the assignee and controller phase.
- Reserve `in_review` for a separately authorized real Paperclip terminal
  review/approval/monitor flow; do not create one merely to wake an agent.
- Require code approval to return the same still-active issue to CTO for
  integration.
- Require CTO to mark `done` only after Android/control merges and exact cleanup
  evidence are complete.
- Rebuild and deploy the six generated Glitcherry Codex role bundles.

## Out of scope

- Android source, tests, plans, acceptance criteria, dependencies, or toolchain.
- Removing exact-head review, reviewer independence, or the three-cycle ceiling.
- Changing Paperclip server code or bypassing its disposition validator.
- Adding a typed execution policy to every slice issue.
- Changing sprint smoke or stage-gate rules.

## Affected areas

- `paperclips/projects/glitcherry-android/overlays/codex/_common.md`
- `paperclips/projects/glitcherry-android/roles-codex/glitcherry-cto.md`
- `paperclips/projects/glitcherry-android/roles-codex/android-engineer.md`
- `paperclips/projects/glitcherry-android/roles-codex/media-pipeline-engineer.md`
- `paperclips/projects/glitcherry-android/roles-codex/code-reviewer.md`
- generated `paperclips/dist/glitcherry-android*` artifacts

## Acceptance criteria

1. Generated roles state that internal spec, plan, implementation, review, and
   integration routing retains issue status `in_progress`.
2. Implementer handoff assigns Code Reviewer with `status=in_progress`, never
   `in_review`.
3. Reviewer approval assigns CTO with `status=in_progress`, never terminal
   `done` or an execution-policy decision.
4. Reviewer changes requested assigns the recorded implementer with
   `status=in_progress` and the existing controller rejection count.
5. CTO sets `done` only after both repository integrations and workspace/ref
   cleanup have been verified.
6. No internal handoff creates a typed execution policy, pending interaction,
   approval, or monitor solely to satisfy the `in_review` validator.
7. The existing exact-head, evidence, independence, and maximum-three-review
   rules remain unchanged.

## Verification plan

1. Build the Glitcherry Codex assembly.
2. Run the instruction validator.
3. Search all six generated roles for the internal-review-status marker.
4. Confirm implementer and reviewer atomic handoffs name `in_progress` and
   forbid `in_review` for this lifecycle.
5. Confirm CTO terminal completion remains after integration and cleanup.
6. Run `git diff --check` and inspect the changed-file allowlist.
7. Merge, deploy the exact `develop` merge SHA on the iMac, and verify all six
   live instruction files contain the marker.

## Open questions

None. This policy uses Paperclip's ordinary active issue state and does not
change terminal review semantics.

