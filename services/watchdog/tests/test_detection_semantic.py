"""Tests for watchdog.detection_semantic — all three detectors."""

from __future__ import annotations

import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from freezegun import freeze_time

from gimle_watchdog import detection_semantic as ds
from gimle_watchdog.models import (
    CommentOnlyHandoffFinding,
    Comment,
    FindingType,
    InfraBlockFinding,
    OwnerlessCompletionFinding,
    ReviewOwnedByImplementerFinding,
    StaleBundleFinding,
    WrongAssigneeFinding,
)
from gimle_watchdog.paperclip import Issue

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PE_ID = "127068ee-b564-4b37-9370-616c81c63f35"
CR_ID = "bd2d7e20-7ed8-474c-91fc-353d610f4c52"
CTO_ID = "7fb0fdbb-e17f-4487-a4da-16993a907bec"
BOGUS_ID = "00000000-0000-0000-0000-000000000001"

NOW = datetime(2026, 5, 3, 12, 0, tzinfo=timezone.utc)

HIRED_IDS: frozenset[str] = frozenset({PE_ID, CR_ID, CTO_ID})
NAME_BY_ID: dict[str, str] = {
    PE_ID: "PythonEngineer",
    CR_ID: "CodeReviewer",
    CTO_ID: "CTO",
}


def _issue(
    *,
    id: str = "issue-1",
    status: str = "in_progress",
    assignee_id: str | None = PE_ID,
    updated_at: datetime = NOW,
    issue_number: int = 1,
) -> Issue:
    return Issue(
        id=id,
        assignee_agent_id=assignee_id,
        execution_run_id=None,
        status=status,
        updated_at=updated_at,
        issue_number=issue_number,
    )


def _comment(
    *,
    id: str = "cmt-1",
    body: str = "",
    author_id: str | None = PE_ID,
    created_at: datetime = NOW - timedelta(minutes=10),
) -> Comment:
    return Comment(id=id, body=body, author_agent_id=author_id, created_at=created_at)


def _cfg(**kwargs: object) -> ds.HandoffDetectionConfig:
    defaults = dict(
        handoff_alert_enabled=True,
        handoff_comment_lookback_min=5,
        handoff_wrong_assignee_min=3,
        handoff_review_owner_min=5,
        handoff_comments_per_issue=5,
        handoff_max_issues_per_tick=30,
        handoff_alert_cooldown_min=30,
    )
    defaults.update(kwargs)
    return ds.HandoffDetectionConfig(**defaults)  # type: ignore[arg-type]


async def _fetch_none(issue_id: str) -> list[Comment]:
    return []


# ---------------------------------------------------------------------------
# Mention parser
# ---------------------------------------------------------------------------


def test_parse_mention_markdown_link():
    body = f"[@CR](agent://{CR_ID}?i=eye) please review."
    assert ds.parse_mention_targets(body) == [CR_ID]


def test_parse_mention_bare_url_with_extra_query():
    body = f"agent://{CR_ID}?i=eye&extra=1"
    assert ds.parse_mention_targets(body) == [CR_ID]


def test_parse_mention_multiple():
    body = f"[@A](agent://{CR_ID}?i=eye) and [@B](agent://{PE_ID}?i=code)"
    result = ds.parse_mention_targets(body)
    assert result == [CR_ID, PE_ID]


def test_parse_mention_no_match():
    assert ds.parse_mention_targets("just text, no agent links") == []


def test_parse_mention_malformed_uuid_not_matched():
    assert ds.parse_mention_targets("agent://not-a-uuid") == []


def test_parse_mention_case_insensitive_uuid():
    upper = CR_ID.upper()
    body = f"agent://{upper}"
    result = ds.parse_mention_targets(body)
    assert result == [CR_ID.lower()]


# ---------------------------------------------------------------------------
# comment_only_handoff detector
# ---------------------------------------------------------------------------

