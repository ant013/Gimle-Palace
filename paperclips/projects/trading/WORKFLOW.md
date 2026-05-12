# Trading workflow

Authoritative spec for how Trading-team agents move tasks from `roadmap.md`
to a merged PR. **All Trading agent overlays reference this file. Update here,
not in 5 separate AGENTS.md.**

---

## Topology — parent/child issues

Two levels:

### Outer loop — `roadmap walker` (parent issue)

- One long-lived paperclip issue per active roadmap "track" (usually one).
- Assignee: CTO.
- CTO reads `roadmap.md` at the root of the **trading-agents** repo, picks the
  first `- [ ]` (queued) item top-to-bottom, spawns a **child issue** for it,
  and waits.
- When the child closes, CTO swaps `- [~]` → `- [x]` for that row in
  `roadmap.md`, picks the next `- [ ]`, repeats.
- Parent stays `in_progress` until `roadmap.md` has zero `- [ ]` rows.

### Inner loop — child issue

7-phase chain. CTO opens, CTO closes. See "Inner loop phase chain" below.

---

## roadmap.md schema (root of `trading-agents`)

```markdown
# Trading roadmap

## Legend
- [ ] queued — first one from top = CTO's next pick
- [~] in-flight — CTO writes child issue link beside it
- [x] done — closed by CTO after child merges
- [!] blocked — operator-set; CTO skips

## Tasks

### Track 1 — Data ingestion
- [ ] **TRD-data-1** News feed (CryptoPanic) — first cut, single source
- [ ] **TRD-data-2** OHLC candles (Binance spot, 1m/5m/1h)
- [ ] **TRD-data-3** SQLite warehouse + idempotent upsert

### Track 2 — Strategy
- [ ] **TRD-strat-1** Strategy ABC + backtester skeleton
- ...
```

The slug after `**TRD-...**` is *operator's task label*, not the paperclip
issue identifier (paperclip assigns `TRD-N` numerically on POST). CTO writes
the paperclip issue link beside `- [~]` when spawning:

```markdown
- [~] **TRD-data-1** ... — [TRD-3](https://paperclip.ant013.work/issue/<uuid>)
```

---

## Inner loop phase chain

7 phases / 7 transitions. Single CodeReviewer agent appears twice — once on
spec, once on code.

| # | Phase | Owner | What | Exit handoff |
|---|---|---|---|---|
| 1 | Spec | CTO | Draft `docs/specs/<slug>.md` from roadmap row + repo scan. Define inputs, outputs, success criteria, file-set boundary, out-of-scope list | PATCH `assignee=CR, comment="spec ready for review"` |
| 2 | Spec review | CR | Dispatch 3 voltAgent subagents in parallel (see "Spec-review subagents"). Aggregate findings into single comment with severity | PATCH `assignee=CTO, comment="spec findings: <N> blockers, <M> major, <K> minor"` |
| 3 | Plan | CTO | Address CR blockers in spec rev2; write `docs/plans/<slug>.md` with concrete tests → impl → commits | PATCH `assignee=PE, comment="plan ready"` |
| 4 | Implement | PE | TDD per plan on `feature/TRD-<N>-<slug>`. Frequent push. Final commit + open PR | PATCH `assignee=CR, comment="impl ready, PR #X"` |
| 5 | Code review | CR | Run `ruff check && mypy && pytest && coverage report` — paste output in APPROVE comment. Read diff for quality (no rubber-stamps). Flag scope drift if file-set ≠ plan | PATCH `assignee=QA, comment="code OK, ready for smoke"` |
| 6 | Smoke | QA | Per QA criteria (below): run impl end-to-end, verify acceptance from spec, check coverage threshold + scope drift | PATCH per QA criteria |
| 7 | Close | CTO | Merge PR, close child issue, mark `roadmap.md` row `[~]` → `[x]`, push roadmap change, parent issue auto-resumes (next pick) | `status=done` on child |

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

When a child child issue closes:

- **Preferred** — paperclip `relatedWork.outbound` link between parent and
  child. Autonomous queue rule (commit `1c4014b`) propagates close-event back
  to parent. CTO's parent-side runtime wakes on the propagation.
- **Fallback** — parent CTO polls `roadmap.md` rows tagged `[~]` and asks
  paperclip for child status. If child `status=done`, swap to `[x]`.

The first approach is right way; fallback is documented because as of 2026-05-12
the propagation has not been smoke-tested for Trading. Parent CTO must
self-check on wake.

---

## Diff vs Gimle's 7-phase

| | Gimle | Trading |
|---|---|---|
| Phase 1.1 | Formalize plan placeholder | Spec drafting |
| Phase 1.2 | Plan-first review by CR | **Spec-first review** by CR + 3 voltAgent subagents |
| Phase 2 | Implement | Implement |
| Phase 3.1 | Mechanical review by CR | **Code review** (mechanical + quality) by CR |
| Phase 3.2 | Adversarial review by Opus | **Skipped** (no Opus in roster) |
| Phase 4.1 | Live smoke | Smoke with pinned QA criteria |
| Phase 4.2 | Merge by CTO | Merge by CTO + roadmap update + parent unblock |

Key inversions:
- CR sees **spec first**, not plan. Catches design problems before plan investment.
- CR uses **independent voltAgent subagents** instead of running review in own session.
- QA has **pinned routing criteria**, not "use judgment".
- No Phase 3.2 (no Opus).
- Outer loop is a real paperclip parent/child link, not just a docs reference.

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
