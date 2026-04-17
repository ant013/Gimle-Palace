"""Async HTTP client for paperclip's public API.

Reads issues, comments, agents — that's the entire surface needed by
this slice. Separate module so the transport can be swapped in tests
via `httpx.MockTransport`.
"""

from types import TracebackType
from typing import Any, Self

import httpx


class PaperclipClient:
    def __init__(
        self,
        base_url: str,
        token: str,
        company_id: str,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._company_id = company_id
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": f"Bearer {token}"},
            transport=transport,
            timeout=timeout,
        )

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self._client.aclose()

    async def list_issues(self) -> list[dict[str, Any]]:
        resp = await self._client.get(f"/api/companies/{self._company_id}/issues")
        resp.raise_for_status()
        data = resp.json()
        # API returns either {"issues":[...]} or a bare list depending on endpoint version.
        if isinstance(data, dict):
            issues = data.get("issues", [])
            return list(issues) if isinstance(issues, list) else []
        if isinstance(data, list):
            return data
        return []

    async def list_comments_for_issue(self, issue_id: str) -> list[dict[str, Any]]:
        resp = await self._client.get(f"/api/issues/{issue_id}/comments")
        resp.raise_for_status()
        data = resp.json()
        return list(data) if isinstance(data, list) else []

    async def list_agents(self) -> list[dict[str, Any]]:
        resp = await self._client.get(f"/api/companies/{self._company_id}/agents")
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict):
            agents = data.get("agents", [])
            return list(agents) if isinstance(agents, list) else []
        if isinstance(data, list):
            return data
        return []