_CO_BODY = f"[@CR](agent://{CR_ID}?i=eye) please review."


def test_comment_only_handoff_happy_path():
    issue = _issue(status="in_progress", assignee_id=PE_ID, updated_at=NOW)
    comments = [_comment(body=_CO_BODY, author_id=PE_ID, created_at=NOW - timedelta(minutes=10))]
    result = ds._detect_comment_only_handoff(issue, comments, lookback_min=5)
    assert isinstance(result, CommentOnlyHandoffFinding)
    assert result.issue_id == "issue-1"
    assert result.mentioned_agent_id == CR_ID
    assert result.current_assignee_id == PE_ID


def test_mention_from_non_assignee_ignored():
    issue = _issue(assignee_id=PE_ID)
    comments = [_comment(body=_CO_BODY, author_id=CR_ID, created_at=NOW - timedelta(minutes=10))]
    assert ds._detect_comment_only_handoff(issue, comments, lookback_min=5) is None


def test_mention_from_none_author_ignored():
    """Watchdog self-authored alert: authorAgentId is None — must not trigger."""
    issue = _issue(assignee_id=PE_ID)
    comments = [_comment(body=_CO_BODY, author_id=None, created_at=NOW - timedelta(minutes=10))]
    assert ds._detect_comment_only_handoff(issue, comments, lookback_min=5) is None


def test_mention_age_below_threshold_no_finding():
    issue = _issue(updated_at=NOW)
    comments = [_comment(body=_CO_BODY, author_id=PE_ID, created_at=NOW - timedelta(minutes=3))]
    assert ds._detect_comment_only_handoff(issue, comments, lookback_min=5) is None


def test_mention_target_already_matches_assignee_no_finding():
    issue = _issue(assignee_id=CR_ID)
    body = f"[@CR](agent://{CR_ID}?i=eye)"
    comments = [_comment(body=body, author_id=CR_ID, created_at=NOW - timedelta(minutes=10))]
    assert ds._detect_comment_only_handoff(issue, comments, lookback_min=5) is None


def test_comment_only_status_done_no_finding():
    issue = _issue(status="done", assignee_id=PE_ID, updated_at=NOW)
    comments = [_comment(body=_CO_BODY, author_id=PE_ID, created_at=NOW - timedelta(minutes=10))]
    assert ds._detect_comment_only_handoff(issue, comments, lookback_min=5) is None


def test_comment_only_no_mentions_in_window_no_finding():
    issue = _issue()
    comments = [_comment(body="no mentions here", author_id=PE_ID)]
    assert ds._detect_comment_only_handoff(issue, comments, lookback_min=5) is None


def test_comment_only_multiple_comments_most_recent_wins():
    issue = _issue(updated_at=NOW)
    old = _comment(
        id="old",
        body=f"[@CR](agent://{CR_ID}?i=eye)",
        author_id=PE_ID,
        created_at=NOW - timedelta(minutes=20),
    )
    recent = _comment(
        id="new",
        body=f"[@CTO](agent://{CTO_ID}?i=crown)",
        author_id=PE_ID,
        created_at=NOW - timedelta(minutes=8),
    )
    result = ds._detect_comment_only_handoff(issue, [old, recent], lookback_min=5)
    assert result is not None
    assert result.mention_comment_id == "new"
    assert result.mentioned_agent_id == CTO_ID


# ---------------------------------------------------------------------------
# wrong_assignee detector
# ---------------------------------------------------------------------------


def test_wrong_assignee_happy_path():
    issue = _issue(assignee_id=BOGUS_ID, updated_at=NOW - timedelta(minutes=5))
    result = ds._detect_wrong_assignee(issue, HIRED_IDS, NOW, min_age_min=3)
    assert isinstance(result, WrongAssigneeFinding)
    assert result.bogus_assignee_id == BOGUS_ID


