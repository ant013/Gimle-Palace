# GIM-775 Plan: git_history group_id regression

## Goal

Fix the `git_history` extractor so every project-scoped node it creates has `group_id`, allowing APOC `require_group_id` to pass on projects with real history and unblocking `hotspot`.

## Assumptions

- `ExtractorRunContext.group_id` is the canonical scope and is passed to `git_history` writer calls as `project_id`.
- `services/palace-mcp/src/palace_mcp/extractors/foundation/scope_tagging.py` is not present in this checkout. If a concurrent GIM-756 branch introduces `ScopeTaggedWriter`, use it; otherwise the minimum safe fix is to set `group_id` in the existing git history Cypher writer.
- Scope is limited to `git_history` write paths and the cascading `hotspot` smoke. Do not refactor unrelated extractors.
- The working tree already contains uncommitted changes in `git_history/neo4j_writer.py` and `test_git_history_neo4j_writer.py`; verify and adapt them instead of overwriting blindly.

## Acceptance Criteria

- `Author`, `Commit`, `File`, `PR`, and `PRComment` nodes created by `git_history` have `group_id = ctx.group_id`.
- Existing matched git-history nodes get `group_id` backfilled with `coalesce(existing, ctx.group_id)` where the writer touches them.
- Unit tests under `tests/extractors/unit/test_git_history_neo4j_writer.py` assert every git-history node-creating Cypher path sets `group_id`.
- `palace.ingest.run_extractor(name='git_history', project='uw-ios-app')` succeeds with `nodes_written > 1000`.
- `MATCH (c:Commit) WHERE c.group_id IS NULL RETURN count(c)` returns `0` after the uw-ios-app run.
- `palace.ingest.run_extractor(name='hotspot', project='uw-ios-app')` succeeds after git_history.

## Steps

- [x] Implement the minimum writer fix
  - Owner: `CXPythonEngineer`
  - Affected paths:
    - `services/palace-mcp/src/palace_mcp/extractors/git_history/neo4j_writer.py`
    - `services/palace-mcp/tests/extractors/unit/test_git_history_neo4j_writer.py`
  - Details:
    - Ensure `_MERGE_AUTHOR_CYPHER`, `_MERGE_COMMIT_CYPHER`, `_MERGE_TOUCHED_CYPHER`, PR write Cypher, and PR comment write Cypher set `group_id`.
    - Keep existing identity keys, relationship semantics, and async driver call structure unchanged.
    - If `ScopeTaggedWriter` exists when implementing, route node creation through it; if not, explicit Cypher `group_id` assignment is the approved minimal fix for this blocker.
  - Check:
    - `uv run pytest services/palace-mcp/tests/extractors/unit/test_git_history_neo4j_writer.py`
  - Status:
    - Verified in the isolated live smoke recorded on 2026-05-22; clean `origin/develop` already contains the writer-side `group_id` fix.

- [x] Add the regression guard requested by the issue
  - Owner: `CXPythonEngineer`
  - Depends on: Step 1
  - Affected paths:
    - `services/palace-mcp/tests/extractors/unit/test_git_history_neo4j_writer.py`
  - Details:
    - Add a table-driven assertion that every git-history node label written by this module has `group_id` assignment in its Cypher.
    - Keep the guard local to `git_history`; broader extractor coverage belongs to GIM-756.
  - Check:
    - `uv run pytest services/palace-mcp/tests/extractors/unit/test_git_history_neo4j_writer.py`

- [ ] Verify the production cascade on a full-history checkout
  - Owner: `CXQAEngineer`
  - Depends on: Step 2
  - Affected paths:
    - No new files expected unless a reusable smoke command already exists.
  - Details:
    - Run the smallest available live command/API path for `palace.ingest.run_extractor(name='git_history', project='uw-ios-app')`.
    - Query orphan commits with `MATCH (c:Commit) WHERE c.group_id IS NULL RETURN count(c)`.
    - Run `palace.ingest.run_extractor(name='hotspot', project='uw-ios-app')`.
  - Check:
    - Evidence comment includes exact commands and outputs for git_history success, orphan commit count, and hotspot success.
  - Status:
    - Isolated local smoke already passed with `success=true`, `orphan_commits=0`, and `hotspot` success.
    - This workspace's `uw-ios-app` checkout is shallow, so the `nodes_written > 1000` acceptance proof still needs the production iMac or another full-history checkout.

## Review Gates

- Implementation: `CXPythonEngineer`
- Mechanical review: `CXCodeReviewer`
- Live smoke evidence: `CXQAEngineer` if the implementer cannot access the production iMac path directly; otherwise include the live evidence in the implementation handoff.
- Merge: `CXCTO` only after review approval, QA/live evidence, and green required checks.

## Branch and PR

- Branch: use the active GIM-775 feature branch or create `feature/GIM-775-git-history-group-id`.
- PR target: `develop`.
- PR body must reference this plan file and include `## QA Evidence`.
