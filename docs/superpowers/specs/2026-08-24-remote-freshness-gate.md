# Remote freshness gate for Palace incremental analysis

## Goal

Prevent an incremental Palace run from being reported as current when its local
checkout is behind its configured Git upstream.

## Assumptions

- Palace indexes the local working tree, not a remote Git server.
- Fetching remote refs is safe; changing a checkout is not automatically safe.
- A dirty tracked working tree must never be fast-forwarded automatically.

## Scope

- Add a narrow remote-freshness probe for registered Git projects.
- Surface local and upstream commit identity, upstream divergence, and a
  checked-at timestamp in project overview and project-analysis results.
- Gate incremental execution when a checkout is behind upstream: return a
  structured `remote_checkout_behind` status with an operator next action.
- Add the native macOS runbook procedure: fetch, inspect divergence, use
  `merge --ff-only` only on a clean tracked tree, regenerate SCIP when Swift
  source changes, then run incremental analysis.
- Add unit tests for equal, behind, unavailable-upstream, and dirty-tree cases.

## Non-scope

- Automatic `pull`, merge, rebase, branch switching, or remote writes.
- Altering source-index freshness semantics: `indexed_commit` remains a commit
  of the local tree that was actually indexed.
- A full refresh of global extractors.

## Affected areas

- `services/palace-mcp/src/palace_mcp/git/` — bounded Git remote probe.
- `services/palace-mcp/src/palace_mcp/project_analyze.py` — preflight gate and
  structured result.
- `services/palace-mcp/src/palace_mcp/memory/project_tools.py` and
  `memory/schema.py` — overview metadata.
- `services/palace-mcp/tests/` — probe, orchestration, and overview contracts.
- `docs/runbooks/native-macos-palace-mcp.md` — operator workflow.

## Design

The primary local-freshness contract remains `indexed_commit` versus local
`HEAD`. Before planning an incremental run, Palace additionally runs
`git fetch <remote> --prune` and reads the configured branch/upstream. It never
updates the checkout itself.

If `HEAD` is behind upstream, Palace does not issue a no-op incremental result.
It returns an explicit blocked status containing local/upstream SHAs and commit
count. The runbook directs the operator to verify a clean tracked tree, run a
fast-forward-only update, regenerate Swift SCIP if source changed, then retry.

If no upstream is configured or fetch fails, Palace reports remote freshness as
`unknown` and does not claim GitHub/current-remote freshness; local incremental
behavior remains available with an explicit warning.

## Acceptance criteria

1. A checkout behind its upstream cannot produce a misleading no-change
   incremental result.
2. Palace never changes a repository checkout automatically.
3. Overview distinguishes local index freshness from remote freshness.
4. A clean, equal local/upstream checkout preserves the current incremental
   path.
5. The native runbook provides an executable safe recovery sequence, including
   dirty-tree refusal and Swift SCIP regeneration.

## Verification

- Unit tests for remote probe states and the project-analysis gate.
- Unit tests for overview serialization of remote freshness metadata.
- Run the targeted Palace test modules, then formatting/type checks required by
  the service.
- Manual dry run against a local Git fixture with an upstream four commits
  ahead; confirm no checkout mutation and a structured blocked response.

## Risks and open questions

- Fetch requires network and may be slow; probe timeout and `unknown` state
  must be explicit.
- Multi-remote projects need an explicit policy; MVP uses the branch's tracked
  upstream only.
- The exact public error/status field names will follow the existing
  `project_analyze` envelope conventions during implementation.
