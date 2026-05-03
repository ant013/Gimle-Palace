---
slug: watchdog-handoff-detector
status: proposed
branch: feature/GIM-181-watchdog-handoff-detector
paperclip_issue: 180
spec: docs/superpowers/specs/2026-05-03-GIM-181-watchdog-handoff-detector.md
predecessor: 9262aca
date: 2026-05-03
---

# GIM-181 — Implementation plan: watchdog handoff detector (alert-only)

This plan is the source of truth for implementation steps. Each task ends
with a green test target before the next starts. All paths below relative
to `services/watchdog/` unless noted.

---

## Task 0 — Bootstrap (Phase 1.1 CTO mechanical)

**Owner**: CTO

**Steps**:
1. Verify `feature/GIM-181-watchdog-handoff-detector` branches from
   `9262aca`.
2. Verify spec + this plan exist at the paths declared in frontmatter.
3. Confirm paperclip issue `GIM-181` matches this slug.
4. Atomic-handoff PATCH `status=in_progress + assigneeAgentId=CodeReviewer + comment`
   per `paperclips/fragments/profiles/handoff.md`. GET-verify assignee
   afterwards.

**Acceptance**: paperclip issue `GIM-181` is `in_progress`, assigned to
CodeReviewer, with handoff comment referencing this plan path. GET-verify
log line in handoff comment.

**Files touched**: none.

**Tests**: none.

---

## Task 1 — Plan-first review (Phase 1.2 CR)

**Owner**: CodeReviewer

**Steps**:
1. Read spec and plan in full.
2. Verify each Phase 2 task has explicit acceptance + test + file list +
   commit boundary.
3. Verify file overlap with active CX slice (GIM-128) is zero — only
   `services/watchdog/*` and `docs/runbooks/watchdog-handoff-alerts.md`.
4. APPROVE → atomic-handoff to PythonEngineer.

**Acceptance**: full compliance checklist posted with `[x]` per item;
issue assigned to PythonEngineer with GET-verify.

---

## Task 2 — Models module + role taxonomy + strict markers

**Owner**: PythonEngineer

**Goal**: Lay down type contracts, role taxonomy with casefold lookup, and
pytest hygiene before any detection code is written.

**Steps**:
1. Create `src/gimle_watchdog/models.py` per spec §4.1.1:
   `FindingType` (StrEnum), three frozen-slots finding dataclasses with
   `Literal[FindingType.X]` discriminator, `Finding` union alias,
   `AlertResult`, `Comment`, `Agent`. All `datetime` fields tz-aware UTC.
2. Create `tests/test_models.py`:
   - `test_finding_type_values_are_stable` (assert string values).
   - `test_construct_each_finding_type_with_required_fields`.
   - `test_naive_datetime_in_comment_raises` (assert tz enforcement).
   - `test_alert_result_round_trips_via_dataclass_fields`.
3. Create `src/gimle_watchdog/role_taxonomy.py` per spec §4.3:
   `_ROLE_CLASS_RAW` (20 entries), casefold-normalized `_ROLE_CLASS`,
   `VALID_ROLE_CLASSES` frozenset, `classify(name) -> str | None`.
4. Create `tests/test_role_taxonomy.py`:
   - `test_classify_returns_role_class_for_each_known_agent`
     (parametrized over all 20 entries).
   - `test_classify_returns_none_for_unknown_agent`.
   - `test_classify_is_case_insensitive` (e.g. `pythonengineer`,
     `PYTHONENGINEER`).
   - `test_role_class_values_are_subset_of_valid_set`.
   - `test_role_taxonomy_covers_all_hired_agents` —
     `@pytest.mark.requires_paperclip`; calls live API; skipped when
     `PAPERCLIP_API_KEY` unset.
5. Update `pyproject.toml` `[tool.pytest.ini_options]`:
   - `addopts = "--strict-markers"` (or extend existing `addopts`).
   - `markers = ["requires_paperclip: requires PAPERCLIP_API_KEY against live API"]`.

**Acceptance**:
- `uv run pytest tests/test_models.py tests/test_role_taxonomy.py -q` green.
- `uv run mypy src/gimle_watchdog/models.py src/gimle_watchdog/role_taxonomy.py` clean.
- `uv run ruff check` clean.
- Typo test: rename a marker to `requires_paperclip_typo` in one test
  file, run pytest, confirm CI fails. Revert before commit.

