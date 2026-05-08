---
slug: handoff-assign-rules-unification
status: proposed
branch: feature/handoff-assign-rules-unification-spec
date: 2026-05-08
related:
  - GIM-239
  - GIM-229
  - GIM-216
  - GIM-181
review:
  - 2026-05-08 multi-agent spec review incorporated
---

# Handoff / Assign Rules Unification

## Context

Paperclip agents currently learn handoff and assignment behavior from several
Markdown layers:

- `paperclips/fragments/profiles/handoff.md`
- shared-fragment submodule sources under `paperclips/fragments/shared`
- target-materialized shared copies such as
  `paperclips/fragments/targets/codex/shared/fragments/phase-handoff.md`
- `paperclips/fragments/local/agent-roster.md`
- `paperclips/fragments/targets/codex/local/agent-roster.md`
- generated `paperclips/dist/**`
- watchdog docs and detector runbooks

The rules overlap but are not presented as one decision model. Two live failure
classes show that the current shape is too easy for agents to misapply:

1. **Ownerless exit**: an agent finishes a phase but leaves the issue without a
   next owner. The text fix exists in `paperclip-shared-fragments@origin/main`:
   before exit, the issue must be either `status=done` or assigned to the next
   agent / team CTO.
2. **Cross-team handoff**: in GIM-239, Claude-side `PythonEngineer` handed Phase
   4.2 to Codex `CXCTO` (`da97dbd9`) instead of Claude `CTO` (`7fb0fdbb`).
   The current watchdog treats `CXCTO` as a valid hired agent, so this is not
   caught by the existing `wrong_assignee` detector.

The shared fragments repository has already moved forward:

- `paperclip-shared-fragments@origin/main` includes role-family naming and the
  before-exit invariant.
- The Gimle submodule pointer on `origin/develop` is behind that shared-fragment
  tip, so generated/live bundles may not yet contain the latest wording.

## Goal

Make handoff/assign behavior a single, unambiguous runtime contract for agents:

1. Every completed agent phase exits in exactly one valid shape:
   close (`status=done`, assignees cleared) or handoff (active status plus
   `assigneeAgentId` set to a valid next owner).
2. If the next phase owner is unclear, the agent assigns to **its own team CTO**.
3. Agents resolve concrete names and UUIDs only through their team-local roster.
4. Claude-side agents never hand off to `CX*` agents; CX/Codex-side agents never
   hand off to bare Claude-side agents.
5. Build and validation fail if generated bundles omit stable handoff markers
   or contain actionable cross-team targets.
6. Watchdog detects and alerts on obvious cross-team or ownerless handoff
   states. Automatic repair is a follow-up unless team ownership is proven
   unambiguous.

## Non-Goals

- Do not redesign Paperclip issue statuses.
- Do not change Paperclip server semantics in this slice.
- Do not merge implementation changes into this spec commit.
- Do not remove phase matrices; this is a consolidation and guardrail pass.
- Do not depend on agents reliably interpreting incident narratives. The runtime
  rule must be concise and machine-verifiable.
- Do not make watchdog auto-reassign issues in this slice unless an
  unambiguous same-team target is available and the repair is explicitly gated.

## Assumptions

- `origin/develop` is the integration branch for Gimle Palace.
- `docs/superpowers/specs/` remains the accepted spec location.
- `paperclip-shared-fragments@origin/main` is the desired shared-fragment source
  of truth after PRs #16, #17, and #18.
- Claude and CX/Codex teams are intentionally isolated for phase handoffs.
- `@Board` remains operator-side and is not a normal agent UUID target.
- Live agents consume generated/deployed `AGENTS.md`, not shared fragments
  directly; rebuild and deploy are required after fragment changes.
- Wrong-team examples may remain in runtime bundles only when they are clearly
  labeled as anti-patterns. Validators must reject actionable wrong-team
  targets, not every foreign UUID string.

## Affected Areas

### Shared fragments / submodule

- `paperclips/fragments/shared` submodule pointer
- upstream shared fragment:
  `paperclip-shared-fragments/fragments/phase-handoff.md`
