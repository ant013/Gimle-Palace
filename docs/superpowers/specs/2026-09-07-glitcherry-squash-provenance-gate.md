# Glitcherry squash provenance gate

Date: 2026-09-07  
Baseline: `0f53f03a71bd22bd789ec740b693422b5db06864`  
Branch: `fix/glitcherry-squash-provenance-gate`

## Goal

Prevent a disposable feature-commit attribution trailer from consuming a
technical review rejection or blocking an otherwise approved Glitcherry slice.
The durable attribution contract belongs to the squash commit integrated into
`develop`.

## Assumptions

- Glitcherry slice PRs are integrated by the CTO with squash merge.
- Feature commits are review transport and are not ancestors of the resulting
  `develop` history.
- Product behavior, tests, plans, evidence, and review findings remain unchanged.
- The Human Engineering Lead has granted standing approval for narrowly scoped
  autonomous process corrections that prevent administrative-only stalls.

## Scope

- Tell the CTO not to make feature-commit trailers a slice acceptance gate or a
  required plan checkbox.
- Tell implementers to use a safe two-paragraph commit form when they include a
  trailer and to verify it before first push/handoff.
- Tell the reviewer that a missing or malformed trailer on an already-pushed
  feature commit is administrative metadata, not a technical rejection.
- Require the CTO to put the valid Paperclip co-author trailer in the final
  squash commit whenever attribution is required.
- Rebuild the generated Glitcherry Codex role bundles.

## Out of scope

- Android product code, tests, dependencies, or toolchain.
- Rewriting, amending, rebasing, or force-pushing published slice history.
- Weakening substantive code, security, architecture, or evidence review.
- Rerunning Gradle, AVD, Maestro, or physical-device checks for provenance-only
  metadata.

## Affected areas

- `paperclips/projects/glitcherry-android/overlays/codex/_common.md`
- `paperclips/projects/glitcherry-android/roles-codex/glitcherry-cto.md`
- `paperclips/projects/glitcherry-android/roles-codex/android-engineer.md`
- `paperclips/projects/glitcherry-android/roles-codex/media-pipeline-engineer.md`
- `paperclips/projects/glitcherry-android/roles-codex/code-reviewer.md`
- generated `paperclips/dist/glitcherry-android*` artifacts

## Acceptance criteria

1. Future Glitcherry plans do not require a feature-commit co-author trailer as
   a technical acceptance condition.
2. Implementers have an unambiguous safe commit form and verify the trailer
   before the first push when a trailer is requested.
3. A missing or malformed trailer on a published feature commit never increments
   the technical rejection counter and never causes `LOCAL_BLOCKED` by itself.
4. No history rewrite or synthetic no-op commit is required to repair published
   feature history.
5. CTO squash integration records a valid `Co-Authored-By: Paperclip
   <noreply@paperclip.ing>` trailer when required.
6. Provenance-only correction reuses existing green test/device evidence.
7. All six generated Glitcherry role bundles contain the resolved policy and the
   instruction validator passes.

## Verification plan

1. Build the Glitcherry Codex assembly.
2. Run the instruction validator.
3. Search all generated roles for the provenance policy marker.
4. Confirm the reviewer text explicitly forbids a technical rejection for this
   metadata-only condition.
5. Run `git diff --check` and inspect the changed-file allowlist.
6. Merge to `develop`, deploy the exact merge SHA on the iMac, and verify all six
   live instruction files contain the marker.

## Open questions

None. The final squash commit is the single durable attribution surface.