**Files**:
- `src/gimle_watchdog/models.py` (NEW)
- `src/gimle_watchdog/role_taxonomy.py` (NEW)
- `tests/test_models.py` (NEW)
- `tests/test_role_taxonomy.py` (NEW)
- `pyproject.toml` (markers + strict-markers)

**Commit**: `feat(GIM-181): add models, role taxonomy, strict pytest markers`

---

## Task 3 — Paperclip API client extensions

**Owner**: PythonEngineer

**Goal**: `list_recent_comments` and `list_company_agents` returning
`models.Comment` and `models.Agent`.

**Steps**:
1. Extend `src/gimle_watchdog/paperclip.py`:
   - Import `Comment`, `Agent` from `models`.
   - `async def list_recent_comments(self, issue_id: str, limit: int = 5) -> list[Comment]`
     — `GET /api/issues/{id}/comments?limit={N}`.
   - `async def list_company_agents(self, company_id: str) -> list[Agent]`
     — `GET /api/companies/{id}/agents`.
   - Datetime parsing: `datetime.fromisoformat(s)` then assert
     `.tzinfo is not None`; raise `PaperclipClientError` if naive (server
     contract violation).
2. Add fixture files to `tests/fixtures/`:
   - `comments_normal_handoff.json` — current assignee posts a mention
     comment AND assigneeAgentId reflects the mentioned target (no
     finding expected).
   - `comments_comment_only_handoff.json` — current assignee posts a
     mention comment, assigneeAgentId unchanged (finding expected).
   - `comments_self_authored_alert.json` — comment authored by
     `null` (system) with watchdog alert template body (must NOT trigger
     detector).
   - `company_agents.json` — minimal hired-agent list with at least
     CTO, CodeReviewer, PythonEngineer.
3. Optional baseline fixtures (per spec §6.1 step 3): if Board has
   captured normative samples, save under `tests/fixtures/_normative/`
   with date-stamped filename. Skip if Board did not pre-capture.
4. Extend `tests/test_paperclip.py`:
   - `test_list_recent_comments_returns_parsed_objects`.
   - `test_list_recent_comments_handles_empty_response`.
   - `test_list_recent_comments_propagates_429`.
   - `test_list_recent_comments_rejects_naive_created_at`.
   - `test_list_company_agents_returns_parsed_objects`.
   - `test_list_company_agents_propagates_429`.
   - All using `httpx.MockTransport`.

**Acceptance**:
- `uv run pytest tests/test_paperclip.py -q` green.
- `uv run mypy src/gimle_watchdog/paperclip.py` clean.

**Files**:
- `src/gimle_watchdog/paperclip.py` (EXTEND)
- `tests/test_paperclip.py` (EXTEND)
- `tests/fixtures/comments_*.json` (NEW × 3)
- `tests/fixtures/company_agents.json` (NEW)

**Commit**: `feat(GIM-181): add paperclip client methods for comments and agents`

---

## Task 4 — State extension with cooldown + backward-compat

**Owner**: PythonEngineer

**Goal**: `alerted_handoffs` field with edge-triggered + cooldown methods;
pre-GIM-181 state files load cleanly.

**Steps**:
1. Extend `src/gimle_watchdog/state.py`:
   - Add `alerted_handoffs: dict[str, dict[str, Any]]` field (default
     factory).
   - Implement `_SNAPSHOT_KEYS` per spec §4.4.2.
   - `def has_active_alert(issue_id, ftype, current_snapshot) -> bool`
     — uses `_snapshot_matches`.
   - `def cooldown_elapsed(issue_id, ftype, now_server, cooldown_min) -> bool`.
   - `def record_handoff_alert(issue_id, ftype, snapshot, alerted_at) -> None`.
   - `def clear_handoff_alert(issue_id, ftype) -> None`.
   - Update `to_dict` / `from_dict`:
     - `from_dict` reads `raw.get("alerted_handoffs") or {}` (backward-compat).
     - All datetime values stored as ISO 8601 with tz offset.
2. Create fixture `tests/fixtures/issue_pre_gim180_state.json` —
   real-shape `state.json` from before this slice (no `alerted_handoffs`
   key).
