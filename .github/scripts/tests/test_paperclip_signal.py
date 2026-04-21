"""Tests for paperclip_signal.py — added incrementally per plan tasks."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
import yaml as _yaml
from pytest_httpx import HTTPXMock

import paperclip_signal as ps


# ---------------------------------------------------------------------------
# Task 4: Infrastructure smoke-test
# ---------------------------------------------------------------------------


def test_infrastructure_loads(load_fixture):
    """Smoke-test: fixtures load via conftest helper."""
    payload = load_fixture("workflow_run_success")
    assert payload["workflow_run"]["conclusion"] == "success"


# ---------------------------------------------------------------------------
# Task 5: Config loader
# ---------------------------------------------------------------------------


def test_config_parse_valid(tmp_path: Path):
    """Valid config parses into Config with expected rules and bot_authors."""
    cfg = tmp_path / "signals.yml"
    cfg.write_text(
        """
version: 1
company_id: 9d8f432c-ff7d-4e3a-bbe3-3cd355f73b64
rules:
  - trigger: ci.success
    target: issue_assignee
  - trigger: pr.review
    target: issue_assignee
bot_authors:
  - github-actions[bot]
  - ant013
"""
    )
    config = ps.load_config(cfg)
    assert config.version == 1
    assert config.company_id == "9d8f432c-ff7d-4e3a-bbe3-3cd355f73b64"
    assert len(config.rules) == 2
    assert config.rules[0].trigger == "ci.success"
    assert config.rules[0].target == "issue_assignee"
    assert config.bot_authors == ["github-actions[bot]", "ant013"]


def test_config_parse_unknown_trigger_raises(tmp_path: Path):
    """trigger not in {ci.success, pr.review, qa.smoke_complete} → ConfigError."""
    cfg = tmp_path / "signals.yml"
    cfg.write_text(
        """
version: 1
company_id: x
rules:
  - trigger: not.a.real.trigger
    target: issue_assignee
bot_authors: []
"""
    )
    with pytest.raises(ps.ConfigError) as excinfo:
        ps.load_config(cfg)
    assert "not.a.real.trigger" in str(excinfo.value)


def test_config_parse_pr_review_comment_rejected(tmp_path: Path):
    """pr.review_comment as a config trigger → ConfigError (must be folded to pr.review)."""
    cfg = tmp_path / "signals.yml"
    cfg.write_text(
        """
version: 1
company_id: x
rules:
  - trigger: pr.review_comment
    target: issue_assignee
bot_authors: []
"""
    )
    with pytest.raises(ps.ConfigError) as excinfo:
        ps.load_config(cfg)
    assert "pr.review_comment" in str(excinfo.value)
    assert "pr.review" in str(excinfo.value)


def test_config_parse_unknown_target_raises(tmp_path: Path):
    """target not in {issue_assignee, role(...)} → ConfigError."""
    cfg = tmp_path / "signals.yml"
    cfg.write_text(
        """
version: 1
company_id: x
rules:
  - trigger: ci.success
    target: bogus_target
bot_authors: []
"""
    )
    with pytest.raises(ps.ConfigError):
        ps.load_config(cfg)


def test_config_parse_role_target_parses(tmp_path: Path):
    """role(Name) target parses successfully; runtime raises NotImplementedError later."""
    cfg = tmp_path / "signals.yml"
    cfg.write_text(
        """
version: 1
company_id: x
rules:
  - trigger: ci.success
    target: role(Translator)
bot_authors: []
"""
    )
    config = ps.load_config(cfg)
    assert config.rules[0].target == "role(Translator)"


def test_config_parse_unknown_version_raises(tmp_path: Path):
    """version != 1 → ConfigError."""
    cfg = tmp_path / "signals.yml"
    cfg.write_text(
        """