- local materialized target copies produced from shared fragments, including
  `paperclips/fragments/targets/codex/shared/fragments/phase-handoff.md`

### Local Paperclip instruction sources

- `paperclips/fragments/profiles/handoff.md`
- new shared/core handoff fragment, if introduced
- `paperclips/fragments/local/agent-roster.md`
- `paperclips/fragments/targets/codex/local/agent-roster.md`
- `paperclips/fragments/targets/codex/shared/fragments/phase-handoff.md`
- `paperclips/fragments/targets/codex/shared/fragments/heartbeat-discipline.md`
- `paperclips/instruction-profiles.yaml`
- `paperclips/instruction-coverage.matrix.yaml`
- `paperclips/bundle-size-baseline.json`
- `paperclips/bundle-size-allowlist.json`
- `paperclips/scripts/validate_instructions.py`
- `paperclips/tests/test_validate_instructions.py`
- `paperclips/validate-codex-target.sh`
- Claude-side validation wrapper, if added
- deploy scripts that upload generated agent bundles
- generated `paperclips/dist/**`

### Watchdog

- `services/watchdog/src/gimle_watchdog/detection_semantic.py`
- `services/watchdog/src/gimle_watchdog/models.py`
- `services/watchdog/src/gimle_watchdog/actions.py`
- `services/watchdog/src/gimle_watchdog/daemon.py`
- `services/watchdog/src/gimle_watchdog/role_taxonomy.py`
- watchdog tests and runbook docs

## Proposed Runtime Contract

The canonical agent-facing rule should appear once as the primary decision
model, then be referenced by narrower fragments.

```md
<!-- paperclip:handoff-contract:v2 -->

## Exit / Handoff Rule

Before exit, choose exactly one valid exit shape.

### Close

Use only when required QA / merge / deploy evidence already exists:

- `status=done`
- `assigneeAgentId=null`
- `assigneeUserId=null`
- final comment contains evidence and merge / deploy SHA when applicable

### Handoff

Use when another agent must continue the issue:

- `status=<explicit active handoff status>` (`in_progress` or `in_review` as
  required by the phase)
- `assigneeAgentId=<next owner from YOUR TEAM roster>`
- `comment=<evidence + formal mention + exact next action>`

If the next owner is unclear, assign to YOUR TEAM CTO.

Invalid exit states:

- `status=done` with an agent assignee still set
- non-`done` status with no `assigneeAgentId`
- assigned to yourself after your phase is complete
- assigned to another team's agent
- comment-only handoff without PATCH

Matrix role names are role families. Resolve `role_family -> concrete agent`
using the current team's local roster. Do not use another team's names or UUIDs
as active targets.

Handoff must be one ownership update:
`PATCH status + assigneeAgentId + comment`

Then `GET` verify both:

- `status == expected`
- `assigneeAgentId == expected`

If PATCH or GET verification is ambiguous, do not blindly duplicate comments.
Retry once only when the first ownership write is known not to have committed.
Still mismatched or ambiguous -> `status=blocked` + `@Board` with actual vs
expected.

After verified handoff, make no further Paperclip mutations or comments for
this issue in the same run. If local cleanup is needed, do it before handoff.

If a write returns `403 Cloudflare 1010` or `429`, this is a control-plane
block, not an agent error. Comment `@Board infra-block <code>` if any
non-blocked write path is available, then exit. Do NOT silent-exit and
do NOT loop on retries.
```

## Full Agent Task Cycle

This is the intended end-to-end cycle for one Paperclip task. The concrete
agent names differ by team, but role families and ownership rules stay the same.

### Team Mapping

| Role family | Claude team concrete agent | CX/Codex team concrete agent |
|---|---|---|
| CTO | `CTO` (`7fb0fdbb`) | `CXCTO` (`da97dbd9`) |
| Code reviewer | `CodeReviewer` | `CXCodeReviewer` |
| Implementer | `PythonEngineer` / `MCPEngineer` / `InfraEngineer` / domain engineer | `CXPythonEngineer` / `CXMCPEngineer` / `CXInfraEngineer` / domain engineer |
| Architect reviewer | `OpusArchitectReviewer` | `CodexArchitectReviewer` |
| QA | `QAEngineer` | `CXQAEngineer` |
| Writer / research / security | team-local role | team-local `CX*` role |