3. Extend `tests/test_state.py`:
   - `test_has_active_alert_false_when_no_entry`.
   - `test_has_active_alert_true_when_snapshot_keys_match`.
   - `test_has_active_alert_false_when_assignee_id_changed`.
   - `test_has_active_alert_false_when_status_changed`.
   - `test_has_active_alert_true_when_updated_at_drifts_only` (regression
     against equality bug).
   - `test_has_active_alert_for_comment_only_uses_mention_uuid_and_comment_id`.
   - `test_cooldown_elapsed_false_when_recent`.
   - `test_cooldown_elapsed_true_when_past_threshold`.
   - `test_record_handoff_alert_persists_alerted_at`.
   - `test_clear_handoff_alert_removes_entry`.
   - `test_alerted_handoffs_round_trip_through_json`.
   - `test_state_loads_pre_gim180_json` — loads fixture, asserts
     `alerted_handoffs == {}`.

**Acceptance**:
- `uv run pytest tests/test_state.py -q` green.
- `uv run mypy src/gimle_watchdog/state.py` clean.

**Files**:
- `src/gimle_watchdog/state.py` (EXTEND)
- `tests/test_state.py` (EXTEND)
- `tests/fixtures/issue_pre_gim180_state.json` (NEW)

**Commit**: `feat(GIM-181): add cooldown-aware alerted_handoffs state`

---

## Task 5 — Detection logic with server-time anchoring + isolation

**Owner**: PythonEngineer

**Goal**: All three detectors, async signature, server-time anchoring,
precedence chain, per-issue fail isolation.

**Steps**:
1. Create `src/gimle_watchdog/detection_semantic.py`:
   - `_UUID_RE` regex per spec §4.2.2.
   - `def parse_mention_targets(body: str) -> list[str]`.
   - Per-detector functions:
     - `def _detect_comment_only_handoff(issue, comments) -> Finding | None`
     - `def _detect_wrong_assignee(issue, hired_ids, now_server) -> Finding | None`
     - `def _detect_review_owned_by_implementer(issue, name_by_id, now_server) -> Finding | None`
   - Precedence chain in `_evaluate_one_issue`:
     `wrong_assignee > comment_only > review_owned_by_implementer`;
     return at most one finding per issue.
   - `async def scan_handoff_inconsistencies(issues, fetch_comments,
     hired_ids, name_by_id, config, now_server) -> list[Finding]`:
     - Loop over `issues[:config.handoff_max_issues_per_tick]`.
     - Per-issue try/except (log + continue).
   - **No** `time.time()` or `datetime.now()` calls. Static-analysis
     check: `grep -nE "datetime\.now\(\)|time\.time\(\)" src/gimle_watchdog/detection_semantic.py`
     must be empty.
2. Mention author filter: in `_detect_comment_only_handoff`, only
   consider comments where `comment.author_agent_id ==
   issue.assigneeAgentId`. Test
   `test_mention_from_non_assignee_ignored` covers watchdog-self-trigger
   (author_agent_id is `None`) and mention from a different agent.
3. Create `tests/test_detection_semantic.py` with the following test
   classes (≥ 90% per-module coverage required):
   - **Mention parser** (6 tests): markdown link, bare URL with extra
     query string, multiple mentions, no mention, malformed UUID-like
     string, case-insensitive UUID.
   - **comment_only_handoff** (8 tests): happy path; mention from
     non-assignee → ignored; watchdog self-author (author None) →
     ignored; mention age below threshold; assignee already matches
     mention; status not eligible (`done`); no mentions in window;
     multiple mentions in different comments → most recent wins.
   - **wrong_assignee** (5 tests): happy path; assignee in hired list
     → no finding; assignee None → no finding; issue too young; status
     not eligible.
   - **review_owned_by_implementer** (6 tests): happy path; status not
     `in_review`; assignee resolves to reviewer; assignee not in hired
     list (precedence: wrong_assignee fires instead); assignee unknown
     name (`classify` returns None) → no finding; issue too young.
   - **Precedence** (3 tests): both wrong_assignee and comment_only
     conditions hold → wrong_assignee wins; both comment_only and
     review_owned hold → comment_only wins; only review_owned holds →
     review_owned emits.
   - **Server-time anchoring** (2 tests): detector outputs same age
     regardless of frozen `time.time()` value (use `freezegun` to set
     local clock to a wildly different time; assert age is server-derived).
   - **Failure isolation** (parametrized × 4): one detector raises in
     issue N — assert findings for issues N+1, N+2, N+3 still emitted.
     Test names:
     `test_scan_continues_when_comment_only_detector_raises_for_one_issue`,
     `test_scan_continues_when_wrong_assignee_detector_raises_for_one_issue`,
     `test_scan_continues_when_review_owned_detector_raises_for_one_issue`,
     `test_scan_continues_when_fetch_comments_raises_for_one_issue`.
   - **Max-issues cap** (1 test): list of 50 issues with
     `handoff_max_issues_per_tick=30` → only 30 evaluated.

