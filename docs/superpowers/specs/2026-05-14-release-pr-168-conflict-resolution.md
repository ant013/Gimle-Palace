# Release PR #168 conflict resolution

**Date:** 2026-05-14
**Branch:** `fix/GIM-283-release-conflicts`
**Target PR:** GitHub PR #168, `develop -> main`
**Status:** spec for review before implementation

## Problem

GitHub marks release PR #168 (`develop -> main`) as `CONFLICTING` / `DIRTY`.
The release branch `origin/develop` currently includes the completed GIM-283
series and follow-up fixes through `e182a32`, but it cannot be merged into
`origin/main` (`568888a`) without manual conflict resolution.

`git merge-tree --name-only origin/main origin/develop` reports conflicts across
three broad areas:

- Audit pipeline and extractor code under `services/palace-mcp/src/palace_mcp`.
- Watchdog code and tests under `services/watchdog`.
- Paperclip fragments, generated dist files, assembly inventory/baselines, and
  the `paperclips/fragments/shared` submodule.

## Assumptions

- `develop` is the integration branch for the release train.
- The goal is to make the existing release PR mergeable, not to change the
  functional scope of GIM-283 or add new audit behavior.
- Generated Paperclip files should match the repo's generator output after the
  conflict is resolved, rather than hand-edited conflict-marker removal.
- The `paperclips/fragments/shared` submodule pointer must be resolved
  deliberately and verified against the generated assembly outputs.
- Existing untracked local files (`.serena/`, `services/watchdog/.coverage`) are
  unrelated and must not be committed.

## Scope

In scope:

- Create a conflict-resolution branch from `origin/develop`.
- Merge `origin/main` into that branch to reproduce the same conflict GitHub sees.
- Resolve conflicts manually, preserving the GIM-283 audit changes from
  `develop` while keeping any `main`-only release metadata that is still valid.
- Resolve the `paperclips/fragments/shared` submodule pointer intentionally.
- Regenerate or validate Paperclip dist artifacts if the repository tooling
  supports it.
- Run focused validation for the touched code paths.
- Push the resolved branch and use it to unblock PR #168, either by merging the
  resolution into `develop` or by updating the release PR strategy as agreed.

Out of scope:

- New feature work beyond conflict resolution.
- Reworking GIM-283 behavior.
- Deleting stale feature branches.
- Cleaning unrelated local files or coverage artifacts.

## Affected Areas

High-risk conflict groups from the dry merge:

- `services/palace-mcp/src/palace_mcp/audit/*`
- `services/palace-mcp/src/palace_mcp/audit/templates/*`
- `services/palace-mcp/src/palace_mcp/extractors/*`
- `services/palace-mcp/src/palace_mcp/memory/*`
- `services/palace-mcp/tests/audit/*`
- `services/palace-mcp/tests/extractors/*`
- `services/watchdog/src/gimle_watchdog/*`
- `services/watchdog/tests/*`
- `paperclips/fragments/**`
- `paperclips/dist/**`
- `paperclips/assembly-inventory.json`
- `paperclips/bundle-size-baseline.json`
- `paperclips/fragments/shared` submodule

## Resolution Strategy

1. Reproduce the conflict with a real `git merge origin/main` on the
   conflict-resolution branch.
2. Resolve source-code conflicts by reviewing both sides and keeping the
   semantically newer `develop` behavior unless `main` contains release-only
   changes absent from `develop`.
3. Resolve Paperclip generated artifacts from source fragments where possible;
   if regeneration is available, regenerate and compare instead of manually
   editing generated files.
4. Resolve the submodule pointer only after checking which commit is expected by
   `develop` and whether `main` contains a newer required pointer.
5. Keep the final commit limited to conflict-resolution changes.

## Acceptance Criteria

- PR #168 no longer reports merge conflicts after the resolution lands.
- No conflict markers remain in the repository.
- The final diff contains only merge-resolution changes needed for `main` /
  `develop` convergence.
- GIM-283 audit behavior remains present on the resolved branch.
- Watchdog changes merged after `main` remain present.
- Paperclip dist artifacts and submodule pointer are internally consistent.
- Unrelated local files are not committed.

## Verification Plan

- `git status --short --branch`
- `rg -n '<<<<<<<|=======|>>>>>>>'`
- Targeted Palace MCP tests for audit renderer/discovery/fetcher/run paths.
- Targeted extractor tests for conflicted extractors.
- Targeted watchdog tests for conflicted watchdog modules.
- Paperclip validation/build command if available in the repo.
- `gh pr view 168 --json mergeable,mergeStateStatus,statusCheckRollup`

## Open Questions

- Should the resolution be merged into `develop` directly, or should PR #168 be
  retargeted/recreated from this conflict-resolution branch?
- Which `paperclips/fragments/shared` submodule commit is canonical for this
  release: the pointer on `main`, the pointer on `develop`, or a newer commit
  that needs to be fetched from the submodule remote?