`Role family` values are the only names allowed in the phase matrix. Concrete
agent names and UUIDs must come from the current team's local roster.

### Phase Cycle

| Step | Current owner | Required action | Next owner |
|---|---|---|---|
| 0. Intake / wake | Assigned agent | `GET /agents/me`, locate assigned issue, claim or continue existing run | same owner |
| 1. Formalization | CTO | normalize issue, scope, acceptance, branch/spec gate | Code reviewer |
| 2. Plan review | Code reviewer | review spec/plan for feasibility, missing gates, phase ownership | Implementer or CTO if blocked |
| 3. Implementation | Implementer | make scoped code/doc changes, push branch, provide evidence | Code reviewer |
| 4. Mechanical review | Code reviewer | review diff, request fixes or approve | Implementer on changes, architect reviewer on approve |
| 5. Architecture review | Architect reviewer | review boundaries, integration risks, long-term maintainability | Implementer on changes, QA on approve |
| 6. QA / runtime validation | QA | run required tests/smoke, post owned evidence | CTO |
| 7. Merge / close | CTO | verify QA evidence, merge, deploy/smoke if required, close | done or next queue issue |

Typical status by next owner:

- reviewer / architect-reviewer phase -> `status=in_review`
- implementer / QA / merger phase -> `status=in_progress`
- terminal close -> `status=done`, assignees cleared

If existing Paperclip status conventions for a specific phase disagree, the
phase-specific convention wins, but the issue must still have a next owner
unless it is truly `done`.

### Agent-To-Agent Call Matrix

| From role family | To role family | Required call |
|---|---|---|
| CTO | Code reviewer | "Phase 1.1 complete: review the spec/plan, risks, and ownership. Request changes or hand to implementer." |
| Code reviewer | Implementer | "Plan approved: implement this scoped slice on the named branch, push commits, and hand back for review." |
| Code reviewer | CTO | "Plan blocked: decision needed. Here are the blockers and options." |
| Implementer | Code reviewer | "Implementation complete: review this branch/commit with listed verification evidence." |
| Code reviewer | Implementer | "Changes requested: address these findings and hand back with new commit/evidence." |
| Code reviewer | Architect reviewer | "Mechanical review approved: review architecture/integration risks and either approve or request changes." |
| Architect reviewer | Implementer | "Architecture changes requested: address these boundary/design issues and hand back." |
| Architect reviewer | QA | "Architecture approved: run QA/runtime validation using this evidence checklist." |
| QA | Implementer | "QA failed: fix these reproducible failures and hand back for review/QA as required." |
| QA | CTO | "QA passed: merge/deploy readiness evidence is attached; perform Phase 4.2 close." |
| CTO | Team CTO for next queue | "Merged and closed: create or claim the next queued slice if issue body specifies queue continuation." |

All calls resolve concrete names through the current team roster. For example,
the Claude implementation-complete call goes to `CodeReviewer`, while the
CX/Codex implementation-complete call goes to `CXCodeReviewer`.

### Handoff Call Pattern

Every phase-to-phase call uses the same pattern:

1. Finish local work and collect evidence before changing ownership.
2. Push commits / publish artifacts required by the next owner.
3. Resolve next owner through current team roster.
4. PATCH issue in one call:
   - `status=<expected next status>`
   - `assigneeAgentId=<next owner uuid>`
   - `comment=<phase complete + evidence + formal mention + exact ask>`
5. GET issue and verify both `status` and `assigneeAgentId`.
6. If mismatch and first write definitely did not commit, retry once.
7. If still mismatched or ambiguous, PATCH `status=blocked` and comment `@Board`
   with actual vs expected.
8. After verified handoff, stop Paperclip mutations/comments for this issue.

Handoff comment template:

```md
## Phase <N.M> complete — <short result>

Evidence:
- Branch: `<branch>`
- Commit: `<sha>`
- Verification: `<commands / CI / smoke / review evidence>`

[@<TeamLocalNextAgent>](agent://<team-local-uuid>?i=<icon>) your turn —
Phase <N.M+1>: <exact next action>.
```