def test_wrong_assignee_in_hired_list_no_finding():
    issue = _issue(assignee_id=PE_ID, updated_at=NOW - timedelta(minutes=5))
    assert ds._detect_wrong_assignee(issue, HIRED_IDS, NOW, min_age_min=3) is None


def test_wrong_assignee_none_no_finding():
    issue = _issue(assignee_id=None, updated_at=NOW - timedelta(minutes=5))
    assert ds._detect_wrong_assignee(issue, HIRED_IDS, NOW, min_age_min=3) is None


def test_wrong_assignee_issue_too_young_no_finding():
    issue = _issue(assignee_id=BOGUS_ID, updated_at=NOW - timedelta(minutes=1))
    assert ds._detect_wrong_assignee(issue, HIRED_IDS, NOW, min_age_min=3) is None


def test_wrong_assignee_status_not_eligible_no_finding():
    issue = _issue(status="done", assignee_id=BOGUS_ID, updated_at=NOW - timedelta(minutes=5))
    assert ds._detect_wrong_assignee(issue, HIRED_IDS, NOW, min_age_min=3) is None


# ---------------------------------------------------------------------------
# review_owned_by_implementer detector
# ---------------------------------------------------------------------------


def test_review_owned_happy_path():
    issue = _issue(status="in_review", assignee_id=PE_ID, updated_at=NOW - timedelta(minutes=7))
    result = ds._detect_review_owned_by_implementer(
        issue, HIRED_IDS, NAME_BY_ID, NOW, min_age_min=5
    )
    assert isinstance(result, ReviewOwnedByImplementerFinding)
    assert result.implementer_assignee_id == PE_ID
    assert result.implementer_role_class == "implementer"


def test_review_owned_status_not_in_review_no_finding():
    issue = _issue(status="in_progress", assignee_id=PE_ID, updated_at=NOW - timedelta(minutes=7))
    assert (
        ds._detect_review_owned_by_implementer(issue, HIRED_IDS, NAME_BY_ID, NOW, min_age_min=5)
        is None
    )


def test_review_owned_reviewer_assignee_no_finding():
    issue = _issue(status="in_review", assignee_id=CR_ID, updated_at=NOW - timedelta(minutes=7))
    assert (
        ds._detect_review_owned_by_implementer(issue, HIRED_IDS, NAME_BY_ID, NOW, min_age_min=5)
        is None
    )


def test_review_owned_assignee_not_in_hired_no_finding():
    """wrong_assignee wins by precedence; review_owned should not double-fire."""
    issue = _issue(status="in_review", assignee_id=BOGUS_ID, updated_at=NOW - timedelta(minutes=7))
    assert (
        ds._detect_review_owned_by_implementer(issue, HIRED_IDS, NAME_BY_ID, NOW, min_age_min=5)
        is None
    )


def test_review_owned_unknown_name_no_finding():
    issue = _issue(status="in_review", assignee_id=PE_ID, updated_at=NOW - timedelta(minutes=7))
    name_by_id = {}  # no mapping
    assert (
        ds._detect_review_owned_by_implementer(issue, HIRED_IDS, name_by_id, NOW, min_age_min=5)
        is None
    )


def test_review_owned_issue_too_young_no_finding():
    issue = _issue(status="in_review", assignee_id=PE_ID, updated_at=NOW - timedelta(minutes=2))
    assert (
        ds._detect_review_owned_by_implementer(issue, HIRED_IDS, NAME_BY_ID, NOW, min_age_min=5)
        is None
    )


# ---------------------------------------------------------------------------
# Precedence chain
# ---------------------------------------------------------------------------


async def _make_fetch(comments_map: dict[str, list[Comment]]):
    async def fetch(issue_id: str) -> list[Comment]:
        return comments_map.get(issue_id, [])

    return fetch


