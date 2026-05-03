# Paperclip Agent Instruction Efficiency

## Status

Proposed.

## Context

Gimle now has two Paperclip agent targets:

- the existing Claude team, generated into `paperclips/dist/*.md`;
- the new Codex/CX team, generated into `paperclips/dist/codex/*.md`.

Both targets inherited large shared instruction bundles. This is intentional
history: many fragments were added after real Paperclip failures around stale
session memory, phase handoff gaps, missing QA evidence, branch drift, merge
readiness, and runtime setup. The current shape preserves those lessons, but it
also makes every agent pay for large context on every wake, including idle wakes
and narrow read-only tasks.

The goal of this work is to reduce instruction weight and improve role focus
without weakening the safety behavior that the fragments encode.

## Assumptions

- Claude remains the production baseline.
- Codex remains a parallel target and should receive equivalent safety
  discipline, not a weaker shortcut.
- Efficiency changes must be symmetric: if a shared rule is split or moved to a
  role/phase profile, both Claude and Codex outputs must be considered.
- Heavy bug lessons should remain available, but not necessarily expanded into
  every role bundle by default.
- When a long lesson can be replaced by a short mandatory rule plus a
  reviewable runbook reference, the generated bundle should use the short rule.
- The existing `CXCodeReviewer` compact role is a useful reference, but not a
  reason to leave the rest of the Codex team heavy.
- Existing untracked local files are out of scope and must not be touched.

## Scope

- Define role/phase instruction profiles for both Claude and Codex agents.
- Split always-needed rules from phase-specific and role-specific runbooks.
- Reduce repeated large fragments in generated Paperclip bundles.
- Add validation that tracks bundle size and role/profile coverage.
- Preserve Claude/Codex target separation in build and deploy outputs.
- Keep lessons from past bugs available through concise references or on-demand
  runbooks.
- Add an explicit safety-coverage matrix so slimming can be reviewed against
  concrete rules, profiles, roles, and validation checks.

## Out Of Scope

- Changing live Paperclip agent records.
- Uploading bundles to Claude or Codex agents.
- Creating new Paperclip agents.
- Changing Paperclip adapter settings.
- Removing safety rules instead of relocating or tightening them.
- Refactoring unrelated service code.

## Current Problem

Current generated role bundles are large and repetitive. Most roles include the
same heavy lifecycle fragments regardless of whether the role performs
implementation, review, QA, research, writing, or merge/deploy work.

Examples of repeated concepts:

- phase handoff matrix and incident history;
- heartbeat and stale-session discipline;
- git workflow and branch safety;
- QA evidence format;
- merge-readiness rules;
- test-design and compliance checklists.

These rules are valuable, but the current all-in bundle shape creates three
costs:

- higher prompt/token cost on every wake;
- more noise before the agent reaches role-specific work;
- higher drift risk when Claude and Codex variants diverge through string
  replacement instead of explicit target-aware fragments.

## Design Principle

Prefer a mandatory mechanical rule over repeated incident narrative in generated
agent bundles.

Long incident write-ups should live in runbooks or lessons unless the incident
text itself is required for the agent to execute the current role. Runtime
bundles should keep the rule, the checklist, and the validation target.

Example:

```markdown
## Phase handoff

At phase completion, you must:

- push your branch before handoff;
- set the next phase assignee explicitly;
- @mention the next agent;
- include commit SHA, branch, evidence, and next requested action;
- never leave the issue as only `status=todo`;
- never mark `done` unless required next-phase evidence exists.

Background: see `paperclips/fragments/lessons/phase-handoff.md`.
```

This preserves the GIM-48 lesson without expanding the full incident history
into every implementer, researcher, or writer bundle.

## Proposed Model

Introduce explicit instruction profiles:

| Profile | Purpose | Typical consumers |
|---|---|---|
| `core` | identity, source of truth, idle behavior, minimal safety | all roles |
| `task-start` | branch/spec/plan discovery and context loading | all active roles |
| `implementation` | coding, tests, verification, handoff to review | engineer roles |
| `review` | plan/code review, findings format, approval rules | CodeReviewer, ArchitectReviewer |
| `qa-smoke` | live smoke, runtime evidence, checkout restore | QA roles |
| `research` | citation and source verification discipline | ResearchAgent |
| `handoff` | short universal handoff rules | all roles |
| `handoff-full` | full phase matrix and incident lessons | CTO, reviewers, QA |
| `merge-deploy` | merge, deploy, rollback, release evidence | CTO, Infra, QA |