### Fallback Calls

- Unknown next implementer -> current team CTO.
- Phase matrix conflict -> current team CTO.
- Missing roster UUID -> `status=blocked` + `@Board`, do not guess.
- Execution lock conflict (`409`) -> ask current lock holder to release; if
  unresolved, `status=blocked` + `@Board`.
- Current team cannot be determined -> alert/escalate, no auto-repair.

### Autonomous Queue Continuation

After merge/close, CTO must inspect the issue body for next-queue or autonomous
trigger pointers.

- No next queue -> close as `done` with assignees cleared.
- Next queue exists -> close current issue as `done`, then create the next issue
  assigned to the same team's CTO with source issue, merge SHA, queue position,
  and spec/plan links.
- If next queue exists but required data is missing -> `status=blocked` +
  `@Board`; do not silently close.

## Consolidation Plan

1. **Bump shared fragments**
   - Update the submodule pointer to
     `paperclip-shared-fragments@1a932f9`.
   - Confirm `fragments/phase-handoff.md` includes:
     - role-family naming disclaimer;
     - before-exit invariant;
     - autonomous queue propagation;
     - comment-is-not-handoff rule.

2. **Introduce one canonical handoff core**
   - Prefer a small `handoff-core` fragment with stable marker
     `paperclip:handoff-contract:v2`.
   - Include that core from both short `profiles/handoff.md` and full
     `phase-handoff.md`, or duplicate only through the build system if includes
     cannot be nested.
   - Keep phase matrix in `phase-handoff.md`.
   - Treat role names as role families, not concrete names.
   - Add explicit fallback: unclear next owner -> own-team CTO.

3. **Thin out duplicate handoff wording**
   - `profiles/handoff.md` should not define a second competing protocol.
   - Either include the canonical block or become a short wrapper that points to
     the canonical phase-handoff rule while preserving bundle-size goals.
   - `heartbeat-discipline.md` should focus on wake/start behavior. Handoff
     examples there should be short and defer to the canonical handoff rule.

4. **Keep rosters purely team-local**
   - Claude roster lists only Claude roles and UUIDs.
   - Codex/CX roster lists only CX roles and UUIDs.
   - Both rosters state that "your CTO" means the CTO of the current team.
   - Foreign-team UUIDs are allowed only in clearly labeled anti-pattern text,
     never in active roster tables or positive handoff templates.

5. **Rebuild generated bundles**
   - Rebuild Claude and Codex bundles.
   - Commit generated `paperclips/dist/**` diffs with the source changes.
   - Record shared-fragment SHA and generated bundle SHA in deploy evidence.

## Validation Plan

Add validation that fails closed when generated bundles are inconsistent:

1. Every generated role bundle contains stable markers, not loose prose:
   - `paperclip:handoff-contract:v2`
   - `paperclip:handoff-exit-shapes:v1`
   - `paperclip:handoff-verify-status-assignee:v1`
   - `paperclip:team-local-roster:v1`
2. Every generated role bundle contains the atomic handoff requirements:
   - `PATCH status + assigneeAgentId + comment`
   - verify both `status` and `assigneeAgentId`
   - unclear next owner -> current team CTO
3. Scoped cross-team validation:
   - Claude bundles must not contain actionable CX targets in active roster
     tables or positive handoff templates.
   - Codex bundles must not contain actionable Claude targets in active roster
     tables or positive handoff templates.
   - Foreign-team names/UUIDs are allowed only inside sections explicitly marked
     as anti-pattern / NOT examples.
4. Validator tests cover:
   - missing stable markers;
   - actionable wrong-team target rejected;
   - wrong-team anti-pattern example allowed;
   - exact role id, bundle path, and offending marker in error output.
5. Bundle-size policy remains enforced. If the canonical block increases size
   beyond policy, update `bundle-size-baseline.json` or allowlist with owner,
   reason, and review/expiry date.
6. Validator reports the exact bundle path and offending marker.

## Watchdog Plan

Extend semantic handoff detection beyond "valid hired UUID" checks. This spec
implements alert-first detection. Auto-repair is gated behind explicit
confidence checks and may be split into a follow-up.