**Acceptance**:
- `uv run pytest tests/test_detection_semantic.py -q` green.
- `uv run pytest --cov=src/gimle_watchdog/detection_semantic --cov-fail-under=90 tests/test_detection_semantic.py -q` green.
- `uv run mypy src/gimle_watchdog/detection_semantic.py` clean.
- `grep -nE "datetime\.now\(\)|time\.time\(\)" src/gimle_watchdog/detection_semantic.py` empty.

**Files**:
- `src/gimle_watchdog/detection_semantic.py` (NEW)
- `tests/test_detection_semantic.py` (NEW)
- `tests/fixtures/issue_wrong_assignee.json` (NEW)
- `tests/fixtures/issue_review_owned_by_implementer.json` (NEW)

**Commit**: `feat(GIM-181): semantic handoff detectors with precedence and server-time anchoring`

---

## Task 6 — Alert action with comment template

**Owner**: PythonEngineer

**Goal**: `post_handoff_alert` and pure renderer per spec §4.6.

**Steps**:
1. Extend `src/gimle_watchdog/actions.py`:
   - `def render_handoff_alert_comment(finding: Finding, version: str,
     ts: datetime, current_assignee_name: str | None) -> str` — pure;
     dispatches on `finding.type` to per-type `reason_short` /
     `expected_summary`.
   - `async def post_handoff_alert(client: PaperclipClient,
     finding: Finding, version: str, ts: datetime,
     current_assignee_name: str | None) -> AlertResult` — calls
     renderer + `client.post_comment(issue_id, body)`; emits
     `handoff_alert_posted` or `handoff_alert_failed` JSONL event.
2. Extend `tests/test_actions.py`:
   - `test_render_handoff_alert_comment_for_comment_only`.
   - `test_render_handoff_alert_comment_for_wrong_assignee`.
   - `test_render_handoff_alert_comment_for_review_owned`.
   - `test_render_handoff_alert_includes_grep_anchor` (literal
     `## Watchdog handoff alert — `).
   - `test_render_handoff_alert_handles_unknown_assignee_name`.
   - `test_post_handoff_alert_emits_jsonl_event_on_success`.
   - `test_post_handoff_alert_emits_jsonl_event_on_failure`.

**Acceptance**:
- `uv run pytest tests/test_actions.py -q` green.
- `uv run mypy src/gimle_watchdog/actions.py` clean.

**Files**:
- `src/gimle_watchdog/actions.py` (EXTEND)
- `tests/test_actions.py` (EXTEND)

**Commit**: `feat(GIM-181): post_handoff_alert action with grep-anchored template`

---

## Task 7 — Daemon integration: config, wiring, JSONL events, E2E

**Owner**: PythonEngineer

**Goal**: Wire pass 3 into `_tick`, emit declared JSONL events, ship E2E
lifecycle test, regression test for existing detectors.

**Steps**:
1. Extend `src/gimle_watchdog/config.py`:
   - Add fields per spec §4.7 (5 new fields plus `handoff_max_issues_per_tick`
     and `handoff_alert_cooldown_min`).
   - Strict validation: in `load_config`, check each YAML threshold key
     is a known dataclass field; unknown → `ConfigError`.
2. Extend `src/gimle_watchdog/daemon.py`:
   - Add `_run_handoff_pass(cfg, client, state, issues, ts_server,
     version) -> None` per spec §4.5.
   - `_tick` flow:
     - Capture `ts_server` from response `Date` header on first
       `/issues` GET (or `datetime.fromisoformat(<header>)`).
     - Call `_run_handoff_pass` only if `cfg.handoff_alert_enabled`.
     - Outer try/except logs `handoff_pass_failed` and continues with
       remaining work.
   - State-clear walk: after evaluating findings, iterate
     `state.alerted_handoffs.keys()`; for any `(issue_id, ftype)` whose
     finding is no longer active, call `state.clear_handoff_alert` and
     emit `handoff_alert_state_cleared` JSONL event.
