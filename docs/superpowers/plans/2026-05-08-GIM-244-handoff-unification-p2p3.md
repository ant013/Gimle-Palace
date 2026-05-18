# Handoff Unification Phase 2+3 — Watchdog Detectors + E2E Tests

> **For agentic workers:** atomic-handoff discipline mandatory.
> **Rev 2** — addresses CodeReviewer Phase 1.2 REQUEST CHANGES (2 critical + 5 warnings).

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

### CR Rev 2 changelog

| CR finding | Resolution |
|---|---|
| **CRITICAL-1**: Neo4j scope creep — watchdog has zero Neo4j dependency | **Dropped Neo4j.** All alert state persists via `state.py` JSON (`alerted_handoffs` dict, same pattern as GIM-181 detectors). Acceptance criteria updated. |
| **CRITICAL-2**: `detection.py` vs `detection_semantic.py` file target | **Fixed.** All references now target `detection_semantic.py`. Acceptance criteria updated. |
| **WARNING-3**: `infra_block` "extend existing" hedge | **Fixed.** Definitively "add new detector" — grep confirms zero `infra_block` references in codebase. |
| **WARNING-4**: Config schema strict validation blocks new keys | **Added Step 3.1a.** Explicitly adds new keys to `_HANDOFF_KNOWN_KEYS` + `HandoffConfig` before detector steps. |
| **WARNING-5**: E2E test location + conftest cross-package | **Fixed.** E2E tests now at `services/watchdog/tests/e2e/` — conftest.py auto-available, CI `watchdog-tests` job covers it without changes. |
| **WARNING-6**: Comment pagination for `ownerless_completion` | **Fixed.** Step 3.3 specifies `limit=50` for comment fetch + notes that QA evidence is always in recent comments by protocol. |
| **WARNING-7**: State machine integration with daemon tick | **Added detail to Step 3.6.** 3-tier machine hooks into existing daemon tick via extended `alerted_handoffs` dict with `tier` + `tier_changed_at` fields. |

---

## Step 1 — Formalization (CTO)

**Owner:** CTO.

- [x] Create feature branch `feature/GIM-244-handoff-unification-p2p3` from develop.
- [x] Write this plan file.
- [x] Note spec location discrepancy: spec is on `feature/handoff-spec-additions`, not develop.
- [x] Push and reassign to CodeReviewer.
- [ ] Rev 2: address CR findings, update acceptance criteria in issue body, push, reassign to CodeReviewer.

**Acceptance:** Plan file rev 2 at `docs/superpowers/plans/2026-05-08-GIM-244-handoff-unification-p2p3.md` committed on feature branch. CodeReviewer assigned.

---

## Step 2 — Plan-first review (CodeReviewer)

**Owner:** CodeReviewer.

- [ ] Validate every Phase 2/3 task has concrete test+impl+commit shape.
- [ ] Verify acceptance criteria completeness.
- [ ] Flag scope creep or vague tasks.
- [ ] Verify rev 2 addresses all 7 findings from initial review.
- [ ] APPROVE → reassign to InfraEngineer.

**Acceptance:** CodeReviewer APPROVE comment on paperclip issue. InfraEngineer is assignee.

---

## Step 3 — Implementation (InfraEngineer)

**Owner:** InfraEngineer.
**Affected files:**
- `services/watchdog/src/gimle_watchdog/detection_semantic.py` — 4 new detectors
- `services/watchdog/src/gimle_watchdog/models.py` — new `FindingType` variants + dataclasses
- `services/watchdog/src/gimle_watchdog/actions.py` — auto-repair actions (PATCH assignee, reopen issue, Board comment)
- `services/watchdog/src/gimle_watchdog/config.py` — new config keys in `_HANDOFF_KNOWN_KEYS` + `HandoffConfig`
- `services/watchdog/src/gimle_watchdog/state.py` — extend `alerted_handoffs` entry schema with `tier` + `tier_changed_at`
- `services/watchdog/src/gimle_watchdog/daemon.py` — 3-tier tick logic in handoff pass
- `services/watchdog/tests/test_detection_semantic.py` — unit tests for 4 new detectors
- `services/watchdog/tests/test_state.py` — unit tests for tier transitions
- `services/watchdog/tests/fixtures/cross_team_misassign.json` — synth fixture
- `services/watchdog/tests/e2e/` — new subdirectory, 3 e2e test files

