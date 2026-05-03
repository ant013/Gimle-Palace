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
| Generated bundle metadata | builder strips YAML front matter from `dist` |
| Coverage source of truth | `paperclips/instruction-coverage.matrix.yaml` |
| Role identity | canonical IDs: `<target>:<role-file-stem>` |
| Initial size enforcement | baseline bytes/lines plus no-growth guard |
| Baseline file | `paperclips/bundle-size-baseline.json` |
| Allowlist file | `paperclips/bundle-size-allowlist.json` |
| Growth failure threshold | generated bundle grows more than 10 percent |
| New fragment warning | above 2 KB |
| New fragment failure | above 3 KB unless allowlisted |
| `handoff-full` default roles | `cto`, `code-reviewer`, `architect-reviewer`, `qa` families, resolved to explicit Claude/Codex role IDs |
| Other roles | short `handoff` profile by default |
| Lesson text | runbook/lesson files, not repeated in every generated bundle |

## Task 1: Baseline Measurement And Manifest

**Owner:** CTO or implementation engineer
**Files:**
- `paperclips/roles/*.md`
- `paperclips/roles-codex/*.md`
- `paperclips/instruction-coverage.matrix.yaml`
- `paperclips/bundle-size-baseline.json`

**Work:**
- Record current bytes and line counts for all generated Claude and Codex
  bundles.
- Add profile declarations to role files without removing existing includes.
- Add canonical role IDs using `<target>:<role-file-stem>`.
- Add machine-readable safety coverage matrix data.

**Acceptance:**
- Every Claude and Codex role declares `target` and `profiles`.
- Baseline report covers `paperclips/dist/*.md` and
  `paperclips/dist/codex/*.md`.
- Baseline data is committed to `paperclips/bundle-size-baseline.json`.
- Coverage matrix is committed to `paperclips/instruction-coverage.matrix.yaml`
  and references explicit role IDs.
- No generated bundle content is slimmed in this task.

## Task 2: Validators Without Slimming

**Owner:** implementation engineer
**Files:**
- `paperclips/build.sh`
- `paperclips/validate-codex-target.sh`
- `paperclips/bundle-size-allowlist.json`
- new validation script if cleaner

**Work:**
- Validate YAML profile declarations.
- Strip YAML front matter from generated bundles.
- Validate required profiles against the safety coverage matrix.
- Add bundle-size reporting.
- Fail only on new no-growth violations or malformed declarations.

**Acceptance:**
- Claude build still emits `paperclips/dist/*.md`.
- Codex build still emits `paperclips/dist/codex/*.md`.
- Codex validation still rejects Claude-only runtime assumptions.
- Validator reports size, profile coverage, and missing required rules.
- Generated bundles do not contain source role YAML front matter.
- No-growth exceptions must be listed in
  `paperclips/bundle-size-allowlist.json`.

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

## Task 4: Symmetric Role-Group Rollout

**Owner:** implementation engineer
**Dependencies:** Tasks 1-3 reviewed

**Work:**
- Apply profile split by role group across Claude and Codex together.
- Preferred order: reviewers, QA, implementation engineers, research/writer,
  then CTO/infra/architect.
- Avoid keeping heavy fragments in roles that only need short mandatory rules.
- Preserve Claude production-baseline behavior.
- Preserve Codex runtime behavior.

**Acceptance:**
- All Claude bundles build.
- All Codex bundles build.
- All changed Claude and Codex roles pass profile coverage validation.
- Future target bands are reported, but existing oversize roles are not failed
  solely for missing the future band.

## Task 5: Target-Specific Cleanup

**Owner:** implementation engineer
**Dependencies:** Tasks 1-4 reviewed

**Work:**
- Replace broad post-build string substitutions with target-aware fragments
  where practical.
- Keep Codex instructions grounded in `AGENTS.md`, `codebase-memory`, `serena`,
  Codex agents, and Codex skills only where the role needs them.
- Keep Claude-specific runtime text only where Claude roles need it.

**Acceptance:**
- All Claude and Codex bundles build.
- `paperclips/validate-codex-target.sh` passes.
- Codex bundles do not contain Claude-only runtime assumptions.
- Claude bundles do not lose required production-baseline safety behavior.

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

Validator-specific checks:

```bash
test -f paperclips/instruction-coverage.matrix.yaml
test -f paperclips/bundle-size-baseline.json
test -f paperclips/bundle-size-allowlist.json
```

## Review Gates

1. Spec and plan committed and pushed to the feature branch.
2. Plan-first review confirms the safety coverage matrix is specific enough.
3. Implementation begins only after approval.
4. Pilot split is reviewed before broad Claude/Codex rollout.
5. Broad rollout proceeds by symmetric role groups, not all Claude before all
   Codex.
6. Live deploy is a separate approved step after generated bundles pass review.