3. Extend `tests/test_daemon.py`:
   - `test_tick_skips_handoff_pass_when_disabled` (no API calls to
     `/agents` or `/comments`).
   - `test_tick_posts_alert_for_new_finding`.
   - `test_tick_skips_alert_when_already_alerted_with_same_snapshot`.
   - `test_tick_skips_alert_when_cooldown_not_elapsed_with_changed_snapshot`
     (emits `handoff_alert_skipped_cooldown`).
   - `test_tick_re_alerts_when_cooldown_elapsed_with_changed_snapshot`.
   - `test_tick_clears_state_when_finding_no_longer_active`
     (emits `handoff_alert_state_cleared`).
   - `test_tick_e2e_lifecycle` — single fixture sequence: alert →
     finding cleared (assignee fixed) → finding reactivates (assignee
     broken again) → re-alert; assert event sequence on log.
   - `test_tick_continues_when_handoff_pass_raises` — patch
     `scan_handoff_inconsistencies` to raise; assert `_tick` still calls
     existing `scan_died_mid_work` and `scan_idle_hangs`.
   - `test_tick_runs_existing_detectors_when_handoff_enabled` —
     regression: with `handoff_alert_enabled=true`, fixture issue that
     would also fire `scan_died_mid_work` and `scan_idle_hangs` must
     fire all three detectors (no shadowing).
4. Extend `tests/test_config.py`:
   - `test_config_defaults_handoff_alert_disabled`.
   - `test_config_loads_handoff_thresholds`.
   - `test_config_rejects_unknown_threshold_key`.

**Acceptance**:
- `uv run pytest tests/test_daemon.py tests/test_config.py -q` green.
- `uv run pytest -q` (full suite) green.
- `uv run mypy src/gimle_watchdog/daemon.py src/gimle_watchdog/config.py` clean.

**Files**:
- `src/gimle_watchdog/config.py` (EXTEND)
- `src/gimle_watchdog/daemon.py` (EXTEND)
- `tests/test_daemon.py` (EXTEND)
- `tests/test_config.py` (EXTEND)

**Commit**: `feat(GIM-181): wire handoff detector into tick with JSONL events and E2E test`

---

## Task 8 — Runbook + README

**Owner**: PythonEngineer

**Goal**: Operator-facing documentation.

**Steps**:
1. Create `docs/runbooks/watchdog-handoff-alerts.md` covering:
   - What detector does (3 finding types, threshold semantics).
   - How to enable per company (YAML edit + tick restart).
   - How to interpret each alert type and what to PATCH to remediate.
   - Cooldown behavior (30 min default; how to override).
   - How to clear stuck state if needed: `gimle-watchdog status` shows
     active alerts; manual clear via state file edit (documented path
     and shape).
   - JSONL event reference table (mirror of spec §4.9).
   - Smoke procedure cross-reference to spec §6.4.
2. Extend `services/watchdog/README.md`:
   - Add "Semantic handoff detector (GIM-181)" section with one-line
     summary + link to runbook.

**Acceptance**: Files exist; manual review at Phase 3.1.

**Files**:
- `docs/runbooks/watchdog-handoff-alerts.md` (NEW)
- `services/watchdog/README.md` (EXTEND)

**Commit**: `docs(GIM-181): handoff detector runbook and README section`

---

## Task 9 — Final gate + handoff to CR

**Owner**: PythonEngineer

**Steps**:
1. From `services/watchdog/`, run all gates verbatim:
   ```bash
   uv run ruff check
   uv run ruff format --check
   uv run mypy src/
   uv run pytest -q
   uv run pytest --cov=src/gimle_watchdog --cov-fail-under=85 -q
   uv run pytest \
     --cov=src/gimle_watchdog/detection_semantic \
     --cov-fail-under=90 \
     tests/test_detection_semantic.py -q
   ```
2. Static check: `grep -nE "datetime\.now\(\)|time\.time\(\)" src/gimle_watchdog/detection_semantic.py`
   must print nothing.
3. Capture full output verbatim.
4. Verify scope: `git diff --name-only origin/develop...HEAD | sort -u`
   matches plan-declared file list.
5. Atomic-handoff to CodeReviewer per
   `paperclips/fragments/profiles/handoff.md`. Comment includes:
   - branch + HEAD SHA
   - full output of all gate commands
   - scope diff
   - GET-verify line for assignee.

**Acceptance**: all 6 commands exit 0; static-anchor grep empty; scope
matches plan; CR assignee GET-verified.

**Files touched**: none.

**Commit**: none (verification only).

---

