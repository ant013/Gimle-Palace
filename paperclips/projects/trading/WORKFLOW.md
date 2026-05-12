# Trading workflow

Authoritative spec for how Trading-team agents move tasks from `ROADMAP.md`
to a merged PR. All Trading agent overlays reference this file. Update here,
not in 5 separate AGENTS.md.

---

## Trading repo conventions (matches existing 2L-era practice)

- **Mainline**: `main`. No `develop`. Feature branches cut from `main`,
  squash-merge back to `main` via PR.
- **Branch naming**: `feature/<phase-id>-<slug>` where `<phase-id>` matches
  the operator's scheme (e.g. `phase-2l5d`, `phase-2l6`, etc.). Existing
  examples: `feature/phase-2l5c-real-baseline-replay-runtime`,
  `feature/phase-2l4j-news-collector-phase2i-adapter`,
  `feature/root-roadmap-cleanup`.
- **Specs**: `docs/specs/<phase-id>-<slug>.md`.
- **Plans**: `docs/plans/<phase-id>-<slug>-plan.md`.
- **Roadmap**: `ROADMAP.md` at repo root, narrative format with phase sections
  (e.g. `## Phase 2L.5: Finish Replay Evidence` → `### 2L.5d <Name>`).

The trading-agents repo has `pyproject.toml` (uv-managed), `pytest` test
infra, and an existing src/tests structure. Agents work on it, not from scratch.

---

## Topology — parent/child issues

### Outer loop — `roadmap walker` (parent issue)

- One long-lived paperclip issue per active roadmap track.
- Assignee: CTO.
- CTO reads `ROADMAP.md` at the root of the **trading-agents** repo and finds
  the next phase sub-section explicitly marked "not yet implemented" (or the
  first sub-section under the active `## Phase X` heading whose
  `docs/specs/<phase-id>-*.md` does not exist).
- CTO spawns a **child issue** for that phase, waits for child close, then
  picks next.
- When the child closes and lands on `main`, CTO posts a comment to parent
  with the merged PR link and advances.
- Parent stays `in_progress` until the active `## Phase` heading is fully
  implemented (all sub-sections have spec + plan + PR merged).

### Inner loop — child issue

7 transitions. CTO opens, CTO closes. See below.

---

## ROADMAP.md walk rule

Existing ROADMAP.md uses narrative sub-sections (no checkboxes). CTO's
heuristic for "next pick":

1. Scan ROADMAP.md top-to-bottom.
2. Under the first `## Phase X` heading not yet fully complete, find the
   first `### X.Yz <Name>` sub-section whose corresponding
   `docs/specs/phase-XYz-<slug>.md` does NOT exist on `main`.
3. That sub-section becomes the child issue title.

If ambiguous (no clear "next"), CTO posts to parent issue with current candidates
and waits for operator clarification — does NOT guess.

---

## Inner loop phase chain

7 phases / 7 transitions. Single CodeReviewer agent appears twice — once on
spec, once on code.

| # | Phase | Owner | What | Exit handoff |
|---|---|---|---|---|
| 1 | Spec | CTO | Cut `feature/<phase-id>-<slug>` from `main`. Draft `docs/specs/<phase-id>-<slug>.md` from ROADMAP row + repo scan. Define inputs, outputs, success criteria, file-set boundary, out-of-scope list | PATCH `assignee=CR, comment="spec ready for review on feature/<phase-id>-<slug>"` |
| 2 | Spec review | CR | Dispatch 3 voltAgent subagents in parallel (see "Spec-review subagents"). Aggregate findings into single comment with severity | PATCH `assignee=CTO, comment="spec findings: <N> blockers, <M> major, <K> minor"` |
| 3 | Plan | CTO | Address CR blockers in spec rev2; write `docs/plans/<phase-id>-<slug>-plan.md` with concrete tests → impl → commits | PATCH `assignee=PE, comment="plan ready"` |
| 4 | Implement | PE | TDD per plan on `feature/<phase-id>-<slug>`. Frequent push. Final commit + open PR to `main` | PATCH `assignee=CR, comment="impl ready, PR #X"` |
| 5 | Code review | CR | Run `uv run ruff check && uv run mypy && uv run pytest && uv run coverage report` — paste output in APPROVE comment. Read diff for quality (no rubber-stamps). Flag scope drift if file-set ≠ plan | PATCH `assignee=QA, comment="code OK, ready for smoke"` |
| 6 | Smoke | QA | Per QA criteria (below): run impl end-to-end, verify acceptance from spec, check coverage threshold + scope drift | PATCH per QA criteria |
| 7 | Close | CTO | Merge PR to `main` (squash), close child issue, advance parent | `status=done` on child |

