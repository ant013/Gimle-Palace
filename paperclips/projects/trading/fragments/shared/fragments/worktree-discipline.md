<!-- derived-from: paperclips/fragments/shared/fragments/worktree-discipline.md @ shared-submodule 285bf36 -->
<!-- on shared advance, manually diff and re-derive -->
<!-- Trading integration branch is `main` (no `develop`); QA stage renamed for Trading chain -->

## Worktree discipline

Paperclip creates a git worktree per issue. Work only inside it:

- `cwd` at wake = worktree path. Never `cd` into primary repo.
- No cross-branch git (`checkout main`, `rebase` from main repo).
- Commit/push/PR — all from the worktree.
- Parallel agents in separate worktrees; don't read neighbors' files (may be mid-work).
- Post-merge — paperclip cleans worktree itself; don't `git worktree remove` manually.

## Shared codebase memory

Worktree isolation ≠ memory isolation. Trading agents share code knowledge:

- `{{mcp.tool_namespace}}.code.*` / codebase-memory with project `{{CODEBASE_MEMORY_PROJECT}}` for indexed search/architecture/impact.
- `serena` only for current worktree + branch state.
- Durable findings: write via `{{mcp.tool_namespace}}.memory.decide(...)`, read via `{{mcp.tool_namespace}}.memory.lookup(...)`.
- Each finding needs provenance: issue id, branch, commit SHA, source path/symbol, `canonical|provisional`, evidence.
- `canonical` = grounded in `origin/main` or merged commits. `provisional` = branch-local hints needing local verification.
- Never treat other team's uncommitted files as project truth — share via commits/PRs/comments/`{{mcp.tool_namespace}}.memory`.

## Cross-branch carry-over forbidden

No cherry-pick / copy-paste between parallel slice branches. If Slice B needs Slice A, declare `depends_on: A` in spec, rebase on main after A merges. CR enforces: every changed file must be in slice's declared scope.

Why: {{evidence.worktree_discipline_issue_pair}}.

## QA: restore checkout to main after Phase 6

Before run exit, on iMac:

    git switch main && git pull --ff-only

Verify `git branch --show-current` = `main`. Don't `cd` into another team's checkout — Trading has its own root at `/Users/Shared/Trading/repo`.

Why: team checkouts drive their own deploys/observability. {{evidence.graphiti_mock_issue}}.