async def test_precedence_wrong_assignee_beats_comment_only():
    # Issue has wrong assignee AND has @mention comment
    issue = _issue(
        id="i1", assignee_id=BOGUS_ID, status="in_progress", updated_at=NOW - timedelta(minutes=5)
    )
    comments = [_comment(body=_CO_BODY, author_id=BOGUS_ID, created_at=NOW - timedelta(minutes=10))]
    fetch = await _make_fetch({"i1": comments})
    findings = await ds.scan_handoff_inconsistencies(
        [issue], fetch, HIRED_IDS, NAME_BY_ID, _cfg(), NOW
    )
    assert len(findings) == 1
    assert findings[0].type == FindingType.WRONG_ASSIGNEE


async def test_precedence_comment_only_beats_review_owned():
    # Issue is in_review with PE, AND PE posted @mention
    issue = _issue(id="i1", assignee_id=PE_ID, status="in_review", updated_at=NOW)
    comments = [_comment(body=_CO_BODY, author_id=PE_ID, created_at=NOW - timedelta(minutes=10))]
    fetch = await _make_fetch({"i1": comments})
    findings = await ds.scan_handoff_inconsistencies(
        [issue], fetch, HIRED_IDS, NAME_BY_ID, _cfg(), NOW
    )
    assert len(findings) == 1
    assert findings[0].type == FindingType.COMMENT_ONLY_HANDOFF


async def test_precedence_only_review_owned_emits():
    issue = _issue(
        id="i1", assignee_id=PE_ID, status="in_review", updated_at=NOW - timedelta(minutes=7)
    )
    fetch = await _make_fetch({"i1": []})
    findings = await ds.scan_handoff_inconsistencies(
        [issue], fetch, HIRED_IDS, NAME_BY_ID, _cfg(), NOW
    )
    assert len(findings) == 1
    assert findings[0].type == FindingType.REVIEW_OWNED_BY_IMPLEMENTER


# ---------------------------------------------------------------------------
# Server-time anchoring
# ---------------------------------------------------------------------------


@freeze_time("2050-01-01T00:00:00Z")
async def test_age_is_server_derived_not_local_clock():
    """Age in WrongAssigneeFinding must use now_server, not local time.time()."""
    updated = datetime(2026, 5, 3, 11, 55, tzinfo=timezone.utc)
    issue = _issue(assignee_id=BOGUS_ID, status="in_progress", updated_at=updated)
    result = ds._detect_wrong_assignee(issue, HIRED_IDS, NOW, min_age_min=3)
    assert result is not None
    expected_age = int((NOW - updated).total_seconds())
    assert result.age_seconds == expected_age


@freeze_time("2050-01-01T00:00:00Z")
def test_comment_only_age_server_derived():
    """mention_age_seconds must use issue.updated_at - comment.created_at."""
    issue = _issue(updated_at=NOW)
    comment_created = NOW - timedelta(minutes=10)
    comments = [_comment(body=_CO_BODY, author_id=PE_ID, created_at=comment_created)]
    result = ds._detect_comment_only_handoff(issue, comments, lookback_min=5)
    assert result is not None
    expected = int((NOW - comment_created).total_seconds())
    assert result.mention_age_seconds == expected


# ---------------------------------------------------------------------------
# Failure isolation
# ---------------------------------------------------------------------------


async def test_scan_continues_when_fetch_comments_raises_for_one_issue():
    issue_err = _issue(
        id="issue-err", status="in_review", assignee_id=PE_ID, updated_at=NOW - timedelta(minutes=7)
    )
    issue_ok1 = _issue(
        id="issue-ok1",
        status="in_review",
        assignee_id=PE_ID,
        updated_at=NOW - timedelta(minutes=7),
        issue_number=2,
    )
    issue_ok2 = _issue(
        id="issue-ok2",
        status="in_review",
        assignee_id=PE_ID,
        updated_at=NOW - timedelta(minutes=7),
        issue_number=3,
    )

    async def fetch(issue_id: str) -> list[Comment]:
        if issue_id == "issue-err":
            raise RuntimeError("simulated fetch failure")
        return []

    findings = await ds.scan_handoff_inconsistencies(
        [issue_err, issue_ok1, issue_ok2], fetch, HIRED_IDS, NAME_BY_ID, _cfg(), NOW
    )
    found_ids = {f.issue_id for f in findings}
    assert "issue-ok1" in found_ids
    assert "issue-ok2" in found_ids