---

## Spec-review subagents (Phase 2)

CR dispatches **3 voltAgent subagents in parallel** with fresh context each.
Same prompt prefix, different specialisation:

| Subagent | Looks for |
|---|---|
| **arch-reviewer** | Coupling violations (e.g., strategy reaching into provider internals), missing layer separation, premature abstraction, tech-debt risk, dead-code in proposed structure |
| **security-reviewer** | API-key handling (env var? secret store?), signed-request hygiene, replay-attack vectors, balance/price integer-vs-float arithmetic, race conditions in order placement, log-leak of credentials |
| **cost-efficiency** | Unbounded polling, N+1 calls to exchanges, sync I/O in hot paths, missing rate-limit awareness, retry-storm risk, hot-path allocations |

Each subagent returns a list of findings tagged `BLOCKER | MAJOR | MINOR`.
CR aggregates into one issue comment, then reassigns to CTO.

If all three subagents return zero `BLOCKER` findings → spec passes; CTO may
proceed to plan without rev2.

---

## QA criteria (Phase 6 routing)

Pin the back-or-forward decision **explicitly**, no "use your judgment":

| QA observation | Action |
|---|---|
| All tests pass, coverage ≥ 80 %, file-set == plan, acceptance from spec verified | PATCH `assignee=CTO` ("ready to merge") |
| Tests fail OR coverage < 80 % | PATCH `assignee=PE` ("back: <failure>, fix and re-PR") |
| File-set ≠ plan (extra files added OR planned files missing) | PATCH `assignee=CTO` ("scope drift: <files>, plan rev needed") |
| Acceptance criterion missed but tests pass | PATCH `assignee=CTO` ("plan gap: <criterion>, plan rev needed") |

QA never bounces back to CR or to its own role. QA's only exits are PE (rework)
or CTO (merge or plan-rev).

---

## Parent unblock mechanics

When a child issue closes:

- **Preferred** — paperclip `relatedWork.outbound` link between parent and
  child. Autonomous queue rule (commit `1c4014b`) propagates close-event back
  to parent. CTO's parent-side runtime wakes on the propagation.
- **Fallback** — parent CTO polls ROADMAP.md sub-sections and asks paperclip
  for child status on wake. If child `status=done`, CTO posts the merged PR
  link beside the implemented sub-section and picks next.

The first approach is right way; fallback is documented because as of 2026-05-12
the propagation has not been smoke-tested for Trading.

---

## Diff vs Gimle's 7-phase

| | Gimle | Trading |
|---|---|---|
| Mainline | `develop` (cut from), `main` (release) | `main` only |
| Branch name | `feature/GIM-N-<slug>` (paperclip number) | `feature/<phase-id>-<slug>` (operator's phase number) |
| Spec dir | `docs/superpowers/specs/` | `docs/specs/` |
| Plan dir | `docs/superpowers/plans/` | `docs/plans/` |
| Phase 1.1 | Formalize plan placeholder | **Spec drafting** |
| Phase 1.2 | Plan-first review by CR | **Spec-first review** by CR + 3 voltAgent subagents |
| Phase 2 | Implement | Implement |
| Phase 3.1 | Mechanical review by CR | **Code review** (mechanical + quality) by CR |
| Phase 3.2 | Adversarial review by Opus | **Skipped** (no Opus in Trading roster) |
| Phase 4.1 | Live smoke | Smoke with pinned QA criteria |
| Phase 4.2 | Merge by CTO | Merge by CTO + ROADMAP update + parent advance |

Key invertions:
- CR sees **spec first**, not plan. Catches design problems before plan investment.
- CR uses **independent voltAgent subagents** instead of running review in own session.
- QA has **pinned routing criteria**, not "use judgment".
- No Phase 3.2 (no Opus).
- Single mainline `main` (no `develop`).
- Outer loop is a paperclip parent/child relation, not just docs reference.

---

## Atomic handoff (unchanged from Gimle)

Each transition above = single PATCH:

```
PATCH /api/issues/{id}
{
  "status": "in_progress",
  "assigneeAgentId": "<next-agent-uuid>",
  "comment": "<exit note + next phase entry>"
}
```

`@mention` is decoration; the PATCH does the wake.
