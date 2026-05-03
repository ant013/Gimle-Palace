# Paperclip Shared Codebase Memory

## Summary

Claude and CX/Codex Paperclip teams must use isolated worktrees for execution, but they should share confirmed codebase findings through one canonical `codebase-memory` project namespace.

This spec defines the shared memory policy and the minimum instruction/config changes needed so both teams can read and write the same repository knowledge without mixing dirty worktree state.

## Assumptions

- `develop` is the integration branch for Gimle-Palace.
- Claude and CX/Codex teams may run in separate worktree roots, for example:
  - `/Users/Shared/Ios/worktrees/claude/Gimle-Palace`
  - `/Users/Shared/Ios/worktrees/cx/Gimle-Palace`
- `serena` remains worktree-local: it should activate the current agent `cwd`.
- `codebase-memory` is the shared knowledge layer: it should use a canonical project namespace independent of the current worktree path.
- Shared memory findings are useful only when they include enough provenance to distinguish canonical repository facts from branch-local observations.

## Goals

- Make Claude and CX/Codex agents share codebase findings through one `codebase-memory` project namespace.
- Preserve worktree isolation for files, branches, uncommitted changes, and runtime execution.
- Prevent agents from treating another team's dirty worktree as project truth.
- Require provenance on memory writes so future agents can judge whether a finding is canonical or provisional.
- Keep existing Claude behavior intact except for the added shared-memory discipline.

## Non-Goals

- Do not merge Claude and CX/Codex worktrees.
- Do not change agent adapter types or models.
- Do not force `serena` to use a shared workspace.
- Do not auto-ingest uncommitted worktree changes into shared memory.
- Do not redesign `codebase-memory` storage internals unless discovery proves a namespace alias is impossible through config/instructions.

## Affected Areas

- `paperclips/fragments/shared/**`
  - Add a shared fragment for team worktree isolation and shared codebase-memory policy, or extend the existing worktree discipline fragment if one already owns this rule.
- `paperclips/fragments/codex/**`
  - Add Codex-specific runtime wording only if needed to name the CX workspace root.
- `paperclips/roles/**`
  - Claude bundles should include the shared policy without replacing Claude-only skills/workflows.
- `paperclips/roles-codex/**`
  - Codex bundles should include the same shared policy plus Codex runtime wording.
- `paperclips/build.sh`
  - No expected change unless a new fragment include path requires build support.
- `paperclips/hire-codex-agents.sh`
  - May need default workspace root alignment after the worktree-isolation slice.
- Live Paperclip agent configuration
  - May need `adapterConfig.cwd` patch in a separate approved implementation step.

## Required Behavior

### Worktree Isolation

Agents must execute only inside their assigned team/issue worktree.

- Claude agents use the Claude team worktree root.
- CX/Codex agents use the CX team worktree root.
- Agents must not read uncommitted files from another team's worktree as evidence.
- Agents must not switch branches in a shared or foreign worktree.
- Branch switching is allowed only in a dedicated idle worktree owned by that team/issue.

### Shared `codebase-memory` Namespace

All teams must use one canonical `codebase-memory` project namespace for Gimle-Palace.

Recommended canonical name:

```text
Gimle-Palace
```

If the current `codebase-memory` service only exposes path-derived project IDs, implementation must add a documented alias/mapping so these worktrees resolve to the same memory project:

```text
/Users/Shared/Ios/worktrees/claude/Gimle-Palace -> Gimle-Palace
/Users/Shared/Ios/worktrees/cx/Gimle-Palace     -> Gimle-Palace
/Users/Shared/Ios/Gimle-Palace                  -> Gimle-Palace
```

### Memory Write Provenance

Every agent-written finding in shared `codebase-memory` must include:

- issue identifier, when applicable;
- branch name;
- commit SHA, when available;
- source path or symbol, when applicable;
- status: `canonical` or `provisional`;
- short evidence note explaining how the finding was verified.

