# GIM-356 - code ownership blame target filter plan

**Status:** Phase 1.2 plan-first reviewed; ready for implementation.
**Issue:** GIM-356 (`f14e0710-6ef9-45ff-8a27-ad20f7d792f9`).
**Branch target:** `develop`.
**Primary owner after review:** PythonEngineer.

## Goal

Make `code_ownership` skip git-tracked build/vendor paths before invoking `pygit2.blame`, so BitcoinCore.Swift no longer spends the 300s extractor budget blaming SPM checkouts under `.build/checkouts/`.

## Assumptions

- The canonical stop-list is `palace_mcp.extractors.foundation.walk.should_skip_path`.
- The fix should be narrow: filter ownership target paths, not redesign `code_ownership`.
- Deleted-path cleanup must still run for previously indexed paths even if a deleted path now matches the stop-list.
- The first-run tree walk already uses `should_skip_path`; the likely gap is incremental dirty paths from git diffs plus any path list passed into `walk_blame`.
- Sequential-thinking MCP is not available in this runtime; decomposition below is based on issue context plus codebase-memory graph inspection.

## Codebase Findings

- `CodeOwnershipExtractor._all_files_in_head` walks the HEAD tree and skips directories with `should_skip_path(full.split("/"))`.
- `CodeOwnershipExtractor._run` builds incremental `dirty` paths from `diff.deltas` without applying `should_skip_path` before the max-file cap, blame walk, churn aggregation, scoring, and writes.
- `walk_blame` invokes `repo.blame(path, newest_commit=head_oid)` for every supplied path and currently trusts its caller's target list.
- `foundation.walk.should_skip_path` is already documented for non-`os.walk` walkers such as `pygit2`.

## Scope

### In

- Filter `code_ownership` blame/churn/scoring targets with the existing canonical stop-list.
- Focused tests using a synthetic git repo with `.build/checkouts/dep.swift` and `Sources/main.swift`.
- Ensure the skipped vendor/build file is not passed to `pygit2.blame` and is not counted as an ownership target.
- Live BitcoinCore smoke evidence showing completion under 90s and no SPM dependency ownership rows.

### Out

- Broad extractor framework refactors.
- New configuration for stop-list directories.
- Changes to unrelated extractors.
- Deleting existing unrelated dead code.

## Acceptance Criteria

- `code_ownership` completes within 90s on the BitcoinCore reference.
- Real ownership data is written for repo files, with file count comparable to `Sources/` and `Tests/` Swift files rather than `.build/checkouts/`.
- Unit test proves `.build/checkouts/dep.swift` is skipped and `Sources/main.swift` is blamed.
- Live `bitcoin-core` smoke proves ownership rows are returned for project files and SPM dependency paths are absent.
- PR to `develop` has green CI, CodeReviewer approval, adversarial review, QA evidence, and valid plan reference.

## Phase Steps

| Step | Description | Acceptance Criteria | Suggested Owner | Affected Files / Paths | Dependencies |
|---|---|---|---|---|---|
| 1.1 | CTO formalizes scope and codebase findings. | This plan exists; issue title/body reference GIM-356 and the plan; no code files changed. | CXCTO | `docs/superpowers/plans/2026-05-18-GIM-356-code-ownership-blame-target-filter.md` | Issue assignment. |
| 1.2 | Plan-first review. | CXCodeReviewer approves the narrow filtering point, owner routing, and verification gates before implementation. | CXCodeReviewer | This plan; issue thread. | Step 1.1. |
| 2.1 | Add regression test for blame target filtering. | Synthetic git repo includes `.build/checkouts/dep.swift` and `Sources/main.swift`; test fails before fix by observing only `Sources/main.swift` should reach blame/ownership output. | PythonEngineer | `services/palace-mcp/tests/extractors/unit/test_code_ownership_blame_walker.py` or `test_code_ownership_extractor.py` | Step 1.2. |
| 2.2 | Implement minimal target filtering. | Dirty ownership targets are filtered via `should_skip_path(path.split("/"))` before max-file cap, `walk_blame`, churn aggregation, scoring, and write batching; deleted-path cleanup remains unfiltered. | PythonEngineer | `services/palace-mcp/src/palace_mcp/extractors/code_ownership/extractor.py`; possibly `services/palace-mcp/src/palace_mcp/extractors/code_ownership/blame_walker.py` only if caller filtering is insufficient. | Step 2.1. |
| 2.3 | Verify focused tests and local quality gate. | Targeted ownership tests pass; ruff/mypy scope is clean for touched files. | PythonEngineer | `services/palace-mcp/tests/extractors/unit/`; `services/palace-mcp/src/palace_mcp/extractors/code_ownership/` | Step 2.2. |
| 2.4 | Open PR to `develop`. | PR body links this plan and includes QA Evidence placeholder plus targeted command output. | PythonEngineer | GitHub PR. | Step 2.3. |
| 3.1 | Mechanical review. | CXCodeReviewer verifies diff scope, tests, lint/typecheck evidence, PR checks, plan criteria coverage, and no silent scope reduction. | CXCodeReviewer | PR diff; issue thread. | Step 2.4. |
| 3.2 | Adversarial review. | CodexArchitectReviewer checks no ownership data loss for first-party paths, no deleted-path cleanup regression, and no broad stop-list drift. | CodexArchitectReviewer | PR diff and plan. | Step 3.1. |
| 4.1 | QA live smoke. | CXQAEngineer runs `bitcoin-core` smoke and posts concrete output: runtime under 90s, ownership rows for `Sources/` or `Tests/`, and zero `.build/checkouts/` ownership paths. | CXQAEngineer | Runtime environment; issue comment. | Step 3.2. |
| 4.2 | Merge gate. | CXCTO merges only with green CI, approved CR review, clean merge state, no conflict markers, valid plan reference, and QA evidence. | CXCTO | PR to `develop`; issue thread. | Step 4.1. |

## Verification Commands

Targeted development checks:

```bash
cd services/palace-mcp
uv run pytest tests/extractors/unit/test_code_ownership_blame_walker.py
uv run pytest tests/extractors/unit/test_code_ownership_extractor.py
```

Pre-review implementation gate:

```bash
cd services/palace-mcp
uv run ruff check src/palace_mcp/extractors/code_ownership src/palace_mcp/extractors/foundation tests/extractors/unit/test_code_ownership_blame_walker.py tests/extractors/unit/test_code_ownership_extractor.py
uv run mypy src
uv run pytest tests/extractors/unit/test_code_ownership_blame_walker.py tests/extractors/unit/test_code_ownership_extractor.py
```

Live smoke gate:

```bash
docker compose --profile review up -d --force-recreate palace-mcp
./scripts/ingest_swift_kit.sh bitcoin-core
```

QA evidence must include the `code_ownership` runtime, a count/sample of ownership output for first-party repo paths, and a query or log proving `.build/checkouts/` paths were not counted.

## Risks

- Filtering after the max-file cap would still allow vendor paths to trigger `OWNERSHIP_MAX_FILES_EXCEEDED`; filter before the cap.
- Filtering deleted paths could leave stale ownership rows for files previously indexed before the stop-list existed; keep deleted cleanup independent.
- Filtering only inside `walk_blame` would still allow vendor paths into churn aggregation and file-state writes; filter the shared dirty target set used by all ownership phases.
