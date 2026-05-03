# Paperclip Agent Instruction Efficiency Implementation Plan

**Spec:** `docs/superpowers/specs/2026-05-03-paperclip-agent-instruction-efficiency.md`
**Branch:** `feature/paperclip-agent-instruction-efficiency`
**Base:** `origin/develop` at `65f5793`
**Reviewed spec baseline:** `48ca294`

Implementation agents must use the branch tip, not the original `a50ee54`
spec-only commit. If the spec or plan changes again before implementation, this
reviewed baseline must be refreshed before Phase 1.1 approval.

## Goal

Reduce generated Paperclip instruction weight for both Claude and Codex agents
without weakening the safety rules learned from real Gimle incidents.

The implementation must convert "everyone gets every heavy fragment" into an
explicit role/profile system with validator-enforced safety coverage.

## Non-Negotiable Guardrails

- Change Claude and Codex symmetrically by role group.
- Do not modify live Paperclip agent records during this work.
- Do not deploy regenerated bundles until reviewers approve generated output.
- Keep distilled mandatory rules inline until runtime runbook access is proven.
- Do not remove safety behavior unless the matrix has an equivalent rule,
  profile, role mapping, and validator check.
- Keep old untracked local files out of scope.
- Update `CLAUDE.md` if workflow, build, validator, or baseline commands change.

## Decisions

| Decision | Value |
|---|---|
| Role/profile declaration | YAML front matter before first heading |
| Generated bundle metadata | builder strips YAML front matter from `dist` |
| Profile source of truth | `paperclips/instruction-profiles.yaml` |
| Coverage source of truth | `paperclips/instruction-coverage.matrix.yaml` |
| Role identity | canonical IDs: `<target>:<role-file-stem>` |
| Profile fragments path | `paperclips/fragments/profiles/` |
| Lessons/runbooks path | `paperclips/fragments/lessons/` |
| Baseline file | `paperclips/bundle-size-baseline.json` |
| Allowlist file | `paperclips/bundle-size-allowlist.json` |
| Breakdown file | `paperclips/bundle-size-breakdown.json` |
| Token metric | report tokens as efficiency metric; bytes remain deterministic gate |
| Validator implementation | Python module plus pytest coverage; shell wrappers are allowed |
| Unknown profile | fail |
| Matrix references unknown role/profile | fail |
| Profile with no fragments | fail unless `empty_allowed: true` |
| Growth failure threshold | generated bundle grows more than 10 percent |
| New fragment warning | above 2 KB |
| New fragment failure | above 3 KB unless allowlisted |
| `handoff-full` default roles | `cto`, `code-reviewer`, `architect-reviewer`, `qa` families, resolved to explicit Claude/Codex role IDs |
| Other roles | short `handoff` profile by default |
| Canary | heavy Python engineer pair, not `CXCodeReviewer` |
| Shared repo productization | starts only after Gimle proof and heavy canary approval |

## Profile Contract

Profiles are not implicit labels. A profile must resolve to an ordered fragment
list through `paperclips/instruction-profiles.yaml`.

Example shape:

```yaml
profiles:
  core:
    fragments:
      - paperclips/fragments/profiles/core.md
  handoff:
    fragments:
      - paperclips/fragments/profiles/handoff.md
    runbooks:
      - paperclips/fragments/lessons/phase-handoff.md
  handoff-full:
    fragments:
      - paperclips/fragments/shared/fragments/phase-handoff.md
```

The final profile-driven builder flow is:

1. Read role front matter.
2. Validate `target`, canonical role ID, and requested profiles.
3. Resolve each profile through `paperclips/instruction-profiles.yaml`.
4. Expand the ordered fragment list.
5. Strip source front matter from generated bundles.
6. Emit Claude output under `paperclips/dist/*.md` and Codex output under
   `paperclips/dist/codex/*.md`.

During the Gimle proof migration, existing `<!-- @include ... -->` expansion
remains the builder path. In this phase, the profile manifest is the validation
source of truth: validators must ensure role metadata, matrix requirements,
resolved fragments, generated markers, and size policy remain coherent before a
later slice makes profile resolution drive bundle assembly directly.

## Validator Invariants

- `role.front_matter.profiles` must contain every profile required by
  `instruction-coverage.matrix.yaml` for that role ID.
- Every profile in role front matter must exist in
  `paperclips/instruction-profiles.yaml`.
