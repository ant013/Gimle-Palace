# Native incremental analysis and worktree hygiene

**Status:** ready for review

**Branch:** `fix/worktree-docker-hygiene`

**Grounded in:** `origin/develop` at
`c634cda4f23075d7e98df3dbeae9271281a55ac1` (fetched 2026-07-24)

## Problem

The 2026-07-24 local disk audit exposed two independent sources of confusion:

1. The active `project analyze` implementation is native-first and does not
   manage Docker unless `--manage-runtime` is passed, but the focused operator
   runbook still describes Docker, port `8080`, compose override generation,
   and Neo4j startup as the default path.
2. Repository rules explain where feature and Paperclip worktrees are created,
   but do not require the creator of an ad hoc task worktree to remove it when
   the task reaches a terminal successful handoff. Old task directories
   therefore remain registered and can retain duplicated virtual environments,
   submodules, and build products.

### Host evidence from the cleanup

Before pruning, Docker contained no Gimle/Palace container and no tagged
Gimle/Palace image. The unused image set was 19 images / 11.59 GB, dominated by
old Medic/Supabase images, plus one untagged Neo4j image of about 536 MB. Docker
build cache was empty. Two Medic volumes totalling about 73.7 MB were preserved.
After unused-image pruning and Docker Desktop space reclamation, `Docker.raw`
fell from about 15 GB to about 4 GB.

This means the large Docker allocation was not produced by the current Gimle
incremental path. The untagged Neo4j image may have come from an older Gimle
Docker workflow or another Neo4j consumer; its provenance cannot be proven
after pruning and must not be asserted as Gimle-owned.

The worktree registry, in contrast, showed both clean pushed task worktrees and
dirty/detached worktrees alongside deliberately persistent primary, runtime,
and Paperclip team workspaces. The missing control is lifecycle classification
and terminal cleanup, not a blanket directory deletion command.

## Assumptions

- Native `palace-mcp` on `http://localhost:8765/mcp` is the default local
  operator runtime.
- Native sync/update inputs come from clean repository copies under
  `/Users/Shared/Ios/Gimle-Repos/HorizontalSystems/`, not product-development
  checkouts, unless the operator explicitly overrides that boundary.
- `project analyze --mode incremental` must reuse that running native service
  and must not start Docker, write a compose override, or mutate compose-only
  environment mappings.
- The legacy iMac/Docker path remains supported, but only when the operator
  explicitly supplies both `--manage-runtime` and
  `--url http://localhost:8080/mcp`.
- A task worktree is ephemeral only when the current session created that exact
  path for the current task. The creator owns its terminal cleanup.
- Primary checkouts, `Gimle-Palace-native`, production checkouts, stable
  `Gimle-Palace-claude` / `Gimle-Palace-cx` roots, and
  `<team_workspace_root>/<AgentName>/workspace/` are persistent.
- `scip_emit_swift/.build`, project SCIP indexes, native service environments,
  and historical data are outside cleanup scope.

## Goals

- Make the native incremental operator path copy-paste correct and explicitly
  free of Docker side effects.
- Keep the legacy Docker path documented without allowing it to be selected
  accidentally.
- Add an ownership-aware exit gate so a coding agent removes its own clean,
  pushed, ad hoc worktree after terminal task completion.
- Fail safe: preserve and report any dirty, unpushed, locked, unknown-owner, or
  persistent worktree instead of forcing deletion.

## Non-goals

- No change to `palace-mcp` runtime behavior; the native/Docker boundary is
  already implemented and covered by tests.
- No broad Docker prune command, Docker Desktop automation, or removal of the
  legacy Docker deployment surface.
- No automated deletion of arbitrary existing worktrees.
- No deletion or modification of persistent Paperclip agent workspaces.
- No change to the `paperclip-shared-fragments` submodule; its persistent
  workspace rule is correct and belongs to a separate repository.
- No cleanup of `.venv`, Swift build products, SCIP output, caches, volumes, or
  source mirrors as part of this repository change.

## Design

### 1. Native incremental analysis is the default

Rewrite `docs/runbooks/project-analyze-operator-path.md` around the current CLI
contract:

