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
---

# Handoff / Assign Rules Unification

## Context

Paperclip agents currently learn handoff and assignment behavior from several
Markdown layers:

- `paperclips/fragments/profiles/handoff.md`
- `paperclips/fragments/shared/fragments/phase-handoff.md`
- `paperclips/fragments/shared/fragments/heartbeat-discipline.md`
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

1. Every completed agent phase exits in an owned state:
   `status=done` or `assigneeAgentId` set to a valid next owner.
2. If the next phase owner is unclear, the agent assigns to **its own team CTO**.
3. Agents resolve concrete names and UUIDs only through their team-local roster.
4. Claude-side agents never hand off to `CX*` agents; CX/Codex-side agents never
   hand off to bare Claude-side agents.
5. Build and validation fail if generated bundles omit the invariant or contain
   cross-team UUID/name leakage.
6. Watchdog detects, alerts, and optionally repairs obvious cross-team or
   ownerless handoff states.

## Non-Goals

- Do not redesign Paperclip issue statuses.
- Do not change Paperclip server semantics in this slice.
- Do not merge implementation changes into this spec commit.
- Do not remove phase matrices; this is a consolidation and guardrail pass.
- Do not depend on agents reliably interpreting incident narratives. The runtime
  rule must be concise and machine-verifiable.

## Assumptions

- `origin/develop` is the integration branch for Gimle Palace.
- `docs/superpowers/specs/` remains the accepted spec location.
- `paperclip-shared-fragments@origin/main` is the desired shared-fragment source
  of truth after PRs #16, #17, and #18.
- Claude and CX/Codex teams are intentionally isolated for phase handoffs.
- `@Board` remains operator-side and is not a normal agent UUID target.
- Live agents consume generated/deployed `AGENTS.md`, not shared fragments
  directly; rebuild and deploy are required after fragment changes.

## Affected Areas

### Shared fragments / submodule

- `paperclips/fragments/shared` submodule pointer
- upstream shared fragment:
  `paperclip-shared-fragments/fragments/phase-handoff.md`

### Local Paperclip instruction sources

- `paperclips/fragments/profiles/handoff.md`
- `paperclips/fragments/local/agent-roster.md`
- `paperclips/fragments/targets/codex/local/agent-roster.md`
- `paperclips/fragments/targets/codex/shared/fragments/phase-handoff.md`
- `paperclips/fragments/targets/codex/shared/fragments/heartbeat-discipline.md`
- `paperclips/instruction-coverage.matrix.yaml`
- `paperclips/scripts/validate_instructions.py`
- `paperclips/validate-codex-target.sh`
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
## Exit / Handoff Rule

Before you exit, the issue MUST be in exactly one terminal/owned state:

1. `status=done` only after required merge / QA / deploy evidence exists; OR
2. `assigneeAgentId` is set to the next agent in YOUR TEAM; OR
3. if unsure who is next, assign to YOUR TEAM CTO.

Never leave `status=todo`, unassigned, or assigned to yourself after your phase
is complete.

Role names in the matrix are role families. Resolve concrete name + UUID from
`fragments/local/agent-roster.md`. Do not use another team's UUID.

Handoff must be one API update:
`PATCH status + assigneeAgentId + comment`

Then `GET` verify `assigneeAgentId == expected`.
Mismatch -> retry once.
Still mismatch -> `status=blocked` + `@Board`.

After verified handoff: stop tool use immediately.
```

## Consolidation Plan

1. **Bump shared fragments**
   - Update the submodule pointer to
     `paperclip-shared-fragments@1a932f9`.
   - Confirm `fragments/phase-handoff.md` includes:
     - role-family naming disclaimer;
     - before-exit invariant;
     - autonomous queue propagation;
     - comment-is-not-handoff rule.

2. **Make `phase-handoff.md` canonical**
   - Keep phase matrix and exit invariant in `phase-handoff.md`.
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

5. **Rebuild generated bundles**
   - Rebuild Claude and Codex bundles.
   - Commit generated `paperclips/dist/**` diffs with the source changes.

## Validation Plan

Add validation that fails closed when generated bundles are inconsistent:

1. Every generated role bundle contains the before-exit invariant marker:
   - `status=done OR assigneeAgentId`
   - `your team CTO` or equivalent team-local fallback language
2. Every generated role bundle contains the atomic handoff marker:
   - `PATCH status + assigneeAgentId + comment`
   - `GET` verify
3. Claude generated bundles must not contain:
   - `CXCTO`
   - `CXCodeReviewer`
   - known CX UUIDs such as `da97dbd9`
   - Codex/CX roster header text
4. Codex generated bundles must not contain:
   - bare Claude handoff examples such as `[@CTO](agent://7fb0fdbb`
   - known Claude UUIDs where a CX equivalent exists
   - Claude roster header text
5. Validator reports the exact bundle path and offending marker.

## Watchdog Plan

Extend semantic handoff detection beyond "valid hired UUID" checks.

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

Phase 1 may be alert-only if the team marker is ambiguous.

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

## Acceptance Criteria

1. Main repo submodule points at `paperclip-shared-fragments@1a932f9` or newer
   containing the naming disclaimer and before-exit invariant.
2. Claude and Codex generated bundles both contain the canonical exit/handoff
   rule.
3. Claude generated bundles contain only Claude roster UUIDs for phase handoff.
4. Codex generated bundles contain only CX/Codex roster UUIDs for phase handoff.
5. `PythonEngineer` generated bundle contains enough text to prevent the GIM-239
   mistake:
   - "your team CTO" maps to `CTO`, not `CXCTO`;
   - `CTO` UUID is `7fb0fdbb`.
6. `CXPythonEngineer` generated bundle contains the mirror rule:
   - "your team CTO" maps to `CXCTO`, not `CTO`;
   - `CXCTO` UUID is `da97dbd9`.
7. Validator fails when a Claude bundle contains `da97dbd9` or `CXCTO`.
8. Validator fails when a Codex bundle contains `7fb0fdbb` in a handoff example.
9. Watchdog has tests for:
   - Claude issue assigned to `CXCTO`;
   - CX issue assigned to `CTO`;
   - phase-complete comment with no next assignee;
   - ambiguous team marker -> alert-only, no unsafe repair.
10. Existing watchdog handoff detectors still pass:
    - `comment_only_handoff`;
    - `wrong_assignee`;
    - `review_owned_by_implementer`;
    - `in_review` lost-wake recovery.

## Verification Plan

Instruction bundle verification:

```bash
./paperclips/build.sh --target claude
./paperclips/build.sh --target codex
./paperclips/validate-codex-target.sh
python3 paperclips/scripts/validate_instructions.py
```

Targeted grep checks:

```bash
rg -n "CXCTO|da97dbd9" paperclips/dist/*.md
rg -n "\\[@CTO\\]\\(agent://7fb0fdbb" paperclips/dist/codex/*.md
rg -n "status=done OR assigneeAgentId|your team CTO" paperclips/dist paperclips/dist/codex
```

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

## Open Questions

1. What is the most reliable source of issue team ownership?
   - explicit issue body marker such as `Team = Claude`;
   - assignee role prefix;
   - project / queue metadata;
   - Paperclip company/team API, if available.
2. Should watchdog auto-repair cross-team assignments immediately, or start
   alert-only and promote to repair after live confidence?
3. Should the phase matrix remain in all roles, or only in roles that perform
   non-default phase transitions?
4. Should `profiles/handoff.md` include the full canonical rule despite bundle
   size, or should validation require the canonical markers via another include?
5. Should deploy scripts refuse to upload bundles when cross-team validator
   checks fail, even in dry-run mode?
