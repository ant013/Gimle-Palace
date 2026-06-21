# Analog-Driven Development — Degraded Mode + RR2

Grounding:
- `GIM-1682` (`GIM-1640` W12), approved plan rev3 `d6add188-232a-4d7c-9e47-12f75d2063f8`
- repo state `0734b39d1ae792ace8c25c9ac2028c7022228575`
- benchmark evidence in `docs/research/gimle-ab-benchmark-methodology.md` and `docs/research/gimle-ab-benchmark-results-2026-06.md`

This repo does not vendor the canonical `analog-driven-development`
skill prompt. This runbook records the Gimle-side contract the skill
must follow when Palace MCP is unavailable, stale, or otherwise not
usable for a dogfood run.

Out of scope: W11b maintenance-window kit-embeddings backfill.

## Degraded mode trigger

Enter degraded mode when any of these is true:

- Palace health or project probes fail (`Unable to connect`,
  transport error, timeout).
- The target project cannot be resolved from Palace tools even though
  the local worktree is present.
- Palace returns data that cannot be trusted for the current task
  because the local repo HEAD and the indexed state are clearly out of
  sync.

When degraded mode starts, the run must say so near the top of the
artifact with the exact marker `[DEGRADED-PALACE]`.

## Degraded mode procedure

1. Probe the Palace tier first.
   Example: health + project/list call for the target slug.
2. If the probe fails or is stale, state the failed probe in the
   artifact and switch to degraded mode immediately.
3. Verify the local substrate before discovery:
   - confirm `pwd` is the intended worktree
   - record `git rev-parse HEAD`
   - confirm the target files are present locally
4. Fall back in this order:
   - local symbol/index tools already available in the session
   - `rg`/`rg --files`
   - direct file reads
   - git metadata for commit/file provenance when needed
5. Cite only facts you can re-prove from the fallback substrate.
6. Keep the degraded scope honest:
   - read/investigation tasks may stop at anchored findings
   - implementation-only phases are skipped when the task does not need
     them
   - do not invent synthetic helpers, extracted code, or stale graph
     facts to make the flow look complete

## Evidence rules in degraded mode

Every degraded run must capture:

- the `[DEGRADED-PALACE]` marker
- the failed Palace probe or the stale-index reason
- the repo/worktree identity used for fallback
- the exact fallback substrate used (`serena`, `rg`, direct read, git)
- file:line anchors for every material claim
- any scope reduction caused by degraded mode

If the task cannot be completed honestly without live Palace data,
stop and say that directly. Do not blur "degraded but still grounded"
into "best guess."

## RR2 protocol

`RR2` is the second dogfood re-run on the same task after the operator
has decided the loop should be repeated. The goal is reproducible
evidence, not a fresh prompt lottery.

Before RR2:

1. Freeze the target:
   - same task/prompt
   - same repo/worktree
   - same commit SHA unless the operator intentionally changed it
2. Record the run context:
   - issue or benchmark task id
   - repo slug or worktree name
   - commit SHA
   - whether Palace is expected to be healthy
3. Re-probe Palace at RR2 start and record whether the run is healthy or
   degraded.

During RR2:

1. Follow the normal skill flow if Palace is healthy.
2. Follow the degraded-mode procedure above if Palace is not healthy.
3. Keep the artifact explicit about which path was used.

After RR2:

Record these evidence items together:

- the RR2 artifact or transcript location
- healthy vs degraded status
- the Palace probe result
- the commit SHA used
- the main findings or output
- the delta vs the previous run:
  - same result, cleaner evidence
  - different result because Palace recovered
  - different result because the repo/input changed

If RR2 is still degraded for the same reason, keep the run as valid
degraded evidence and open follow-up work separately. Do not report it as
equivalent to a healthy Palace-backed pass.
