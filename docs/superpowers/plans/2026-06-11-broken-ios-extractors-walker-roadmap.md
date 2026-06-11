# Walker Plan - Source of truth: broken iOS extractor repair

Grounded in spec
`docs/superpowers/specs/2026-06-11-broken-ios-extractors-repair.md`
at commit `f9d92ba2c601d1328844b1b07a82d2bfd69a3d01`.

This file is the source of truth for the walker. The Paperclip issue may
summarize status, but the authoritative queue, current task, and completion
evidence live here.

## Non-negotiable execution policy

- Team: CX/Codex only.
- Main walker assignee: `CXCTO`
  (`da97dbd9-6627-48d0-b421-66af0750eacf`).
- Do not assign or mention Claude-side roles for this walker. In particular,
  never use bare `CTO`, bare `CodeReviewer`, or `OpusArchitectReviewer`.
- Run exactly one executable fix task at a time.
- Do not create the next fix issue while any previous fix issue is open,
  in progress, blocked, in review, or waiting for merge.
- Each fix task must use its own Paperclip issue and its own reviewable branch
  or Paperclip worktree branch.
- After each fix merges and the blocker issue is closed, wake the walker issue.
  `CXCTO` then updates this file before creating the next fix issue.
- Native macOS Neo4j is the target substrate. Do not reintroduce Docker Neo4j.
- iOS-only repair. Do not extract or rebaseline Android repositories.
- Use only dedicated Gimle clone repos under `/Users/Shared/Ios/Gimle-Repos/`.
  Do not read or mutate active developer clones under
  `/Users/Shared/Ios/HorizontalSystems/`.

## Walker state

| Field | Value |
| --- | --- |
| Walker issue | `GIM-1611` / `c3af6f53-340b-4aa0-a080-83f6a2850b33` |
| Walker assignee | `CXCTO` |
| Current task | `fix-4` |
| Active blocker issue | `none` |
| Last completed task | `fix-3` |
| Queue mode | strict sequential |
| Allowed team | CX/Codex only |
| Source spec | `docs/superpowers/specs/2026-06-11-broken-ios-extractors-repair.md` |

## Walker control loop

When `CXCTO` receives control of the walker issue:

1. Read this roadmap and the source spec.
2. Check `Active blocker issue`.
3. If `Active blocker issue` is not `none`, read that issue first.
   - If it is still executable, blocked, in review, or waiting for merge, do
     not create another task.
   - If it is closed/merged, update the matching row below to `done`, write
     commit/PR/CI evidence, clear `Active blocker issue`, and continue.
4. Select only the first `todo` task after `Last completed task`.
5. Update this roadmap in git:
   - set `Current task` to that `fix-N`;
   - set that row to `selected`;
   - leave all later tasks as `todo`;
   - commit and push the roadmap update.
6. Create one new Paperclip issue for that selected task.
7. Patch the walker issue to `blocked` with the new issue in
   `blockedByIssueIds`.
8. Set `Active blocker issue` to the new issue number/id in this roadmap,
   commit and push the roadmap update.
9. Wake the new issue with a direct mention to the assigned CX agent.
10. Do not wake or start any later task until the active blocker is done.

After the active blocker finishes:

1. Wake the walker issue with a direct mention to `CXCTO`.
2. `CXCTO` verifies merge/CI/evidence.
3. `CXCTO` marks the completed task `done` here.
4. `CXCTO` selects the next `todo` task using the same loop.

## Paperclip issue template for fix tasks

Title format:

```text
GIM-XXXX fix-N - <short task title>
```

Required description sections:

- Source of truth: this roadmap path and source spec path.
- Sequential lock: state that no other `fix-*` task may run concurrently.
- Scope: copy only the task-specific scope from the table below.
- Acceptance criteria: copy only the task-specific acceptance criteria.
- Verification: include targeted tests and any live native Neo4j checks.
- Handoff: use only CX roles and direct `agent://` mentions from the Codex
  roster.

The new issue must become the single blocker of the walker issue before the
task starts.

## Task queue