async def test_scan_continues_when_wrong_assignee_detector_raises_for_one_issue():
    real_detect = ds._detect_wrong_assignee
    issues = [
        _issue(
            id=f"i{n}", assignee_id=BOGUS_ID, updated_at=NOW - timedelta(minutes=5), issue_number=n
        )
        for n in range(4)
    ]

    def raising_detect(issue, hired_ids, now_server, min_age_min):
        if issue.id == "i0":
            raise RuntimeError("injected")
        return real_detect(issue, hired_ids, now_server, min_age_min)

    with patch.object(ds, "_detect_wrong_assignee", side_effect=raising_detect):
        findings = await ds.scan_handoff_inconsistencies(
            issues, _fetch_none, HIRED_IDS, NAME_BY_ID, _cfg(), NOW
        )
    found_ids = {f.issue_id for f in findings}
    assert "i0" not in found_ids
    assert {"i1", "i2", "i3"}.issubset(found_ids)


async def test_scan_continues_when_comment_only_detector_raises_for_one_issue():
    issues = [
        _issue(id=f"i{n}", assignee_id=PE_ID, status="in_progress", updated_at=NOW, issue_number=n)
        for n in range(4)
    ]
    comments_body = _CO_BODY

    async def fetch(issue_id: str) -> list[Comment]:
        return [
            _comment(body=comments_body, author_id=PE_ID, created_at=NOW - timedelta(minutes=10))
        ]

    def raising_co(issue, comments, lookback_min):
        if issue.id == "i0":
            raise RuntimeError("injected")
        return None

    with patch.object(ds, "_detect_comment_only_handoff", side_effect=raising_co):
        findings = await ds.scan_handoff_inconsistencies(
            issues, fetch, HIRED_IDS, NAME_BY_ID, _cfg(), NOW
        )
    assert not any(f.issue_id == "i0" for f in findings)


async def test_scan_continues_when_review_owned_detector_raises_for_one_issue():
    real_ro = ds._detect_review_owned_by_implementer
    issues = [
        _issue(
            id=f"i{n}",
            assignee_id=PE_ID,
            status="in_review",
            updated_at=NOW - timedelta(minutes=7),
            issue_number=n,
        )
        for n in range(4)
    ]

    def raising_ro(issue, hired_ids, name_by_id, now_server, min_age_min):
        if issue.id == "i0":
            raise RuntimeError("injected")
        return real_ro(issue, hired_ids, name_by_id, now_server, min_age_min)

    with patch.object(ds, "_detect_review_owned_by_implementer", side_effect=raising_ro):
        findings = await ds.scan_handoff_inconsistencies(
            issues, _fetch_none, HIRED_IDS, NAME_BY_ID, _cfg(), NOW
        )
    found_ids = {f.issue_id for f in findings}
    assert "i0" not in found_ids
    assert {"i1", "i2", "i3"}.issubset(found_ids)


# ---------------------------------------------------------------------------
# Max-issues cap
# ---------------------------------------------------------------------------


async def test_max_issues_cap_limits_evaluation():
    issues = [
        _issue(
            id=f"i{n}", assignee_id=BOGUS_ID, updated_at=NOW - timedelta(minutes=5), issue_number=n
        )
        for n in range(50)
    ]
    cfg = _cfg(handoff_max_issues_per_tick=30)
    findings = await ds.scan_handoff_inconsistencies(
        issues, _fetch_none, HIRED_IDS, NAME_BY_ID, cfg, NOW
    )
    assert len(findings) == 30


