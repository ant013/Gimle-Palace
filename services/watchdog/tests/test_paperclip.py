"""Tests for watchdog.paperclip — REST client with httpx MockTransport."""

from __future__ import annotations

import json as _json
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

from gimle_watchdog import paperclip as pc
import gimle_watchdog.paperclip as _pc_mod

_FIXTURES = Path(__file__).parent / "fixtures"


BASE = "http://paperclip.test"
CO_ID = "9d8f432c-ff7d-4e3a-bbe3-3cd355f73b64"
ISSUE_ID = "issue-1234"


async def _client_with_mock(handler):
    transport = httpx.MockTransport(handler)
    return pc.PaperclipClient(base_url=BASE, api_key="tok", transport=transport)


async def _noop_sleep(_: float) -> None:
    """Drop-in async no-op replacement for _sleep in tests."""


@pytest.mark.asyncio
async def test_list_in_progress_issues():
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == f"{BASE}/api/companies/{CO_ID}/issues?status=in_progress"
        assert request.headers["Authorization"] == "Bearer tok"
        return httpx.Response(
            200,
            json=[
                {
                    "id": ISSUE_ID,
                    "assigneeAgentId": "agent-1",
                    "executionRunId": None,
                    "status": "in_progress",
                    "updatedAt": "2026-04-21T10:00:00Z",
                },
            ],
        )

    client = await _client_with_mock(handler)
    try:
        issues = await client.list_in_progress_issues(CO_ID)
        assert len(issues) == 1
        assert issues[0].id == ISSUE_ID
        assert issues[0].assignee_agent_id == "agent-1"
        assert issues[0].execution_run_id is None
        assert issues[0].updated_at == datetime(2026, 4, 21, 10, 0, tzinfo=timezone.utc)
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_get_issue():
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == f"{BASE}/api/issues/{ISSUE_ID}"
        return httpx.Response(
            200,
            json={
                "id": ISSUE_ID,
                "assigneeAgentId": "agent-1",
                "executionRunId": "run-1",
                "status": "in_progress",
                "updatedAt": "2026-04-21T10:05:00Z",
            },
        )

    client = await _client_with_mock(handler)
    try:
        issue = await client.get_issue(ISSUE_ID)
        assert issue.execution_run_id == "run-1"
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_patch_issue_assignee():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        captured["body"] = request.content.decode()
        return httpx.Response(200, json={"id": ISSUE_ID})

    client = await _client_with_mock(handler)
    try:
        await client.patch_issue(ISSUE_ID, {"assigneeAgentId": "agent-1"})
        assert captured["method"] == "PATCH"
        assert captured["url"] == f"{BASE}/api/issues/{ISSUE_ID}"
        assert '"assigneeAgentId"' in captured["body"]
        assert "agent-1" in captured["body"]
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_post_release():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"id": ISSUE_ID})

    client = await _client_with_mock(handler)
    try:
        await client.post_release(ISSUE_ID)
        assert captured["method"] == "POST"
        assert captured["url"] == f"{BASE}/api/issues/{ISSUE_ID}/release"
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_post_issue_comment():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["body"] = request.content.decode()
        return httpx.Response(201, json={"id": "comment-1"})

    client = await _client_with_mock(handler)
    try:
        await client.post_issue_comment(ISSUE_ID, "hello")
        assert captured["method"] == "POST"
        assert '"body"' in captured["body"]
        assert "hello" in captured["body"]
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_retry_5xx_then_succeed():
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count <= 2:
            return httpx.Response(503, json={"error": "busy"})
        return httpx.Response(200, json=[])

    original_sleep = _pc_mod._sleep
    _pc_mod._sleep = _noop_sleep
    client = await _client_with_mock(handler)
    try:
        issues = await client.list_in_progress_issues(CO_ID)
        assert issues == []
        assert call_count == 3
    finally:
        _pc_mod._sleep = original_sleep
        await client.aclose()


@pytest.mark.asyncio
async def test_429_backs_off():
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return httpx.Response(429, json={"error": "slow_down"})
        return httpx.Response(200, json=[])

    original_sleep = _pc_mod._sleep
    _pc_mod._sleep = _noop_sleep
    client = await _client_with_mock(handler)
    try:
        issues = await client.list_in_progress_issues(CO_ID)
        assert issues == []
        assert call_count == 2
    finally:
        _pc_mod._sleep = original_sleep
        await client.aclose()