version: 999
company_id: x
rules: []
bot_authors: []
"""
    )
    with pytest.raises(ps.ConfigError):
        ps.load_config(cfg)


# ---------------------------------------------------------------------------
# Task 6: Event parser — all 4 event types
# ---------------------------------------------------------------------------


def test_parse_event_ci_success(load_fixture):
    """workflow_run with conclusion=success → Event(trigger=ci.success, ...)."""
    payload = load_fixture("workflow_run_success")
    event = ps.parse_event("workflow_run", payload)
    assert event is not None
    assert event.trigger == "ci.success"
    assert event.sha == "abc123def456"
    assert event.pr_number == 77
    assert event.branch == "feature/GIM-62-async-signal"
    assert event.author == "ant013"


def test_parse_event_ci_failure_returns_none(load_fixture):
    """workflow_run with conclusion=failure → None (red CI out of scope)."""
    payload = load_fixture("workflow_run_failure")
    event = ps.parse_event("workflow_run", payload)
    assert event is None


def test_parse_event_pr_review_approved(load_fixture):
    """pull_request_review submitted → trigger=pr.review."""
    payload = load_fixture("pull_request_review_approved")
    event = ps.parse_event("pull_request_review", payload)
    assert event is not None
    assert event.trigger == "pr.review"
    assert event.sha == "abc123def456"
    assert event.pr_number == 77
    assert event.branch == "feature/GIM-62-async-signal"
    assert event.author == "operator"


def test_parse_event_pr_review_comment_folds_to_pr_review(load_fixture):
    """pull_request_review_comment → trigger=pr.review (debounce fold)."""
    payload = load_fixture("pull_request_review_comment_created")
    event = ps.parse_event("pull_request_review_comment", payload)
    assert event is not None
    assert event.trigger == "pr.review"
    assert event.sha == "abc123def456"
    assert event.pr_number == 77


def test_parse_event_repository_dispatch_qa_smoke(load_fixture):
    """repository_dispatch action=qa-smoke-complete → trigger=qa.smoke_complete."""
    payload = load_fixture("repository_dispatch_qa_smoke")
    event = ps.parse_event("repository_dispatch", payload)
    assert event is not None
    assert event.trigger == "qa.smoke_complete"
    assert event.sha == "xyz789"
    assert event.pr_number == 80
    assert event.branch == "develop"


def test_parse_event_repository_dispatch_missing_branch_raises():
    """repository_dispatch without client_payload.branch → ConfigError."""
    payload = {
        "action": "qa-smoke-complete",
        "client_payload": {"pr_number": 80, "sha": "abc"},
        "sender": {"login": "x", "type": "User"},
    }
    with pytest.raises(ps.ConfigError):
        ps.parse_event("repository_dispatch", payload)


def test_parse_event_unknown_event_name_returns_none():
    """Unknown event_name → None (graceful, not fail)."""
    event = ps.parse_event("push", {"ref": "refs/heads/main"})
    assert event is None


# ---------------------------------------------------------------------------
# Task 7: Branch regex + issue-number extraction
# ---------------------------------------------------------------------------


def test_extract_issue_number_valid_branch():
    """feature/GIM-62-async-signal → 62."""
    assert ps.extract_issue_number("feature/GIM-62-async-signal") == 62


def test_extract_issue_number_two_digit_number():
    """feature/GIM-123-big-slug → 123."""
    assert ps.extract_issue_number("feature/GIM-123-big-slug") == 123


def test_extract_issue_number_no_match():
    """Non-feature branches return None (log warning, skip)."""
    assert ps.extract_issue_number("fix/typo") is None
    assert ps.extract_issue_number("main") is None
    assert ps.extract_issue_number("feature/bootstrap-no-number") is None


def test_extract_issue_number_empty_branch():
    assert ps.extract_issue_number("") is None


# ---------------------------------------------------------------------------
# Task 8: Bot filter
# ---------------------------------------------------------------------------


def test_is_bot_author_in_list():
    """author in bot_authors → True."""
    bot_authors = ["github-actions[bot]", "ant013"]
    assert ps.is_bot_author("ant013", bot_authors) is True
    assert ps.is_bot_author("github-actions[bot]", bot_authors) is True


def test_is_bot_author_not_in_list():
    bot_authors = ["github-actions[bot]", "ant013"]
    assert ps.is_bot_author("operator", bot_authors) is False
    assert ps.is_bot_author("", bot_authors) is False


# ---------------------------------------------------------------------------
# Task 9: PaperclipClient — GET issue + release + reassign
# ---------------------------------------------------------------------------


def test_paperclip_get_issue_success(httpx_mock: HTTPXMock):
    """GET /api/issues?issueNumber=62 returns single issue with assignee + executionRunId."""
    httpx_mock.add_response(
        method="GET",
        url="https://paperclip.example.com/api/issues?issueNumber=62&companyId=C1",
        json=[
            {
                "id": "issue-uuid-1",
                "issueNumber": 62,
                "assigneeAgentId": "agent-uuid-1",
                "assigneeName": "MCPEngineer",
                "executionRunId": None,
            }
        ],
    )
    client = ps.PaperclipClient(
        base_url="https://paperclip.example.com", api_key="k", company_id="C1"
    )
    issue = client.get_issue_by_number(62)
    assert issue.id == "issue-uuid-1"
    assert issue.assignee_id == "agent-uuid-1"
    assert issue.assignee_name == "MCPEngineer"
    assert issue.execution_run_id is None
    client.close()


def test_paperclip_get_issue_not_found(httpx_mock: HTTPXMock):
    """Empty response list → raises PaperclipError."""
    httpx_mock.add_response(
        method="GET",
        url="https://paperclip.example.com/api/issues?issueNumber=99&companyId=C1",
        json=[],
    )
    client = ps.PaperclipClient(
        base_url="https://paperclip.example.com", api_key="k", company_id="C1"
    )
    with pytest.raises(ps.PaperclipError) as excinfo:
        client.get_issue_by_number(99)
    assert "99" in str(excinfo.value)
    client.close()


def test_paperclip_release_and_reassign(httpx_mock: HTTPXMock):
    """POST /release + PATCH assigneeId. Both calls made with correct payloads."""
    httpx_mock.add_response(
        method="POST",
        url="https://paperclip.example.com/api/issues/issue-uuid-1/release",
        json={"ok": True},
    )
    httpx_mock.add_response(
        method="PATCH",
        url="https://paperclip.example.com/api/issues/issue-uuid-1",
        match_json={"assigneeAgentId": "agent-uuid-1"},
        json={"ok": True},
    )
    client = ps.PaperclipClient(
        base_url="https://paperclip.example.com", api_key="k", company_id="C1"
    )
    client.release_and_reassign(issue_id="issue-uuid-1", assignee_id="agent-uuid-1")
    requests = httpx_mock.get_requests()
    assert len(requests) == 2
    assert requests[0].method == "POST" and requests[0].url.path.endswith("/release")
    assert requests[1].method == "PATCH"
    client.close()


# ---------------------------------------------------------------------------
# Task 10: Retry logic — 5xx + 409 with backoff
# ---------------------------------------------------------------------------


def test_release_and_reassign_retry_5xx_then_success(httpx_mock: HTTPXMock):
    """503 on release → retry → success. Confirms retry loop wraps call."""
    for _ in range(2):
        httpx_mock.add_response(
            method="POST",
            url="https://paperclip.example.com/api/issues/uuid/release",
            status_code=503,
            json={"error": "temporarily unavailable"},
        )
    httpx_mock.add_response(
        method="POST",
        url="https://paperclip.example.com/api/issues/uuid/release",
        json={"ok": True},
    )
    httpx_mock.add_response(
        method="PATCH",
        url="https://paperclip.example.com/api/issues/uuid",
        json={"ok": True},
    )
    client = ps.PaperclipClient("https://paperclip.example.com", "k", "C1")
    with patch.object(ps, "_sleep", lambda s: None):
        ps.release_and_reassign_with_retry(
            client, issue_id="uuid", assignee_id="agent-uuid"
        )
    client.close()


def test_release_and_reassign_retry_all_fail(httpx_mock: HTTPXMock):
    """503 forever → PaperclipError after max attempts."""
    for _ in range(3):
        httpx_mock.add_response(
            method="POST",
            url="https://paperclip.example.com/api/issues/uuid/release",
            status_code=503,
            json={"error": "down"},
        )
    client = ps.PaperclipClient("https://paperclip.example.com", "k", "C1")
    with patch.object(ps, "_sleep", lambda s: None):
        with pytest.raises(ps.PaperclipError):
            ps.release_and_reassign_with_retry(
                client, issue_id="uuid", assignee_id="agent-uuid"
            )
    client.close()


def test_release_and_reassign_retry_409_transient_lock(httpx_mock: HTTPXMock):
    """409 on release → retry → success (stale-lock recovers)."""
    httpx_mock.add_response(
        method="POST",
        url="https://paperclip.example.com/api/issues/uuid/release",
        status_code=409,
        json={"error": "execution lock"},
    )
    httpx_mock.add_response(
        method="POST",
        url="https://paperclip.example.com/api/issues/uuid/release",
        json={"ok": True},
    )
    httpx_mock.add_response(
        method="PATCH",
        url="https://paperclip.example.com/api/issues/uuid",
        json={"ok": True},
    )
    client = ps.PaperclipClient("https://paperclip.example.com", "k", "C1")
    with patch.object(ps, "_sleep", lambda s: None):
        ps.release_and_reassign_with_retry(
            client, issue_id="uuid", assignee_id="agent-uuid"
        )
    client.close()


def test_release_and_reassign_no_retry_on_4xx_not_409(httpx_mock: HTTPXMock):
    """403 on release → immediate PaperclipError (no retry)."""
    httpx_mock.add_response(
        method="POST",
        url="https://paperclip.example.com/api/issues/uuid/release",
        status_code=403,
        json={"error": "forbidden"},
    )
    client = ps.PaperclipClient("https://paperclip.example.com", "k", "C1")
    with patch.object(ps, "_sleep", lambda s: None):
        with pytest.raises(ps.PaperclipError):
            ps.release_and_reassign_with_retry(
                client, issue_id="uuid", assignee_id="agent-uuid"
            )
    assert len(httpx_mock.get_requests()) == 1
    client.close()


# ---------------------------------------------------------------------------
# Task 11: Active-session pre-check + deferred path
# ---------------------------------------------------------------------------


def test_resolve_target_issue_assignee_active_run_null(httpx_mock: HTTPXMock):
    """executionRunId=null → ResolveResult.proceed with assignee."""
    httpx_mock.add_response(
        method="GET",
        url="https://paperclip.example.com/api/issues?issueNumber=62&companyId=C1",
        json=[
            {
                "id": "uuid",
                "issueNumber": 62,
                "assigneeAgentId": "agent-uuid",
                "assigneeName": "MCPEngineer",
                "executionRunId": None,
            }
        ],
    )
    client = ps.PaperclipClient("https://paperclip.example.com", "k", "C1")
    result = ps.resolve_target_issue_assignee(client, issue_number=62)
    assert result.status == "proceed"
    assert result.issue.id == "uuid"
    assert result.issue.assignee_id == "agent-uuid"
    client.close()


def test_resolve_target_issue_assignee_deferred_active_run_persists(
    httpx_mock: HTTPXMock,
):
    """executionRunId non-null on first AND recheck → status=deferred."""
    for _ in range(2):
        httpx_mock.add_response(
            method="GET",
            url="https://paperclip.example.com/api/issues?issueNumber=62&companyId=C1",
            json=[
                {
                    "id": "uuid",
                    "issueNumber": 62,
                    "assigneeAgentId": "agent-uuid",
                    "assigneeName": "MCPEngineer",
                    "executionRunId": "run-active-1",
                }
            ],
        )
    client = ps.PaperclipClient("https://paperclip.example.com", "k", "C1")
    with patch.object(ps, "_sleep", lambda s: None):
        result = ps.resolve_target_issue_assignee(client, issue_number=62)
    assert result.status == "deferred"
    assert result.issue.execution_run_id == "run-active-1"
    client.close()


def test_resolve_target_issue_assignee_active_run_clears(httpx_mock: HTTPXMock):
    """executionRunId non-null then null → status=proceed."""
    httpx_mock.add_response(
        method="GET",
        url="https://paperclip.example.com/api/issues?issueNumber=62&companyId=C1",
        json=[
            {
                "id": "uuid",
                "issueNumber": 62,
                "assigneeAgentId": "agent-uuid",
                "assigneeName": "MCPEngineer",
                "executionRunId": "run-active-1",
            }
        ],
    )
    httpx_mock.add_response(
        method="GET",
        url="https://paperclip.example.com/api/issues?issueNumber=62&companyId=C1",
        json=[
            {
                "id": "uuid",
                "issueNumber": 62,
                "assigneeAgentId": "agent-uuid",
                "assigneeName": "MCPEngineer",
                "executionRunId": None,
            }
        ],
    )
    client = ps.PaperclipClient("https://paperclip.example.com", "k", "C1")
    with patch.object(ps, "_sleep", lambda s: None):
        result = ps.resolve_target_issue_assignee(client, issue_number=62)
    assert result.status == "proceed"
    client.close()


def test_resolve_target_issue_assignee_null_assignee(httpx_mock: HTTPXMock):
    """Assignee is null on issue → status=no_assignee."""
    httpx_mock.add_response(
        method="GET",
        url="https://paperclip.example.com/api/issues?issueNumber=62&companyId=C1",
        json=[
            {
                "id": "uuid",
                "issueNumber": 62,
                "assigneeAgentId": None,
                "assigneeName": None,
                "executionRunId": None,
            }
        ],
    )
    client = ps.PaperclipClient("https://paperclip.example.com", "k", "C1")
    result = ps.resolve_target_issue_assignee(client, issue_number=62)
    assert result.status == "no_assignee"
    client.close()


# ---------------------------------------------------------------------------
# Task 12: Dedup marker check
# ---------------------------------------------------------------------------


def test_pr_has_signal_marker_present():
    """Comment body with matching marker → True."""
    comments = [
        {"body": "Some random comment"},
        {
            "body": "<!-- paperclip-signal: ci.success abc123 assignee=MCPEngineer --> Woke MCPEngineer on ci.success at abc123."
        },
    ]
    assert ps.pr_has_signal_marker(comments, trigger="ci.success", sha="abc123") is True


def test_pr_has_signal_marker_absent():
    """Comments without matching marker → False."""
    comments = [
        {"body": "Unrelated"},
        {"body": "<!-- paperclip-signal: ci.success DIFFERENT_SHA -->"},
    ]
    assert (
        ps.pr_has_signal_marker(comments, trigger="ci.success", sha="abc123") is False
    )


def test_pr_has_signal_marker_different_trigger():
    """Marker with same sha but different trigger → False."""
    comments = [{"body": "<!-- paperclip-signal: pr.review abc123 -->"}]
    assert (
        ps.pr_has_signal_marker(comments, trigger="ci.success", sha="abc123") is False
    )


def test_pr_has_signal_marker_empty_comments():
    assert ps.pr_has_signal_marker([], trigger="ci.success", sha="abc123") is False


def test_pr_has_signal_marker_failed_marker_not_counted():
    """signal-failed markers do NOT deduplicate — a failed prior attempt should retry."""
    comments = [{"body": "<!-- paperclip-signal-failed: ci.success abc123 -->"}]
    assert (
        ps.pr_has_signal_marker(comments, trigger="ci.success", sha="abc123") is False
    )


def test_pr_has_signal_marker_deferred_marker_not_counted():
    """signal-deferred markers do NOT deduplicate — a deferred signal should retry next event."""
    comments = [{"body": "<!-- paperclip-signal-deferred: ci.success abc123 -->"}]
    assert (
        ps.pr_has_signal_marker(comments, trigger="ci.success", sha="abc123") is False
    )


# ---------------------------------------------------------------------------
# Task 13: Comment builders + GitHub API helpers
# ---------------------------------------------------------------------------


def test_build_success_comment_body():
    body = ps.build_success_comment(
        trigger="ci.success",
        sha="abc123",
        agent_name="MCPEngineer",
    )
    assert "<!-- paperclip-signal: ci.success abc123 assignee=MCPEngineer -->" in body
    assert "Woke MCPEngineer on ci.success at abc123" in body


def test_build_deferred_comment_body():
    body = ps.build_deferred_comment(
        trigger="ci.success",
        sha="abc123",
        execution_run_id="run-xyz",
    )
    assert "<!-- paperclip-signal-deferred: ci.success abc123 -->" in body
    assert "run-xyz" in body
    assert "deferred" in body.lower()


def test_build_failed_comment_body():
    body = ps.build_failed_comment(
        trigger="ci.success",
        sha="abc123",
        error_message="503 Service Unavailable",
    )
    assert "<!-- paperclip-signal-failed: ci.success abc123 -->" in body
    assert "503 Service Unavailable" in body
    assert "operator" in body.lower()


def test_build_no_assignee_comment_body():
    body = ps.build_no_assignee_comment(trigger="ci.success", sha="abc123")
    assert "no assignee" in body.lower()
    assert "ci.success" in body


def test_github_post_pr_comment(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        method="POST",
        url="https://api.github.com/repos/ant013/Gimle-Palace/issues/77/comments",
        match_json={"body": "hello"},
        json={"id": 1234},
    )
    ps.github_post_pr_comment(
        repo="ant013/Gimle-Palace",
        pr_number=77,
        body="hello",
        github_token="gh_token",
    )


def test_github_get_pr_comments(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        method="GET",
        url="https://api.github.com/repos/ant013/Gimle-Palace/issues/77/comments?per_page=100",
        json=[{"body": "c1"}, {"body": "c2"}],
    )
    comments = ps.github_get_pr_comments(
        repo="ant013/Gimle-Palace",
        pr_number=77,
        github_token="gh_token",
    )
    assert len(comments) == 2
    assert comments[0]["body"] == "c1"


# ---------------------------------------------------------------------------
# Task 14: main() orchestration
# ---------------------------------------------------------------------------


@pytest.fixture
def minimal_config(tmp_path: Path) -> Path:
    cfg = tmp_path / "signals.yml"
    cfg.write_text(
        """
