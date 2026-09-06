# Glitcherry review-evidence preflight

Date: 2026-09-07  
Status: APPROVED under the standing Human Engineering Lead delegation for TP2
autonomous process corrections  
Baseline: `d5ef653ef789911253c113b1820b96a3e424cd05` (`origin/develop`)  
Branch: `fix/glitcherry-review-evidence-preflight`

## Problem

Two consecutive Glitcherry slices reached independent Code Review with green
product verification but stale administrative evidence:

- TP2-005 had completed work while its tracked plan still had every checkbox
  open; after the tracked plan was corrected, its Paperclip plan mirror was
  stale and caused a second process return.
- TP2-006 corrected all substantive review findings and passed its proportional
  and AVD gates, but the tracked plan and PR body still described the rejected
  head and prior test counts.

These are preventable producer-side handoff defects. Treating them as full Code
Review rejections consumes the three-cycle technical review budget and adds an
extra role round trip without improving product correctness.

## Assumptions

- The tracked plan may record factual progress and evidence after its technical
  content has been approved; those updates do not change acceptance or scope.
- Implementers already have supported access to update the issue's Paperclip
  plan document and the existing PR body.
- The controller can hand a process-only preflight correction back without
  recording a technical Code Review rejection.
- Exact-head review remains mandatory; this change does not weaken code review,
  test gates, clean-worktree requirements, or the three-cycle limit for real
  technical findings.

## Scope

Add a mandatory producer-side preflight before every implementation or
implementation-fix handoff to `GlitcherryCodeReviewer`:

1. mark only completed tracked-plan items and record the current exact-head
   verification evidence;
2. when tracked plan bytes changed, update the Paperclip plan mirror from those
   exact bytes and verify SHA-256 plus revision identity;
3. update the existing PR body to the exact head, current test totals, artifact
   paths/hashes, limitations, and required evidence headings;
4. only then record controller handoff and reassign the issue.

Define stale plan progress, stale plan mirror, or stale PR body as a
process-preflight correction rather than a technical Code Review rejection when
the exact product head is otherwise reviewable. The reviewer returns the same
issue/workspace/PR to the recorded producer without incrementing the rejection
counter, then checks only the corrected metadata delta before continuing the
pending technical verdict.

## Non-goals

- No weakening of technical, architecture, security, lifecycle, or acceptance
  review.
- No permission to rewrite acceptance criteria, thresholds, scope, roadmap,
  ADRs, or test meaning after approval.
- No second PR, branch, worktree, issue, reviewer workspace, or QA phase.
- No repeated build or device run for documentation-only evidence corrections.
- No change to merge authority, sprint smoke timing, or the maximum of three
  substantive Code Review rejection cycles.

## Affected areas

- `paperclips/projects/glitcherry-android/overlays/codex/_common.md`
- `paperclips/projects/glitcherry-android/roles-codex/android-engineer.md`
- `paperclips/projects/glitcherry-android/roles-codex/media-pipeline-engineer.md`
- `paperclips/projects/glitcherry-android/roles-codex/code-reviewer.md`
- Rendered Glitcherry Codex agent instructions produced by the existing build
  and deployment path.

## Acceptance criteria

1. Both implementer roles require tracked-plan, Paperclip-mirror, and PR-body
   synchronization before first review and every correction review.
2. The shared instruction layer states the same invariant so every role sees a
   single lifecycle rule.
3. Code Reviewer checks this evidence as a preflight and does not consume a
   technical rejection cycle for a metadata-only mismatch.
4. Documentation-only correction heads reuse already-valid product evidence and
   do not rerun Gradle, AVD, or device gates solely because metadata changed.
5. The one-issue, one-worktree, one-branch, one-PR, exact-head, and independent
   review boundaries remain unchanged.
6. Generated Glitcherry bundles contain the new rules and instruction validation
   passes.
7. The change contains no credentials or Glitcherry product-code mutation.

## Verification plan

- Run `git diff --check`.
- Build the Glitcherry instruction bundle with the repository's existing build
  command.
- Run the instruction validator and relevant bundle/assembly checks documented
  by the project scripts.
- Inspect the generated Android Engineer, Media Pipeline Engineer, and Code
  Reviewer instructions for the exact preflight and non-rejection language.
- Open a PR to `develop`; after merge, deploy through
  `paperclips/scripts/imac-agents-deploy.sh` and compare the deployed agent
  instructions.

## Open questions

None. The Human Engineering Lead already delegated bounded process corrections
needed to keep TP2 autonomous, and this change preserves every product and
technical review gate.
