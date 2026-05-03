# Paperclip Shared Codebase Memory

## Summary

Claude and CX/Codex Paperclip teams must use isolated worktrees for execution, but they should share confirmed codebase findings through one canonical code-knowledge namespace.

This spec defines the shared memory policy and the minimum instruction/config changes needed so both teams can read the same indexed repository knowledge and write provenance-backed findings without mixing dirty worktree state.

## Assumptions

- `develop` is the integration branch for Gimle-Palace.
- Claude and CX/Codex teams will run in separate team roots, for example:
  - `/Users/Shared/Ios/worktrees/claude/Gimle-Palace`
  - `/Users/Shared/Ios/worktrees/cx/Gimle-Palace`
- `serena` remains worktree-local: it should activate the current agent `cwd`.
- `codebase-memory` graph/search tools are the shared code index layer.
- The existing canonical CM project key is `repos-gimle`; it is already embedded in palace-mcp defaults and role-prime fragments.
- `palace.memory.decide(...)` is the v1 writable path for provenance-backed findings and decisions; upstream CM ADR/write tools are not used in this slice.
- Shared memory findings are useful only when they include enough provenance to distinguish canonical repository facts from branch-local observations.

## Goals

- Make Claude and CX/Codex agents share indexed code findings through the existing `codebase-memory` project `repos-gimle`.
- Make Claude and CX/Codex agents write provenance-backed findings through `palace.memory.decide(...)` so later agents can read them through `palace.memory.lookup(...)`.
- Preserve worktree isolation for files, branches, uncommitted changes, and runtime execution.
- Prevent agents from treating another team's dirty worktree as project truth.
- Require provenance on memory writes so future agents can judge whether a finding is canonical or provisional.
- Keep existing Claude behavior intact except for the added shared-memory discipline.

## Non-Goals

- Do not merge Claude and CX/Codex worktrees.
- Do not change agent adapter types or models.
- Do not force `serena` to use a shared workspace.
- Do not auto-ingest uncommitted worktree changes into shared memory.
- Do not rename or migrate the current CM project from `repos-gimle` to `Gimle-Palace`.
- Do not add upstream codebase-memory write/ADR support in the instruction-only slice.
- Do not redesign `codebase-memory` storage internals unless discovery proves the existing `repos-gimle` contract cannot serve both team roots.

## Affected Areas

- `paperclips/fragments/shared/**`
  - Add a shared fragment for team worktree isolation and shared codebase-memory policy, or extend the existing worktree discipline fragment if one already owns this rule.
- `paperclips/fragments/codex/**`
  - Add Codex-specific runtime wording only if needed to name the CX workspace root.
- `paperclips/roles/**`
  - Claude bundles should include the shared policy without replacing Claude-only skills/workflows.
- `paperclips/roles-codex/**`
  - Codex bundles should include the same shared policy plus Codex runtime wording.
- `services/palace-mcp/**`
  - No expected Slice 1 change. Later slices may add helper tooling only if the existing `palace.memory.decide` path is insufficient.
- `paperclips/hire-codex-agents.sh` and live Paperclip agent configuration
  - Out of scope for Slice 1. Covered by the later worktree/cwd rollout slice.

## Required Behavior

### Worktree Isolation

Agents must execute only inside their assigned team or issue worktree.

- Claude agents use the Claude team root as their default execution root.
- CX/Codex agents use the CX team root as their default execution root.
- If Paperclip creates per-issue worktrees, those worktrees must be under, or explicitly associated with, the owning team root.
- A stable team checkout may exist for deploy/inspection, but issue work must still happen inside the assigned issue worktree when Paperclip provides one.
- Agents must not read uncommitted files from another team's worktree as evidence.
- Agents must not switch branches in a shared or foreign worktree.
- Branch switching is allowed only in a dedicated idle worktree owned by that team/issue.

### Shared `codebase-memory` Namespace

All teams must use the existing canonical `codebase-memory` project namespace for Gimle-Palace.

Canonical CM project:

```text
repos-gimle
```

Operator-facing slug:

```text
gimle
```

Rationale:

- `Settings.palace_cm_default_project` defaults to `repos-gimle`.
- `code_composite._slug_to_cm_project("gimle")` maps to `repos-gimle`.
- Existing role-prime fragments already use `project="repos-gimle"` for `palace.code.*`.

The implementation must not create a new empty `Gimle-Palace` CM project in v1. If worktree path-derived indexing would create separate project keys for team worktrees, implementation must explicitly route reads to `repos-gimle` and document any required alias/backfill in a later runtime slice.

### Writable Findings Path

For v1, agents do not write findings into upstream CM ADR storage. The supported write path is:

```text
palace.memory.decide(...)
```

The supported read paths are:

```text
palace.code.* project="repos-gimle"   # indexed code graph/search/snippets
palace.memory.lookup(...)             # provenance-backed findings and decisions
```

`palace.code.manage_adr` remains disabled and must not be used as a hidden write path.

### Finding Provenance

Every agent-written finding in shared memory must include:

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

- `palace.code.*` / `codebase-memory`: shared indexed repository knowledge under project `repos-gimle`.
- `palace.memory.decide` / `palace.memory.lookup`: shared provenance-backed decisions and findings.
- `serena`: current worktree navigation, symbols, diagnostics, and edits.
- `context7`: shared external documentation lookup.
- `playwright`: shared browser capability, but agents must coordinate ports/dev servers through issue comments or team-specific runtime config.