# ---------------------------------------------------------------------------
# Ownerless completion detector
# ---------------------------------------------------------------------------

_CLAUDE_QA_ID = ds._CLAUDE_QA_UUID
_CODEX_QA_ID = ds._CODEX_QA_UUID


def _qa_comment(body: str, author_id: str = _CLAUDE_QA_ID) -> Comment:
    return _comment(body=body, author_id=author_id)


def test_ownerless_fires_when_done_without_qa_evidence():
    issue = _issue(status="done")
    result = ds._detect_ownerless_completion(issue, [])
    assert isinstance(result, OwnerlessCompletionFinding)
    assert result.issue_id == issue.id


def test_ownerless_suppressed_by_phase_41_qa_pass_from_claude_qa():
    issue = _issue(status="done")
    body = "## Phase 4.1 — QA PASS ✅\nEvidence: commit SHA abc123"
    comments = [_qa_comment(body, author_id=_CLAUDE_QA_ID)]
    result = ds._detect_ownerless_completion(issue, comments)
    assert result is None


def test_ownerless_suppressed_by_phase_41_qa_pass_from_codex_qa():
    issue = _issue(status="done")
    body = "Phase 4.1 QA Pass — all green"
    comments = [_qa_comment(body, author_id=_CODEX_QA_ID)]
    result = ds._detect_ownerless_completion(issue, comments)
    assert result is None


def test_ownerless_not_suppressed_by_qa_comment_without_pass():
    issue = _issue(status="done")
    body = "## Phase 4.1 — QA FAIL ❌"
    comments = [_qa_comment(body)]
    result = ds._detect_ownerless_completion(issue, comments)
    assert isinstance(result, OwnerlessCompletionFinding)


def test_ownerless_not_suppressed_by_non_qa_author():
    issue = _issue(status="done")
    body = "## Phase 4.1 — QA PASS ✅"
    comments = [_comment(body=body, author_id=PE_ID)]  # wrong author
    result = ds._detect_ownerless_completion(issue, comments)
    assert isinstance(result, OwnerlessCompletionFinding)


def test_ownerless_no_finding_when_not_done():
    for status in ("todo", "in_progress", "in_review"):
        issue = _issue(status=status)
        result = ds._detect_ownerless_completion(issue, [])
        assert result is None, f"should not fire for status={status}"


# ---------------------------------------------------------------------------
# Infra-block detector
# ---------------------------------------------------------------------------


def test_infra_block_fires_on_cloudflare_1010():
    issue = _issue()
    c = _comment(body="Error 1010 from Cloudflare", created_at=NOW - timedelta(minutes=10))
    result = ds._detect_infra_block(issue, [c], lookback_min=60, now=NOW)
    assert isinstance(result, InfraBlockFinding)
    assert result.error_kind == "cloudflare_1010"
    assert result.actionable is False


def test_infra_block_fires_on_429():
    issue = _issue()
    c = _comment(body="HTTP 429 Too Many Requests", created_at=NOW - timedelta(minutes=5))
    result = ds._detect_infra_block(issue, [c], lookback_min=60, now=NOW)
    assert isinstance(result, InfraBlockFinding)
    assert result.error_kind == "rate_limit_429"


def test_infra_block_fires_on_502():
    issue = _issue()
    c = _comment(body="Got a 502 Bad Gateway", created_at=NOW - timedelta(minutes=5))
    result = ds._detect_infra_block(issue, [c], lookback_min=60, now=NOW)
    assert isinstance(result, InfraBlockFinding)
    assert result.error_kind == "service_unavailable"


def test_infra_block_fires_on_cloudflare_generic():
    issue = _issue()
    c = _comment(body="Cloudflare is blocking the request", created_at=NOW - timedelta(minutes=5))
    result = ds._detect_infra_block(issue, [c], lookback_min=60, now=NOW)
    assert isinstance(result, InfraBlockFinding)
    assert result.error_kind == "cloudflare_generic"