Use `canonical` only for facts grounded in `origin/develop`, merged commits, or committed artifacts that are expected to survive the current branch.

Use `provisional` for branch-local discoveries, unmerged PR findings, or observations that depend on a specific issue worktree.

### Read Policy

Agents may use shared `codebase-memory` findings from either team, but must treat provenance as load-bearing:

- `canonical` findings can guide implementation decisions.
- `provisional` findings can guide investigation, but require local verification before implementation.
- Findings without branch/commit/status metadata must be treated as hints, not truth.

### MCP Division Of Responsibility

- `codebase-memory`: shared repository knowledge and cross-team findings.
- `serena`: current worktree navigation, symbols, diagnostics, and edits.
- `context7`: shared external documentation lookup.
- `playwright`: shared browser capability, but agents must coordinate ports/dev servers through issue comments or team-specific runtime config.

## Acceptance Criteria

- A shared instruction fragment exists that explicitly defines:
  - worktree-local execution;
  - shared `codebase-memory` namespace;
  - `serena` as current-worktree local;
  - provenance requirements for memory writes.
- Claude target bundles still preserve Claude-only references such as `CLAUDE.md` and Claude skill names where they were intentionally present.
- Codex target bundles reference `AGENTS.md` and CX/Codex role names where applicable.
- Generated Claude and Codex bundles both contain the shared memory policy.
- Codex target validation still passes with no Claude-only leakage.
- Existing Paperclip instruction validation passes.
- Live deployment, if performed in this slice, confirms at least one CX agent can read/write the canonical shared `codebase-memory` namespace without using the Claude worktree.

## Verification Plan

Before implementation:

1. Confirm the active branch starts from `origin/develop`.
2. Inspect current `codebase-memory` project naming behavior for the three relevant worktree paths.
3. Decide whether namespace sharing is instruction-only or requires service/config aliasing.

After implementation:

1. Build both targets:
   ```bash
   ./paperclips/build.sh --target claude
   ./paperclips/build.sh --target codex
   ```
2. Run instruction validation:
   ```bash
   python3 paperclips/scripts/validate_instructions.py
   ./paperclips/validate-codex-target.sh
   ```
3. Run paperclip tests:
   ```bash
   services/palace-mcp/.venv/bin/pytest -q paperclips/tests/test_validate_instructions.py
   ```
4. Check generated bundles for policy presence:
   ```bash
   rg "Shared Codebase Memory|canonical.*codebase-memory|provisional" paperclips/dist paperclips/dist/codex
   ```
5. If live runtime is included, create a CX smoke issue that asks the agent to report:
   - current `cwd`;
   - active `serena` worktree context;
   - canonical `codebase-memory` project namespace;
   - one read or write attempt with provenance metadata.

## Rollout Plan

1. Add or update shared instruction fragment.
2. Wire the fragment into Claude and Codex role bundles.
3. If needed, add codebase-memory namespace alias/config support.
4. Rebuild and validate bundles locally.
5. Deploy Codex bundles first and smoke with CXCTO or CXCodeReviewer.
6. Deploy Claude bundles after confirming no Claude-target semantic regressions.

## Risks

- If `codebase-memory` keys projects strictly by path, instructions alone will not create shared memory. Implementation must add aliasing or canonical project mapping.
- If agents write provisional branch findings without provenance, future agents may treat stale branch-local observations as repository truth.
- If `serena` is pointed at a shared root instead of the current worktree, agents may inspect the wrong branch.
- If Playwright/dev server ports are shared without coordination, UI smoke tests can interfere across teams.

## Open Questions

- What exact project identifier does the live `codebase-memory` MCP expose for `/Users/Shared/Ios/Gimle-Palace` today?
- Does `codebase-memory` already support project aliases, or do we need to add a small mapping layer?
- Should the canonical namespace be exactly `Gimle-Palace`, or should it match the existing indexed project id to avoid migration?
- Should memory writes be done through a dedicated helper command/template so provenance metadata is consistent across agents?