Every role should declare its profiles explicitly. Generated bundles should
contain only the profiles needed by that role.

## Profile Declaration Format

Use YAML front matter in role files. The declaration must be present before the
first heading.

Claude example:

```yaml
---
target: claude
profiles:
  - core
  - task-start
  - implementation
  - handoff
---
```

Codex example:

```yaml
---
target: codex
profiles:
  - core
  - task-start
  - review
  - handoff-full
---
```

The build/validation path should read this metadata and verify that generated
output contains the required profile fragments. Existing `@include` expansion
can remain during migration, but profile metadata becomes the reviewable source
of truth for which rules belong to each role.

## Safety Coverage Matrix

The first implementation slice must create a machine-readable or
review-friendly matrix with this minimum content:

| Rule area | Risk guarded | Required profiles | Required roles | Validation check |
|---|---|---|---|---|
| stale-session / heartbeat | agent acts from stale memory or idle wake | `core` | all roles | all bundles include concise source-of-truth and idle rule |
| branch/spec gate | implementation starts before reviewed scope | `task-start` | all active roles | profile manifest and generated bundle check |
| short handoff | issue becomes ownerless between phases | `handoff` | all roles | generated bundle includes mandatory handoff rule |
| full phase matrix | QA/review/merge gate is skipped | `handoff-full` | CTO, CodeReviewer, ArchitectReviewer, QAEngineer | generated bundle includes phase matrix or approved runbook reference |
| QA evidence | weak or fake smoke evidence reaches merge | `qa-smoke` | QAEngineer, CodeReviewer, ArchitectReviewer, CTO | bundle includes evidence checklist or structured schema reference |
| merge readiness | PR closes without tested merge/deploy state | `merge-deploy` | CTO, InfraEngineer, QAEngineer | bundle includes merge/deploy pre-close checklist |
| implementation verification | code lands without tests/commands | `implementation` | engineer roles, QAEngineer | bundle includes test/verification checklist |
| research evidence | uncited claims drive architecture | `research` | ResearchAgent, ArchitectReviewer | bundle includes citation/source rule |

Reviewers should use this matrix as the oracle for safety preservation. A
bundle-size reduction is not acceptable if it removes a required rule without
an equivalent short rule or runbook-backed profile.

## Runbook Access Model

Runbook references are only valid when the agent can read them during a
Paperclip run. The first implementation slice must verify one of these models:

- the runbook file is included in the uploaded Paperclip instruction bundle; or
- the agent has repository checkout access and the runbook path exists in that
  checkout; or
- the generated bundle keeps a distilled mandatory rule and the runbook is only
  background for maintainers/reviewers.

Until that access model is verified, generated bundles must keep the distilled
mandatory rule inline. They may link to the full lesson, but the link cannot be
the only copy of the rule.

## Bundle Size Policy

Current generated bundles range from about 7.4 KB for `CXCodeReviewer` to about
35.5 KB for the current Claude `CodeReviewer`. This spec starts with a
baseline-first policy:

- Slice 1 records current bytes and line counts for all generated Claude and
  Codex bundles.
- Slice 1 is warn-only for existing oversized bundles and fragments.
- New validation fails if a generated bundle grows more than 10 percent from
  the recorded baseline without an explicit allowlist entry.
- New fragments warn above 2 KB and fail above 3 KB unless allowlisted.

Post-split target bands:

| Role class | Target bundle size | Notes |
|---|---:|---|
| compact reviewer / canary | <= 12 KB | `CXCodeReviewer` is already below this |
| research / writer / light roles | <= 18 KB | should avoid full lifecycle runbooks |
| implementation / QA roles | <= 24 KB | may include implementation or QA profiles |
| CTO / ArchitectReviewer temporary ceiling | <= 28 KB | allow larger during migration |
| hard ceiling | <= 32 KB | exception requires explicit review note |

The first implementation should not fail existing bundles solely for exceeding
the future target bands. It should record the baseline, enforce no-growth, and
then reduce role groups in later slices.

## Claude Symmetry

Claude output must be optimized alongside Codex output.

Required behavior:

- `paperclips/roles/*.md` continues to generate `paperclips/dist/*.md`.
- Claude roles keep Claude-specific runtime concepts where appropriate.
- Claude safety behavior remains equivalent after fragment splitting.
- Claude bundles should not retain heavy fragments solely because Codex needed
  a new profile or vice versa.

## Codex Symmetry

Codex output must use the same profile model with target-specific runtime text.

Required behavior:

- `paperclips/roles-codex/*.md` continues to generate
  `paperclips/dist/codex/*.md`.
- Codex roles use `AGENTS.md`, `codebase-memory`, `serena`, Codex agents, and
  Codex skills where relevant.
- Codex roles do not rely on Claude-only `superpowers:*`, `claude-api`,
  `CLAUDE.md`, or Claude CLI/session assumptions.
- String replacement in the builder should not be the primary way to express
  target differences when a target-aware fragment is clearer.

## Affected Areas

- `paperclips/roles/*.md`
- `paperclips/roles-codex/*.md`
- `paperclips/fragments/profiles/**` or equivalent profile-fragment directory
- `paperclips/fragments/lessons/**` or equivalent runbook directory
- `paperclips/fragments/**`
- `paperclips/fragments/shared/fragments/**`
- `paperclips/build.sh`
- `paperclips/validate-codex-target.sh`
- future validation scripts for bundle size and profile coverage
- shared fragments repository, if the same changes need to be upstreamed

## Acceptance Criteria

- Each Claude and Codex role declares the instruction profiles it needs.
- Generated Claude and Codex bundles preserve required safety rules according
  to the safety coverage matrix.
- Role bundles no longer include full heavy lifecycle runbooks unless the role
  needs them.
- Heavy incident lessons remain available through concise references or
  role/phase-specific runbooks.
- Any runbook-backed rule keeps a distilled mandatory inline rule until runtime
  access to the runbook is verified.
- Claude build still emits `paperclips/dist/*.md`.
- Codex build still emits `paperclips/dist/codex/*.md`.
- Codex validation still rejects Claude-only runtime assumptions.
- New validation reports bundle size and fails or warns on oversized fragments
  according to an explicit threshold.
- Reviewers and QA still receive enough handoff/evidence rules to catch the
  bugs that motivated the original fragments.
- No live Paperclip agent is modified by this spec-only slice.

## Implementation Slices

1. Baseline measurement and profile manifest.
   - Measure current bundle bytes/lines.
   - Add role/profile declarations.
   - Add safety coverage matrix.
   - Do not remove heavy fragments yet.
2. Validators without slimming.
   - Validate profile declarations.
   - Validate role/profile coverage.
   - Add bundle-size report and no-growth guard.
3. Pilot profile split.
   - Apply profile fragments to `CXCodeReviewer` and one Claude reviewer role.
   - Keep mandatory rules inline.
   - Move long lesson text to runbook references.
4. Claude target rollout.
   - Apply profile split to Claude roles by role group.
   - Verify safety matrix coverage.
5. Codex target rollout.
   - Apply the same profile model to Codex roles.
   - Replace regex target substitutions with target-aware fragments where
     practical.
6. Shared-fragments upstream.
   - Upstream proven profile/runbook shape to `paperclip-shared-fragments`.
   - Repair shared repo build/docs drift if it remains authoritative.
7. Canary validation.
   - Run `CXCodeReviewer` canary review.
   - Compare before/after bundle size and missed-rule findings.

## Verification Plan

For this spec-only slice:

- Confirm only this spec and its implementation plan are committed.
- Confirm the branch is based on `origin/develop`.
- Confirm the branch is pushed to
  `origin/feature/paperclip-agent-instruction-efficiency` before
  implementation begins.

For implementation slices:

1. Build Claude target:

```bash
./paperclips/build.sh --target claude
```

2. Build Codex target:

```bash
./paperclips/build.sh --target codex
```

3. Validate Codex target:

```bash
./paperclips/validate-codex-target.sh
```

4. Compare bundle sizes before and after profile splitting.
5. Validate role/profile coverage against the safety coverage matrix.
6. Review generated bundles for missing role-critical rules.
7. Verify runbook access model or keep distilled rules inline.
8. Run a canary review task with `CXCodeReviewer`.
9. Keep live bundle deploy and agent creation out of scope until the generated
   outputs are reviewed.

## Decisions

- Bundle-size enforcement starts as baseline plus no-growth. Future target
  bands are defined in the Bundle Size Policy section.
- Heavy incident lessons should be proven in Gimle first under
  `paperclips/fragments/lessons/` or an equivalent local runbook directory, then
  upstreamed after the shape is reviewed.
- Gimle proves the profile/runbook shape first. `paperclip-shared-fragments`
  should become authoritative after the first safe implementation slice.
- `handoff-full` is required by default for CTO, CodeReviewer,
  ArchitectReviewer, and QAEngineer. Other roles receive short `handoff` by
  default and may read the full runbook only when needed.