### Step 3.1 — Models + finding types

- [ ] Add `FindingType` variants: `CROSS_TEAM_HANDOFF`, `OWNERLESS_COMPLETION`, `INFRA_BLOCK`, `STALE_BUNDLE`.
- [ ] Add frozen slotted dataclasses: `CrossTeamHandoffFinding`, `OwnerlessCompletionFinding`, `InfraBlockFinding`, `StaleBundleFinding`.
- [ ] Each finding includes `kind: str`, `issue_id: str`, `fired_at: float` (UTC epoch). The `escalated_at` and `repaired_at` fields live in state, not in the finding — findings are detection snapshots; state tracks lifecycle.
- [ ] Add `_SNAPSHOT_KEYS` entries for each new `FindingType` (per `state.py` pattern).

**Acceptance:** `uv run mypy services/watchdog/src/` passes. New types importable.

### Step 3.1a — Config schema update

- [ ] Add new keys to `_HANDOFF_KNOWN_KEYS`: `handoff_cross_team_enabled`, `handoff_ownerless_enabled`, `handoff_infra_block_enabled`, `handoff_stale_bundle_enabled`, `handoff_auto_repair_enabled`, `handoff_escalation_delay_min`, `handoff_repair_delay_min`, `handoff_stale_bundle_threshold_hours`, `handoff_ownerless_comment_limit`.
- [ ] Add matching fields to `HandoffConfig` with safe defaults (all `_enabled` default `False`, `repair_delay_min` = 60, `escalation_delay_min` = 90, `stale_bundle_threshold_hours` = 24, `ownerless_comment_limit` = 50).
- [ ] Existing `handoff_alert_cooldown_min` remains; new detectors reuse it.
- [ ] Unit test: verify config.yaml with new keys parses without `ConfigError`.

**Acceptance:** `uv run pytest services/watchdog/tests/test_config.py` passes. New keys accepted.

### Step 3.2 — `cross_team_handoff` detector

- [ ] Implement in `detection_semantic.py` as `_detect_cross_team_handoff()`.
- [ ] Reuse `validate_instructions.load_team_uuids()` — import from `paperclips.scripts.validate_instructions` (do NOT re-parse deploy-agents.sh or codex-agent-ids.env).
- [ ] Trigger: `assigneeAgentId` switches from Claude UUID set to Codex UUID set (or vice versa) AND no `infra-block` marker in recent comments.
- [ ] Comment scanning: check last `handoff_comments_per_issue` comments (existing config key) for `infra-block` text marker.
- [ ] Returns `CrossTeamHandoffFinding` with source/target team, agent UUIDs.
- [ ] Unit test in `test_detection_semantic.py` with fixture `cross_team_misassign.json`: synth Claude PE → CXCTO assignment.

**Acceptance:** Unit test passes. Detector correctly identifies cross-team assignment.
**Dependency:** Steps 3.1, 3.1a.

### Step 3.3 — `ownerless_completion` detector

- [ ] Implement in `detection_semantic.py` as `_detect_ownerless_completion()`.
- [ ] Trigger: issue has `status=done` but no Phase 4.1 QA PASS comment exists with `authorAgentId` matching team's QA agent.
- [ ] Claude QA UUID: `58b68640-1e83-4d5d-978b-51a5ca9080e0`.
- [ ] Codex QA UUID: `99d5f8f8-822f-4ddb-baaa-0bdaec6f9399`.
- [ ] Comment fetch: use `limit=handoff_ownerless_comment_limit` (default 50) from config. Rationale: Phase 4.1 QA evidence is always a late-lifecycle comment — 50 is generous. If issue has >50 comments and QA evidence is buried deeper, that's already a process anomaly worth flagging.
- [ ] Scan for "Phase 4.1" AND ("QA PASS" OR "QA FAIL") patterns + correct `authorAgentId`.
- [ ] Unit test in `test_detection_semantic.py`.

**Acceptance:** Unit test passes. Detector fires when QA evidence comment is missing on a done issue.
**Dependency:** Steps 3.1, 3.1a.

