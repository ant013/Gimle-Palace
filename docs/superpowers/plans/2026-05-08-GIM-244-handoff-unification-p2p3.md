# Handoff Unification Phase 2+3 — Watchdog Detectors + E2E Tests

> **For agentic workers:** atomic-handoff discipline mandatory.

**Issue:** GIM-244.
**Spec:** `docs/superpowers/specs/2026-05-08-handoff-assign-rules-unification.md` (on `feature/handoff-spec-additions`; not yet on develop — spec PR needed separately).
**Phase 1 merge SHA:** `4e743c3` (PR #122) — stable handoff markers + `validate_cross_team_targets` + `validate_handoff_markers` + 7 unit tests.
**Source branch:** `feature/GIM-244-handoff-unification-p2p3` cut from `origin/develop` at `4e743c3`.
**Target branch:** `develop`. Squash-merge on APPROVE.
**Team:** Claude. Phase chain: CTO → CodeReviewer (plan-first) → InfraEngineer (impl) → CodeReviewer (mechanical CR) → OpusArchitectReviewer (adversarial) → QAEngineer (live smoke) → CTO (merge).

**Foundation:** GIM-181 (Phase 1 alert-only) landed 3 semantic detectors in `detection_semantic.py`:
- `comment_only_handoff` — phase-complete comment with no PATCH reassign.
- `wrong_assignee` — assigned UUID not in hired set.
- `review_owned_by_implementer` — CR phase owned by the implementer.

All three are alert-only. GIM-244 adds 4 new detectors with a 3-tier state machine: alert → auto-repair (1h) → escalate (30min).

---

## Step 1 — Formalization (CTO)

**Owner:** CTO.

- [ ] Create feature branch `feature/GIM-244-handoff-unification-p2p3` from develop.
- [ ] Write this plan file.
- [ ] Note spec location discrepancy: spec is on `feature/handoff-spec-additions`, not develop.
- [ ] Push and reassign to CodeReviewer.

**Acceptance:** Plan file at `docs/superpowers/plans/2026-05-08-GIM-244-handoff-unification-p2p3.md` committed on feature branch. CodeReviewer assigned.

---

## Step 2 — Plan-first review (CodeReviewer)

**Owner:** CodeReviewer.

- [ ] Validate every Phase 2/3 task has concrete test+impl+commit shape.
- [ ] Verify acceptance criteria completeness.
- [ ] Flag scope creep or vague tasks.
- [ ] APPROVE → reassign to InfraEngineer.

**Acceptance:** CodeReviewer APPROVE comment on paperclip issue. InfraEngineer is assignee.

---

## Step 3 — Implementation (InfraEngineer)

**Owner:** InfraEngineer.
**Affected files:**
- `services/watchdog/src/gimle_watchdog/detection_semantic.py` — new detectors
- `services/watchdog/src/gimle_watchdog/models.py` — new FindingType variants + dataclasses
- `services/watchdog/src/gimle_watchdog/actions.py` — auto-repair actions
- `services/watchdog/src/gimle_watchdog/config.py` — new config knobs
- `services/watchdog/tests/test_detection_semantic.py` — unit tests for 4 new detectors
- `services/watchdog/tests/fixtures/cross_team_misassign.json` — synth fixture
- `paperclips/tests/e2e/` — new directory, 3 e2e test files
- `services/watchdog/tests/conftest.py` — shared fixtures for e2e

### Step 3.1 — Models + finding types

- [ ] Add `FindingType` variants: `CROSS_TEAM_HANDOFF`, `OWNERLESS_COMPLETION`, `INFRA_BLOCK`, `STALE_BUNDLE`.
- [ ] Add dataclasses: `CrossTeamHandoffFinding`, `OwnerlessCompletionFinding`, `InfraBlockFinding`, `StaleBundleFinding`.
- [ ] Each finding includes `kind`, `issue_id`, `fired_at`, `escalated_at`, `repaired_at` fields per acceptance criteria.

**Acceptance:** `uv run mypy services/watchdog/src/` passes. New types importable.

### Step 3.2 — `cross_team_handoff` detector

- [ ] Implement in `detection_semantic.py`.
- [ ] Reuse `validate_instructions.load_team_uuids()` — import from `paperclips.scripts.validate_instructions` (do NOT re-parse deploy-agents.sh or codex-agent-ids.env).
- [ ] Trigger: `assigneeAgentId` switches from Claude UUID set to Codex UUID set (or vice versa) AND no `infra-block` marker in recent comments.
- [ ] Write unit test with fixture `cross_team_misassign.json`: synth Claude PE → CXCTO PATCH.

**Acceptance:** Unit test passes. Detector correctly identifies cross-team assignment.
**Dependency:** None (can start immediately).

### Step 3.3 — `ownerless_completion` detector

- [ ] Implement in `detection_semantic.py`.
- [ ] Trigger: issue closes (`status=done`) but no Phase 4.1 QA PASS comment exists with `authorAgentId` matching team's QA agent.
- [ ] Claude QA UUID: `58b68640-1e83-4d5d-978b-51a5ca9080e0`.
- [ ] Codex QA UUID: `99d5f8f8-822f-4ddb-baaa-0bdaec6f9399`.
- [ ] Check via paperclip API GET for comments on the issue; scan for "Phase 4.1" + "QA PASS" + correct `authorAgentId`.
- [ ] Write unit test.

**Acceptance:** Unit test passes. Detector fires when QA evidence comment is missing.
**Dependency:** Step 3.1 (models).

### Step 3.4 — `infra_block` extension

- [ ] Extend existing `infra_block` detector (if it exists) or add new one.
- [ ] Add `actionable: bool` field (default `true`).
- [ ] When `actionable=false`: suppress auto-repair for 30min, then escalate to Board.
- [ ] Control-plane errors (Cloudflare 1010, 429, 502) set `actionable=false`.
- [ ] Write unit test.

**Acceptance:** Unit test passes. `actionable=false` suppresses repair; escalation fires after 30min.
**Dependency:** Step 3.1 (models).

### Step 3.5 — `stale_bundle` detector

- [ ] Implement in `detection_semantic.py`.
- [ ] Read deployed bundle SHA from `paperclips/scripts/imac-agents-deploy.log` (line format: `timestamp\tmain_sha=...`).
- [ ] Compare against current `origin/main` HEAD.
- [ ] Trigger: SHA differs for >24h.
- [ ] Auto-repair: post Board comment with SHA delta + suggest running `imac-agents-deploy.sh`.
- [ ] Write unit test with synth log line 25h old.

**Acceptance:** Unit test passes. Detector fires on stale bundle.
**Dependency:** Step 3.1 (models).

### Step 3.6 — Auto-repair state machine

- [ ] Implement 3-tier state machine for all 4 detectors:
  - Tier 1 (0–1h): alert-only, write `:WatchdogAlert` Neo4j node.
  - Tier 2 (1h+): attempt auto-repair (per-detector logic).
  - Tier 3 (1h30m+): escalate to Board with `severity=critical`.
- [ ] `cross_team_handoff` repair: PATCH `assigneeAgentId` back to previous-team CTO + comment.
- [ ] `ownerless_completion` repair: re-open issue (`status=blocked`) + comment requiring Phase 4.1 + ping team QA.
- [ ] `infra_block` repair: no auto-repair when `actionable=false`; escalate after 30min.
- [ ] `stale_bundle` repair: Board comment with SHA delta.
- [ ] Config knob: `auto_repair_enabled: false` (default) in `services/watchdog/config.yaml`.

**Acceptance:** State machine transitions tested. `:WatchdogAlert` nodes written with all required fields.
**Dependency:** Steps 3.2–3.5.

### Step 3.7 — E2E test: `test_cross_team_misassign_repaired.py`

- [ ] Create `paperclips/tests/e2e/` directory.
- [ ] Use `services/watchdog/tests/conftest.py` fixtures for `PaperclipClient` mock + Neo4j testcontainer.
- [ ] Synth Claude PE → CXCTO PATCH with no `infra-block` marker.
- [ ] Assert: (a) detector fires within 30s, (b) auto-repair PATCHes assignee back to Claude CTO within 1h, (c) `:WatchdogAlert{kind:'cross_team'}` node persists.

**Acceptance:** Test passes with `pytest paperclips/tests/e2e/test_cross_team_misassign_repaired.py`.
**Dependency:** Steps 3.2, 3.6.

### Step 3.8 — E2E test: `test_ownerless_done_blocked.py`

- [ ] Synth `status=done` PATCH without Phase 4.1 QA-PASS comment.
- [ ] Assert: (a) detector fires, (b) auto-repair flips to `status=blocked` with QA-evidence-missing comment, (c) original issue reopened.

**Acceptance:** Test passes.
**Dependency:** Steps 3.3, 3.6.

### Step 3.9 — E2E test: `test_stale_bundle_detected.py`

- [ ] Synth `imac-agents-deploy.log` line with `main_sha` 25h old vs current `origin/main`.
- [ ] Assert: detector fires + Board comment posted.

**Acceptance:** Test passes.
**Dependency:** Steps 3.5, 3.6.

### Step 3.10 — Local green

- [ ] `uv run ruff check services/watchdog/ paperclips/tests/e2e/`
- [ ] `uv run mypy services/watchdog/src/`
- [ ] `uv run pytest services/watchdog/ paperclips/tests/e2e/ -v`
- [ ] All existing GIM-181 detectors still pass (regression guard).
- [ ] Push all work. Reassign to CodeReviewer.

**Acceptance:** All commands green. Push visible on origin.

---

## Step 4 — Mechanical CR (CodeReviewer)

**Owner:** CodeReviewer.

- [ ] Run `uv run ruff check && uv run mypy services/watchdog/src/ && uv run pytest services/watchdog/ paperclips/tests/e2e/`.
- [ ] Paste full output in APPROVE comment (no LGTM rubber-stamps).
- [ ] Verify `cross_team_handoff` reuses `load_team_uuids` (acceptance criterion).
- [ ] Verify `:WatchdogAlert` node schema matches acceptance criteria fields.
- [ ] Reassign to OpusArchitectReviewer.

**Acceptance:** CodeReviewer APPROVE with tool output. OpusArchitectReviewer assigned.

---

## Step 5 — Adversarial review (OpusArchitectReviewer)

**Owner:** OpusArchitectReviewer.

- [ ] Race conditions in detect→repair window (concurrent agent PATCHes during 1h alert).
- [ ] False-positive triggers (legitimate cross-team admin ops, Board reassignments).
- [ ] UUID parser edge cases (`load_team_uuids` robustness with missing files).
- [ ] State machine timing: test clock skew, overlapping tier transitions.
- [ ] Reassign to QAEngineer once findings addressed.

**Acceptance:** All HIGH/CRITICAL findings resolved. QAEngineer assigned.

---

## Step 6 — Live smoke (QAEngineer)

**Owner:** QAEngineer.

- [ ] On iMac: real watchdog process running.
- [ ] Fire a real `cross_team_misassign` event on a synth test issue.
- [ ] Observe alert creation in Neo4j.
- [ ] Observe auto-repair PATCH succeed (if `auto_repair_enabled: true`).
- [ ] Comment with evidence: commit SHA, log lines, Cypher invariant for `:WatchdogAlert` nodes.
- [ ] Reassign to CTO.

**Acceptance:** Phase 4.1 evidence comment authored by QAEngineer. CTO assigned.

---

## Step 7 — Merge (CTO)

**Owner:** CTO.

- [ ] Squash-merge to develop after CI green.
- [ ] PATCH `status=done, assigneeAgentId=null`.
- [ ] Autonomous queue propagation: next slice is S3 `bundle propagation refactor`.

**Acceptance:** PR merged. CI green on merge commit. `status=done`.

---

## Notes

- **Spec location:** The referenced spec (`2026-05-08-handoff-assign-rules-unification.md`) is on `feature/handoff-spec-additions` branch, NOT on develop. It contains 3 commits (b14cf4c, 7928b40, c7b72fb) never merged. The issue description is self-contained and does not depend on the spec being merged first, but the spec branch should be merged separately.
- **`load_team_uuids` import path:** `paperclips/scripts/validate_instructions.py` → `load_team_uuids(repo_root)`. Returns `{'claude': {uuid,...}, 'codex': {uuid,...}}`. InfraEngineer must import this, not re-implement.
- **Existing detectors to preserve:** `comment_only_handoff`, `wrong_assignee`, `review_owned_by_implementer`, `in_review` recovery (all in `detection_semantic.py`).
- **Neo4j `:WatchdogAlert` schema:** `{kind, issue_id, fired_at, escalated_at, repaired_at}` — per acceptance criteria. New node label, not reusing existing `:AlertResult`.
