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
- `paperclips/fragments/**`
- `paperclips/fragments/shared/fragments/**`
- `paperclips/build.sh`
- `paperclips/validate-codex-target.sh`
- future validation scripts for bundle size and profile coverage
- shared fragments repository, if the same changes need to be upstreamed

## Acceptance Criteria

- Each Claude and Codex role declares the instruction profiles it needs.
- Generated Claude and Codex bundles preserve existing safety intent.
- Role bundles no longer include full heavy lifecycle runbooks unless the role
  needs them.
- Heavy incident lessons remain available through concise references or
  role/phase-specific runbooks.
- Claude build still emits `paperclips/dist/*.md`.
- Codex build still emits `paperclips/dist/codex/*.md`.
- Codex validation still rejects Claude-only runtime assumptions.
- New validation reports bundle size and fails or warns on oversized fragments
  according to an explicit threshold.
- Reviewers and QA still receive enough handoff/evidence rules to catch the
  bugs that motivated the original fragments.
- No live Paperclip agent is modified by this spec-only slice.

## Verification Plan

For this spec-only slice:

- Confirm only this spec file is committed.
- Confirm the branch is based on `origin/develop`.

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
5. Review generated bundles for missing role-critical rules.
6. Run a canary review task with `CXCodeReviewer`.
7. Keep live bundle deploy and agent creation out of scope until the generated
   outputs are reviewed.

## Open Questions

- What bundle-size threshold should be enforced for each role type?
- Should heavy incident lessons live in `paperclips/fragments/lessons/` or in
  the shared fragments repository first?
- Should `paperclip-shared-fragments` become the authoritative build/control
  plane before this refactor, or should Gimle prove the shape first and then
  upstream it?
- Which roles require `handoff-full` by default: CTO, CodeReviewer,
  ArchitectReviewer, QAEngineer, or all four?
