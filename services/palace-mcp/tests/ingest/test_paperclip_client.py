import httpx
import pytest

from palace_mcp.ingest.paperclip_client import PaperclipClient


@pytest.mark.asyncio
async def test_list_issues_returns_list(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer test-token"
        assert request.url.path == "/api/companies/co-1/issues"
        return httpx.Response(
            200, json={"issues": [{"id": "i1", "identifier": "GIM-1"}]}
        )

    transport = httpx.MockTransport(handler)
    async with PaperclipClient(
        base_url="https://pc",
        token="test-token",
        company_id="co-1",
        transport=transport,
    ) as client:
        issues = await client.list_issues()
    assert issues == [{"id": "i1", "identifier": "GIM-1"}]


@pytest.mark.asyncio
async def test_list_comments_for_issue(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/issues/i1/comments"
        return httpx.Response(200, json=[{"id": "c1", "body": "hi"}])

    transport = httpx.MockTransport(handler)
    async with PaperclipClient(
        base_url="https://pc",
        token="test-token",
        company_id="co-1",
        transport=transport,
    ) as client:
        comments = await client.list_comments_for_issue("i1")
    assert comments == [{"id": "c1", "body": "hi"}]


@pytest.mark.asyncio
async def test_list_agents_returns_list(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/companies/co-1/agents"
        return httpx.Response(200, json=[{"id": "a1", "name": "CodeReviewer"}])

    transport = httpx.MockTransport(handler)
    async with PaperclipClient(
        base_url="https://pc",
        token="test-token",
        company_id="co-1",
        transport=transport,
    ) as client:
        agents = await client.list_agents()
    assert agents == [{"id": "a1", "name": "CodeReviewer"}]
