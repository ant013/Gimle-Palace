# Paperclip Agent Instruction Efficiency Implementation Plan

**Spec:** `docs/superpowers/specs/2026-05-03-paperclip-agent-instruction-efficiency.md`
**Branch:** `feature/paperclip-agent-instruction-efficiency`
**Base:** `origin/develop` at `65f5793`
**Spec commit:** `a50ee54`

## Goal

Reduce generated Paperclip instruction weight for both Claude and Codex agents
without weakening the safety rules learned from real Gimle incidents.

The implementation should prefer short mandatory rules in generated bundles and
move long background lessons to runbooks when the rule can still be executed
without reading the full incident narrative.

## Guardrails

- Change Claude and Codex symmetrically.
- Do not modify live Paperclip agent records during this work.
- Do not deploy regenerated bundles until reviewers approve the generated
  output.
- Keep distilled mandatory rules inline until runtime runbook access is proven.
- Do not remove safety behavior unless the safety coverage matrix has an
  equivalent required rule, profile, role mapping, and validation check.
- Keep old untracked local files out of scope.

## Decisions

| Decision | Value |
|---|---|
| Role/profile declaration | YAML front matter before first heading |
| Initial size enforcement | baseline bytes/lines plus no-growth guard |
| Growth failure threshold | generated bundle grows more than 10 percent |
| New fragment warning | above 2 KB |
| New fragment failure | above 3 KB unless allowlisted |
| `handoff-full` default roles | CTO, CodeReviewer, ArchitectReviewer, QAEngineer |
| Other roles | short `handoff` profile by default |
| Lesson text | runbook/lesson files, not repeated in every generated bundle |

## Task 1: Baseline Measurement And Manifest

**Owner:** CTO or implementation engineer
**Files:**
- `paperclips/roles/*.md`
- `paperclips/roles-codex/*.md`
- new validator/report output as needed

**Work:**
- Record current bytes and line counts for all generated Claude and Codex
  bundles.
- Add profile declarations to role files without removing existing includes.
- Add a reviewable safety coverage matrix file or embedded validator data.

**Acceptance:**
- Every Claude and Codex role declares `target` and `profiles`.
- Baseline report covers `paperclips/dist/*.md` and
  `paperclips/dist/codex/*.md`.
- No generated bundle content is slimmed in this task.

## Task 2: Validators Without Slimming

**Owner:** implementation engineer
**Files:**
- `paperclips/build.sh`
- `paperclips/validate-codex-target.sh`
- new validation script if cleaner

**Work:**
- Validate YAML profile declarations.
- Validate required profiles against the safety coverage matrix.
- Add bundle-size reporting.
- Fail only on new no-growth violations or malformed declarations.

**Acceptance:**
- Claude build still emits `paperclips/dist/*.md`.
- Codex build still emits `paperclips/dist/codex/*.md`.
- Codex validation still rejects Claude-only runtime assumptions.
- Validator reports size, profile coverage, and missing required rules.

## Task 3: Pilot Profile Split

**Owner:** implementation engineer
**Files:**
- `paperclips/roles-codex/cx-code-reviewer.md`
- one Claude reviewer role, preferably `paperclips/roles/code-reviewer.md`
- profile/runbook fragments under `paperclips/fragments/**`

**Work:**
- Split one Codex reviewer and one Claude reviewer into explicit profiles.
- Keep mandatory rules inline.
- Move long lesson narrative to runbook references.
- Verify that `handoff-full`, review, QA evidence, branch safety, and stale
  session rules remain present where required.

**Acceptance:**
- Generated pilot bundles are smaller or no larger than baseline.
- Safety matrix has no missing required rules for pilot roles.
- Reviewer can identify where each required rule came from.

## Task 4: Claude Target Rollout

**Owner:** implementation engineer
**Dependencies:** Tasks 1-3 reviewed

**Work:**
- Apply profile split to Claude roles by role group.
- Avoid keeping heavy fragments in roles that only need short mandatory rules.
- Preserve Claude-specific runtime text where it is actually required.

**Acceptance:**
- All Claude bundles build.
- All Claude roles pass profile coverage validation.
- Future target bands are reported, but existing oversize roles are not failed
  solely for missing the future band.

## Task 5: Codex Target Rollout

**Owner:** implementation engineer
**Dependencies:** Tasks 1-4 reviewed

**Work:**
- Apply the same profile model to Codex roles.
- Replace broad post-build string substitutions with target-aware fragments
  where practical.
- Keep Codex instructions grounded in `AGENTS.md`, `codebase-memory`, `serena`,
  Codex agents, and Codex skills only where the role needs them.

**Acceptance:**
- All Codex bundles build.
- `paperclips/validate-codex-target.sh` passes.
- Codex bundles do not contain Claude-only runtime assumptions.

## Task 6: Shared Fragments Upstream

**Owner:** implementation engineer
**Dependencies:** Tasks 1-5 proven in Gimle

**Work:**
- Port the proven profile/runbook shape to `paperclip-shared-fragments`.
- Repair shared-fragments build/docs drift if it blocks the upstream move.
- Bump the Gimle submodule only after the shared-fragments PR is reviewed.

**Acceptance:**
- Shared repo has the same safety semantics.
- Gimle submodule bump is forward-only and reviewable.
- Generated Gimle output remains equivalent after the upstream move.

## Task 7: Canary Validation

**Owner:** CodeReviewer, QAEngineer, CTO
**Dependencies:** Tasks 1-6

**Work:**
- Run a read-only `CXCodeReviewer` canary review.
- Compare before/after bundle size and instruction clarity.
- Check whether the canary misses any safety rule that old bundles covered.

**Acceptance:**
- Canary output uses the right role profile.
- Canary does not miss branch/spec, stale-session, handoff, QA evidence, or
  review-readiness rules.
- Results decide whether to expand the pattern to the remaining roles.

## Verification Commands

```bash
./paperclips/build.sh --target claude
./paperclips/build.sh --target codex
./paperclips/validate-codex-target.sh
```

Additional required checks:

```bash
find paperclips/dist -maxdepth 2 -type f -name '*.md' -print0 | xargs -0 wc -c | sort -n
find paperclips/dist -maxdepth 2 -type f -name '*.md' -print0 | xargs -0 wc -l | sort -n
```

## Review Gates

1. Spec and plan committed and pushed to the feature branch.
2. Plan-first review confirms the safety coverage matrix is specific enough.
3. Implementation begins only after approval.
4. Pilot split is reviewed before broad Claude/Codex rollout.
5. Live deploy is a separate approved step after generated bundles pass review.