## Phase 3.1 — CR mechanical review

**Owner**: CodeReviewer

**Mandatory steps**:
1. Re-run all 6 gate commands locally; assert output matches PE's claim
   within ±1 line (paste verbatim).
2. Run `gh pr checks` and paste full output.
3. Scope audit: `git diff --name-only origin/develop...HEAD | sort -u`;
   compare against plan-declared file list. Any out-of-scope file →
   REQUEST CHANGES per `feedback_silent_scope_reduction.md`.
4. **Live-API shape audit** (per spec §4.8). Run on a paperclip
   environment with `PAPERCLIP_API_KEY`:
   ```bash
   curl -sS "$PAPERCLIP_API_URL/api/issues/<sample-id>/comments?limit=2" \
     -H "Authorization: Bearer $PAPERCLIP_API_KEY" | jq .
   curl -sS "$PAPERCLIP_API_URL/api/companies/$COMPANY_ID/agents" \
     -H "Authorization: Bearer $PAPERCLIP_API_KEY" | jq '.[0:2]'
   ```
   Compare field names, types, and required-vs-optional with PE's
   fixture files in `tests/fixtures/comments_*.json` and
   `tests/fixtures/company_agents.json`. Any divergence → REQUEST
   CHANGES; closes the GIM-127-vector PE-as-oracle risk.
5. Static-anchor grep: confirm no `datetime.now()` or `time.time()` in
   `detection_semantic.py`.
6. APPROVE only when 1-5 are green; full compliance checklist with
   `[x]` per item + verbatim evidence.

**Atomic-handoff to OpusArchitectReviewer** with GET-verify.

---

## Phase 3.2 — Opus adversarial review

**Owner**: OpusArchitectReviewer

**Required attack vectors** (each documented with verdict):
1. **False-positive on legitimate fast handoff** — operator manual
   reassign under threshold.
2. **False-negative on plain text @AgentName** without UUID — by-design
   skip; verify graceful no-error.
3. **Race**: assignee changes between comment fetch and detector eval.
4. **Cooldown thrashing**: A→B→A→B alternating between ticks; assert
   cooldown bounds re-alert frequency.
5. **Time-source drift**: iMac local clock 1h ahead of server; assert
   server-time anchor produces correct age (no `datetime.now()` in
   detector code).
6. **Mention-author bypass**: synthetic comment with author_agent_id =
   issue.assigneeAgentId but body crafted as alert-template — ensure
   detector still parses (treating it as a real handoff signal — this
   is desired behavior, not a bug, but Opus should explicitly note it).
7. **Coverage gap**: any branch in `scan_handoff_inconsistencies`
   below 90% coverage flagged.
8. **State corruption**: malformed `alerted_handoffs` entry in JSON
   file — does state-file version-migration policy apply (rename
   .bak + start empty)?
9. **Resource budget**: cumulative API call count per tick under
   `handoff_max_issues_per_tick * handoff_comments_per_issue + 1` cap.
10. **Precedence shadow**: confirm `review_owned_by_implementer` cannot
    fire when `wrong_assignee` precondition holds (assignee not in
    hired list).

**Acceptance**: each attack documented with verdict (mitigated /
acceptable / change required). Atomic-handoff to QAEngineer with
GET-verify.

---

## Phase 4.1 — QA live smoke (iMac)

**Owner**: QAEngineer

**All steps execute on iMac via SSH.** Local-Mac evidence is not
acceptable per `feedback_pe_qa_evidence_fabrication.md`.

**Steps**:

1. **Identity capture** (top of evidence block):
   ```bash
   ssh imac-ssh.ant013.work 'date -u; hostname; uname -a; uptime'
   ```
2. **Pause production daemon** (so it does not act on smoke issues):
   ```bash
   ssh imac-ssh.ant013.work \
     'launchctl unload ~/Library/LaunchAgents/work.ant013.gimle-watchdog.plist'
   ```
3. **Build wheel + install in test virtualenv on iMac** (not touching
   production install):
   ```bash
   ssh imac-ssh.ant013.work bash -c '
     cd ~/Gimle-Palace && \
     git fetch origin && \
     git checkout feature/GIM-181-watchdog-handoff-detector && \
     cd services/watchdog && \
     uv sync && \
     uv pip install --target ~/.paperclip/test-watchdog .
   '
   ```
