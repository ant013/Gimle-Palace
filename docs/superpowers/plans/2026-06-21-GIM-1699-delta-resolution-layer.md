# GIM-1699 Plan: delta-resolution layer

Grounded in `origin/develop` at `8a6d51a388c9436835d44d98a96e60b4ecf314f8`.
Authoritative spec: `docs/superpowers/specs/2026-06-21-incremental-global-extractors.md`
section `0.5 PREREQUISITE LAYER — delta resolution`.

## Goal

Add the file-scoped delta-resolution foundation that incremental global
extractors can consume instead of raw changed/removed paths.

## Assumptions

- Implementation branch: `feature/GIM-1699-delta-resolution-layer` cut from
  `origin/develop`; PR targets `develop`.
- Scope is limited to the delta-resolution foundation plus the tests required
  to prove parity for a known commit pair.
- The symbol-writer stale-edge sweep remains the ordering gate; this slice does
  not change writer scheduling.
- Review lane is codex-only: `CXCodeReviewer` ->
  `CodexArchitectReviewer` -> `CXQAEngineer` -> `CXCTO`.

## Acceptance Criteria

- AC-1: changed and removed paths can be resolved into a symbol delta covering
  added, removed, and moved symbols.
- AC-2: changed files can be resolved into an edge delta covering added and
  removed `CALLS`, `REFERENCES`, `EXTENDS`, `CONFORMS_TO`,
  `EXTENSION_OF`, and `EXISTENTIAL_USE` relationships sourced from those files.
- AC-3: changed files can be resolved into seed-flag deltas and public-API
  deltas, including `signature_hash` changes.
- AC-4: the integration parity test compares the resolved delta with an
  independent, fixed expected delta for a known before/after commit pair rather
  than replaying the production diff logic.
- AC-5: the slice remains isolated to the delta-resolution foundation files and
  its tests.

## Work Plan

1. [x] Define snapshot and diff primitives for symbols, edges, seeds, and
   public API rows.
   - Owner: `CXPythonEngineer`.
   - Files: `services/palace-mcp/src/palace_mcp/extractors/foundation/delta_resolution.py`,
     `services/palace-mcp/src/palace_mcp/extractors/foundation/__init__.py`.
   - Acceptance: the foundation can normalize prior and current per-file state
     into comparable snapshots and emit a `ResolvedDelta`.
   - Verification: unit tests cover add/remove/move, seed flips, and
     `signature_hash` changes.

2. [x] Prove file-scoped diff behavior with unit tests.
   - Owner: `CXPythonEngineer`.
   - Files: `services/palace-mcp/tests/extractors/unit/test_delta_resolution.py`.
   - Acceptance: tests cover symbol adds/removes/moves, edge adds/removes,
     seed flips, and public-API adds/removes/changes.
   - Verification: `uv run pytest tests/extractors/unit/test_delta_resolution.py`.

3. [x] Add a real-Neo4j parity fixture for a known commit pair.
   - Owner: `CXPythonEngineer`.
   - Files: `services/palace-mcp/tests/extractors/integration/test_delta_resolution_integration.py`.
   - Acceptance: the expected delta is expressed as a fixed literal derived from
     the known fixture pair, not by duplicating `diff_delta_snapshots`.
   - Verification: `uv run pytest tests/extractors/integration/test_delta_resolution_integration.py -rs`.

4. [x] Package the slice for review.
   - Owner: `CXPythonEngineer`.
   - Acceptance: the PR references this plan and includes a `## QA Evidence`
     section keyed to the review commit SHA.
   - Verification: `gh pr view 491 --json body` shows both the plan reference
     and QA evidence section.

## Verification

From `services/palace-mcp`:

- `uv run ruff check`
- `uv run ruff format --check tests/extractors/integration/test_delta_resolution_integration.py`
- `uv run mypy src/`
- `uv run pytest tests/extractors/unit/test_delta_resolution.py tests/extractors/integration/test_delta_resolution_integration.py -rs`

## Risks

- If the parity test computes its expected delta through the same production
  diff algorithm, the acceptance proof is invalid.
- If delta resolution is consumed before the stale-edge sweep completes for the
  commit, removed-edge deltas can be incomplete.
