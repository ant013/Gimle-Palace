from datetime import datetime, timezone
import httpx
import pytest
import respx

from palace_mcp.extractors.git_history.github_client import (
    GitHubClient, RateLimitExhausted,
)


@pytest.mark.asyncio
async def test_fetch_prs_single_page():
    fake_response = {
        "data": {
            "repository": {
                "pullRequests": {
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                    "nodes": [
                        {
                            "number": 1, "title": "first", "body": "b",
                            "state": "MERGED",
                            "author": {"login": "user1", "email": "user1@example.com"},
                            "createdAt": "2026-05-01T10:00:00Z",
                            "updatedAt": "2026-05-01T10:00:00Z",
                            "mergedAt": "2026-05-01T10:30:00Z",
                            "headRefOid": "0" * 40,
                            "baseRef": {"name": "develop"},
                            "comments": {
                                "totalCount": 0,
                                "pageInfo": {"hasNextPage": False, "endCursor": None},
                                "nodes": [],
                            },
                        }
                    ],
                },
                "rateLimit": {"cost": 1, "remaining": 4999, "limit": 5000,
                              "resetAt": "2026-05-03T13:00:00Z"},
            }
        }
    }
    with respx.mock:
        respx.post("https://api.github.com/graphql").mock(
            return_value=httpx.Response(200, json=fake_response)
        )
        client = GitHubClient(token="tok")
        prs = []
        async for batch in client.fetch_prs_since("owner", "repo", since=None):
            prs.extend(batch)
        assert len(prs) == 1
        assert prs[0]["number"] == 1


@pytest.mark.asyncio
async def test_fetch_prs_pagination_two_pages():
    page1 = {"data": {"repository": {
        "pullRequests": {
            "pageInfo": {"hasNextPage": True, "endCursor": "CURSOR1"},
            "nodes": [{"number": 1, "title": "a", "body": "",
                       "state": "OPEN", "author": {"login": "u"},
                       "createdAt": "2026-05-01T00:00:00Z",
                       "updatedAt": "2026-05-01T00:00:00Z",
                       "mergedAt": None, "headRefOid": None,
                       "baseRef": {"name": "develop"},
                       "comments": {"totalCount": 0, "pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": []}}],
        },
        "rateLimit": {"cost": 1, "remaining": 4998, "limit": 5000,
                      "resetAt": "2026-05-03T13:00:00Z"},
    }}}
    page2 = {"data": {"repository": {
        "pullRequests": {
            "pageInfo": {"hasNextPage": False, "endCursor": None},
            "nodes": [{"number": 2, "title": "b", "body": "",
                       "state": "MERGED", "author": {"login": "u"},
                       "createdAt": "2026-04-30T00:00:00Z",
                       "updatedAt": "2026-04-30T00:00:00Z",
                       "mergedAt": "2026-04-30T00:00:00Z",
                       "headRefOid": "0" * 40,
                       "baseRef": {"name": "develop"},
                       "comments": {"totalCount": 0, "pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": []}}],
        },
        "rateLimit": {"cost": 1, "remaining": 4997, "limit": 5000,
                      "resetAt": "2026-05-03T13:00:00Z"},
    }}}
    with respx.mock:
        route = respx.post("https://api.github.com/graphql")
        route.side_effect = [
            httpx.Response(200, json=page1),
            httpx.Response(200, json=page2),
        ]
        client = GitHubClient(token="tok")
        all_prs = []
        async for batch in client.fetch_prs_since("o", "r", since=None):
            all_prs.extend(batch)
        assert [pr["number"] for pr in all_prs] == [1, 2]


@pytest.mark.asyncio
async def test_fetch_prs_stops_at_since_boundary():
    """PR with updated_at < since must NOT be yielded."""
    fake = {"data": {"repository": {
        "pullRequests": {
            "pageInfo": {"hasNextPage": False, "endCursor": None},
            "nodes": [
                {"number": 1, "title": "newer", "body": "",
                 "state": "OPEN", "author": {"login": "u"},
                 "createdAt": "2026-05-03T12:00:00Z",
                 "updatedAt": "2026-05-03T12:00:00Z",
                 "mergedAt": None, "headRefOid": None,
                 "baseRef": {"name": "develop"},
                 "comments": {"totalCount": 0, "pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": []}},
                {"number": 2, "title": "older", "body": "",
                 "state": "MERGED", "author": {"login": "u"},
                 "createdAt": "2026-05-01T00:00:00Z",
                 "updatedAt": "2026-05-01T00:00:00Z",  # before since
                 "mergedAt": "2026-05-01T00:00:00Z", "headRefOid": "0"*40,
                 "baseRef": {"name": "develop"},
                 "comments": {"totalCount": 0, "pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": []}},
            ],
        },
        "rateLimit": {"cost": 1, "remaining": 4999, "limit": 5000,
                      "resetAt": "2026-05-03T13:00:00Z"},
    }}}
    since = datetime(2026, 5, 2, tzinfo=timezone.utc)
    with respx.mock:
        respx.post("https://api.github.com/graphql").mock(
            return_value=httpx.Response(200, json=fake)
        )
        client = GitHubClient(token="tok")
        all_prs = []
        async for batch in client.fetch_prs_since("o", "r", since=since):
            all_prs.extend(batch)
        assert [pr["number"] for pr in all_prs] == [1]


@pytest.mark.asyncio
async def test_rate_limit_fail_fast_below_threshold():
    """remaining < 100 → raise RateLimitExhausted, NOT sleep."""
    fake = {"data": {"repository": {
        "pullRequests": {"pageInfo": {"hasNextPage": True, "endCursor": "C"},
                         "nodes": []},
        "rateLimit": {"cost": 50, "remaining": 50, "limit": 5000,
                      "resetAt": "2026-05-03T13:00:00Z"},
    }}}
    with respx.mock:
        respx.post("https://api.github.com/graphql").mock(
            return_value=httpx.Response(200, json=fake)
        )
        client = GitHubClient(token="tok")
        with pytest.raises(RateLimitExhausted):
            async for batch in client.fetch_prs_since("o", "r", since=None):
                pass


@pytest.mark.asyncio
async def test_429_retry_with_backoff():
    """429 followed by 200 should succeed within bounded backoff."""
    fake_ok = {"data": {"repository": {
        "pullRequests": {"pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": []},
        "rateLimit": {"cost": 1, "remaining": 4999, "limit": 5000,
                      "resetAt": "2026-05-03T13:00:00Z"},
    }}}
    with respx.mock:
        route = respx.post("https://api.github.com/graphql")
        route.side_effect = [
            httpx.Response(429, json={"error": "rate"}),
            httpx.Response(200, json=fake_ok),
        ]
        client = GitHubClient(token="tok", max_retries=2, retry_initial_ms=10)
        async for _ in client.fetch_prs_since("o", "r", since=None):
            pass
        assert route.call_count == 2
