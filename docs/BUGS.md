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
| PBUG-5 | 2026-05-12 | Paperclip server / execution lock | HIGH | open | Second PE run on same issue gets 403 on PATCH/POST — exec-lock still bound to first run-id (TRD-4 22:47 + 22:53) |
| PBUG-6 | 2026-05-13 | Trading CR / API contract | MEDIUM | open | CR PATCH sends `comment` as object `{body:...}` instead of string → server 400 (TRD-4 round 3 08:32 UTC) |
| PBUG-7 | 2026-05-12 | iMac tooling / deploy | LOW | open | `imac-agents-deploy.sh` hardcodes Gimle company UUID; Trading bundles require manual `cp` on every update |

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

Server log evidence:

```
[22:36:05] PATCH 404   x-paperclip-run-id: d4c4a43a-…   first run (PBUG-4)
[22:47:08] PATCH 403   x-paperclip-run-id: f6754a27-…   second run, "Taking back Phase 4"
[22:53:57] POST  403   x-paperclip-run-id: f6754a27-…   second run, "Phase 4 fix ready"
```

PE in the second run could not return the issue to itself or post a comment.

**Expected:** A live agent's PATCH/POST against its own assigned issue must
succeed when the prior run for that issue has terminated. The execution
lock should release on subprocess exit OR be re-acquirable by the next run
of the same `assigneeAgentId`.

**Impact:** Trading handoff blocked even when PE knew exactly what to do.
PE fell back to leaving the re-review signal in PR #34 comments (lossy —
paperclip thread stayed silent). Board manual re-kick required.

Total `403` in paperclip server.log: 1629 — pattern not exclusive to
Trading, occurs occasionally on Gimle and others too.

**Root cause (preliminary):** Paperclip server-side binds an issue's
execution lock to the agent's first `x-paperclip-run-id`. When that run's
subprocess exits without an explicit `POST /release` (or the release does
not actually clear the binding — see `reference_paperclip_stale_execution_lock`
in operator memory), the lock stays. New run for the same agent presents a
fresh run-id; paperclip authorisation rejects with 403. Needs paperclip
server source inspection to confirm.

**Why mostly invisible on Gimle:** watchdog
(`~/.paperclip/watchdog-config.yaml`) monitors Gimle and runs
`respawn_fallback_release_patch` ~8× per day (79 events over 20 days in
`~/.paperclip/watchdog.log`). That action clears stuck locks before the
next agent run trips over them. Trading is **not** in the watchdog
`companies:` list → no auto-recovery → stall.

**Current mitigation:** Board manual PATCH `assigneeAgentId=<correct-agent>`
with comment from board token clears the lock indirectly (board token
bypasses run-id authorisation).

**Pending fixes / followups:**

- Short-term (1-line YAML): add Trading company to
  `~/.paperclip/watchdog-config.yaml` `companies:` list and reload
  watchdog. Same auto-recovery Gimle has.
- Long-term: inspect paperclip server `POST /release` handler — verify it
  actually clears `executionRunId` on the issue, not just `agent.status`.
- Long-term alternative: relax authorisation so any `x-paperclip-run-id`
  whose underlying agent matches `issue.assigneeAgentId` is accepted, even
  if `issue.executionRunId` is stale.

---

### PBUG-6 — Trading CR PATCH wraps `comment` field as object (400 Bad Request)

**Found:** 2026-05-13 08:32:38 UTC, TRD-4, agent CodeReviewer
(`8eeda1b1-704f-4b97-839f-e050f9f765d2`, Trading codex).

**What happened:** CR (Trading) attempted to PATCH TRD-4 after re-reviewing
PE's commit `94a958b`. Request shape:

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

**Expected:** Per paperclip API contract, `PATCH /api/issues/{id}` body
`comment` field is a plain string. Adjacent example from PE's PATCH at
22:36:05 (same TRD-4): `reqBody.comment: "## Phase 4 complete\n…"` — plain
string, accepted (modulo PBUG-4's 404 on assignee). The nested object
shape `{"body": "..."}` is rejected.

**Impact:** Trading CR review never persists in paperclip when CR uses this
serialisation. CR's evidence + verdict lost from the issue thread (still
visible in CR's own run log + GitHub PR comment if CR cross-posted, but
not on paperclip). Stall + Board manual re-kick to re-route to PE.

**Root cause (preliminary):** Unknown. Suspects:

- CR's codex template / bundle produces `{"body": "..."}` literal for the
  `comment` field in the PATCH JSON. May be inherited from a fragment that
  uses the wrong example shape.
- CR's codex output post-processor (paperclip-side) wraps the comment
  payload during request construction.
- Some recent paperclip-shared-fragments edit introduced the object shape
  in a code example that codex is mis-imitating.

PE (same Trading codex_local adapter) uses the correct string shape, so
the bug is **CR-specific in execution** — likely an artifact of how CR
constructs the PATCH request (its bundle or runtime adapter), not a
project-wide Trading issue.

**Current mitigation:** Board catches via paperclip-server log monitoring;
re-routes manually. No automatic recovery.

**Pending fixes / followups:**

- Diff Trading `CodeReviewer.md` bundle against Trading `PythonEngineer.md`
  bundle for any difference in how `comment` field is documented.
- Inspect codex runtime output coercion for `comment`-shaped payloads.
- Reproduce on a synthetic TRD issue with a controlled CR prompt.
- File paperclip-side: server could return `400` with a more diagnostic
  body listing the offending field path.

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