def test_infra_block_no_finding_outside_lookback():
    issue = _issue()
    c = _comment(body="Error 1010", created_at=NOW - timedelta(minutes=90))
    result = ds._detect_infra_block(issue, [c], lookback_min=60, now=NOW)
    assert result is None


def test_infra_block_no_finding_for_clean_comment():
    issue = _issue()
    c = _comment(body="All good, proceeding normally", created_at=NOW - timedelta(minutes=5))
    result = ds._detect_infra_block(issue, [c], lookback_min=60, now=NOW)
    assert result is None


def test_infra_block_no_finding_for_empty_comments():
    issue = _issue()
    result = ds._detect_infra_block(issue, [], lookback_min=60, now=NOW)
    assert result is None


# ---------------------------------------------------------------------------
# Stale-bundle detector
# ---------------------------------------------------------------------------

_SHA_OLD = "aaa1111111111111111111111111111111111111"
_SHA_NEW = "bbb2222222222222222222222222222222222222"


def _write_deploy_log(path: Path, sha: str, ts: datetime) -> None:
    path.write_text(f"{ts.isoformat()}\tmain_sha={sha}\n")


def test_stale_bundle_fires_when_sha_differs_and_old(tmp_path: Path):
    log = tmp_path / "imac-agents-deploy.log"
    deployed_at = NOW - timedelta(hours=25)
    _write_deploy_log(log, _SHA_OLD, deployed_at)
    with patch.object(
        ds.subprocess,
        "run",
        return_value=subprocess.CompletedProcess([], 0, stdout=_SHA_NEW + "\n", stderr=""),
    ):
        result = ds.detect_stale_bundle(log, tmp_path, threshold_hours=24, now=NOW)
    assert isinstance(result, StaleBundleFinding)
    assert result.deployed_sha == _SHA_OLD
    assert result.current_sha == _SHA_NEW
    assert result.stale_hours > 24.0


def test_stale_bundle_no_finding_when_sha_matches(tmp_path: Path):
    log = tmp_path / "imac-agents-deploy.log"
    deployed_at = NOW - timedelta(hours=25)
    _write_deploy_log(log, _SHA_OLD, deployed_at)
    with patch.object(
        ds.subprocess,
        "run",
        return_value=subprocess.CompletedProcess([], 0, stdout=_SHA_OLD + "\n", stderr=""),
    ):
        result = ds.detect_stale_bundle(log, tmp_path, threshold_hours=24, now=NOW)
    assert result is None


def test_stale_bundle_no_finding_within_threshold(tmp_path: Path):
    log = tmp_path / "imac-agents-deploy.log"
    deployed_at = NOW - timedelta(hours=10)
    _write_deploy_log(log, _SHA_OLD, deployed_at)
    with patch.object(
        ds.subprocess,
        "run",
        return_value=subprocess.CompletedProcess([], 0, stdout=_SHA_NEW + "\n", stderr=""),
    ):
        result = ds.detect_stale_bundle(log, tmp_path, threshold_hours=24, now=NOW)
    assert result is None


def test_stale_bundle_no_finding_when_log_missing(tmp_path: Path):
    log = tmp_path / "nonexistent.log"
    result = ds.detect_stale_bundle(log, tmp_path, threshold_hours=24, now=NOW)
    assert result is None


def test_stale_bundle_no_finding_when_git_fails(tmp_path: Path):
    log = tmp_path / "imac-agents-deploy.log"
    deployed_at = NOW - timedelta(hours=25)
    _write_deploy_log(log, _SHA_OLD, deployed_at)
    with patch.object(
        ds.subprocess,
        "run",
        return_value=subprocess.CompletedProcess([], 1, stdout="", stderr="fatal: not a repo"),
    ):
        result = ds.detect_stale_bundle(log, tmp_path, threshold_hours=24, now=NOW)
    assert result is None
