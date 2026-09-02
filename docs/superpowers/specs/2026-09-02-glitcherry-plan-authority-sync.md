# Glitcherry plan authority and Paperclip mirror synchronization

Date: 2026-09-02
Status: Proposed
Branch: `fix/glitcherry-plan-authority-sync`
Baseline: `479dd2d0aac7da99f818886ad9d1c4b1d185e879`

## Problem

During GLA-16 recovery, the CTO committed the revised implementation plan in the
Android task worktree and handed that exact clean HEAD to the Code Reviewer. The
reviewer found that Paperclip's `plan` issue document still contained the prior
revision. The two copies therefore gave incompatible timing instructions. The
reviewer correctly refused to approve the plan, and the CTO had to perform an
otherwise avoidable revision cycle to publish the Git file into Paperclip.

The project workflow currently names the tracked Android `docs/plans/...` file
but does not define when or how its Paperclip issue-document mirror is updated.
The generic Paperclip skill then fills the gap and may require a new human
confirmation even when an earlier Human Engineering Lead decision explicitly
delegated a bounded test/tools-only feasibility correction to the CTO plus the
independent reviewer. This creates both a stale-authority risk and unnecessary
human stops.

## Assumptions

- The tracked plan file at the controller-recorded Android task HEAD is the
  durable implementation authority for a slice.
- Paperclip's `plan` issue document is the UI/API mirror of that exact tracked
  file, not an independently editable second plan.
- Human Engineering Lead confirmation remains mandatory when a revision changes
  product behavior, roadmap/slice scope, production dependencies, quality
  thresholds, accepted ADRs, or another owner-controlled decision.
- A prior structured Human Engineering Lead decision may explicitly delegate a
  bounded correction to CTO plus Code Reviewer. A revision entirely inside that
  delegation does not need a second human confirmation merely because the plan
  mirror received a new revision ID.
- Independent plan review remains mandatory after every changed plan HEAD.
- The pending GLA-16 revision-4 confirmation is existing live state and is not
  automatically accepted, rejected, or cancelled by this repository change.

## Goal

Make plan authority and synchronization deterministic so every plan review sees
one byte-identical plan in Git and Paperclip, while preserving human gates only
for decisions that actually require human authority.

## Scope

### In scope

- Define the tracked plan as the slice implementation authority and the
  Paperclip `plan` document as its byte-identical mirror.
- Require CTO synchronization before every plan-review handoff, including
  initial plans and revisions.
- Require the handoff evidence to record Android HEAD, tracked-plan SHA-256,
  Paperclip plan revision ID/number, and mirrored-body SHA-256.
- Require the Code Reviewer to reject a missing or non-identical mirror before
  technical review.
- Define when an exact-revision `request_confirmation` is required and when a
  recorded structured Human Engineering Lead delegation is sufficient.
- Add assembly tests that preserve these rules in generated agent instructions.

### Out of scope

- Changing the slice controller state schema or lease transitions.
- Changing application code, Android tests, the GLA-16 plan, or its live
  interaction state.
- Removing independent spec/plan/code review.
- Allowing agents to change roadmap scope, thresholds, product behavior, ADRs,
  or owner decisions without Human Engineering Lead authority.
- Automatically approving any confirmation on behalf of a user.

## Proposed contract

### One authority, one mirror

The controller-recorded tracked `docs/plans/...` file at the exact task HEAD is
the implementation authority. The Paperclip document with key `plan` must be
published from those exact bytes. Agents must not author divergent prose in the
issue document or treat it as a separate source of requirements.

Before handing a plan to `GlitcherryCodeReviewer / plan_review`, the CTO must:

1. finish and commit the tracked plan;
2. prove the worktree is clean and record the exact task HEAD;
3. read the tracked plan bytes and calculate SHA-256;
4. create/update the Paperclip `plan` document from those exact bytes using the
   current `baseRevisionId`;
5. read back the created revision and prove its body hash equals the tracked
   file hash;
6. record both hashes plus revision ID/number in the handoff comment;
7. only then perform the controller and Paperclip handoff.

Any API conflict, stale `baseRevisionId`, missing read-back, body mismatch, or
second writer stops the handoff. It does not create a replacement plan or issue.

### Human-confirmation classifier

An exact-revision `request_confirmation` is required when the plan revision
introduces or changes any of:

- product behavior or user-visible acceptance;
- roadmap/slice scope or ordering;
- production dependency/toolchain/API-floor choice;
- quality threshold or pass/fail meaning;
- accepted ADR/architecture decision;
- a choice reserved to the Human Engineering Lead by the roadmap or workflow.

No additional confirmation is required when all of the following are proven:

- a structured, answered Human Engineering Lead interaction explicitly
  delegates the named correction class to CTO plus independent reviewer;
- the revision stays within that delegation;
- product behavior, slice scope, production dependencies, thresholds, and ADRs
  are unchanged;
- the plan mirror is byte-identical to the tracked plan;
- the independent Code Reviewer approves the exact changed HEAD.

Ambiguity uses one structured question to the Human Engineering Lead. It must not
be resolved by silently choosing the cheaper path or by repeatedly asking for
confirmation after an explicit delegation already covers the revision.

### Reviewer behavior

The reviewer first verifies the exact Git/Paperclip mirror tuple. A mismatch is
one consolidated process finding returned to CTO and consumes a plan-revision
round because the handoff was incomplete. Once synchronized, the reviewer
evaluates the technical plan. It must not manufacture an extra human gate for a
revision that satisfies the recorded delegation classifier above.

## Affected files

- `paperclips/projects/glitcherry-android/WORKFLOW.md`
  - add the plan authority, mirror publication/read-back order, evidence tuple,
    and confirmation classifier to Phase 3 and decision-revision recovery.
- `paperclips/projects/glitcherry-android/roles-codex/glitcherry-cto.md`
  - require synchronization and classification before plan-review handoff.
- `paperclips/projects/glitcherry-android/roles-codex/code-reviewer.md`
  - require mirror verification and forbid duplicate human gates inside an
    explicit delegation.
- `paperclips/tests/test_glitcherry_android_assembly.py`
  - assert that source and assembled role instructions retain the contract.

No controller Python change is expected.

## Acceptance criteria

1. Project instructions explicitly name the tracked plan as authority and the
   Paperclip `plan` document as a byte-identical mirror.
2. CTO instructions require publish plus read-back before every `plan_review`
   handoff and record HEAD, both hashes, and revision identity.
3. Reviewer instructions reject an absent/stale/divergent mirror before
   technical approval.
4. The confirmation classifier preserves human authority for product, scope,
   production dependency, threshold, ADR, and owner-decision changes.
5. The classifier permits CTO plus independent reviewer to finish a bounded
   delegated test/tools-only correction without a duplicate human stop.
6. Existing one-worktree, exact-HEAD, lease, revision-ceiling, no-push-before-
   implementation, and sprint-smoke-only-after-all-slices rules are unchanged.
7. Assembly tests prove the markers exist in `WORKFLOW.md`, CTO role, reviewer
   role, and generated Codex instructions.
8. No live Paperclip issue/interaction/controller state or Android repository is
   mutated by this change.

## Verification plan

- Run focused Glitcherry assembly tests:
  `pytest -q paperclips/tests/test_glitcherry_android_assembly.py`.
- Run the controller tests to prove no lifecycle regression:
  `pytest -q paperclips/tests/test_glitcherry_slice_worktree.py`.
- Run the broader Paperclip assembly/instruction suite used by the project if
  available in the repository environment.
- Generate/inspect assembled CTO and Code Reviewer instructions and verify the
  plan-mirror and confirmation-classifier markers are present.
- Run `git diff --check`.
- Verify the changed-path set is limited to this spec and the four affected
  implementation/test files above.

## Risks and recovery

- Risk: wording accidentally allows CTO to reinterpret a product decision as a
  test-only correction. Mitigation: all five unchanged dimensions plus explicit
  structured delegation are required conjunctively; ambiguity returns to HEL.
- Risk: Paperclip document API conflict creates another stop. Mitigation: use
  `baseRevisionId`, read back the exact created revision, and retry only after
  reloading authoritative state; never overwrite blindly.
- Risk: generic Paperclip instructions conflict with project policy. Mitigation:
  state that this project-specific classifier narrows when confirmation is
  needed without weakening the Human Engineering Lead's reserved authority.
- Recovery: revert the single documentation/test change. No live controller or
  task state migration is involved.

## Open questions

None for implementation. The Human Engineering Lead must approve this spec
before the workflow and role instructions are changed.