- Every profile referenced by the matrix must exist in
  `paperclips/instruction-profiles.yaml`.
- Every role ID referenced by the matrix must map to an existing role file.
- Every resolved fragment path must exist.
- Generated bundles must not contain YAML front matter.
- Generated bundles must contain the validation markers required by the matrix.
- Runbook-backed rules are valid only if the distilled mandatory rule remains
  inline or runbook access has been verified before split.

## Handoff Split

The implementation must create two explicit semantics:

- `handoff`: short mandatory rule in
  `paperclips/fragments/profiles/handoff.md`.
- `handoff-full`: full phase matrix and incident lessons, initially backed by
  existing `paperclips/fragments/shared/fragments/phase-handoff.md`.

`paperclips/fragments/lessons/phase-handoff.md` stores the long background
lesson if narrative text is moved out of runtime bundles. The plan must measure
the byte and token savings from roles moving from `handoff-full` to `handoff`.

## Part 1: Gimle Proof

Part 1 proves the profile, validation, size, and runbook model inside
Gimle-Palace only. `paperclip-shared-fragments` remains unchanged until Part 1
has a reviewed heavy pilot and canary result.

## Task 1: Baseline Measurement And Manifests

**Owner:** implementation engineer
**Files:**
- `paperclips/roles/*.md`
- `paperclips/roles-codex/*.md`
- `paperclips/instruction-profiles.yaml`
- `paperclips/instruction-coverage.matrix.yaml`
- `paperclips/bundle-size-baseline.json`

**Work:**
- Record current bytes, lines, and token estimate for all generated Claude and
  Codex bundles.
- Add profile declarations to role files without slimming generated content.
- Add canonical role IDs using `<target>:<role-file-stem>`.
- Add `paperclips/instruction-profiles.yaml`.
- Add machine-readable safety coverage matrix data.

**Acceptance:**
- Every Claude and Codex role declares `target` and `profiles`.
- `instruction-profiles.yaml` maps every declared profile to explicit fragment
  paths.
- `instruction-coverage.matrix.yaml` references explicit role IDs.
- Baseline data is committed to `paperclips/bundle-size-baseline.json`.
- No generated bundle content is slimmed in this task.

## Task 1.5: Fragment Breakdown Audit

**Owner:** implementation engineer
**Dependencies:** Task 1
**Files:**
- `paperclips/bundle-size-breakdown.json`
- validator/report module

**Work:**
- Produce expanded-fragment breakdown for heavy bundles before slimming.
- Minimum roles: `claude:code-reviewer`, `claude:python-engineer`,
  `claude:mcp-engineer`, `claude:cto`, `codex:cx-python-engineer`.
- Report bytes, lines, token estimate, and source fragment path per expanded
  fragment.
- Identify expected savings from `handoff` vs `handoff-full`.

**Acceptance:**
- Breakdown explains which fragments dominate the 25-35 KB bundles.
- Size target bands are reviewed against real fragment contribution data.
- No broad slimming begins until this audit is reviewed.

## Task 2: Validators Without Slimming

**Owner:** implementation engineer
**Files:**
- `paperclips/build.sh`
- `paperclips/validate-codex-target.sh`
- `paperclips/bundle-size-allowlist.json`
- validator Python module and tests
- `CLAUDE.md` if commands/workflow change

**Work:**
- Validate YAML profile declarations.
- Validate profile manifest, coverage matrix, baseline, and allowlist schemas.
- Enforce validator invariants from this plan.
- Strip YAML front matter from generated bundles.
- Add bundle-size reporting.
- Add token estimate reporting as warn-only efficiency metric.
- Fail only on malformed declarations, unknown profiles, missing required
  profiles, missing fragments, missing markers, or no-growth violations.

**Acceptance:**
- Claude build still emits `paperclips/dist/*.md`.
- Codex build still emits `paperclips/dist/codex/*.md`.
- Codex validation still rejects Claude-only runtime assumptions.
- Generated bundles do not contain source role YAML front matter.
- No-growth exceptions must be listed in
  `paperclips/bundle-size-allowlist.json`.
- Validator logic has pytest coverage for known-good and known-bad fixtures.

## Task 2.5: Runbook Access Verification

**Owner:** implementation engineer plus reviewer
**Dependencies:** Task 2