- prerequisite: a healthy native MCP at `http://localhost:8765/healthz`;
- target paths: clean source mirrors under
  `/Users/Shared/Ios/Gimle-Repos/HorizontalSystems/`;
- example: `project analyze --mode incremental` without
  `--manage-runtime`;
- expected behavior: use the already running native MCP and emit the report and
  summary only;
- explicit negative invariant: no Docker/Colima startup, no compose override,
  and no compose-only `.env` mutation;
- troubleshooting focuses first on native launchd health and CLI/package
  context.

Move the Docker material into a clearly labelled legacy section. Its command
must include:

```bash
--manage-runtime \
--url http://localhost:8080/mcp
```

The URL is not optional in this section: Docker compose publishes host port
`8080`, while the CLI parser defaults to native port `8765`.

The existing `docs/runbooks/operator-guide.md` is explicitly an iMac Docker
guide. Preserve that boundary and update only its `project analyze` example and
explanation to opt into legacy runtime management and port `8080`.

### 2. Creator-owned ephemeral worktree exit gate

Add one short operational rule to `AGENTS.md`, link/summarize it in `CLAUDE.md`,
and document the full lifecycle in `docs/contributing/branch-flow.md`.

For an ad hoc worktree created by the current task:

1. Keep it while the task is active, awaiting spec approval, or otherwise
   expected to continue.
2. Before terminal cleanup, fetch the remote, remove only generated files
   proven to be owned by the current session, confirm
   `git status --short` is clean, and verify that `HEAD` exactly matches the
   configured upstream:

   ```bash
   git -C <exact-created-path> fetch origin --prune
   test -z "$(git -C <exact-created-path> status --short)"
   test "$(git -C <exact-created-path> rev-parse HEAD)" = \
     "$(git -C <exact-created-path> rev-parse '@{upstream}')"
   ```

   A missing upstream or unequal SHA preserves the worktree.
3. Run cleanup from the owning repository or another directory outside the
   target worktree:

   ```bash
   git -C <owning-repo> worktree remove <exact-created-path>
   ```

4. Never add `--force` and never fall back to `rm -rf` for a general task
   worktree.
5. If Git refuses removal, the branch is not pushed, the worktree is dirty or
   locked, ownership is unclear, or the path is persistent, keep it and report
   the exact path and reason.
6. Report cleanup success or preservation in the terminal handoff.

This copies the lifecycle of the repository-owned
`imac-agents-deploy.sh` temporary worktree while deliberately rejecting that
script's `--force` / `rm -rf` fallback. Those destructive fallbacks are safe
only for its fixed, script-owned disposable `/tmp` path.

## Affected areas

| File | Intended change |
|---|---|
| `AGENTS.md` | Add the concise ephemeral-worktree exit gate and persistent-workspace exclusions. |
| `CLAUDE.md` | Surface the same terminal ownership rule and point to branch-flow details. |
| `docs/contributing/branch-flow.md` | Define persistent versus creator-owned ephemeral worktrees and the safe cleanup procedure. |
| `docs/runbooks/project-analyze-operator-path.md` | Make native incremental operation the default; isolate explicit legacy Docker operation. |
| `docs/runbooks/operator-guide.md` | Add explicit legacy runtime and port flags to the Docker-specific analysis example. |

No application source, dependency, generated bundle, submodule content, or
runtime configuration file is in scope.

## Analog family and delta matrix

| Behavior | Primary invariant | Supporting evidence | Deliberate delta | Failure handling |
|---|---|---|---|---|
| Native incremental analysis | `_cmd_project_analyze` gates staging, env mutation, compose override, and runtime startup behind `manage_runtime`. | Parser/tests enforce native `8765`, `manage_runtime=False`, and `--mode incremental`. | Correct stale operator prose; do not alter CLI code. | Native health/package errors are reported without starting Docker. |
| Legacy Docker analysis | Docker compose publishes `palace-mcp` on host port `8080` and runtime management waits on the supplied URL. | Docker-specific operator guide and legacy CLI tests. | Require both `--manage-runtime` and explicit port `8080`. | Keep the legacy section visibly separate; never imply it is local default. |
| Ephemeral worktree cleanup | `imac-agents-deploy.sh` creates an exact owned worktree and binds cleanup to terminal exit. | Its README and safety-envelope test; `palace-cleanup.sh` ownership/path guards. | Apply the lifecycle to creator-owned agent worktrees, but reject force removal and raw directory deletion. | Git refusal preserves the worktree and becomes a reported residual, not a forced cleanup. |
| Persistent workspace protection | Shared Paperclip workspaces rotate branches but keep their directories. | `worktree/active.md` and `imac-team-workspaces.sh`. | Explicitly exclude primary/runtime/production/team workspaces. | Ambiguous ownership always resolves to preservation. |