## Slice Boundaries

### Slice 1: Instruction Policy Only

Scope:

- Add or update shared instruction fragments.
- Wire the policy into Claude and Codex bundles.
- Preserve existing Claude-specific workflows and Codex-specific substitutions.

Out of scope:

- Creating iMac worktree directories.
- Patching live agent `adapterConfig.cwd`.
- Adding CM alias/backfill code.
- Adding new `palace.memory` write APIs.

### Slice 2: Runtime Namespace Helper, If Needed

Only start this slice if Slice 1 discovery proves that instructions plus existing `repos-gimle` routing are insufficient.

Possible scope:

- Add a helper/template for `palace.memory.decide` finding writes.
- Add tests that enforce required provenance fields.
- Add documented alias/config support if path-derived CM projects split the team roots.

### Slice 3: Team Worktree Runtime Rollout

Scope:

- Create team roots on iMac.
- Update `paperclips/hire-codex-agents.sh` default `PAPERCLIP_WORKSPACE`.
- Patch existing live Claude and CX/Codex `adapterConfig.cwd`.
- Smoke both teams with explicit assignment because heartbeat is disabled.

### Slice 4: Deploy And Live Smoke

Scope:

- Rebuild bundles.
- Deploy Codex bundles first.
- Smoke CX agent memory/read policy.
- Deploy Claude bundles after confirming Claude-target text is unchanged except for shared policy additions.

## Acceptance Criteria

- A shared instruction fragment exists that explicitly defines:
  - worktree-local execution;
  - shared `codebase-memory` project `repos-gimle`;
  - `palace.memory.decide` as v1 writable findings path;
  - `serena` as current-worktree local;
  - provenance requirements for memory writes.
- Claude target bundles still preserve Claude-only references such as `CLAUDE.md` and Claude skill names where they were intentionally present.
- Codex target bundles reference `AGENTS.md` and CX/Codex role names where applicable.
- Generated Claude and Codex bundles both contain the shared memory policy.
- Codex target validation still passes with no Claude-only leakage.
- Existing Paperclip instruction validation passes.
- Slice 1 implementation does not patch live `adapterConfig.cwd`.
- Live deployment, if performed in a later slice, confirms at least one CX agent can read `palace.code.* project="repos-gimle"` and write/read a provenance-backed finding through `palace.memory.decide` / `palace.memory.lookup` without using the Claude worktree.

## Verification Plan

Before implementation:

1. Confirm the active branch starts from `origin/develop`.
2. Confirm `repos-gimle` remains the active CM project in:
   - `Settings.palace_cm_default_project`;
   - `code_composite._slug_to_cm_project`;
   - role-prime fragments.
3. Confirm `palace.code.manage_adr` is disabled and `palace.memory.decide` is the intended write path.
4. Decide whether Slice 1 is instruction-only or whether a later Slice 2 helper is required.

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
   python3 -m pytest -q paperclips/tests/test_validate_instructions.py
   ```
   If the local environment requires the palace MCP virtualenv, use:
   ```bash
   services/palace-mcp/.venv/bin/pytest -q paperclips/tests/test_validate_instructions.py
   ```
4. Check generated bundles for policy presence:
   ```bash
   rg "repos-gimle|palace\\.memory\\.decide|provisional" paperclips/dist paperclips/dist/codex
   ```
5. If live runtime is included in a later slice, create a CX smoke issue that asks the agent to report:
   - current `cwd`;
   - active `serena` worktree context;
   - canonical `codebase-memory` project `repos-gimle`;
   - one `palace.code.*` read with `project="repos-gimle"`;
   - one `palace.memory.decide` / `palace.memory.lookup` round trip with provenance metadata.

## Rollout Plan

1. Slice 1: add or update shared instruction fragment.
2. Slice 1: wire the fragment into Claude and Codex role bundles.
3. Slice 1: rebuild and validate bundles locally.
4. Slice 2, only if needed: add helper/alias/config support for shared memory writes.
5. Slice 3: create team roots and patch live `adapterConfig.cwd`.
6. Slice 4: deploy Codex bundles first and smoke with CXCTO or CXCodeReviewer.
7. Slice 4: deploy Claude bundles after confirming no Claude-target semantic regressions.

## Risks

- If implementation accidentally uses `Gimle-Palace` instead of `repos-gimle`, it can create a second empty/partial CM project.
- If `codebase-memory` keys projects strictly by path during indexing, team worktree indexing can split knowledge unless reads are routed back to `repos-gimle` or a later alias/backfill slice is implemented.
- If agents write provisional branch findings without provenance, future agents may treat stale branch-local observations as repository truth.
- If `serena` is pointed at a shared root instead of the current worktree, agents may inspect the wrong branch.
- If Playwright/dev server ports are shared without coordination, UI smoke tests can interfere across teams.

## Open Questions

- Do the iMac team roots need to be stable checkouts, parents for Paperclip issue worktrees, or both?
- Does live Paperclip support per-agent issue worktree placement under team-specific roots, or only `adapterConfig.cwd` stable root selection?
- Should Slice 2 add a dedicated helper command/template around `palace.memory.decide` so provenance metadata is consistent across agents?
- Should live smoke create a temporary `Decision` record or a dedicated `Finding` entity type if one already exists?
