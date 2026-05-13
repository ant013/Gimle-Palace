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
| PBUG-4 | 2026-05-12 | Trading / roster | HIGH | fixed | Trading codex bundles fell back to Gimle CX agent-roster → PE addressed `45e3b24d` (CXCodeReviewer) → paperclip 404 → silent PR-comment fallback (TRD-4) |
| PBUG-5 | 2026-05-12 | Paperclip server / execution lock | HIGH | open | Later agent runs get 403 on PATCH/POST — exec-lock still bound to earlier run-id (TRD-4, GIM-277) |
| PBUG-6 | 2026-05-13 | Paperclip API contract | HIGH | open | Agents send comment payloads with wrong JSON shape (`comment` vs `body`, or object vs string) → server 400 and lost evidence |
| PBUG-7 | 2026-05-12 | iMac tooling / deploy | LOW | open | `imac-agents-deploy.sh` hardcodes Gimle company UUID; Trading bundles require manual `cp` on every update |
| PBUG-8 | 2026-05-13 | Paperclip UI / log signal | MEDIUM | open | Markdown/autolink placeholders generate mass `/issues/<TOKEN>` 404 noise, masking real failures in `server.log` |
| PBUG-9 | 2026-05-13 | Watchdog coverage | HIGH | open | Live watchdog covers one company and has recovery disabled → non-Gimle stale-lock/handoff failures do not self-heal |

---

## Log analysis snapshot

**Source:** `/Users/anton/.paperclip/instances/default/logs/server.log`
(1.0 GB pino JSON-per-line, iMac production) and
`/Users/anton/.paperclip/watchdog.log` (3.0 MB).

**Window sampled:** `tail -800000` of `server.log` plus `tail -2000` of
`watchdog.log`, analyzed on 2026-05-13 from this Mac over SSH.

Top signal classes from the sample:

- repeated comment/action auth failures: `403` on `PATCH/POST /issues/...`
  for TRD-4 and GIM-277, matching PBUG-5;
- repeated comment contract failures: `400` on `POST /api/issues/.../comments`
  when body shape is `{"comment": "..."}` instead of `{"body": "..."}`,
  plus `PATCH /api/issues/...` with `comment: {"body": ...}`, matching PBUG-6;
- mass issue-token 404s from rendered text/link probes:
  `PHASE-1` (2728), `PHASE-2` (2540), `AGP-9` (2537),
  `%7Bid%7D` (1574), `TIER-1` (947), `TIER-2` (926),
  `PAPERCLIP-500` (901), `%3Cissue-identifier%3E` (749),
  `SWIFT-6` (666), `LOW-1` (599), `TOP-5` (485), `TOP-3` (440),
  `$PAPERCLIP_TASK_ID` (392), and similar tokens, matching PBUG-8;
- live watchdog tail shows repeated `tick_start companies=1` and
  `recovery_pass_disabled`, matching PBUG-9.

The high-volume `401` class is noisy but not entered as its own PBUG yet:
it mixes expected unauthenticated probes (`/auth/get-session`, `agents/me`)
with real failed automation calls. It should be split only after a focused
auth-token analysis.

## Watchdog / roadmap cross-check

Existing watchdog roadmap work covers important pieces, but the live failures
show three remaining effectiveness gaps:

| Existing work | Helps with | Gap exposed by logs | Decision |
|---|---|---|---|
| GIM-181 semantic handoff detector | comment-only handoff, wrong assignee, review-owned-by-implementer | PBUG-1 also lacks a formal mention, so pure mention-based detection can miss "phase complete prose" comments | Add a detector or server invariant for phase-complete comments without an atomic PATCH in the same run |
| GIM-244 tier detectors | ownerless completion, infra block, stale bundle, tiered repair/escalation | GIM-244 introduced useful coverage but earlier rollout caused noisy alerts and later recovery was disabled | Keep tier detectors gated by GIM-255 age/status/origin/budget rules; re-enable one flag at a time |
| GIM-255 hardening | suppress stale/recovery-origin spam, shared alert budget, successful alert logs | It does not protect against disabled recovery or missing company coverage | Add watchdog status/deploy gate for company coverage and recovery enabled state |
| In-review recovery spec | lost wakeups for `in_review` handoffs | PBUG-5 is broader: stale execution lock can reject comments/PATCH even when the actor is correct | Add release/lock health checks and server-side stale-lock cleanup, not just wake recovery |
| Watchdog runbook safe re-enable | avoids repeating the 258-comment spam incident | Runbook is manual; current logs still show `recovery_pass_disabled` | Make "safe re-enable" observable: status output, startup warning, and alert on prolonged disabled recovery |