## Acceptance criteria

1. The focused operator runbook shows a native incremental command using
   `--mode incremental`, defaults to port `8765`, and states that Docker,
   compose override generation, and compose-only env mutation do not occur.
2. The native example reads from the clean
   `/Users/Shared/Ios/Gimle-Repos/HorizontalSystems/` mirror boundary.
3. Every documented path that asks `project analyze` to start Docker includes
   both `--manage-runtime` and `--url http://localhost:8080/mcp`.
4. The Docker-specific operator guide no longer relies on the native-default
   parser URL accidentally.
5. Agent/contributor instructions distinguish creator-owned ephemeral
   worktrees from persistent Paperclip, primary, runtime, and production
   workspaces.
6. Terminal cleanup verifies a clean tree and exact pushed upstream SHA, then
   uses exact-path `git worktree remove` without `--force`; dirty, unpushed,
   locked, unknown-owner, and persistent paths are preserved and reported.
7. The current task worktree remains present through review/implementation, then
   is removed after the completed implementation branch is pushed and clean;
   if cleanup is refused, the final handoff reports why.
8. No runtime source, submodule content, generated bundle, Docker resource,
   virtual environment, SCIP output, or Swift build cache changes.
9. Verification does not create another `.venv` inside the task worktree.

## Verification plan

1. Confirm the existing runtime contract remains green:

   ```bash
   PYTHONPATH="$PWD/src" \
     /Users/ant013/Android/Gimle-Palace-native/.venv/bin/python \
     -m pytest tests/test_project_analyze_cli.py -q
   ```

   Run from `services/palace-mcp`. This deliberately reuses the installed
   native environment while forcing imports to resolve from the current
   worktree, avoiding another task-local `.venv`.

2. Verify documentation boundaries with targeted searches:

   ```bash
   rg -n "mode incremental|manage-runtime|localhost:8765|localhost:8080" \
     docs/runbooks/project-analyze-operator-path.md \
     docs/runbooks/operator-guide.md
   ```

   Manually verify that every Docker-starting example contains both legacy
   arguments and that native examples contain neither.

3. Verify the worktree exit contract:

   ```bash
   rg -n "ephemeral|persistent|worktree remove|--force|rm -rf" \
     AGENTS.md CLAUDE.md docs/contributing/branch-flow.md
   ```

   Manually verify that `--force` and `rm -rf` appear only as forbidden
   behavior for general task worktrees.

4. Run repository-level text checks:

   ```bash
   git diff --check
   git status --short
   ```

5. After implementation is committed and pushed, perform the live lifecycle
   check on this exact task worktree from an owning checkout:

   ```bash
   git -C /Users/ant013/Android/Gimle-Palace \
     worktree remove /Users/ant013/Android/Gimle-Palace-worktree-docker-hygiene
   git -C /Users/ant013/Android/Gimle-Palace worktree list --porcelain
   ```

   The final listing must not contain the removed exact path. Do not run this
   step while approval or implementation work is still pending. Routine
   cleanup does not run broad `git worktree prune`; successful
   `git worktree remove` already removes the target's administrative metadata.

## Rollback

Revert the documentation/instruction commit or close the feature branch without
merge. No data migration or runtime rollback is required. Worktree cleanup is
independently fail-safe because Git removal is non-forced and only targets the
exact creator-owned path.

## Open questions

None. The implementation boundary and persistent workspace exclusions are
verified at the grounded commit. Host-level provenance of the old untagged
Neo4j image remains intentionally unresolved because it does not affect the
repository change.