**Work:**
- Verify whether Paperclip runtime agents can read
  `paperclips/fragments/lessons/` during actual task execution.
- If access is not proven, require every runbook-backed rule to keep a
  distilled mandatory inline rule in the profile fragment.
- Record the result in the PR description and validator config if needed.

**Acceptance:**
- Pilot split is blocked until this result is known.
- Dead links to lessons are not used as the only copy of a required rule.

## Task 3: Heavy Pilot Profile Split

**Owner:** implementation engineer
**Dependencies:** Tasks 1, 1.5, 2, 2.5 reviewed
**Files:**
- `paperclips/roles/python-engineer.md`
- `paperclips/roles-codex/cx-python-engineer.md`
- profile/runbook fragments under `paperclips/fragments/profiles/` and
  `paperclips/fragments/lessons/`

**Work:**
- Split the Python engineer pair first because it exercises real heavy-bundle
  profile mechanics.
- Keep mandatory rules inline.
- Move long lesson narrative to `paperclips/fragments/lessons/` only when the
  short executable rule remains in profile output.
- Verify `implementation`, `task-start`, `handoff`, branch safety,
  stale-session, and verification rules remain present.

**Acceptance:**
- Pilot roles are smaller or explicitly justified in the allowlist.
- Bundle savings are shown in bytes and token estimate.
- Safety matrix has no missing required rules for pilot roles.
- Reviewer can identify which profile/fragment supplies each required rule.

## Task 4: Symmetric Role-Group Rollout

**Owner:** implementation engineer
**Dependencies:** Task 3 approved

**Work:**
- Apply profile split by role group across Claude and Codex together.
- Preferred order: implementation engineers, reviewers, QA, research/writer,
  then CTO/infra/architect.
- Use the breakdown audit to choose high-impact fragments first.
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
- Update `CLAUDE.md` if new validator/build commands become required workflow.

**Acceptance:**
- All Claude and Codex bundles build.
- `paperclips/validate-codex-target.sh` passes.
- Codex bundles do not contain Claude-only runtime assumptions.
- Claude bundles do not lose required production-baseline safety behavior.

## Task 6: Heavy Canary Validation

**Owner:** CodeReviewer, QAEngineer, CTO
**Dependencies:** Tasks 1-5

**Work:**
- Run a read-only canary with a role that actually changed from heavy to
  profiled output. Default canary pair:
  `claude:python-engineer` and `codex:cx-python-engineer`.
- Compare before/after bundle size, token estimate, and instruction clarity.
- Check whether the canary misses any safety rule that old bundles covered.

**Acceptance:**
- Canary output uses the right role profile.
- Canary does not miss branch/spec, stale-session, handoff, QA evidence, or
  verification-readiness rules.
- Results decide whether to expand the pattern to remaining heavy roles.

## Part 2: Shared Fragments Reusable Toolkit

Part 2 starts only after Part 1 is reviewed. Its goal is to make
`paperclip-shared-fragments` usable for new projects as more than a loose
fragment library: documented install flow, starter layout, reusable validators,
and a smoke-tested consumer fixture.

## Task 7: Shared Repo Audit And README Refresh

**Owner:** implementation engineer
**Dependencies:** Part 1 approved
**Repo:** `paperclip-shared-fragments`

**Work:**
- Audit current shared repo state and record the current baseline SHA.
- Update README from old slice wording to current capability wording.
- Document what is supported now: fragments, templates, `@include` builder,
  Codex runtime map.
- Document what remains consumer-owned: project-local roles, local fragments,
  live Paperclip agent records, deploy scripts.

**Acceptance:**
- README no longer claims only `v0.0.1` slice status.
- New-project usage section explains the minimum setup path.
- Limitations are explicit so consumers do not assume full team-builder
  automation exists before it is implemented.

## Task 8: Starter Consumer Layout

**Owner:** implementation engineer
**Dependencies:** Task 7
**Repo:** `paperclip-shared-fragments`

**Work:**
- Add or document a starter layout for a new consumer project:
  `paperclips/roles/`, `paperclips/fragments/local/`,
  `paperclips/fragments/shared`, `paperclips/dist/`, and validation files.
- Provide starter role examples that use shared fragments without Gimle-specific
  assumptions.
- Provide a project-local override pattern for local rules.

**Acceptance:**
- A new project can copy or reference the starter layout without importing
  Gimle-specific files.