### Step 3.4 — `infra_block` detector (new — no existing detector)

- [ ] Add new detector in `detection_semantic.py` as `_detect_infra_block()`. **No existing `infra_block` detector exists** — this is greenfield.
- [ ] Add `actionable: bool` field to `InfraBlockFinding` (default `true`).
- [ ] When `actionable=false`: suppress auto-repair entirely. Alert persists, escalates to Board after `escalation_delay_min` (default 90min).
- [ ] Control-plane errors (Cloudflare 1010, 429, 502) set `actionable=false`.
- [ ] Unit test in `test_detection_semantic.py`.

**Acceptance:** Unit test passes. `actionable=false` suppresses repair; escalation fires after delay.
**Dependency:** Steps 3.1, 3.1a.

### Step 3.5 — `stale_bundle` detector

- [ ] Implement in `detection_semantic.py` as `_detect_stale_bundle()`.
- [ ] Read deployed bundle SHA from `paperclips/scripts/imac-agents-deploy.log` (line format: `timestamp\tmain_sha=...`). Parse last line with `main_sha=` prefix.
- [ ] Compare against current `origin/main` HEAD via `git rev-parse origin/main`.
- [ ] Trigger: SHA differs for > `handoff_stale_bundle_threshold_hours` (default 24h).
- [ ] Auto-repair: post Board comment with SHA delta + suggest running `imac-agents-deploy.sh`.
- [ ] Unit test in `test_detection_semantic.py` with synth log line 25h old.

**Acceptance:** Unit test passes. Detector fires on stale bundle.
**Dependency:** Steps 3.1, 3.1a.

### Step 3.6 — 3-tier state machine integration

- [ ] Extend `state.py` `alerted_handoffs` entry schema:
  - Existing fields: `alerted_at`, `snapshot`, `finding_type`.
  - New fields: `tier` (int, 1/2/3), `tier_changed_at` (float, UTC epoch), `repaired_at` (float | None), `escalated_at` (float | None), `actionable` (bool, default True).
- [ ] `STATE_VERSION` bump to 2 with migration: existing entries get `tier=1, tier_changed_at=alerted_at`.
- [ ] 3-tier logic in daemon tick (extend existing handoff pass in `daemon.py`):
  - **Tier 1** (0 → `repair_delay_min`): alert-only. Post comment via existing `post_handoff_alert()`. State entry created with `tier=1`.
  - **Tier 2** (`repair_delay_min` → `escalation_delay_min`): attempt auto-repair per detector type. On success: set `repaired_at`, clear entry. On failure: remain at tier 2.
  - **Tier 3** (`escalation_delay_min`+): escalate to Board with `severity=critical`. Set `escalated_at`. Post escalation comment.
  - Transition check: each tick reads `tier_changed_at`, computes elapsed time, promotes tier if threshold crossed.
- [ ] Auto-repair actions (add to `actions.py`):
  - `cross_team_handoff`: PATCH `assigneeAgentId` back to same-team CTO + comment with `[@<team>CTO](agent://...)`.
  - `ownerless_completion`: PATCH `status=blocked` + comment requiring Phase 4.1 + ping team QA.
  - `infra_block` (actionable=false): no auto-repair. Tier 2 is skipped → tier 1 holds until `escalation_delay_min`, then tier 3.
  - `stale_bundle`: Board comment with SHA delta (same as alert — escalation adds `severity=critical`).
- [ ] Config knob: `handoff_auto_repair_enabled: false` (default) — master switch. When false, all detectors remain alert-only (tier 1 indefinitely, no tier 2/3 transitions).
- [ ] Unit tests in `test_state.py`: tier promotion at correct elapsed times, `actionable=false` skip, state version migration.

**Acceptance:** State machine transitions tested. Alert state persists in JSON with all lifecycle fields.
**Dependency:** Steps 3.2–3.5.

### Step 3.7 — E2E test: `test_cross_team_misassign_repaired.py`