| Task | Status | Blocker issue | Owner | Scope | Acceptance criteria |
| --- | --- | --- | --- | --- | --- |
| fix-1 | done | GIM-1612 / 8a2e4437-53a5-4392-95d8-ded7f066f487 | CXCTO -> CX implementer | Persist extractor outcome contract across `extractors/cypher.py`, `memory/cypher.py`, runner `_finalize`, `IngestRunResult`, bundle state, and bundle counters. Decide and document `success=true` plus explicit `outcome` semantics for `MISSING_INPUT`/`NOT_APPLICABLE`. | Every `IngestRun` from both Cypher paths stores `outcome`, `message`, and `next_action`; bundle responses separate `members_ok`, `members_missing_input`, `members_not_applicable`, and `members_failed`; focused runner/bundle tests pass. |
| fix-2 | done | GIM-1615 / 0f3c0311-58fe-4981-97c3-f7484f039007 | CXCTO -> CX implementer | Harden cheap incorrect default-OK paths in extractors without doing deep graph repairs yet: `arch_layer`, `code_ownership`, `git_history`, and `cross_module_contract` diagnostics. | Skipped/no-input/no-baseline/correlation-failure paths return explicit `ExtractorOutcome`; persisted runs no longer show misleading green OK for missing input or skipped work; targeted unit tests assert outcomes. |
| fix-3 | done | GIM-1617 / 29f9b2c3-8c13-4797-88d2-1fd9292c660a | CXCTO -> CX implementer | Verify and test already-fixed `reactive_dependency_tracer` and `hot_path_profiler`; do not rewrite their core logic unless verification finds a real regression. | Missing `reactive_facts.json` persists `MISSING_INPUT`; absent profile traces persist `NOT_APPLICABLE` or `MISSING_INPUT`; live `Project.expected_profile` values are checked for app projects; regression tests assert outcomes. |
| fix-4 | selected | none | CXCTO -> CX implementer | Fix `git_history` commit identity from global `Commit(sha)` to project-scoped identity, with composite constraint migration and controlled purge for stale old groups. | Per-project commit counts are close to `git rev-list --count HEAD` for each iOS repo; shared SHAs can exist for multiple projects; old groups such as `project/uw-ios-baseline` no longer pollute counts; migration tests pass. |
| fix-5 | todo | none | CXCTO -> CX implementer | Fix `code_ownership` clean rebaseline behavior: purge/invalidate project-scoped stale checkpoints and prevent `no_change` before baseline `OwnershipFileState` exists. | All seven iOS repos write `OwnershipFileState` on clean rebaseline; no repo returns `no_change` before a baseline exists; rebaseline orchestration explicitly handles `OwnershipCheckpoint`. |
| fix-6 | todo | none | CXCTO -> CX implementer | Complete `public_api_surface` artifact path for interface-capable SwiftPM kits on the dev Mac; keep app projects `NOT_APPLICABLE` unless a deliberate public API artifact exists. | SwiftPM kits with generated `.swiftinterface` write `PublicApiSurface`/`PublicApiSymbol`; missing artifacts persist `MISSING_INPUT` with `next_action`; `uw-ios-app` is explicitly `NOT_APPLICABLE` unless a real app API artifact is introduced. |
| fix-7 | todo | none | CXCTO -> CX implementer | Repair `arch_layer` iOS module graph using SCIP and/or Xcode target inputs instead of relying only on root `Package.swift`/Gradle shape. | Every iOS repo has meaningful module/file graph data; `uw-ios-app` module count is materially greater than zero; module dependency and containment edges are explainable from SCIP or Xcode evidence. |
| fix-8 | todo | none | CXCTO -> CX implementer | Repair `cross_module_contract` Swift symbol correlation by bridging `.swiftinterface` FQNs to SCIP/Tantivy descriptor qualified names. | GIM-1603 baseline snapshots remain; real `CONSUMES_PUBLIC_SYMBOL` edges appear when consumers exist; zero consumer edges are distinguishable from correlation failure; tests include mismatched Swift name formats. |
| fix-9 | todo | none | CXCTO -> CX implementer | Repair `cross_repo_version_skew`: read canonical bundle `:CONTAINS` relationships and add declared-constraint skew detection in addition to resolved-version skew. | Bundles created by canonical registration are processed; resolved-version and declared-constraint skew are reported; tests use real bundle CRUD shape, not only synthetic `:HAS_MEMBER`. |
| fix-10 | todo | none | CXCTO -> CX implementer | Run full sequential clean rebaseline on the seven dedicated iOS repos and write the numeric completion report. | All extractor outcomes and per-project counts are recorded; broken/partial extractors show real numbers or explicit `MISSING_INPUT`/`NOT_APPLICABLE`; report includes native Neo4j evidence, benchmark timing, and sanity queries. |

## Completion evidence

| Task | Evidence |
| --- | --- |
| fix-1 | `GIM-1612` done. PR #437 merged to `develop` at merge commit `e6477a74cedcdc29bb066bc6d44eb5454e30b3b2` with exact head `44d1eb4caa85f075649ed325150a86d570b2c3a6`; Paperclip CR approval comment `3567bd33-8218-4b13-bfe5-a209d6ade336`; exact-head QA smoke comment `072940b8-3cea-459d-8dd6-945ccf7b29c4`; required checks `check`, `detect-changes`, `submodule-drift-check`, `lint`, `test`, `typecheck`, and `docker-build` passed. |
| fix-2 | `GIM-1615` done. PR #439 merged to `develop` at merge commit `86cfaee8d521dc3f92f9b70cd2743e7cd1c73ae9` with exact head `c85d334a10699f39cde524e519f808419b43ae7b`; Paperclip CR approval comment `4e9c270c-03cd-4b89-a816-0ff20a5dee95`; QA PASS comment `fc3f4789-37ee-49f1-8d93-8e5da3aec483`; required checks `check`, `detect-changes`, `submodule-drift-check`, `lint`, `test`, `typecheck`, and `docker-build` passed. |
| fix-3 | `GIM-1617` done. Verification-only task with no PR/merge action; CTO closure comment `6c31fc5f-c00d-46a9-be46-fbaa45a2eecb`; QA verification comment `a2d96aab-a531-4a0d-a56b-cb52ee37c22d`; architectural approval comment `73064b4d-3cbe-4b53-97d0-3e05fcaf505f`; mechanical review comment `6c42db11-78c0-456f-9470-5cbcb7a0b40e`; QA evidence covered missing `reactive_facts.json` as `MISSING_INPUT`, hot-path `NOT_APPLICABLE`/`MISSING_INPUT`, live `Project.expected_profile`, and live Neo4j extractor verification. |

## Final acceptance for the walker

- All `fix-1` through `fix-10` rows are `done`.
- No walker-created blocker issue remains open.
- The final rebaseline report shows all intended iOS extractors either produce
  real graph data or explicit, persisted non-OK outcomes with messages and
  next actions.
- The report proves the run used the seven dedicated iOS clone repos under
  `/Users/Shared/Ios/Gimle-Repos/`.
- The report proves native macOS Neo4j was used.
- There is no evidence of Claude-side role assignment or parallel fix tasks.