4. **Test config** with 1-min lookbacks and `handoff_alert_enabled: true`
   for the gimle company:
   ```bash
   ssh imac-ssh.ant013.work \
     'cp ~/.paperclip/watchdog-config.yaml \
        ~/.paperclip/watchdog-config-gim180-test.yaml'
   # edit handoff_* thresholds to 1 minute and enable
   ```
5. **Run drift-detection test** with API key set on iMac:
   ```bash
   ssh imac-ssh.ant013.work \
     'cd ~/Gimle-Palace/services/watchdog && \
      PAPERCLIP_API_KEY="$KEY" uv run pytest \
        -q -m requires_paperclip tests/test_role_taxonomy.py'
   ```
   Must exit 0. Capture output for evidence.
6. **Smoke procedure with trap-cleanup** (full bash script):
   ```bash
   set -euo pipefail
   SMOKE_IDS=()
   cleanup() {
     for id in "${SMOKE_IDS[@]}"; do
       paperclip-cli cancel "$id" --reason "GIM-181 smoke" || true
     done
     ssh imac-ssh.ant013.work \
       'launchctl load ~/Library/LaunchAgents/work.ant013.gimle-watchdog.plist'
   }
   trap cleanup EXIT

   ID_A=$(create_smoke_issue \
     --assignee 127068ee-b564-4b37-9370-616c81c63f35 --status todo \
     --title 'GIM-181 smoke A: comment-only handoff')
   SMOKE_IDS+=("$ID_A")
   post_comment "$ID_A" \
     '[@CodeReviewer](agent://bd2d7e20-7ed8-474c-91fc-353d610f4c52?i=eye)' \
     --as 127068ee-b564-4b37-9370-616c81c63f35

   ID_B=$(create_smoke_issue \
     --assignee 00000000-0000-0000-0000-000000000000 --status todo \
     --title 'GIM-181 smoke B: wrong assignee')
   SMOKE_IDS+=("$ID_B")

   ID_C=$(create_smoke_issue \
     --assignee 127068ee-b564-4b37-9370-616c81c63f35 --status in_review \
     --title 'GIM-181 smoke C: review owned by implementer')
   SMOKE_IDS+=("$ID_C")

   sleep 90  # let 1-min thresholds elapse

   ssh imac-ssh.ant013.work \
     '~/.paperclip/test-watchdog/bin/gimle-watchdog tick \
        --config ~/.paperclip/watchdog-config-gim180-test.yaml --once' \
     | tee /tmp/gim180-smoke-tick.log
   ```
7. **Capture evidence**:
   ```bash
   ssh imac-ssh.ant013.work \
     'cat ~/.paperclip/watchdog.log | \
      jq -c "select(.event==\"handoff_alert_posted\")" | tail -3'
   ssh imac-ssh.ant013.work "gh issue view $ID_A --comments | grep -A5 'Watchdog handoff alert'"
   ssh imac-ssh.ant013.work "gh issue view $ID_B --comments | grep -A5 'Watchdog handoff alert'"
   ssh imac-ssh.ant013.work "gh issue view $ID_C --comments | grep -A5 'Watchdog handoff alert'"
   ```
8. **Cleanup happens via trap** (smoke issues cancelled, production
   daemon reloaded).

**PR body `## QA Evidence` section** must include verbatim:
- Output of step 1 (`hostname` resolves to expected iMac).
- Output of step 5 (drift test).
- Output of step 7 (3 alert events with `event=handoff_alert_posted`,
  3 comment views).
- Confirmation that production daemon is loaded again after cleanup
  (`launchctl list | grep gimle-watchdog` returns one row).

**Acceptance**: PR body has all the above; CR Phase 3.2 spot-checks one
comment ID via paperclip API to confirm authenticity.

Atomic-handoff to CTO with GET-verify.

---

## Phase 4.2 — CTO merge

**Owner**: CTO

**Steps**:
1. `gh pr view --json mergeStateStatus,statusCheckRollup,reviewDecision,headRefOid`.
2. If `mergeStateStatus=CLEAN` and reviews APPROVED:
   `gh pr merge --squash --auto`.
3. After merge: post merged-SHA confirmation on issue and close.
4. iMac production deploy (if applicable) per
   `paperclips/scripts/imac-deploy.README.md` — but watchdog is not
   in the palace-mcp Docker image; new code is consumed via venv
   reinstall. Operator handles deploy; not a CTO task.

**Acceptance**: PR squash-merged; develop tip advanced; issue closed
with merge SHA in final comment.