version: 1
company_id: C1
rules:
  - trigger: ci.success
    target: issue_assignee
bot_authors:
  - github-actions[bot]
  - ant013
"""
    )
    return cfg


def test_main_happy_path_ci_success(
    httpx_mock: HTTPXMock, load_fixture, minimal_config: Path
):
    """workflow_run success → GET issue → release+patch → success comment → exit 0."""
    payload = load_fixture("workflow_run_success")
    payload["sender"] = {"login": "operator", "type": "User"}

    httpx_mock.add_response(
        method="GET",
        url="https://paperclip.example.com/api/issues?issueNumber=62&companyId=C1",
        json=[
            {
                "id": "issue-uuid",
                "issueNumber": 62,
                "assigneeAgentId": "agent-uuid",
                "assigneeName": "MCPEngineer",
                "executionRunId": None,
            }
        ],
    )
    httpx_mock.add_response(
        method="GET",
        url="https://api.github.com/repos/ant013/Gimle-Palace/issues/77/comments?per_page=100",
        json=[],
    )
    httpx_mock.add_response(
        method="POST",
        url="https://paperclip.example.com/api/issues/issue-uuid/release",
        json={"ok": True},
    )
    httpx_mock.add_response(
        method="PATCH",
        url="https://paperclip.example.com/api/issues/issue-uuid",
        json={"ok": True},
    )
    httpx_mock.add_response(
        method="POST",
        url="https://api.github.com/repos/ant013/Gimle-Palace/issues/77/comments",
        json={"id": 1},
    )

    with patch.object(ps, "_sleep", lambda s: None):
        rc = ps.main(
            event_name="workflow_run",
            event_payload=payload,
            config_path=minimal_config,
            paperclip_base_url="https://paperclip.example.com",
            paperclip_api_key="k",
            github_token="ght",
            repo="ant013/Gimle-Palace",
        )
    assert rc == 0


def test_main_bot_sender_exits_early(
    httpx_mock: HTTPXMock, load_fixture, minimal_config: Path
):
    """sender=ant013 → exit 0, no API calls."""
    payload = load_fixture("workflow_run_success")  # sender=ant013 by default
    rc = ps.main(
        event_name="workflow_run",
        event_payload=payload,
        config_path=minimal_config,
        paperclip_base_url="https://paperclip.example.com",
        paperclip_api_key="k",
        github_token="ght",
        repo="ant013/Gimle-Palace",
    )
    assert rc == 0
    assert httpx_mock.get_requests() == []


def test_main_branch_mismatch_warn_exit_0(load_fixture, minimal_config: Path):
    """Branch not feature/GIM-N → exit 0 with log WARNING, no API calls."""
    payload = load_fixture("workflow_run_success")
    payload["sender"] = {"login": "operator", "type": "User"}
    payload["workflow_run"]["head_branch"] = "random-branch"
    rc = ps.main(
        event_name="workflow_run",
        event_payload=payload,
        config_path=minimal_config,
        paperclip_base_url="https://paperclip.example.com",
        paperclip_api_key="k",
        github_token="ght",
        repo="ant013/Gimle-Palace",
    )
    assert rc == 0


def test_main_dedup_hit_exits_0(
    httpx_mock: HTTPXMock, load_fixture, minimal_config: Path
):
    """Existing success marker → skip reassign, exit 0, no paperclip release calls."""
    payload = load_fixture("workflow_run_success")
    payload["sender"] = {"login": "operator", "type": "User"}
    httpx_mock.add_response(
        method="GET",
        url="https://paperclip.example.com/api/issues?issueNumber=62&companyId=C1",
        json=[
            {
                "id": "issue-uuid",
                "issueNumber": 62,
                "assigneeAgentId": "agent-uuid",
                "assigneeName": "MCPEngineer",
                "executionRunId": None,
            }
        ],
    )
    httpx_mock.add_response(
        method="GET",
        url="https://api.github.com/repos/ant013/Gimle-Palace/issues/77/comments?per_page=100",
        json=[
            {
                "body": "<!-- paperclip-signal: ci.success abc123def456 assignee=MCPEngineer --> Woke."
            }
        ],
    )
    rc = ps.main(
        event_name="workflow_run",
        event_payload=payload,
        config_path=minimal_config,
        paperclip_base_url="https://paperclip.example.com",
        paperclip_api_key="k",
        github_token="ght",
        repo="ant013/Gimle-Palace",
    )
    assert rc == 0


def test_main_deferred_posts_deferred_comment_exits_0(
    httpx_mock: HTTPXMock, load_fixture, minimal_config: Path
):
    """executionRunId persists non-null → post deferred comment, exit 0."""
    payload = load_fixture("workflow_run_success")
    payload["sender"] = {"login": "operator", "type": "User"}
    for _ in range(2):
        httpx_mock.add_response(
            method="GET",
            url="https://paperclip.example.com/api/issues?issueNumber=62&companyId=C1",
            json=[
                {
                    "id": "issue-uuid",
                    "issueNumber": 62,
                    "assigneeAgentId": "agent-uuid",
                    "assigneeName": "MCPEngineer",
                    "executionRunId": "run-active",
                }
            ],
        )
    httpx_mock.add_response(
        method="POST",
        url="https://api.github.com/repos/ant013/Gimle-Palace/issues/77/comments",
        json={"id": 42},
    )
    with patch.object(ps, "_sleep", lambda s: None):
        rc = ps.main(
            event_name="workflow_run",
            event_payload=payload,
            config_path=minimal_config,
            paperclip_base_url="https://paperclip.example.com",
            paperclip_api_key="k",
            github_token="ght",
            repo="ant013/Gimle-Palace",
        )
    assert rc == 0


def test_main_role_target_raises(load_fixture, tmp_path: Path):
    """role(<Name>) target triggers NotImplementedError."""
    cfg = tmp_path / "signals.yml"
    cfg.write_text(
        """