### Team Resolution

Use this precedence:

1. Explicit issue metadata or body marker such as `Team = Claude` or
   `Team = CX`, if present and parseable.
2. Latest formal handoff comment author team, resolved from committed
   UUID-to-team roster map.
3. Previous assignee team, resolved from committed UUID-to-team roster map.
4. If signals conflict or are missing, team is ambiguous.

The committed roster map is authoritative for `uuid -> team -> role_family`.
Issue text is authoritative only for the intended issue team. Ambiguous team
resolution allows alerting but forbids automatic reassignment.

### New finding: `cross_team_handoff`

Detect when an issue is assigned to a valid hired agent on the wrong team.

Candidate detection inputs:

- current issue assignee UUID;
- issue body or issue metadata team marker, when present;
- current / previous assignee role class and team;
- latest handoff comment formal mention target;
- known Claude and CX UUID sets from config or a committed team roster map.

Examples:

- Claude issue assigned to `CXCTO` -> finding.
- CX issue assigned to `CTO` -> finding.
- Claude `PythonEngineer` comment hands off to `[@CXCTO]` -> finding.

### Ownerless completion detector

Detect likely "phase complete but no owner" states:

- recent comment contains phase-complete / handoff language;
- issue is `todo`, unassigned, or still assigned to the author after a grace
  interval;
- no valid next owner in `assigneeAgentId`.

### Repair policy

Phase 1 is alert-only by default.

Safe repair is allowed only when all are true:

- team is unambiguous;
- expected team CTO UUID is known;
- target is the same team's CTO or phase-matrix next role;
- finding is recent and not stale;
- no concurrent execution lock conflict.

Otherwise:

- post a watchdog alert;
- set `status=blocked` only if configured for repair mode;
- mention `@Board` with actual vs expected assignee.

If repair remains in this slice, restrict it to same-team CTO fallback only.
Phase-matrix next-role repair should be a follow-up after team ownership and
phase detection have live confidence.

### Control-plane class (Cloudflare 1010, 429, 502)

Distinct from agent-decision stalls but same observable effect (issue
stuck, no PATCH). When agent's last write returned `403 Cloudflare 1010`
or `429` rate-limit:

- Agent must comment `@Board infra-block <code>` and exit. **Do not** silent-exit.
- Watchdog must NOT auto-repair these — it is a control-plane issue, not
  an agent issue. Escalate with `infra_block` finding tag.
- Repair = operator manually retries write or restarts paperclip.

This case applied to GIM-238 (CXQAEngineer 10:07Z) and is not in
the same equivalence class as cross-team or ownerless errors.

### Time-bound alert→auto-repair transition

Auto-repair phase enabled when **all** of:

- ≥2 weeks alert-only without false-positives;
- ≥3 real detections successfully alerted (cross-team or ownerless);
- operator explicit approval marker in `services/watchdog/config.yaml`
  (default `auto_repair_enabled: false`).

Default target on first auto-repair phase: same-team CTO fallback only.
Phase-matrix next-role auto-repair stays follow-up.

## Bundle Propagation

