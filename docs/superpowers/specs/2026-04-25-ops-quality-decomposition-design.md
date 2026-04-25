---
slug: ops-quality-decomposition
status: proposed
branch: feature/GIM-79-ops-quality-followups
paperclip_issue: 79 (umbrella)
sub_issues:
  - GIM-80 — Watchdog idle-hang detection improvements
  - GIM-81 — palace.ops.unstick_issue MCP tool (paperclip stale-lock workaround)
  - GIM-82 — Shared-fragments discipline updates (operator+CR review patterns + branch hygiene + spec quality)
predecessor: tip of develop after GIM-75 + GIM-76 + GIM-77 merge (TBD)
date: 2026-04-25
---

# GIM-79 — Ops quality + bug fixes uncovered by N+1 sessions

## Why this document exists

The N+1a sessions (GIM-74 umbrella → GIM-75/76/77 sub-slices) surfaced a class of recurring failures across three orthogonal layers: paperclip platform bugs, watchdog mistuning, and process-discipline gaps. Each is small enough to fix in isolation but together they slow the team and re-surface every few slices. This umbrella issues three atomic followup slices to close the highest-impact items before N+2 work begins.

## Source list (what we found in N+1)

Curated 2026-04-25 by operator after GIM-75/76 spec/plan/impl rounds:

- **A. Paperclip platform** — POST /release HTTP 200 but `executionRunId` not cleared; no public REST endpoint for hard-release; only host-side `kill` actually frees the lock; paperclip can re-spawn run on the same issue immediately after kill.
- **B. Watchdog** — `hang_cpu_max_s=30` too strict; 4-hour idle Claude proc accumulates >30s CPU and is not classified as hang; no signal "time since last stream-json event" which would catch token-quota stalls independent of CPU.
- **C. Branch hygiene** — Cross-branch contamination (PE on GIM-76 branch carried `e7ff6d5` GIM-75 work as a copied commit; later cleanup accidentally regressed `register_code_tools` registration); no rule forbidding stash/cherry-pick between parallel slice branches; CR Phase 3.1 doesn't audit "diff vs develop scope".
- **D. Code discipline** — PE made a false claim "no new mypy errors" on GIM-76 (CR caught 4); `ruff format` forgotten twice (GIM-69 + GIM-75 first-pass + GIM-76 first/second pass); after schema migration PE forgot to clean up dead Cypher (`UPSERT_AGENT/ISSUE/COMMENT`, `BACKFILL_GROUP_ID`, stale `CREATE_CONSTRAINTS/INDEXES` labels).
- **E. Spec quality** — Spec hardcoded `LLM: None` without verifying graphiti-core 0.28 constructor (same antipattern as N+1a revert 2026-04-18); §3.10 said "store slug in EntityNode.name" without grep'ing existing `UPSERT_PROJECT` which uses `name` for display → Opus caught latent production bug; section/task numbering drift; mega-slice scope detected only at operator round-1 review.

## Atomic decomposition

### GIM-80 — Watchdog idle-hang detection improvements

**File:** `docs/superpowers/specs/2026-04-25-watchdog-idle-hang-detection-design.md`

Replace single `hang_cpu_max_s` heuristic with two-criterion detection: (1) ratio-based `cpu_time / etime < threshold` for long-running idle, (2) "time since last stream-json event" parsed from Claude subprocess stdout for token-quota stalls. Estimate ~300 LOC product + tests.

### GIM-81 — `palace.ops.unstick_issue` MCP tool

**File:** `docs/superpowers/specs/2026-04-25-palace-ops-unstick-issue-design.md`

New MCP tool that automates the documented workaround for paperclip stale-execution-lock bug (memory: `reference_paperclip_stale_execution_lock.md`): SSH to host, locate stuck `claude --print` subprocess by `executionRunId` proxy heuristic, kill it, wait for paperclip to detect exit, optionally retry the chain. Estimate ~250 LOC + tests.

### GIM-82 — Shared-fragments discipline updates

**File:** `docs/superpowers/specs/2026-04-25-shared-fragments-discipline-design.md`

Three new/updated paperclip-shared-fragment markdowns:

1. **`branch-hygiene.md`** (NEW) — never copy/stash/cherry-pick between parallel slice branches; if Slice B depends on Slice A, wait for A to merge then rebase B onto develop.
2. **`phase-3.1-implementation-evidence.md`** (UPDATE) — when implementer claims "no new errors", paste exact `mypy --strict` / `ruff check` / `pytest` output diff; CR Phase 3.1 must run `git log origin/develop..HEAD --name-only` and assert no out-of-scope files.
3. **Spec quality rules** added to `pre-work-discovery.md` (the existing fragment that covers Phase 1 discovery) — any external library API reference in spec MUST cite a live-verified version (in-repo spike under `docs/research/`); for any spec change touching a property/field that already exists in code, spec writer MUST run `grep -r '<field-name>' src/` audit and list affected call-sites. The branch-hygiene addition lands in `worktree-discipline.md`; evidence-rigor in `compliance-enforcement.md`. (Sub-spec §3 has the full mapping — none of the file names are fabricated; all three target files exist in the submodule today.)

Doc-only slice. ~150 LOC across 3 markdown files in `paperclip-shared-fragments` submodule + bumping the submodule SHA in this repo. Estimate 1 day end-to-end.

## Order — revised after spec self-review

- **GIM-80 (watchdog)** — fully independent. Touches only `services/watchdog/`. Can merge in any order vs GIM-75/76/77 too — watchdog is a separate Python package.
- **GIM-81 (palace.ops.unstick_issue)** — **depends on GIM-75** for the audit `:Episode` write (re-uses `save_entity_node` from `graphiti_runtime.py`). The kill+poll path itself is independent, but Phase 2 cannot complete without GIM-75 merged first. Wrapped in try/except so audit failure does not block the kill — but at compile/import time GIM-81 still references GIM-75 helpers, so the import has to resolve.
- **GIM-82 (shared-fragments)** — fully independent. Doc-only changes in submodule.

So merge order constraint is just: **GIM-75 before GIM-81**. GIM-80 and GIM-82 can land any time.

None blocks N+2 product work; ops-quality is purely defensive.

## What this umbrella does NOT include

- Upstream paperclip patches — file separately when palace-mcp work goes upstream.
- N+1b (`semantic_search`) and N+1c (`git_events_extractor`) — already planned as N+1 followups, separate from ops-quality.
- 5 stale pre-N+1 PRs (#4, #7, #11, #12, #15 with CONFLICTING merge state) — separate cleanup pass, not in this umbrella.

## Acceptance for the umbrella as a whole

- 3 sub-slice specs committed under `docs/superpowers/specs/` on this branch.
- 3 paperclip issues GIM-79/80/81 created with priority=high, status=backlog, no assignee.
- After PR for this umbrella merges, sub-slices wake one-by-one through standard paperclip flow.
- Inside-job memory `reference_paperclip_stale_execution_lock.md` already updated 2026-04-25 with the new POST /release findings.

## References

- Memory `reference_paperclip_stale_execution_lock.md` (updated 2026-04-25 with POST /release behavior + only-kill-helps confirmation).
- Memory `reference_claude_process_idle_hang.md` (motivates GIM-79).
- N+1a session timeline: GIM-74 umbrella PR #36 (`766629d`), GIM-75 PR #37, GIM-76 branch `feature/GIM-76-codebase-memory-sidecar`.
- N+1 spec catalog: `docs/superpowers/specs/2026-04-24-N1-decomposition-design.md`.