version: 1
company_id: C1
rules:
  - trigger: ci.success
    target: role(Translator)
bot_authors: []
"""
    )
    payload = load_fixture("workflow_run_success")
    payload["sender"] = {"login": "operator", "type": "User"}
    with pytest.raises(NotImplementedError):
        ps.main(
            event_name="workflow_run",
            event_payload=payload,
            config_path=cfg,
            paperclip_base_url="https://paperclip.example.com",
            paperclip_api_key="k",
            github_token="ght",
            repo="ant013/Gimle-Palace",
        )


def test_main_paperclip_down_posts_failed_exits_1(
    httpx_mock: HTTPXMock, load_fixture, minimal_config: Path
):
    """Paperclip 503 forever → signal-failed comment + exit 1."""
    payload = load_fixture("workflow_run_success")
    payload["sender"] = {"login": "operator", "type": "User"}
    httpx_mock.add_response(
        method="GET",
        url="https://paperclip.example.com/api/issues?issueNumber=62&companyId=C1",
        json=[
            {
                "id": "issue-uuid",
                "issueNumber": 62,
                "assigneeAgentId": "agent-uuid",
                "assigneeName": "MCPEngineer",
                "executionRunId": None,
            }
        ],
    )
    httpx_mock.add_response(
        method="GET",
        url="https://api.github.com/repos/ant013/Gimle-Palace/issues/77/comments?per_page=100",
        json=[],
    )
    for _ in range(3):
        httpx_mock.add_response(
            method="POST",
            url="https://paperclip.example.com/api/issues/issue-uuid/release",
            status_code=503,
            json={"error": "down"},
        )
    httpx_mock.add_response(
        method="POST",
        url="https://api.github.com/repos/ant013/Gimle-Palace/issues/77/comments",
        json={"id": 99},
    )
    with patch.object(ps, "_sleep", lambda s: None):
        rc = ps.main(
            event_name="workflow_run",
            event_payload=payload,
            config_path=minimal_config,
            paperclip_base_url="https://paperclip.example.com",
            paperclip_api_key="k",
            github_token="ght",
            repo="ant013/Gimle-Palace",
        )
    assert rc == 1


# ---------------------------------------------------------------------------
# Task 15: Invariant tests — live config + CI workflow name
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_real_config_parses():
    """.github/paperclip-signals.yml must parse without error on every PR."""
    config_path = REPO_ROOT / ".github" / "paperclip-signals.yml"
    assert config_path.exists(), f"Live config missing at {config_path}"
    config = ps.load_config(config_path)
    assert config.version == 1
    assert config.company_id
    assert len(config.rules) >= 1


def test_ci_workflow_name_pinned():
    """The workflow file referenced by paperclip-signal must have name: CI."""
    ci_yaml = REPO_ROOT / ".github" / "workflows" / "ci.yml"
    assert ci_yaml.exists(), f"Missing {ci_yaml}"
    raw = _yaml.safe_load(ci_yaml.read_text())
    assert raw.get("name") == "CI", (
        f"Expected top-level `name: CI` in .github/workflows/ci.yml for "
        f"workflow_run trigger matching; found {raw.get('name')!r}. "
        f"Update .github/workflows/paperclip-signal.yml workflows: key "
        f"if this name is changed intentionally."
    )