Stale bundles are a known root cause: GIM-239's PE used a bundle rendered
before the disclaimer landed (PR #121) and consequently picked the wrong
team's CTO during handoff. The spec must address how new fragment content
reaches live agents.

### Build-time

After submodule pointer bump on `develop`, every Claude and Codex bundle
must be re-rendered + committed in the same PR (per existing convention).
This is enforced today.

### Deploy-time (currently manual)

`paperclips/scripts/imac-agents-deploy.sh` is invoked manually after
develop merge. Add follow-up issue: post-merge auto-deploy hook (e.g.,
GitHub Actions on develop merge → SSH iMac → run script).

### Runtime (in-flight runs hold stale bundle in RAM)

A running agent process keeps its instruction bundle in memory until
process restart. After fragment update on develop:

- New agent runs (next wake) read fresh bundle. ✅
- In-flight runs retain stale bundle until SIGTERM / completion. ⚠

Mitigation in this slice (alert-only):

- Track `bundleSourceSha` in agent's `runtime-state` after each run start.
- Watchdog new finding `stale_bundle`: if agent's `bundleSourceSha`
  differs from current `develop` submodule pointer SHA by >24 hours,
  alert. No auto-restart in this slice.
- Operator can force fresh bundle by restarting paperclip
  (`launchctl bootout` + `bootstrap`) — already documented in
  `docs/runbooks/claude-oauth-recovery.md`.

## Acceptance Criteria

1. Main repo submodule points at `paperclip-shared-fragments@1a932f9` or newer
   containing the naming disclaimer and before-exit invariant.
2. Short and full handoff profiles both include the same canonical handoff core
   marker `paperclip:handoff-contract:v2`.
3. Claude and Codex generated bundles both contain the canonical exit/handoff
   rule and stable validator markers.
4. Claude generated bundles contain only Claude roster UUIDs in active roster
   tables and positive handoff templates.
5. Codex generated bundles contain only CX/Codex roster UUIDs in active roster
   tables and positive handoff templates.
6. Foreign-team UUIDs in generated bundles are either absent or confined to
   explicitly labeled anti-pattern / NOT sections.
7. `PythonEngineer` generated bundle contains enough text to prevent the GIM-239
   mistake:
   - "your team CTO" maps to `CTO`, not `CXCTO`;
   - `CTO` UUID is `7fb0fdbb`.
8. `CXPythonEngineer` generated bundle contains the mirror rule:
   - "your team CTO" maps to `CXCTO`, not `CTO`;
   - `CXCTO` UUID is `da97dbd9`.
9. Validator fails when a Claude bundle contains an actionable CX handoff target.
10. Validator fails when a Codex bundle contains an actionable Claude handoff
    target.
11. Validator allows explicitly labeled wrong-team anti-pattern examples.
12. Validator unit tests cover marker presence, scoped cross-team checks, and
    path/marker error messages.
13. Bundle-size growth is either within policy or explicitly allowed with owner
    and expiry/review date.
14. Watchdog has tests for:
    - Claude issue assigned to `CXCTO`;
    - CX issue assigned to `CTO`;
    - phase-complete comment with no next assignee;
    - ambiguous team marker -> alert-only, no unsafe repair.
15. Existing watchdog handoff detectors still pass:
    - `comment_only_handoff`;
    - `wrong_assignee`;
    - `review_owned_by_implementer`;
    - `in_review` lost-wake recovery.
16. Verification documents any pre-existing baseline validator failures before
    using validators as feature gates.
17. Watchdog has new findings + tests for control-plane class:
    - `infra_block` (1010 / 429) — alert-only, never auto-repair;
    - `stale_bundle` — agent's `bundleSourceSha` >24h behind develop submodule
      pointer SHA, alert.
18. Synthetic e2e test (in `services/watchdog/tests/`) exercises a live
    cross-team scenario: create test issue with `Team=Claude` body marker,
    PATCH assignee to CXCTO, wait ≤2× scan interval, assert
    `cross_team_handoff` finding emitted with `expected_team=Claude,
    actual_team=Codex`.

## Verification Plan

### Baseline Prerequisite

Before using validators as feature gates, initialize/update
`paperclips/fragments/shared` and document whether current validators are green.
If validators fail on pre-existing metadata drift, record the exact unrelated
failures and either fix them first or list them as implementation blockers with
owners.

Instruction bundle verification:

```bash
./paperclips/build.sh --target claude
./paperclips/build.sh --target codex
python3 paperclips/scripts/validate_instructions.py
python3 -m pytest -q paperclips/tests/test_validate_instructions.py
./paperclips/validate-codex-target.sh
```

Targeted grep checks:

```bash
rg -n "paperclip:handoff-contract:v2|paperclip:team-local-roster:v1" paperclips/dist paperclips/dist/codex
rg -n 'PATCH status \+ assigneeAgentId \+ comment|verify both `status` and `assigneeAgentId`' paperclips/dist paperclips/dist/codex
```

Do not use raw absence of `CXCTO`, `CTO`, `da97dbd9`, or `7fb0fdbb` as the
feature gate, because explicit anti-pattern sections may intentionally contain
wrong-team examples.

Watchdog verification:

```bash
cd services/watchdog
uv run pytest tests/test_detection_semantic.py tests/test_daemon.py tests/test_actions.py
uv run ruff check src tests
uv run mypy src
```

Full narrow verification, if dependencies are available:

```bash
cd services/watchdog
uv run pytest
```

### Synthetic cross-team e2e (proves the rule actually fires)

Compile-time validators + unit tests are necessary but not sufficient.
This e2e proves watchdog catches a live violation:

```bash
# Setup: create test issue with team marker
$CURL -s -X POST -H "Authorization: Bearer $PAPERCLIP_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"title":"[wd-e2e] cross-team test","description":"**Team**: Claude","companyId":"<id>","projectId":"<id>"}' \
  "$PAPERCLIP_API_URL/api/companies/<id>/issues" -o /tmp/e2e.json

ISSUE_ID=$(jq -r .id /tmp/e2e.json)

# Inject violation: assign Claude issue to CXCTO
$CURL -s -X PATCH -H "Authorization: Bearer $PAPERCLIP_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"assigneeAgentId":"da97dbd9-6627-48d0-b421-66af0750eacf"}' \
  "$PAPERCLIP_API_URL/api/issues/$ISSUE_ID"

# Wait 2× scan interval (default 60s); assert finding emitted
sleep 130
$CURL -s -H "Authorization: Bearer $PAPERCLIP_API_KEY" \
  "$PAPERCLIP_API_URL/api/companies/<id>/issues?status=blocked" | \
  jq '.[] | select(.id == "'"$ISSUE_ID"'") | .body | contains("cross_team_handoff")' \
  | grep -q true || { echo FAIL; exit 1; }

# Cleanup
$CURL -s -X PATCH -H "Authorization: Bearer $PAPERCLIP_API_KEY" \
  -d '{"status":"cancelled"}' \
  "$PAPERCLIP_API_URL/api/issues/$ISSUE_ID"
echo PASS
```

Run as part of watchdog smoke gate before merge to develop.

### Synthetic ownerless e2e (proves "no next owner" detection)

```bash
# Setup: create test issue, assign to Claude PE
ISSUE_ID=$(...)  # similar setup
$CURL -X PATCH -d '{"assigneeAgentId":"127068ee-..."}' .../issues/$ISSUE_ID

# Inject: post phase-complete comment, then null assignee but keep status=in_progress
$CURL -X POST -d '{"body":"## Phase 2 complete — see commit abc"}' .../comments
$CURL -X PATCH -d '{"assigneeAgentId":null,"status":"in_progress"}' .../issues/$ISSUE_ID

# Wait + assert ownerless finding
sleep 130
# Expect: ownerless_completion finding with phase_complete=true, has_owner=false
```

## Decisions

Default answers below resolve the original Open Questions before
implementation. Implementer may override any default in PR body with
explicit rationale and re-request review; silent override is forbidden
per `feedback_silent_scope_reduction.md`.

| # | Question | Default | Rationale |
|---|----------|---------|-----------|
| 1 | Wrong-team anti-pattern examples in runtime bundles? | Keep inline, clearly labeled `❌ NOT` | Agent reads "DO X / DON'T do Y" together — better comprehension than cross-doc lookup. Validator already distinguishes anti-pattern sections from active tables. |
| 2 | Symmetric `validate-claude-target.sh` wrapper? | No — fold all checks into `validate_instructions.py` | Single validator surface, single failure point, no script-vs-script drift. |
| 3 | Watchdog auto-repair split into follow-up? | Yes — split. This slice ships alert-only. | Confidence requires ≥2 weeks alert-only with no false-positives + ≥3 real detections successfully alerted. |
| 4 | Phase matrix in all roles or specific only? | All roles | ~30 lines per bundle cost, eliminates cross-fragment lookup at runtime, low maintenance. |
| 5 | Deploy refuses upload on validator fail (incl. dry-run)? | Yes — fail-closed | Prevents cross-team UUID leakage into production bundles. Dry-run with explicit `--allow-validator-fail` flag for emergencies. |