@pytest.mark.asyncio
async def test_401_terminal_no_retry():
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(401, json={"error": "unauthorized"})

    client = await _client_with_mock(handler)
    try:
        with pytest.raises(pc.PaperclipError, match="401"):
            await client.list_in_progress_issues(CO_ID)
        assert call_count == 1
    finally:
        await client.aclose()


# ---------------------------------------------------------------------------
# T3: list_recent_comments + list_company_agents
# ---------------------------------------------------------------------------

_COMMENT_JSON = {
    "id": "cmt-001",
    "companyId": CO_ID,
    "issueId": ISSUE_ID,
    "authorAgentId": "127068ee-b564-4b37-9370-616c81c63f35",
    "authorUserId": None,
    "createdByRunId": "run-001",
    "body": "[@CodeReviewer](agent://bd2d7e20-7ed8-474c-91fc-353d610f4c52?i=eye) LGTM",
    "createdAt": "2026-05-03T10:00:00Z",
    "updatedAt": "2026-05-03T10:00:00Z",
}

_AGENT_JSON = {
    "id": "7fb0fdbb-e17f-4487-a4da-16993a907bec",
    "companyId": CO_ID,
    "name": "CTO",
    "role": "engineer",
    "title": "CTO",
    "icon": "crown",
    "status": "idle",
    "reportsTo": None,
    "createdAt": "2026-04-14T00:00:00Z",
    "updatedAt": "2026-05-03T10:00:00Z",
}


@pytest.mark.asyncio
async def test_list_recent_comments_returns_parsed_objects():
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == f"{BASE}/api/issues/{ISSUE_ID}/comments?limit=5"
        return httpx.Response(200, json=[_COMMENT_JSON])

    client = await _client_with_mock(handler)
    try:
        comments = await client.list_recent_comments(ISSUE_ID)
        assert len(comments) == 1
        c = comments[0]
        assert c.id == "cmt-001"
        assert c.body == _COMMENT_JSON["body"]
        assert c.author_agent_id == "127068ee-b564-4b37-9370-616c81c63f35"
        assert c.created_at == datetime(2026, 5, 3, 10, 0, tzinfo=timezone.utc)
        assert c.created_at.tzinfo is not None
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_list_recent_comments_handles_empty_response():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[])

    client = await _client_with_mock(handler)
    try:
        comments = await client.list_recent_comments(ISSUE_ID)
        assert comments == []
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_list_recent_comments_propagates_429():
    original_sleep = _pc_mod._sleep
    _pc_mod._sleep = _noop_sleep
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(429, json={"error": "slow_down"})

    client = await _client_with_mock(handler)
    try:
        with pytest.raises(pc.PaperclipError):
            await client.list_recent_comments(ISSUE_ID)
        assert call_count > 1  # retried
    finally:
        _pc_mod._sleep = original_sleep
        await client.aclose()


@pytest.mark.asyncio
async def test_list_recent_comments_rejects_naive_created_at():
    naive_comment = dict(_COMMENT_JSON, createdAt="2026-05-03T10:00:00")  # no tz

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[naive_comment])

    client = await _client_with_mock(handler)
    try:
        with pytest.raises((pc.PaperclipError, ValueError)):
            await client.list_recent_comments(ISSUE_ID)
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_list_company_agents_returns_parsed_objects():
    fixture = _json.loads((_FIXTURES / "company_agents.json").read_text())

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == f"{BASE}/api/companies/{CO_ID}/agents"
        return httpx.Response(200, json=fixture)

    client = await _client_with_mock(handler)
    try:
        agents = await client.list_company_agents(CO_ID)
        assert len(agents) == 3
        names = {a.name for a in agents}
        assert "CTO" in names
        assert "CodeReviewer" in names
        assert "PythonEngineer" in names
        # All have ids
        assert all(a.id for a in agents)
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_list_company_agents_propagates_429():
    original_sleep = _pc_mod._sleep
    _pc_mod._sleep = _noop_sleep
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(429, json={"error": "slow_down"})

    client = await _client_with_mock(handler)
    try:
        with pytest.raises(pc.PaperclipError):
            await client.list_company_agents(CO_ID)
        assert call_count > 1
    finally:
        _pc_mod._sleep = original_sleep
        await client.aclose()
