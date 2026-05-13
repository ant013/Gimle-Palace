# Process Bugs — agent-team handoff + workflow violations

Verified bugs found while paperclip teams (Gimle Claude/CX, UAudit, Trading)
work on real issues. **Scope:** process-level violations — handoff form,
phase order, exit protocol, watchdog gaps, agent-error recovery.

**Out of scope:**

- Product code bugs found by an audit → live in PR commits + per-Kit
  `docs/audit-reports/<date>-<kit>.md`.
- Incidents (severity-1 outages, broken merges) → `docs/postmortems/`.
- One-off operator slips that don't repeat → conversation history /
  operator memory.

Add a row to the table when a violation is **verified** (reproducible or
clearly traced from artifacts). Add a detail section below when the root
cause is understood enough to write up. Status values: `open`, `mitigated`,
`fixed`, `dropped`.

---

## Table

| ID | Date | Area | Severity | Status | One-line |
|---|---|---|---|---|---|
| PBUG-1 | 2026-05-12 | Gimle / handoff form | HIGH | open | PE comment-only handoff: no atomic PATCH, no formal mention → silent stall ~1.5h on GIM-277 |
| PBUG-2 | 2026-05-12 | Gimle / phase order | MEDIUM | open | PE unauthorized phase-skip Phase 2 → Phase 3.2, bypassing CR Phase 3.1 (GIM-277) |
| PBUG-3 | 2026-05-12 | Gimle / exit protocol | MEDIUM | open | PE continued tool-use after Phase-complete comment, woke second time in same run, enabled PBUG-2 (GIM-277) |

---

## Details

### PBUG-1 — Comment-only handoff without atomic PATCH

**Found:** 2026-05-12 16:03 UTC, GIM-277, agent PythonEngineer (`127068ee-b564-4b37-9370-616c81c63f35`).