- [ ] Create `services/watchdog/tests/e2e/` directory with `__init__.py`.
- [ ] Uses existing `conftest.py` fixtures (`mock_paperclip` + `MockPaperclipState`) — auto-discovered by pytest from parent `tests/` dir.
- [ ] Synth Claude PE → CXCTO assignment with no `infra-block` marker.
- [ ] Assert: (a) detector fires, (b) alert state created with `tier=1`, (c) after simulated 1h+ elapsed (freezegun), tier 2 auto-repair PATCHes assignee back to Claude CTO, (d) state entry cleared or `repaired_at` set.

**Acceptance:** `uv run pytest services/watchdog/tests/e2e/test_cross_team_misassign_repaired.py` passes.
**Dependency:** Steps 3.2, 3.6.

### Step 3.8 — E2E test: `test_ownerless_done_blocked.py`

- [ ] Synth `status=done` without Phase 4.1 QA-PASS comment.
- [ ] Assert: (a) detector fires, (b) tier 1 alert posted, (c) after 1h+ simulated, tier 2 flips to `status=blocked` + QA-evidence-missing comment.

**Acceptance:** Test passes.
**Dependency:** Steps 3.3, 3.6.

### Step 3.9 — E2E test: `test_stale_bundle_detected.py`

- [ ] Synth `imac-agents-deploy.log` line with `main_sha` 25h old vs mock `origin/main`.
- [ ] Assert: detector fires + Board comment posted.

**Acceptance:** Test passes.
**Dependency:** Steps 3.5, 3.6.

### Step 3.10 — Local green

- [ ] `uv run ruff check services/watchdog/`
- [ ] `uv run mypy services/watchdog/src/`
- [ ] `uv run pytest services/watchdog/ -v` (covers `tests/` + `tests/e2e/`)
- [ ] All existing GIM-181 detectors still pass (regression guard).
- [ ] Push all work. Reassign to CodeReviewer.

**Acceptance:** All commands green. Push visible on origin.

---

## Step 4 — Mechanical CR (CodeReviewer)

**Owner:** CodeReviewer.

- [ ] Run `uv run ruff check && uv run mypy services/watchdog/src/ && uv run pytest services/watchdog/`.
- [ ] Paste full output in APPROVE comment (no LGTM rubber-stamps).
- [ ] Verify `cross_team_handoff` reuses `load_team_uuids` (acceptance criterion).
- [ ] Verify alert state schema matches acceptance criteria fields.
- [ ] Verify no Neo4j dependency introduced.
- [ ] Reassign to OpusArchitectReviewer.

**Acceptance:** CodeReviewer APPROVE with tool output. OpusArchitectReviewer assigned.

---

## Step 5 — Adversarial review (OpusArchitectReviewer)

**Owner:** OpusArchitectReviewer.

- [ ] Race conditions in detect→repair window (concurrent agent PATCHes during 1h alert).
- [ ] False-positive triggers (legitimate cross-team admin ops, Board reassignments).
- [ ] UUID parser edge cases (`load_team_uuids` robustness with missing files).
- [ ] State machine timing: test clock skew, overlapping tier transitions.
- [ ] `state.py` version migration from v1 → v2 on existing deployments.
- [ ] Reassign to QAEngineer once findings addressed.

**Acceptance:** All HIGH/CRITICAL findings resolved. QAEngineer assigned.

---

## Step 6 — Live smoke (QAEngineer)

**Owner:** QAEngineer.

- [ ] On iMac: real watchdog process running.
- [ ] Fire a real `cross_team_misassign` event on a synth test issue.
- [ ] Observe alert creation in watchdog state file (`~/.paperclip/watchdog-state.json`).
- [ ] Observe auto-repair PATCH succeed (if `handoff_auto_repair_enabled: true`).
- [ ] Comment with evidence: commit SHA, log lines, state file excerpt showing alert lifecycle.
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
- **Existing detectors to preserve:** `comment_only_handoff`, `wrong_assignee`, `review_owned_by_implementer` (all in `detection_semantic.py`).
- **No Neo4j dependency.** All alert state uses `state.py` JSON persistence (same pattern as GIM-181 `alerted_handoffs`). Alert lifecycle fields (`tier`, `tier_changed_at`, `repaired_at`, `escalated_at`) are state metadata, not Neo4j nodes.
- **E2E tests live at `services/watchdog/tests/e2e/`** — conftest.py fixtures auto-discovered, CI `watchdog-tests` job covers them without changes.
