"""GitHub GraphQL client — see spec GIM-186 §5.2."""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import datetime

import httpx

GRAPHQL_URL = "https://api.github.com/graphql"
PR_QUERY = """
query($owner: String!, $name: String!, $cursor: String) {
  repository(owner: $owner, name: $name) {
    pullRequests(first: 50, after: $cursor,
                 orderBy: {field: UPDATED_AT, direction: DESC}) {
      pageInfo { hasNextPage endCursor }
      nodes {
        number title body state
        author { login ... on User { email } }
        createdAt updatedAt mergedAt
        headRefOid baseRef { name }
        comments(first: 100) {
          totalCount
          pageInfo { hasNextPage endCursor }
          nodes {
            id body
            author { login ... on User { email } }
            createdAt
          }
        }
      }
    }
    rateLimit { cost remaining limit resetAt }
  }
}
"""


class RateLimitExhausted(Exception):
    """Raised when GraphQL budget would be exhausted; fail-fast (no sleep)."""


class GitHubClient:
    def __init__(
        self,
        token: str,
        *,
        max_retries: int = 3,
        retry_initial_ms: int = 500,
        budget_floor: int = 100,
    ) -> None:
        self._client = httpx.AsyncClient(
            headers={"Authorization": f"Bearer {token}"},
            timeout=httpx.Timeout(connect=10.0, read=30.0, write=30.0, pool=30.0),
        )
        self._max_retries = max_retries
        self._retry_initial_ms = retry_initial_ms
        self._budget_floor = budget_floor

    async def aclose(self) -> None:
        await self._client.aclose()

    async def fetch_prs_since(
        self,
        repo_owner: str,
        repo_name: str,
        since: datetime | None,
    ) -> AsyncIterator[list[dict]]:  # type: ignore[override]
        cursor: str | None = None
        while True:
            resp_json = await self._post_query(
                PR_QUERY,
                {"owner": repo_owner, "name": repo_name, "cursor": cursor},
            )
            repo_data = resp_json["data"]["repository"]
            page = repo_data["pullRequests"]
            rate_limit = repo_data["rateLimit"]

            # Cost-aware fail-fast (spec §5.2)
            if rate_limit["remaining"] < self._budget_floor:
                raise RateLimitExhausted(
                    f"remaining={rate_limit['remaining']} < floor={self._budget_floor}"
                )

            # Yield PRs that are newer than `since`
            batch = []
            for pr in page["nodes"]:
                pr_updated = datetime.fromisoformat(pr["updatedAt"].replace("Z", "+00:00"))
                if since is not None and pr_updated < since:
                    yield batch
                    return  # stop outer pagination — older than checkpoint
                batch.append(pr)
            yield batch

            if not page["pageInfo"]["hasNextPage"]:
                return
            cursor = page["pageInfo"]["endCursor"]

    async def _post_query(self, query: str, variables: dict) -> dict:  # type: ignore[type-arg]
        last_exc: Exception | None = None
        for attempt in range(self._max_retries):
            if attempt > 0:
                delay_s = (self._retry_initial_ms / 1000.0) * (2 ** (attempt - 1))
                await asyncio.sleep(delay_s)
            try:
                resp = await self._client.post(
                    GRAPHQL_URL,
                    json={"query": query, "variables": variables},
                )
            except httpx.RequestError as exc:
                last_exc = exc
                continue
            if resp.status_code in (429,) or 500 <= resp.status_code < 600:
                last_exc = httpx.HTTPStatusError(
                    f"transient {resp.status_code}", request=resp.request, response=resp
                )
                continue
            if resp.status_code >= 400:
                raise httpx.HTTPStatusError(
                    f"github graphql {resp.status_code}: {resp.text[:200]}",
                    request=resp.request, response=resp,
                )
            return resp.json()  # type: ignore[no-any-return]
        raise last_exc or RuntimeError("github graphql retries exhausted")