**What happened:** PE posted `POST /api/issues/{id}/comments` after Phase 2
work complete. Comment text named the next phase ("Next: Phase 3.1
(CodeReviewer mechanical review of PR #151)") but did **NOT** call
`PATCH /api/issues/{id}` with `assigneeAgentId=CR`. Comment also did not
include a formal `[@CodeReviewer](agent://<uuid>?i=<icon>)` mention.

Both wake-mechanisms missed:

- assignee-change PATCH wake — didn't fire (no PATCH)
- @-mention wake — didn't fire (no formal mention; only prose "CodeReviewer")

CR never woke → silent stall.

**Expected (per PE AGENTS.md `## Handoff discipline`, lines 491–510):**

> ALWAYS hand off by PATCHing `status + assigneeAgentId + comment` in one
> API call, then GET-verify the assignee; on mismatch retry once with the
> same payload, then mark `status=blocked` and escalate to Board with
> `assigneeAgentId.actual != expected`. **@mention-only handoff is invalid.**

Plus formal-mention rule (lines 449–455):

> `PATCH /api/issues/{id}` with `comment` — wakes ONLY if assignee changed,
> moved out of backlog, or body has @-mentions. No-mention comment on PATCH
> won't wake assignee → silent stall.

**Impact:** ~1.5h silent stall on GIM-277. Operator manual recovery PATCH at
16:12 UTC routed assignee to CR.

**Root cause (current understanding):** Model executed the comment step, did
not execute the PATCH step. The rule is explicit in the agent's instructions
but enforcement is by self-discipline. Memory `feedback_cr_handoff_formal_mention`
(operator-codified after GIM-182, 8h stall evidence) already documented this
anti-pattern — so PBUG-1 is a **recurrence**, not a new finding.

**Current mitigation:** Operator manual recovery (PATCH `assignee=<next>`)
when watchdog or operator notices stall.

**Pending fixes / followups:**

- Verify `services/watchdog/` already has a detector for
  "PE comment with phase-keywords without subsequent PATCH within N seconds";
  if not, add one.
- Add a pre-exit self-check in PE prompt: "after writing a Phase-complete
  comment, immediately verify you have made the atomic PATCH; if not, do it
  before stopping."
- Consider a paperclip-level invariant: an agent cannot end its run with a
  `## Phase N` comment in flight without an accompanying PATCH-handoff in
  the same heartbeat.

---

### PBUG-2 — Unauthorized phase-skip Phase 2 → Phase 3.2 bypassing CR Phase 3.1

**Found:** 2026-05-12 16:42 UTC, GIM-277, agent PythonEngineer (`127068ee-…`).

**What happened:** PE woke a second time in the same run (because of PBUG-3 —
exit-protocol not enforced after the 16:03 PBUG-1 comment). It found a real
bug in `services/palace-mcp/src/palace_mcp/audit/renderer.py`
(`_section_max_severity` used hardcoded `_severity` key but
`crypto_domain_model` stores severity in `severity`; executive summary
incorrectly said "no critical/high findings" while the body had 1 HIGH),
fixed it + added 2 regression tests, committed `2ef4d06`. Then made a
**correctly-formed** atomic PATCH:

- `status=in_review`
- `assigneeAgentId=OpusArchitectReviewer (8d6649e2-…)`
- comment with proper formal mention
  `[@OpusArchitectReviewer](agent://8d6649e2-…?i=eye) your turn — Phase 3.2: …`

Handoff **form** was correct (atomic PATCH + formal mention).
Handoff **target** was wrong — went directly to Phase 3.2 (Opus adversarial
review), skipping Phase 3.1 (CodeReviewer mechanical review).

The CR run that operator's 16:12 PATCH had triggered was cancelled when PE's
16:42 PATCH changed assignee away from CR (paperclip UI shows
"CodeReviewer cancelled after 1 second").

**Expected:** Phase order per Gimle 7-phase chain
(`CLAUDE.md` § Paperclip team workflow): 1.1 (CTO) → 1.2 (CR plan-first) →
2 (Implement) → 3.1 (CR mechanical) → 3.2 (Opus adversarial) → 4.1 (QA
smoke) → 4.2 (CTO merge). Phase 3.1 is enforced by
`feedback_cr_phase31_ci_verification` in operator memory: CR must paste
`ruff/mypy/pytest` output as evidence; PR mechanical lint/test gates run
through CR, not Opus.

**Impact:** Phase 3.1 was skipped. PR #151 still has `lint=FAILURE` on
GitHub Actions that would have been caught by CR mechanical paste. Quality
enforcement lost. Operator routed back to CR per a 2026-05-13 decision.

**Root cause:** Phase **order** is not encoded in PE AGENTS.md as a hard
rule. Only "Phase 3.1 mechanical review" is *referenced* as something CR
does. PE has no rule saying "if you're done with Phase 2, your next handoff
target MUST be CodeReviewer, never any other role." Without that rule, a PE
can syntactically-correctly hand off to any role.

**Current mitigation:** Operator detects via monitoring + manual PATCH back
to CR. No automatic enforcement.

**Pending fixes / followups:**

- Add explicit phase-order rule to PE AGENTS.md and the
  `phase-handoff.md` shared fragment: "after Phase 2 completion, next
  handoff target MUST be CodeReviewer (`bd2d7e20-7ed8-474c-91fc-353d610f4c52`).
  Any other target is invalid."
- Add watchdog detector for "PE assigned a role other than CR immediately
  after Phase 2 implementation commit."
- Consider paperclip-level phase-order enforcement (reject PATCH if it would
  jump >1 phase ahead in the chain).

---

### PBUG-3 — Exit Protocol not enforced when prior handoff was comment-only

**Found:** 2026-05-12 16:03 → 16:42 UTC (same PE run), GIM-277.

**What happened:** After the 16:03 Phase 2 complete comment (PBUG-1), PE
should have stopped all tool use per Exit Protocol. But because PBUG-1 means
the **handoff PATCH never happened**, paperclip's run-supervisor never
detected an assignee-change → never SIGTERM'd the PE process → PE's
execution lock stayed active. About 40 minutes later PE woke up *again* in
the same run (likely a heartbeat retry) and produced PBUG-2.

**Expected (per PE AGENTS.md `### Exit Protocol`, lines 512–526):**

> After the handoff PATCH returns 200 and GET-verify confirms
> `assigneeAgentId == <next>`: **Stop tool use immediately.** The handoff
> PATCH is your last tool call. No more bash, curl, serena, gh, or any
> other tool — even read-only ones. Output your final summary as plain
> assistant text, then end the turn.

**Impact:** Enabled PBUG-2. Made the run un-cancellable via the normal
"assignee changes away → SIGTERM" path that Exit Protocol assumes.

**Root cause:** Exit Protocol is conditional on a successful handoff PATCH.
When PBUG-1 occurs (comment-only "handoff"), the SIGTERM trigger doesn't
fire, and the agent's heartbeat-driven retry keeps the same execution lock
alive. There is no rule that says "if you wrote a Phase-complete comment
without making the PATCH, treat that as an Exit Protocol violation and
self-terminate."

**Current mitigation:** None automatic. Operator catches via monitoring.

**Pending fixes / followups:**

- Couple Exit Protocol enforcement to comment-detection: paperclip's
  run-supervisor should detect "comment posted whose body matches
  `^## Phase \d+(\.\d+)? complete`" and SIGTERM the agent run preemptively
  if no PATCH-handoff arrives in the same heartbeat.
- Or: add to PE AGENTS.md — "if you just posted a Phase-complete comment
  without a PATCH-handoff, stop all further tool calls until the next
  paperclip heartbeat. Do not try to recover within the same run."

---

## How to add a new entry

When a process bug is verified (reproduced or clearly traced from
artifacts):

1. **Add a row to the table at the top.**
   `PBUG-<N> | <YYYY-MM-DD> | <area> | <severity> | open | <one-line>`
   Pick the next free `PBUG-<N>` integer. Severity:
   `LOW | MEDIUM | HIGH | CRITICAL`.

2. **Add a detail section below.** Required fields:
   - **Found:** date + issue ID + responsible agent UUID.
   - **What happened:** observable behaviour, with timestamps.
   - **Expected:** quote the AGENTS.md / fragment rule that was violated,
     with line numbers if possible.
   - **Impact:** what broke + how long it stalled + what data was lost or
     wasted.
   - **Root cause:** current best understanding (mark "preliminary" if
     not confirmed).
   - **Current mitigation:** the band-aid keeping us moving today.
   - **Pending fixes / followups:** bulleted ideas for permanent fix; link
     to issues if filed.

3. **Update status** when the situation changes:
   - `open` → `mitigated` once a temporary fix is in place.
   - `mitigated` → `fixed` once the permanent fix lands.
   - → `dropped` if the bug is judged not worth fixing (with rationale in
     the detail section).
