---
slug: watchdog-handoff-detector
status: proposed
branch: feature/GIM-181-watchdog-handoff-detector
paperclip_issue: 180
predecessor: 9262aca (fix: require atomic paperclip handoffs — PR #77)
date: 2026-05-03
---

# GIM-181 — Watchdog semantic handoff detector (Phase 1 alert-only)

## 1. Context

PR #77 (`9262aca`, 2026-05-03) added an **atomic-handoff rule** to
`paperclips/fragments/profiles/handoff.md`: agents must hand off by PATCHing
`status + assigneeAgentId + comment` in one API call, then GET-verify the
assignee. `@mention-only` handoff is invalid.

That fragment is the **preventive** half of the strategy. This slice adds the
**detective** half: a watchdog detector that catches when agents fail to
follow the rule, posts an alert comment on the affected issue, and tracks
state so it does not spam.

The current watchdog (`scan_died_mid_work`, `scan_idle_hangs`) operates at the
**mechanical** layer (process death, idle CPU, stalled stream-json). It does
not detect three documented failure modes from GIM-128 and GIM-179 operations:

1. **Comment-only handoff** — an agent posts `[@AgentB](agent://uuid?i=eye)`
   in a comment but does not PATCH `assigneeAgentId`. The next agent never
   wakes; the issue sits assigned to the original agent with no execution
   activity.
2. **Wrong `assigneeAgentId`** — handoff PATCHes a UUID that does not match
   any hired agent (typo, removed agent, or stale value). The issue is
   "assigned" but to nothing real.
3. **`in_review` owned by previous implementer** — phase 3.1 review should
   belong to a code-reviewer role, but the implementer (e.g. PythonEngineer)
   PATCHed `status=in_review` while keeping `assigneeAgentId=PE`. The
   reviewer never wakes.

This slice lands a detector for all three with **alert-only behavior**. No
auto-repair. Auto-repair is deferred to Phase 2 (separate slice) once Phase 1
proves detector accuracy.

**Predecessor SHA**: `9262aca` (develop tip, post-PR #77 merge).

**Related memory** (must read before implementation):
- `feedback_parallel_team_protocol.md` — operator's parallel-team rules
  (this slice runs Claude track in parallel with CX GIM-128).
- `feedback_pe_qa_evidence_fabrication.md` — GIM-127 incident; informs
  Phase 3.1 live-API shape audit and Phase 4.1 SSH-evidence mandate.
- `reference_paperclip_inbox_lite.md` — atomic handoff = `reassign + @-mention`
  combined; either alone is insufficient.
- `reference_paperclip_rest_endpoints.md` — verified API paths.
- `reference_agent_ids.md` — Claude team UUIDs.
- `paperclips/codex-agent-ids.env` — CX team UUIDs.

## 2. Goal

Add a fourth detection pass to the watchdog daemon `_tick` loop that
identifies semantic handoff inconsistencies and posts a single alert comment
per `(issue_id, finding_type)` transition. Detector must be:

- **Edge-triggered with cooldown** — alert when finding appears; clear state
  when finding disappears; re-alert on a new occurrence only when both
  snapshot keys differ AND `now − last_alerted_at >= cooldown`.
- **Server-time anchored** — all age calculations use server timestamps
  (`issue.updatedAt`, `comment.createdAt`); no `time.time()` or local clock
  is used for detector logic.
- **Per-issue fail-isolated** — exception while evaluating one issue must
  not stop evaluation of remaining issues in the same tick.
- **Side-effect-bounded** — Phase 1 may only POST comments; it must not
  PATCH `assigneeAgentId`, `status`, or any other issue field.
- **Configurable per company** — opt-in `handoff_alert_enabled: bool` per
  company; existing deployments do not start posting alerts on upgrade.
- **Backward-compatible state** — pre-GIM-181 `state.json` files load
  successfully; missing `alerted_handoffs` field defaults to empty dict.

## 3. Non-Goals

- **NOT** auto-repairing inconsistent handoffs. Auto-repair is Phase 2.
- **NOT** detecting other agent-misbehavior categories (missing QA evidence,
  missing branch-spec gate, etc.). Those would be separate slices.
- **NOT** changing the existing `scan_died_mid_work` or `scan_idle_hangs`
  paths; existing detector behavior must be preserved (regression test
  required, see §5).
- **NOT** modifying paperclip server, paperclip fragments, or any agent role
  file.
- **NOT** introducing a new HTTP-mock library; tests use `httpx.MockTransport`
  per `tests/test_paperclip.py:20` pattern.
- **NOT** depending on local-clock alignment for detection accuracy. Local
  clock may be skewed; only event-emission timestamps use it.

## 4. Architecture

### 4.1 Module layout (additive)

```
services/watchdog/src/gimle_watchdog/
├── models.py                    (NEW — ~60 LOC: Finding, FindingType,
│                                 AlertResult, Comment, Agent dataclasses
│                                 — extracted to break circular imports
│                                 between actions and detection_semantic)
├── role_taxonomy.py             (NEW — ~80 LOC)
├── detection_semantic.py        (NEW — ~280 LOC)
├── detection.py                 (UNCHANGED)
├── actions.py                   (EXTEND — +~60 LOC)
├── state.py                     (EXTEND — +~70 LOC)
├── daemon.py                    (EXTEND — +~50 LOC)
├── config.py                    (EXTEND — +~40 LOC)
└── paperclip.py                 (EXTEND — +~50 LOC)

services/watchdog/tests/
├── test_models.py               (NEW — ~80 LOC)
├── test_detection_semantic.py   (NEW — ~700 LOC)
├── test_role_taxonomy.py        (NEW — ~140 LOC)
├── fixtures/
│   ├── comments_comment_only_handoff.json
│   ├── comments_normal_handoff.json
│   ├── comments_self_authored_alert.json
│   ├── issue_wrong_assignee.json
│   ├── issue_review_owned_by_implementer.json
│   ├── issue_pre_gim180_state.json
│   └── company_agents.json
├── test_paperclip.py            (EXTEND)
├── test_state.py                (EXTEND — backward-compat + cooldown)
├── test_daemon.py               (EXTEND — E2E + regression + isolation)
└── test_config.py               (EXTEND — extra-key validation)

docs/runbooks/watchdog-handoff-alerts.md (NEW)
```

### 4.1.1 Type contracts (`models.py`)

```python
from datetime import datetime
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal


class FindingType(StrEnum):
    COMMENT_ONLY_HANDOFF = "comment_only_handoff"
    WRONG_ASSIGNEE = "wrong_assignee"
    REVIEW_OWNED_BY_IMPLEMENTER = "review_owned_by_implementer"


@dataclass(frozen=True, slots=True)
class CommentOnlyHandoffFinding:
    type: Literal[FindingType.COMMENT_ONLY_HANDOFF]
    issue_id: str
    issue_number: int
    current_assignee_id: str
    mentioned_agent_id: str
    mention_comment_id: str
    mention_author_agent_id: str
    mention_age_seconds: int  # server-derived: issue.updatedAt - comment.createdAt
    issue_status: str


@dataclass(frozen=True, slots=True)
class WrongAssigneeFinding:
    type: Literal[FindingType.WRONG_ASSIGNEE]
    issue_id: str
    issue_number: int
    bogus_assignee_id: str
    issue_status: str
    age_seconds: int  # server-derived: now_server - issue.updatedAt


@dataclass(frozen=True, slots=True)
class ReviewOwnedByImplementerFinding:
    type: Literal[FindingType.REVIEW_OWNED_BY_IMPLEMENTER]
    issue_id: str
    issue_number: int
    implementer_assignee_id: str
    implementer_role_name: str
    implementer_role_class: Literal["implementer"]
    age_seconds: int


Finding = (
    CommentOnlyHandoffFinding
    | WrongAssigneeFinding
    | ReviewOwnedByImplementerFinding
)


@dataclass(frozen=True, slots=True)
class AlertResult:
    finding_type: FindingType
    issue_id: str
    posted: bool
    comment_id: str | None
    error: str | None


@dataclass(frozen=True, slots=True)
class Comment:
    id: str
    body: str
    author_agent_id: str | None
    created_at: datetime  # tz-aware UTC


@dataclass(frozen=True, slots=True)
class Agent:
    id: str
    name: str
    status: str  # "idle" | "running" | "error" | etc — opaque pass-through
```

All `datetime` fields are tz-aware UTC. Parsers must call
`datetime.fromisoformat(s).astimezone(timezone.utc)` and reject naive values.

### 4.2 Detection logic

#### 4.2.1 Server-time anchoring (applies to all detectors)

No detector reads local `time.time()` or `datetime.now()`. Age windows are
derived from server timestamps:

- For comments: `comment_age = issue.updatedAt - comment.createdAt`. If
  `issue.updatedAt < comment.createdAt`, age is treated as 0 (clock skew on
  paperclip server itself; not our problem).
- For issues without comment dependency: `age = now_server - issue.updatedAt`,
  where `now_server` is the `Date` header from the most recent paperclip API
  response in the current tick (cached from initial `GET /issues` call).

This makes detection independent of iMac clock skew (operator's iMac was on
+0600 per memory; user moved to +0500; drift unbounded).

#### 4.2.2 Mention parser

Canonical paperclip mention format: `[@DisplayName](agent://uuid?i=icon)`.
The parser extracts UUIDs only. Display name and icon are ignored.

```python
_UUID_RE = re.compile(
    r"agent://([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
    r"[0-9a-f]{4}-[0-9a-f]{12})",
    re.IGNORECASE,
)

def parse_mention_targets(comment_body: str) -> list[str]:
    """Extract authoritative agent UUIDs from comment body.

    Plain-text @AgentName without a UUID URL is not parsed (by design;
    UUID is the only authoritative identifier).
    """
    return [m.group(1).lower() for m in _UUID_RE.finditer(comment_body)]
```

Code-fence and HTML-comment filtering is **not** included in Phase 1 (low
expected frequency; deferred to followup if observed). Documented as known
risk in §8.

#### 4.2.3 Mention author filter (anti-self-trigger)

A mention is considered for `comment_only_handoff` only when the comment's
`author_agent_id` equals the issue's current `assigneeAgentId`. This filter
protects against:

- Watchdog's own alert comments (whose body contains the next-agent
  `agent://uuid` for operator readability) — watchdog has no
  `author_agent_id` matching the assignee, so its mentions are ignored.
- Operator/Board comments injected manually — same reason; only the
  current owner's @-mentions count as a handoff signal.

#### 4.2.4 `comment_only_handoff` detector

Trigger condition (all must hold):
1. `issue.status` ∈ {`todo`, `in_progress`, `in_review`}.
2. Within the last `handoff_comments_per_issue` comments, there exists a
   comment `c` such that:
   - `c.author_agent_id == issue.assigneeAgentId`, AND
   - `parse_mention_targets(c.body)` is non-empty.
3. Let `c*` be the most-recent qualifying comment. Let `target_uuid` be the
   first UUID in `parse_mention_targets(c*.body)`.
4. `target_uuid != issue.assigneeAgentId` (the mentioned agent is not the
   one already assigned).
5. `(issue.updatedAt - c*.createdAt).total_seconds() / 60 >=
   handoff_comment_lookback_min` (default 5).

Output: `CommentOnlyHandoffFinding`.

#### 4.2.5 `wrong_assignee` detector

Trigger condition:
1. `issue.status` ∈ {`todo`, `in_progress`, `in_review`}.
2. `issue.assigneeAgentId is not None`.
3. `issue.assigneeAgentId not in hired_agent_ids`.
4. `(now_server - issue.updatedAt).total_seconds() / 60 >=
   handoff_wrong_assignee_min` (default 3).

Output: `WrongAssigneeFinding`.

#### 4.2.6 `review_owned_by_implementer` detector

Trigger condition:
1. `issue.status == "in_review"`.
2. `issue.assigneeAgentId in hired_agent_ids` (otherwise wrong_assignee
   wins by precedence — see §4.2.7).
3. Resolve assignee name via `agent_name_by_id[issue.assigneeAgentId]`.
4. `role_taxonomy.classify(name) == "implementer"`.
5. `(now_server - issue.updatedAt).total_seconds() / 60 >=
   handoff_review_owner_min` (default 5).

Output: `ReviewOwnedByImplementerFinding`.

#### 4.2.7 Precedence chain

When more than one detector would fire on the same issue in the same tick,
emit only the highest-precedence finding:

```
wrong_assignee  >  comment_only_handoff  >  review_owned_by_implementer
```

Rationale: `wrong_assignee` is the strongest signal (the assignee literally
does not exist); reporting other findings on top adds noise without
information. `comment_only_handoff` is more actionable than
`review_owned_by_implementer` because it identifies the intended next agent.

`scan_handoff_inconsistencies` returns at most one `Finding` per issue per
tick.

#### 4.2.8 Async signature

```python
async def scan_handoff_inconsistencies(
    issues: list[Issue],
    fetch_comments: Callable[[str], Awaitable[list[Comment]]],
    hired_agent_ids: frozenset[str],
    agent_name_by_id: Mapping[str, str],
    config: HandoffConfig,
    now_server: datetime,
) -> list[Finding]:
    ...
```

All call sites must `await`. The function uses `asyncio.gather` only when
`fetch_comments` cost dominates; baseline implementation may iterate
sequentially since per-tick issue count is bounded (see §4.7
`handoff_max_issues_per_tick`).

#### 4.2.9 Per-issue fail isolation

```python
async def scan_handoff_inconsistencies(...) -> list[Finding]:
    findings: list[Finding] = []
    for issue in issues[:config.handoff_max_issues_per_tick]:
        try:
            finding = await _evaluate_one_issue(...)
            if finding is not None:
                findings.append(finding)
        except Exception as exc:
            logger.warning(
                "handoff_pass_failed_for_issue",
                extra={"issue_id": issue.id, "error": repr(exc)},
            )
            # Continue with remaining issues.
    return findings
```

Test coverage in `test_detection_semantic.py` includes a parametrized test
that injects an exception in each detector path and asserts subsequent
issues still evaluate.

### 4.3 Role taxonomy

`role_taxonomy.py` defines a hardcoded mapping. Keys are stored
casefold-normalized; lookup is casefold-normalized — protects against
operator-written config typos and display-name capitalization drift.

```python
_ROLE_CLASS_RAW: dict[str, str] = {
    # Claude team
    "CTO": "cto",
    "CodeReviewer": "reviewer",
    "OpusArchitectReviewer": "reviewer",
    "PythonEngineer": "implementer",
    "MCPEngineer": "implementer",
    "InfraEngineer": "implementer",
    "BlockchainEngineer": "implementer",
    "QAEngineer": "qa",
    "ResearchAgent": "research",
    "TechnicalWriter": "writer",
    "SecurityAuditor": "reviewer",
    # CX team
    "CXCTO": "cto",
    "CXCodeReviewer": "reviewer",
    "CodexArchitectReviewer": "reviewer",
    "CXPythonEngineer": "implementer",
    "CXMCPEngineer": "implementer",
    "CXInfraEngineer": "implementer",
    "CXQAEngineer": "qa",
    "CXResearchAgent": "research",
    "CXTechnicalWriter": "writer",
}

_ROLE_CLASS = {k.casefold(): v for k, v in _ROLE_CLASS_RAW.items()}

VALID_ROLE_CLASSES = frozenset({
    "cto", "reviewer", "implementer", "qa", "research", "writer"
})


def classify(agent_name: str) -> str | None:
    return _ROLE_CLASS.get(agent_name.casefold())
```

**Drift-detection test** (`test_role_taxonomy_covers_all_hired_agents`):
calls `GET /api/companies/{id}/agents` against the live paperclip API and
asserts every returned `agent.name` casefold-resolves to a role class.
Marker: `@pytest.mark.requires_paperclip`. Skipped when `PAPERCLIP_API_KEY`
unset. **Phase 4.1 QA must run this test on iMac with API key set** as part
of live-smoke evidence.

### 4.4 State

#### 4.4.1 Schema

`State` adds `alerted_handoffs: dict[str, dict[str, Any]]` keyed by
`f"{issue_id}:{finding_type.value}"`. Value:

```json
{
  "alerted_at": "2026-05-03T12:34:56+00:00",
  "snapshot": {
    "assigneeAgentId": "...",
    "status": "in_review",
    "mention_comment_id": "abc-123",      // comment_only_handoff only
    "mention_target_uuid": "..."          // comment_only_handoff only
  }
}
```

All `datetime` values stored as ISO 8601 with explicit UTC offset.

#### 4.4.2 Per-finding equality keys

Snapshot equality is computed only over the keys listed below; other dict
fields are ignored. This prevents `updatedAt` drift, body edits, or
unrelated fields from triggering re-alert.

| Finding type | Snapshot keys |
|---|---|
| `comment_only_handoff` | `assigneeAgentId, status, mention_comment_id, mention_target_uuid` |
| `wrong_assignee` | `assigneeAgentId, status` |
| `review_owned_by_implementer` | `assigneeAgentId, status` |

Implementation:

```python
_SNAPSHOT_KEYS: dict[FindingType, tuple[str, ...]] = {
    FindingType.COMMENT_ONLY_HANDOFF: (
        "assigneeAgentId", "status",
        "mention_comment_id", "mention_target_uuid",
    ),
    FindingType.WRONG_ASSIGNEE: ("assigneeAgentId", "status"),
    FindingType.REVIEW_OWNED_BY_IMPLEMENTER: ("assigneeAgentId", "status"),
}

def _snapshot_matches(stored: dict, current: dict, ftype: FindingType) -> bool:
    keys = _SNAPSHOT_KEYS[ftype]
    return all(stored.get(k) == current.get(k) for k in keys)
```

#### 4.4.3 Cooldown

A finding that produces the same snapshot as the stored alert is **never**
re-alerted (edge-triggered).

A finding that produces a **different** snapshot is re-alerted only when
`now_server − stored.alerted_at >= handoff_alert_cooldown_min`
(default 30 min).

Decision matrix:

| Stored entry | Finding present | Snapshot equal | Cooldown elapsed | Action |
|---|---|---|---|---|
| no | yes | — | — | **alert + record** |
| no | no | — | — | no-op |
| yes | yes | yes | — | skip (already alerted) |
| yes | yes | no | no | skip (cooldown) — log `handoff_alert_skipped_cooldown` |
| yes | yes | no | yes | **re-alert + record (new snapshot, new alerted_at)** |
| yes | no | — | — | **clear entry** — log `handoff_alert_state_cleared` |

#### 4.4.4 Backward-compat

`State.from_dict` must accept pre-GIM-181 JSON files (no `alerted_handoffs`
key) by defaulting to `{}`. Test `test_state_loads_pre_gim180_json` asserts
this against fixture `tests/fixtures/issue_pre_gim180_state.json`.

#### 4.4.5 State methods

```python
@dataclass
class State:
    # ... existing fields ...
    alerted_handoffs: dict[str, dict[str, Any]] = field(default_factory=dict)

    def has_active_alert(
        self, issue_id: str, ftype: FindingType, current_snapshot: dict,
    ) -> bool:
        """True iff entry exists AND snapshot keys match."""

    def cooldown_elapsed(
        self, issue_id: str, ftype: FindingType,
        now_server: datetime, cooldown_min: int,
    ) -> bool:
        """True iff entry exists AND alerted_at older than cooldown."""

    def record_handoff_alert(
        self, issue_id: str, ftype: FindingType,
        snapshot: dict, alerted_at: datetime,
    ) -> None: ...

    def clear_handoff_alert(
        self, issue_id: str, ftype: FindingType,
    ) -> None: ...
```

### 4.5 Daemon integration

Order of detector passes in `_tick`:

1. `scan_idle_hangs` (existing, unchanged)
2. `scan_died_mid_work` (existing, unchanged)
3. **`scan_handoff_inconsistencies`** (new) — async; reads cached
   `issues` list from pass 2 to avoid re-fetching; only runs when
   `cfg.handoff_alert_enabled` for the company.

Pass 3 flow:

```python
async def _run_handoff_pass(cfg, client, state, issues, ts_server, version):
    if not cfg.handoff_alert_enabled:
        return
    try:
        agents = await client.list_company_agents(cfg.company_id)
        hired_ids = frozenset(a.id for a in agents)
        name_by_id = {a.id: a.name for a in agents}
        comment_fetcher = _make_comment_fetcher(
            client, cfg.handoff_comments_per_issue,
        )
        findings = await scan_handoff_inconsistencies(
            issues, comment_fetcher, hired_ids, name_by_id, cfg, ts_server,
        )
        for finding in findings:
            await _maybe_post_alert(finding, client, state, ts_server, cfg, version)
        _clear_stale_alert_entries(state, findings, issues)
    except Exception as exc:
        logger.error(
            "handoff_pass_failed",
            extra={"company_id": cfg.company_id, "error": repr(exc)},
        )
        # Existing detectors (passes 1-2) are unaffected.
```

Pass 3 must NOT block or alter passes 1-2 even if it crashes. Test
`test_tick_continues_when_handoff_pass_raises` asserts this.

### 4.6 Alert comment template

```markdown
## Watchdog handoff alert — {finding_type}

Reason: {reason_short}

Detected state:
- Issue: GIM-{issue_number} (status={status})
- Current assignee: {current_assignee_id} ({current_assignee_name})
- Expected: {expected_summary}

Detector: gimle-watchdog v{version}, tick {timestamp_iso_utc}.
This alert is informational; no automatic repair will be performed.
```

Per finding type:

| Type | `reason_short` | `expected_summary` |
|---|---|---|
| `comment_only_handoff` | `@-mention from current assignee but assigneeAgentId not updated` | `assigneeAgentId should be {mentioned_agent_id} per comment {mention_comment_id}` |
| `wrong_assignee` | `assigneeAgentId is not a hired agent` | `valid hired agent UUID required` |
| `review_owned_by_implementer` | `in_review with implementer-class assignee` | `reassign to a code-reviewer-class agent` |

The literal heading `## Watchdog handoff alert — {finding_type}` is the
grep anchor for QA evidence and the mention-author filter (the watchdog has
no `author_agent_id` so its own template is automatically excluded by
§4.2.3 even without explicit filtering).

### 4.7 Configuration

Per-company additions to `~/.paperclip/watchdog-config.yaml`:

```yaml
companies:
  - id: 9d8f432c-...
    thresholds:
      # ... existing ...
      handoff_alert_enabled: false                 # default; opt-in
      handoff_comment_lookback_min: 5
      handoff_wrong_assignee_min: 3
      handoff_review_owner_min: 5
      handoff_comments_per_issue: 5
      handoff_max_issues_per_tick: 30              # safety cap
      handoff_alert_cooldown_min: 30               # re-alert min interval
```

Removed from earlier draft: `last_known_valid_assignee_id` field
(unused in alert-only Phase 1).

#### 4.7.1 Strict config validation

`config.load_config` must reject unknown keys under `thresholds:`. Each
company's threshold dict is validated against the dataclass field set;
unknown keys raise `ConfigError("unknown threshold key: <name>")`. This
catches typos like `handoff_review_ownr_min`.

Test: `test_config_rejects_unknown_threshold_key`.

### 4.8 Paperclip API client

Two new methods on `PaperclipClient`:

```python
async def list_recent_comments(
    self, issue_id: str, limit: int = 5,
) -> list[Comment]:
    """GET /api/issues/{issue_id}/comments?limit={N}.
    Returns Comment dataclasses with tz-aware UTC created_at.
    Sorted descending by created_at."""

async def list_company_agents(self, company_id: str) -> list[Agent]:
    """GET /api/companies/{company_id}/agents.
    Returns Agent dataclasses for all hired agents."""
```

HTTP error handling matches existing methods (429 backoff, 5xx transient
retry). `Comment` and `Agent` shapes are defined in `models.py` (§4.1.1).

**Phase 3.1 CR live-API audit** (per #10 in CR review): CR must execute
the following before APPROVE and paste verbatim output in the review
comment:

```bash
curl -sS "$PAPERCLIP_API_URL/api/issues/<sample-issue-id>/comments?limit=2" \
  -H "Authorization: Bearer $PAPERCLIP_API_KEY" | jq .
curl -sS "$PAPERCLIP_API_URL/api/companies/$COMPANY_ID/agents" \
  -H "Authorization: Bearer $PAPERCLIP_API_KEY" | jq '.[0:2]'
```

CR confirms PE's fixture shape matches the live response shape (field
names, types, optional vs required). Discrepancy → REQUEST CHANGES.

### 4.9 JSONL event schema

The daemon emits these structured events (one JSON line per event) to
`~/.paperclip/watchdog.log`. Phase 4.1 QA grep relies on this contract.

| `event` | Fields | When |
|---|---|---|
| `handoff_alert_posted` | `issue_id, issue_number, finding_type, comment_id, snapshot` | After successful POST `/comments` |
| `handoff_alert_failed` | `issue_id, finding_type, error` | On POST failure |
| `handoff_alert_skipped_cooldown` | `issue_id, finding_type, last_alerted_at, cooldown_min` | Snapshot mismatch but cooldown not elapsed |
| `handoff_alert_state_cleared` | `issue_id, finding_type` | Finding no longer active; state entry removed |
| `handoff_pass_failed` | `company_id, error` | Outermost try/except in pass 3 |
| `handoff_pass_failed_for_issue` | `issue_id, error` | Per-issue try/except inside `scan_handoff_inconsistencies` |

All events include the standard daemon fields (`ts`, `level`, `tick_id`).

## 5. Acceptance criteria

1. **Three detectors implemented** with per-module unit-test coverage ≥ 90%.
   CI enforces `pytest --cov=src/gimle_watchdog/detection_semantic
   --cov-fail-under=90` as a separate step from the global gate.
2. **Per-finding snapshot equality** verified by unit tests covering
   `assigneeAgentId` change, `status` change, and (for comment_only) both
   `mention_comment_id` and `mention_target_uuid` change. `updatedAt` drift
   alone must NOT trigger re-alert (regression-style test required).
3. **Cooldown logic** verified by 4 tests: no entry/finding active alert;
   matching snapshot skip; mismatch under cooldown skip; mismatch after
   cooldown re-alert.
4. **Edge-triggered clear** verified by E2E lifecycle test in
   `test_daemon.py`: alert → assignee fixed → state cleared → assignee
   broken again → re-alert.
5. **Per-issue fail isolation** verified by parametrized test across the 3
   detectors plus a sequence test (`issue N raises, issue N+1 still
   evaluates`).
6. **Async chain end-to-end** — `scan_handoff_inconsistencies`,
   `_run_handoff_pass`, and all client methods are `async def`; type
   checking under `mypy --strict` passes.
7. **Server-time anchoring** — `grep -nE "datetime\.now\(\)|time\.time\(\)"
   src/gimle_watchdog/detection_semantic.py` returns zero matches.
8. **Mention author filter** — test `test_mention_from_non_assignee_ignored`
   asserts watchdog's own alert template is not parsed as a handoff signal.
9. **Role taxonomy completeness** — `test_role_taxonomy_covers_all_hired_agents`
   passes when run on iMac with `PAPERCLIP_API_KEY` set (Phase 4.1 evidence).
10. **Backward-compat state load** — `test_state_loads_pre_gim180_json` against
    a fixture file mimicking pre-GIM-181 state shape.
11. **Strict config validation** — `test_config_rejects_unknown_threshold_key`
    catches `handoff_review_ownr_min` typo.
12. **Strict pytest markers** — `pyproject.toml` `[tool.pytest.ini_options]`
    contains `addopts = "--strict-markers"` and registers
    `requires_paperclip` marker. CI fails on unknown marker.
13. **Existing detector regression** — `test_tick_runs_all_passes` asserts
    that with `handoff_alert_enabled=true`, both `scan_died_mid_work` and
    `scan_idle_hangs` still execute on a fixture issue that exercises both
    older paths.
14. **No new HTTP mock library** — `pyproject.toml` diff shows no addition
    of `respx`, `pytest-httpx`, or similar.
15. **Type contracts in `models.py`** — `Finding` is a tagged union
    (`Literal[FindingType.X]` discriminator); `mypy --strict` rejects
    incorrect type construction.
16. **JSONL event schema** — every event listed in §4.9 has at least one
    test that emits it and asserts field presence.
17. **Lint / format / type / test gates** — `uv run ruff check`,
    `uv run ruff format --check`, `uv run mypy src/`,
    `uv run pytest --cov=src/gimle_watchdog --cov-fail-under=85` all green.
18. **Live smoke on iMac** — operator-driven smoke per §6.4 with SSH-from-
    iMac evidence captured in PR body.

## 6. Verification plan

### 6.1 Pre-implementation

1. Confirm branch starts from `9262aca` (post-PR #77).
2. Verify `httpx.MockTransport` pattern in `tests/test_paperclip.py:20`.
3. Manual curl: `GET /api/companies/{id}/agents` returns `{id, name, status}`
   shape — Board records sample response in
   `tests/fixtures/_normative/agents_response_2026-05-03.json` for PE
   reference. (Optional baseline; CR audits live API in Phase 3.1
   regardless.)
4. Verify `_normative/` directory is gitignored OR explicitly committed
   with date-stamped filename so it is not mistaken for fresh API truth.

### 6.2 Per-task gates

Each task in the implementation plan ends with a green test target before
the next task starts. See plan file.

### 6.3 Post-implementation gates (run by PE before handoff)

From `services/watchdog/`:

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

All must exit 0. Output is pasted verbatim in handoff comment to CR.

### 6.4 Live smoke (Phase 4.1, on iMac)

QA performs the full procedure on iMac via SSH. Local-Mac execution is
**not acceptable** evidence (per `feedback_pe_qa_evidence_fabrication.md`).

#### 6.4.1 Pre-flight

1. `ssh imac-ssh.ant013.work 'date -u; hostname; uname -a; uptime'` —
   capture for evidence block.
2. `ssh imac-ssh.ant013.work 'launchctl unload \
   ~/Library/LaunchAgents/work.ant013.gimle-watchdog.plist'` — pause
   production daemon for the smoke window. Production must be paused so
   it does not act on disposable smoke issues during the test.
3. Create a test config:
   `cp ~/.paperclip/watchdog-config.yaml \
   ~/.paperclip/watchdog-config-gim180-test.yaml` and edit to set
   `handoff_alert_enabled: true` plus 1-min lookbacks for all thresholds.
4. Build and install in test virtualenv on iMac (do not touch production
   install): `cd services/watchdog && uv sync && uv pip install .`.

#### 6.4.2 Smoke procedure (with trap-cleanup)

```bash
set -euo pipefail
SMOKE_IDS=()
cleanup() {
  for id in "${SMOKE_IDS[@]}"; do
    paperclip-cli cancel "$id" --reason "GIM-181 smoke cleanup" || true
  done
  ssh imac-ssh.ant013.work \
    'launchctl load ~/Library/LaunchAgents/work.ant013.gimle-watchdog.plist'
}
trap cleanup EXIT

# Smoke A: comment-only handoff
ID_A=$(create_smoke_issue 'PythonEngineer' 'todo')
SMOKE_IDS+=("$ID_A")
post_comment "$ID_A" "[@CodeReviewer](agent://bd2d7e20-7ed8-474c-91fc-353d610f4c52?i=eye)"

# Smoke B: wrong assignee
ID_B=$(create_smoke_issue '00000000-0000-0000-0000-000000000000' 'todo')
SMOKE_IDS+=("$ID_B")

# Smoke C: review_owned_by_implementer
ID_C=$(create_smoke_issue 'PythonEngineer' 'in_review')
SMOKE_IDS+=("$ID_C")

# Wait for thresholds (1 min lookbacks per test config)
sleep 90

# Run watchdog tick from iMac (production daemon is paused)
ssh imac-ssh.ant013.work \
  '~/.paperclip/test-watchdog/bin/gimle-watchdog tick \
     --config ~/.paperclip/watchdog-config-gim180-test.yaml --once' \
  > /tmp/gim180-smoke-tick.log

# Drift-detection test (live API; must pass)
ssh imac-ssh.ant013.work \
  'cd ~/Gimle-Palace/services/watchdog && \
   PAPERCLIP_API_KEY=$KEY uv run pytest \
     -q -m requires_paperclip tests/test_role_taxonomy.py'
```

`trap cleanup EXIT` ensures smoke issues cancel and production daemon
reloads even if the script aborts mid-run.

#### 6.4.3 Evidence block (mandatory shape)

PR body `## QA Evidence` section must include verbatim:

```
$ ssh imac-ssh.ant013.work 'date -u; hostname; uname -a'
<output>

$ ssh imac-ssh.ant013.work 'cat ~/.paperclip/watchdog.log | \
  jq -c "select(.event==\"handoff_alert_posted\")" | tail -3'
<3 events, one per smoke issue, with snapshot field>

$ gh issue view <smoke-A-id> --comments | grep -A5 "Watchdog handoff alert"
<alert comment text>

$ gh issue view <smoke-B-id> --comments | grep -A5 "Watchdog handoff alert"
<alert comment text>

$ gh issue view <smoke-C-id> --comments | grep -A5 "Watchdog handoff alert"
<alert comment text>

$ ssh imac-ssh.ant013.work 'cd ~/Gimle-Palace/services/watchdog && \
  PAPERCLIP_API_KEY=$KEY uv run pytest -q -m requires_paperclip \
  tests/test_role_taxonomy.py'
1 passed
```

`hostname` must resolve to the iMac (operator confirms expected name).
`gh issue view` lines must come from a session that ran via SSH on iMac
(or with iMac's own gh credentials), not local. CR Phase 3.2 may sample-
verify by re-fetching one comment via paperclip API and matching IDs.

## 7. Out of scope (deferred)

- **Auto-repair Phase 2** — same detectors but call atomic PATCH instead
  of POST comment. Reactivation trigger: Phase 1 alerts run for ≥ 7 days
  in production with zero false positives in operator log review.
- **Other agent-misbehavior detectors** (missing QA evidence, missing
  branch-spec gate, etc.). Reactivation trigger: documented incidents
  with concrete failure mode + frequency.
- **Code-fence / quote / HTML-comment filtering in mention parser** —
  current parser may catch a UUID inside a code block. Reactivation
  trigger: ≥ 1 false positive in 7 days observed via operator log review.
- **Multi-company alert aggregation** — independent per company.
- **Webhook-driven alerts** — current design polls every 2 min.
- **Weekly scheduled drift-detection Action** — overkill for current
  hire frequency; runs in Phase 4.1 instead. Reactivation trigger: hire
  rate exceeds one new role per 2 weeks.
- **Test-company isolation for smokes** — production daemon pause
  (§6.4.1 step 2) is sufficient for current single-operator setup.
  Reactivation trigger: multiple operators using paperclip concurrently.

## 8. Risks and mitigations

- **Race fetch→post** — between fetching comments and posting alert, the
  issue state may change. Phase 1 accepts this as a known false-positive
  risk (alert posted on a now-resolved finding). Mitigation: cooldown
  prevents repeated FP on the same issue. Documented.
- **False-positive on legitimate fast handoff** — operator reassigns
  manually within 5 min: detector skips because `comment_age_seconds <
  threshold`. Mitigation: edge-triggered logic + thresholds tuned
  generously.
- **Drift in role taxonomy when new agent hired** — drift-detection test
  fails on iMac in Phase 4.1 when API exposes a new agent without
  mapping. Mitigation: clear failure message tells operator which name
  and which role-class to add.
- **Comment fetch overhead** — bounded by `handoff_max_issues_per_tick`
  (default 30) × `handoff_comments_per_issue` (default 5) + 1 agent
  list = ≤ 151 extra API requests per 2-min tick. Existing watchdog
  already polls `/issues`; this is a small marginal cost.
- **Mention parser misses non-canonical formats** — only canonical
  `agent://uuid` is recognized. Plain text `@AgentName` is by-design
  not parsed (UUID is the only authoritative identifier).
- **Code-fence false positive** — UUID inside a code block triggers
  detector. Bounded by mention-author filter (§4.2.3): only the current
  assignee's mentions count, so the only way to FP is for the assignee
  to write `agent://uuid` in their own code block. Acceptable for Phase 1.
- **Cumulative alert spam without auto-repair** — operator sees alert
  but does not act; daemon respects cooldown so spam is bounded to one
  alert per 30 min per `(issue_id, finding_type)`.
- **State file corruption** — malformed `alerted_handoffs` entry. Existing
  state-file handling has version-migration policy
  (rename `.bak` + start empty + WARN); applies here.

## 9. Rollout

1. Phase 1.1 CTO Formalize.
2. Phase 1.2 CR Plan-first review.
3. Phase 2 Implementation — TDD through plan tasks T2-T9.
4. Phase 3.1 CR Mechanical — including live-API shape audit (§4.8).
5. Phase 3.2 Opus Adversarial — false-positive scenarios, race conditions,
   detector ordering, time-source drift, cooldown thrashing.
6. Phase 4.1 QA Live smoke on iMac with SSH-from-iMac evidence.
7. Phase 4.2 CTO Merge.

## 10. Open questions

(none — all earlier open questions resolved by §4.7 defaults and
deferrals listed in §7.)