Effectiveness priorities:

1. **Reduce false positives before adding more detectors.** Keep GIM-255
   gates mandatory for all issue-bound detectors: fresh issue window, status
   whitelist, skip recovery/productivity origins, shared hard budget.
2. **Make coverage visible.** Watchdog must report covered company slugs,
   detector flags, recovery enabled/disabled, and last tick action count.
3. **Move repeated JSON-shape mistakes out of agent discretion.** Agents
   should use generated helpers or copy-paste-safe snippets for Paperclip
   writes; bundle lint should reject known bad shapes.
4. **Separate log noise from process failures.** UI/autolink 404s and expected
   auth probes should not occupy the same WARN stream as failed PATCH/POST
   handoffs.
5. **Treat stale execution locks as a server invariant.** Watchdog can mitigate
   with release+PATCH, but Paperclip should eventually clear or accept same
   assignee runs without requiring operator intervention.

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

### PBUG-4 — Trading codex bundles resolved Gimle CX agent-roster (cross-company UUID → 404)

**Found:** 2026-05-12 22:36:05 UTC, TRD-4, agent PythonEngineer
(`2705af9c-7dda-464c-9f6c-8d0deb38816a`, Trading company `09edf17a-…`).

**What happened:** PE attempted its Phase 4 → 5 handoff PATCH on TRD-4. The
`assigneeAgentId` value was `45e3b24d-a444-49aa-83bc-69db865a1897` — that is
**CXCodeReviewer in Gimle company**, not Trading's CodeReviewer
(`8eeda1b1-704f-4b97-839f-e050f9f765d2`). Paperclip server returned `404 Not
Found` (agent does not exist in TRD's company scope). The formal mention in
the comment body matched: `[@CXCodeReviewer](agent://45e3b24d-…?i=eye)`.

Server log evidence
(`/Users/anton/.paperclip/instances/default/logs/server.log`):

```
[22:36:05] WARN: PATCH /api/issues/350a53f9-… 404
  x-paperclip-run-id: d4c4a43a-…
  reqBody.status: "in_review"
  reqBody.assigneeAgentId: "45e3b24d-a444-49aa-83bc-69db865a1897"
  reqBody.comment: "## Phase 4 complete … [@CXCodeReviewer](agent://45e3b24d-…?i=eye)"
```

PE saw the 404 as a permanent block, left the re-review signal as a comment
on the GitHub PR instead (PR #34 in trading-agents), and the paperclip issue
stalled.

**Expected:** Handoffs must target a UUID from the **same paperclip company**
as the issue. Trading roster contains the 5 agents in TRD company
(`3649a8df` CEO, `4289e2d6` CTO, `8eeda1b1` CR, `2705af9c` PE,
`fbd3d0e4` QA). No cross-company UUIDs.

**Impact:** Every Trading PE/CR handoff PATCH (Phase 4→5 and Phase 5→3
return) hits 404. Bypassed via PR-side communication, but `assigneeAgentId`
in paperclip never updates → next agent does not wake → silent stall.
Required Board manual re-kick on TRD-4 round 1 (15:59 UTC) and round 2
(02:50 UTC 2026-05-13).

**Root cause:** Trading bootstrap PR #144 (2026-05-12) created the Trading
project layer (`paperclips/projects/trading/`) without an agent-roster
override at any of the project-layer paths the build-tool resolver checks
(`projects/<P>/fragments/targets/<target>/local/agent-roster.md` or
`projects/<P>/fragments/local/agent-roster.md`). With no Trading roster
file, build-tool fell back to
`paperclips/fragments/targets/codex/local/agent-roster.md` — the **Gimle CX
codex roster**. Every Trading codex bundle (PE/CR/QA/CEO) shipped with Gimle
UUIDs in its handoff-routing table. UAudit avoids this trap via its own
override at
`paperclips/projects/uaudit/fragments/targets/codex/local/agent-roster.md`;
Trading bootstrap omitted the same pattern.

**Current mitigation:** Fixed — added
`paperclips/projects/trading/fragments/local/agent-roster.md` (target-agnostic
shared override path, picks up for both claude CTO and codex worker
bundles). 5 Trading agent UUIDs + 7-step phase-to-formal-mention routing.
Rebuilt + manually `cp`'d to live agent paths on iMac 2026-05-13 02:49 UTC
(backup: `/tmp/trading-agents-pre-bug1fix-20260513T024935Z`).
Post-fix grep: every Trading bundle has 13 Trading-UUID occurrences and 0
Gimle/CX-UUID occurrences (22-UUID exclusion regex).

**Pending fixes / followups:**

- Update Trading bootstrap pattern in `paperclips/projects/_template/` so new
  paperclip companies cannot ship without a project-layer roster override.
- Add CI guard: build-tool emits warning when an `@include` resolves to a
  cross-company-pre­fixed roster (e.g., `CX*` in a non-Gimle bundle).
- Smoke verification on next live TRD-N: PE handoff PATCH must use Trading
  UUIDs and return 200.

---

### PBUG-5 — Paperclip execution lock not released across agent runs (403)

**Found:** 2026-05-12 22:47:08 UTC, TRD-4, agent PythonEngineer (`2705af9c-…`).
**Observed pattern:** server-side, hypothesised to affect any paperclip
company when an agent's first run on an issue exits without `POST /release`
and a second run on the same agent picks the same issue up.

**What happened:** After PE's first run on TRD-4 ended (the run that
produced PBUG-4 at 22:36:05), a second PE run started ~10 minutes later.
The new run had `x-paperclip-run-id: f6754a27-…` (distinct from the first
run's `d4c4a43a-…`). PATCH and POST against TRD-4 from the new run both
returned `403 Forbidden`.

Server log evidence from TRD-4:

```
[22:36:05] PATCH 404   x-paperclip-run-id: d4c4a43a-…   first run (PBUG-4)
[22:47:08] PATCH 403   x-paperclip-run-id: f6754a27-…   second run, "Taking back Phase 4"
[22:53:57] POST  403   x-paperclip-run-id: f6754a27-…   second run, "Phase 4 fix ready"
```

Second verified occurrence on GIM-277, 2026-05-13 09:04-09:10 UTC:

```
[09:04:03] POST /issues/9b4eaf95-…/comments 403
  x-paperclip-run-id: 7f2959bf-…
  body: "BlockchainEngineer — AC5 Expert Assessment"
[09:10:01] POST /issues/9b4eaf95-…/comments 403
  x-paperclip-run-id: 4caeb824-…
  body: "GitHub PR approval — platform constraint"
```

Both had syntactically valid `body` payloads, so this is not PBUG-6. The
common symptom is run authorization rejecting a later actor's legitimate
comment on the issue.

PE in the second run could not return the issue to itself or post a comment.

**Expected:** A live agent's PATCH/POST against its own assigned issue must
succeed when the prior run for that issue has terminated. The execution
lock should release on subprocess exit OR be re-acquirable by the next run
of the same `assigneeAgentId`.

**Impact:** Trading handoff blocked even when PE knew exactly what to do.
PE fell back to leaving the re-review signal in PR #34 comments (lossy —
paperclip thread stayed silent). On GIM-277, specialist assessment and PR
approval-context comments were rejected, so decision evidence again had to
move outside the normal issue thread. Board manual re-kick required.

Total `403` in paperclip server.log: 1629 — pattern not exclusive to
Trading, occurs occasionally on Gimle and others too.

**Root cause (preliminary):** Paperclip server-side binds an issue's
execution lock to the agent's first `x-paperclip-run-id`. When that run's
subprocess exits without an explicit `POST /release` (or the release does
not actually clear the binding — see `reference_paperclip_stale_execution_lock`
in operator memory), the lock stays. New run for the same agent presents a
fresh run-id; paperclip authorisation rejects with 403. Needs paperclip
server source inspection to confirm.

**Why it was historically less visible on Gimle:** watchdog can clear stuck
locks through `respawn_fallback_release_patch` when recovery is enabled for
the affected company. Current live tail contradicts the expected protection:
`~/.paperclip/watchdog.log` repeatedly shows `tick_start companies=1` and
`recovery_pass_disabled`. That means coverage is currently weaker than the
older runbook assumption and directly feeds PBUG-9.

**Current mitigation:** Board manual PATCH `assigneeAgentId=<correct-agent>`
with comment from board token clears the lock indirectly (board token
bypasses run-id authorisation).

**Pending fixes / followups:**

- Short-term: enable recovery in `~/.paperclip/watchdog-config.yaml` and add
  every live company that runs agents (Gimle, Trading, UAudit, Telegram
  plugin companies). Reload watchdog and verify `recovery_pass_disabled`
  disappears.
- Add watchdog startup log/health check that prints covered company slugs and
  whether recovery is enabled; fail the deploy smoke if a live company is
  missing.
- Long-term: inspect paperclip server `POST /release` handler — verify it
  actually clears `executionRunId` on the issue, not just `agent.status`.
- Long-term alternative: relax authorisation so any `x-paperclip-run-id`
  whose underlying agent matches `issue.assigneeAgentId` is accepted, even
  if `issue.executionRunId` is stale.

---

### PBUG-6 — Comment payload shape drift causes 400 and lost evidence

**Found:** 2026-05-13 08:32:38 UTC, TRD-4, agent CodeReviewer
(`8eeda1b1-704f-4b97-839f-e050f9f765d2`, Trading codex).
Expanded 2026-05-13 after `server.log` analysis showed the same contract
family on Gimle issues too.

**What happened:** Agents and operator-side curl snippets use at least three
different comment JSON shapes across Paperclip endpoints:

1. Correct `PATCH /api/issues/{id}` shape:
   `{"status": "...", "assigneeAgentId": "...", "comment": "plain string"}`.
2. Correct `POST /api/issues/{id}/comments` shape:
   `{"body": "plain string"}`.
3. Rejected shapes observed in production:
   - `PATCH /api/issues/{id}` with `comment: {"body": "..."}`;
   - `POST /api/issues/{id}/comments` with `{"comment": "..."}`.

Trading CR attempted to PATCH TRD-4 after re-reviewing PE's commit
`94a958b`. Request shape:

```
PATCH /api/issues/350a53f9-… 400
  x-paperclip-run-id: 9ce34440-…
  reqBody.status: "in_progress"
  reqBody.assigneeAgentId: "2705af9c-…"
  reqBody.comment: {"body": "## Summary\n…"}     ← OBJECT, not string
```

Server response: `400 Bad Request, content-length: 168`. CR's review work
(WARNING + REQUEST CHANGES verdict + REGRESSION test ask) did not land in
paperclip's issue thread.

Additional verified examples from the iMac `server.log` sample:

```
[21:31:01] POST /api/issues/6f8d5e49-…/comments 400
  reqBody.comment: "## GIM-246 complete — cross_team_handoff detector removed"
[23:12:49] POST /api/issues/GIM-235/comments 400
  reqBody.comment: "## Watchdog acknowledged"
[09:03:44] POST /api/issues/9b4eaf95-…/comments 400
  reqBody.comment: "## BlockchainEngineer — AC5 Expert Assessment"
[09:05:10] POST /api/issues/9b4eaf95-…/comments 400
  reqBody.comment: "## CTO Decision — AC5 §4 exception accepted for v1"
```

**Expected:** Per paperclip API contract:

- `PATCH /api/issues/{id}` body `comment` field is a plain string.
- `POST /api/issues/{id}/comments` body field is `body`, not `comment`.

Adjacent example from PE's PATCH at 22:36:05 (same TRD-4):
`reqBody.comment: "## Phase 4 complete\n…"` — plain string, accepted
(modulo PBUG-4's 404 on assignee). The nested object shape
`{"body": "..."}` is rejected on PATCH; the `{"comment": "..."}` shape is
rejected on POST.

**Impact:** Review verdicts, watchdog acknowledgements, CTO decisions, and
expert assessments never persist in Paperclip when the wrong shape is used.
Some of these comments are recoverable from agent run logs or GitHub PR
comments, but the issue thread loses the canonical evidence and wake signal.
This directly causes stalls when the rejected comment was also the handoff or
unblock signal.

**Root cause (preliminary):** Unknown. Suspects:

- Agent bundles/examples conflate the two endpoint contracts:
  `PATCH.comment` string vs `POST.comments.body` string.
- CR's codex template / bundle may produce `{"body": "..."}` literal for the
  `comment` field in PATCH JSON.
- Operator/agent snippets use `{"comment": "..."}` for POST comments because
  the endpoint name says "comments" and the server error does not clearly
  identify `body` as the expected field.
- CR's codex output post-processor may wrap the comment payload during
  request construction.

PE (same Trading codex_local adapter) uses the correct PATCH string shape, so
the original TRD-4 bug is CR-specific in execution. The broader POST examples
show that documentation/snippet drift is not CR-specific.

**Current mitigation:** Board catches via paperclip-server log monitoring;
re-routes manually. No automatic recovery.

**Pending fixes / followups:**

- Add a tiny generated client or shell helper for the two supported write
  paths so agents stop hand-rolling JSON shapes.
- Add bundle lint that rejects examples containing
  `POST /api/issues/.../comments` with `{"comment": ...}` or
  `PATCH /api/issues/...` with `comment: {"body": ...}`.
- Diff Trading `CodeReviewer.md` bundle against Trading `PythonEngineer.md`
  bundle for endpoint-shape examples.
- Inspect codex runtime output coercion for `comment`-shaped payloads.
- Reproduce on a synthetic issue with controlled CR and CTO prompts.
- File paperclip-side: return `400` with a diagnostic field path and expected
  shape, e.g. `expected body: string for POST /comments`.

---

### PBUG-7 — `imac-agents-deploy.sh` hardcodes Gimle company; Trading needs manual deploy

**Found:** 2026-05-12 21:12 UTC during the Trading rescue session; predicted by
voltAgent QA-expert spec audit (qa-M3) earlier the same day.

**What happened:** `imac-agents-deploy.sh` hardcodes:

```bash
COMPANY_ID="9d8f432c-ff7d-4e3a-bbe3-3cd355f73b64"  # Gimle
CTO_AGENT_ID="7fb0fdbb-…"                            # Gimle CTO
```

The wrapper invokes `paperclips/deploy-codex-agents.sh` which similarly
defaults to Gimle's company (env-overridable via `PAPERCLIP_COMPANY_ID`)
plus a Gimle-only `codex-agent-ids.env` roster file. Running the script on
develop tip:

1. Deploys all Gimle agents from the worktree (correct for Gimle).
2. Skips Codex deploy unless `PAPERCLIP_API_KEY` is exported.
3. Even with the key set, would deploy only the 12 Gimle codex agents from
   `codex-agent-ids.env`; never touches Trading's 4 codex agents.
4. Verify step greps `Phase 4.2` in Gimle CTO AGENTS.md → no observable
   evidence of Trading deploy.

**Expected:** A single deploy invocation should handle all live paperclip
companies on this iMac (Gimle, Trading, UAudit, future ones). Each
company's claude + codex bundles should land at the live agent paths
under `/Users/anton/.paperclip/instances/default/companies/<company-id>/agents/<agent-id>/instructions/AGENTS.md`.

**Impact:** Every Trading bundle update — and every UAudit update — has to
go through a manual `cp` (build + per-agent copy + backup). Reproducible
deploy needs human attention each time. Risk of stale Trading bundles
between fixes if operator forgets the manual step (Trading agents continue
to run with previous bundle content). Predicted in voltAgent spec audit
(qa-M3, 2026-05-12) — confirmed within hours.

**Current mitigation:** Manual `cp` from
`paperclips/dist/trading/{claude,codex}/*.md` to live agent paths, with
prior backup to `/tmp/trading-agents-pre-*-<timestamp>/`. Ran twice
2026-05-12 / 13 (initial override deploy + PBUG-4 fix redeploy).

**Pending fixes / followups:**

- Refactor `imac-agents-deploy.sh` to iterate `PAPERCLIP_COMPANIES` (list)
  or to read live companies from a paperclip-side endpoint, then per-company:
  1. Run `build_project_compat.py --project <slug>` (slug from manifest).
  2. Map output filenames to per-company agent UUIDs via per-project YAML.
  3. Deploy + verify per-company marker.
- Until then: document the manual recipe in `docs/runbooks/` so operator
  has a checklist on demand.

---

### PBUG-8 — Markdown/autolink issue-token probes create mass 404 noise

**Found:** 2026-05-13 while sampling the last 800000 lines of
`/Users/anton/.paperclip/instances/default/logs/server.log`.

**What happened:** Paperclip UI/browser traffic repeatedly requested
`/api/issues/<TOKEN>` for tokens that are not issue IDs. The top offenders in
the sampled window:

```
2728 PHASE-1
2540 PHASE-2
2537 AGP-9
1574 %7Bid%7D
 947 TIER-1
 926 TIER-2
 901 PAPERCLIP-500
 749 %3Cissue-identifier%3E
 666 SWIFT-6
 599 LOW-1
 485 TOP-5
 440 TOP-3
 392 $PAPERCLIP_TASK_ID
 337 SHA-256
 316 PYTHONENGINEER-2
 281 %7BissueId%7D
```

Representative log line:

```
[08:42:09] WARN: GET /issues/TOP-5 404
  referer: https://paperclip.ant013.work/GIM/issues/GIM-277
  routePath: /issues/:id
```

**Expected:** Only real Paperclip issue identifiers should trigger issue API
lookups. Tokens from prose, headings, examples, placeholders, severity labels,
phase names, protocol names, and variable names should render as plain text
unless they are explicit links to a known issue.

**Impact:** This is not a direct handoff blocker, but it massively reduces
log usefulness. Real 404s such as PBUG-4 cross-company UUID routing are buried
under thousands of expected-noise 404s. It also adds avoidable request load and
makes "grep WARN" much less actionable for future incident response.

**Root cause (preliminary):** Either the UI markdown renderer or client-side
link prefetch logic treats many uppercase/hyphenated tokens as issue links
without validating against project key patterns or known issue IDs. Agent
comments also contain many placeholder examples like `{id}`,
`<issue-identifier>`, and `$PAPERCLIP_TASK_ID`, which the UI appears to probe
as real issue IDs.

**Current mitigation:** Manual log filtering: ignore `GET /issues/<TOKEN> 404`
unless the token matches a real issue key or a UUID-like ID and the request is
part of a workflow failure.

**Pending fixes / followups:**

- Restrict auto-linking to known project keys (`GIM-123`, `TRD-4`, `UNS-20`,
  etc.) and UUID issue IDs; do not auto-link arbitrary all-caps tokens.
- Do not prefetch issue detail for markdown links until hover/click, or only
  prefetch after a local pattern allowlist passes.
- Add a server-side WARN filter or lower log level for browser-origin
  `/issues/<TOKEN>` 404s where `<TOKEN>` matches placeholder/prose patterns.
- Add a regression fixture containing `TOP-5`, `PHASE-1`, `AGP-9`,
  `SHA-256`, `{id}`, and `$PAPERCLIP_TASK_ID`; rendering it must not issue
  `/api/issues/...` calls.

---

### PBUG-9 — Watchdog coverage gap: live recovery disabled and one company only

**Found:** 2026-05-13 in `/Users/anton/.paperclip/watchdog.log`.

**What happened:** The current live watchdog tail repeatedly reports:

```
{"message": "tick_start companies=1"}
{"message": "recovery_pass_disabled"}
{"message": "tick_end actions=0"}
```

This means the deployed watchdog is not currently providing the recovery
coverage assumed by PBUG-5's mitigation notes. It is scanning only one company,
and the recovery pass is disabled. Meanwhile `server.log` shows cross-company
failures in Gimle, Trading, UAudit, and plugin companies.

**Expected:** Every live Paperclip company that has agent runs should be in
the watchdog `companies:` list, and mechanical recovery should be enabled
unless intentionally disabled for a short maintenance window. At minimum,
watchdog startup/status should make uncovered companies obvious.

**Impact:** Stale execution locks, lost handoffs, and dead-mid-work states do
not self-heal for non-covered companies. This explains why Trading PBUG-5
became visible while the older Gimle path had previously been masked by
watchdog recovery.

**Root cause (preliminary):** Watchdog config appears to be single-company and
recovery-disabled. This may be deliberate after GIM-255 no-spam hardening, but
the operational state is now too quiet: disabling recovery removes the main
backstop for the execution-lock class without an equivalent replacement.

**Current mitigation:** Board/operator manual PATCH or release+PATCH when a
stale-lock or lost-handoff symptom is noticed.

**Pending fixes / followups:**

- Update `~/.paperclip/watchdog-config.yaml` to include all active company IDs
  and enable mechanical recovery after confirming GIM-255 no-spam gates are
  deployed.
- Add `gimle-watchdog status` output for:
  - company count and slugs;
  - recovery enabled/disabled;
  - handoff/tier detector enabled flags;
  - last tick actions and failures.
- Add a watchdog startup warning when `companies` omits known live companies
  or when recovery is disabled for more than one tick outside a maintenance
  marker.
- Add a deployment checklist item: after every Paperclip company bootstrap,
  add the company to watchdog config or explicitly document why it is excluded.
- Treat `recovery_pass_disabled` as an alert-worthy event if any company has
  active runs.

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
