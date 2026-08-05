# Canonical Gimle-Repos replay preflight

**Status:** proposed — awaiting approval  
**Branch:** `docs/indexed-commit-replay-guard`  
**Base:** `origin/develop` at `0f0a3957db4b6ad94e27a06c2beebc9949510708`

## Goal

Make the native incremental replay procedure fail before indexing stale source
copies, and make clear that a missing `Project.indexed_commit` summary is not
proof that the extractor-level incremental baseline is absent.

## Assumptions

- Production/native source-of-truth copies live under
  `/Users/Shared/Ios/Gimle-Repos/HorizontalSystems`.
- The intended source ref is an explicit operator input; it must never be
  guessed from a missing upstream tracking branch. For example, `uw-ios-app`
  currently uses `origin/version/0.50`; `stable-wallet-ios` uses
  `origin/version/1.1`.
- Extractor-level checkpoints in Neo4j, not the nullable project-summary
  projection, control incremental replay eligibility.

## Scope

- Add a canonical native operator runbook for replaying the registered
  Gimle-Repos copies.
- Mark the existing `bench/ingest-fresh-replay.sh` as benchmark/fresh-workspace
  tooling and point operators to the canonical runbook.
- Link the canonical procedure from the native macOS runtime runbook.
- Document the known `component-kit` mapping mismatch as a stop condition:
  resolve the registered path and build SCIP before replaying it.

## Non-scope

- Do not change Palace checkpoint schema, `project_analyze` mode selection, or
  registered project records.
- Do not pull, reset, clean, or delete any repository during documentation
  work.
- Do not build SCIP or repair the `component-kit` mapping in this slice.

## Affected areas

- `docs/runbooks/gimle-repos-incremental-replay.md` (new)
- `bench/ingest-fresh-replay.sh` (operator-facing header and link only)
- `docs/runbooks/native-macos-palace-mcp.md` (daily-operations link)

## Design

The new runbook will require this per-repository preflight before any extractor
write:

1. Resolve the repository from Palace registration and verify that it is inside
   the canonical Gimle-Repos root.
2. Require an explicit expected remote ref, then run `git fetch origin --prune`.
3. Stop if tracked worktree or index changes exist; retain generated artifacts
   such as `scip/` and `.palace*`.
4. Fast-forward only to the explicit `origin/<ref>` with `git merge --ff-only`.
   Never use an implicit `git pull` default branch.
5. Record the resulting local HEAD and verify/rebuild `scip/index.scip` as
   needed before replay.
6. Run the replay extractor set through `palace.ingest.run_extractor`.
7. Treat `Project.indexed_commit=null` as a summary-projection warning. Use the
   extractor response (for example, the durable Swift baseline match) to decide
   whether replay is incremental; do not invoke a full `project.analyze` solely
   from that null field.

The runbook will include a stop-and-repair branch for a registry path that does
not match the canonical checkout or whose canonical checkout lacks SCIP.

## Analog delta matrix

| Slice | Primary analog | Preserved invariant | Required delta | Rejected alternative | Verification |
| --- | --- | --- | --- | --- | --- |
| Canonical replay preflight | `uaa-live-deploy.md` §0.2 | Fetch and fast-forward before live mutation; stop on preflight failure | Apply the guard per registered source copy and explicit ref | `project analyze` summary as checkpoint authority | Commands and prose include fetch, explicit-ref FF-only merge, and stop conditions |
| Replay execution | `bench/ingest-fresh-replay.sh` | Use existing SCIP and extractor-level replay | Redirect production/native operators to the canonical Gimle-Repos runbook | Rebuild or full-ingest every repository | The legacy script is labelled benchmark-only and links to the new runbook |
| Checkpoint interpretation | `project-analyze-operator-path.md` counterexample | Keep project analysis available for its intended workflow | Explicitly distinguish nullable project summary from durable extractor baseline | Schedule full analysis solely because summary is null | Runbook uses extractor response as the replay signal |

## Acceptance criteria

1. A native operator can follow one documented procedure that synchronizes the
   exact registered source copy before replay.
2. The procedure cannot silently switch branches or merge non-fast-forward
   history.
3. The procedure tells the operator to stop on tracked edits, path mismatch, or
   missing SCIP rather than indexing a different checkout.
4. The procedure distinguishes `Project.indexed_commit` from extractor-level
   checkpoints and forbids a full fallback based only on the summary field.
5. Existing benchmark tooling no longer appears to be the production canonical
   path.

## Verification plan

- `bash -n bench/ingest-fresh-replay.sh`
- Targeted `rg` checks for the explicit-ref sync, `--ff-only`, canonical-root,
  and summary-vs-checkpoint guidance in the new/updated docs.
- Review the final diff to ensure only the three scoped documentation/script
  surfaces changed.

## Risks and open questions

- The source-ref mapping for each registered project is currently operational
  knowledge rather than a validated registry field. The runbook will require it
  explicitly; a future schema change may automate it.
- `component-kit` has a verified path mismatch and no SCIP in its canonical
  copy. Repairing registry metadata and generating SCIP are separate operational
  work, not documentation edits.