- Starter examples build with the shared builder or documented commands.

## Task 9: Bootstrap And Install Flow

**Owner:** implementation engineer
**Dependencies:** Task 8
**Repo:** `paperclip-shared-fragments`

**Work:**
- Document and, if small enough, add a bootstrap script for adding the shared
  repo to a consumer project as a submodule.
- Include commands for building generated role bundles from the starter layout.
- Include rollback/removal instructions.
- Avoid mutating an existing project unless the operator explicitly opts in.

**Acceptance:**
- New project setup is reproducible from README commands.
- Bootstrap path does not require hidden Gimle files.
- Failure modes are documented: missing git, existing `paperclips/`, missing
  Paperclip runtime, missing Codex runtime.

## Task 10: Consumer Fixture Smoke

**Owner:** implementation engineer
**Dependencies:** Task 9
**Repo:** `paperclip-shared-fragments`

**Work:**
- Add a minimal example consumer fixture or documented smoke flow.
- Build at least one Claude role and one Codex/CX role from the fixture.
- Validate that shared fragments resolve and project-local fragments override
  only intended content.

**Acceptance:**
- Smoke build is runnable in CI or with one documented command.
- Fixture proves the shared repo works for a project that is not Gimle.
- Fixture output does not contain Gimle-specific role names, branch names, or
  issue IDs unless clearly marked as examples.

## Task 11: Upstream Profile And Validator Model

**Owner:** implementation engineer
**Dependencies:** Part 1 approved, Tasks 7-10 complete
**Repo:** `paperclip-shared-fragments`

**Work:**
- Port the proven Gimle profile/runbook shape to shared repo.
- Add shared versions of:
  `instruction-profiles.yaml`,
  `instruction-coverage.matrix.yaml`,
  bundle-size baseline/allowlist conventions, and validator tests.
- Keep project-specific role IDs and thresholds overridable by consumers.
- Repair shared-fragments build/docs drift if it blocks the upstream move.

**Acceptance:**
- Shared repo has reusable profile and validator semantics.
- Validators remain project-neutral and do not hardcode Gimle role IDs.
- Tests cover at least one fixture role, one unknown profile failure, and one
  missing required profile failure.

## Task 12: Gimle Submodule Bump After Shared PR

**Owner:** implementation engineer
**Dependencies:** Task 11 shared repo PR reviewed and merged
**Repo:** Gimle-Palace

**Work:**
- Bump `paperclips/fragments/shared` to the reviewed shared repo SHA.
- Rebuild Gimle bundles.
- Compare generated output against the pre-upstream Gimle proof.

**Acceptance:**
- Gimle submodule bump is forward-only and reviewable.
- Generated Gimle output remains equivalent or intentionally improved.
- `paperclips/validate-codex-target.sh` and profile validators pass.

## Verification Commands

```bash
./paperclips/build.sh --target claude
./paperclips/build.sh --target codex
python3 paperclips/scripts/validate_instructions.py
./paperclips/validate-codex-target.sh
services/palace-mcp/.venv/bin/pytest -q paperclips/tests/test_validate_instructions.py
git diff --check
```

Additional required checks:

```bash
find paperclips/dist -maxdepth 2 -type f -name '*.md' -print0 | xargs -0 wc -c | sort -n
find paperclips/dist -maxdepth 2 -type f -name '*.md' -print0 | xargs -0 wc -l | sort -n
```

Validator-specific file checks:

```bash
test -f paperclips/instruction-profiles.yaml
test -f paperclips/instruction-coverage.matrix.yaml
test -f paperclips/bundle-size-baseline.json
test -f paperclips/bundle-size-allowlist.json
test -f paperclips/bundle-size-breakdown.json
```

## Review Gates

1. Spec and plan committed and pushed to the feature branch.
2. Plan-first review confirms profile manifest, matrix, baseline, breakdown,
   and validator invariants are specific enough.
3. Runbook access is verified before pilot split.
4. Heavy pilot split is reviewed before broad rollout.
5. Broad rollout proceeds by symmetric role groups, not all Claude before all
   Codex.
6. Validator implementation includes pytest coverage.
7. Part 2 shared repo productization starts only after Part 1 Gimle proof and
   heavy canary approval.
8. Shared repo changes land in their own PR before Gimle submodule bump.
9. Live deploy is a separate approved step after generated bundles pass review.
