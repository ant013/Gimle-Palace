"""Paperclip REST client — async httpx wrapper with retry + 429 backoff."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx


log = logging.getLogger("watchdog.paperclip")


RETRY_STATUSES = {429, 500, 502, 503, 504}
RETRY_DELAYS_SECONDS = (5, 15, 30)  # up to 4 total attempts
MAX_RETRIES = len(RETRY_DELAYS_SECONDS)


class PaperclipError(Exception):
    """Raised when paperclip API returns a terminal error or all retries exhausted."""


@dataclass(frozen=True)
class Issue:
    id: str
    assignee_agent_id: str | None
    execution_run_id: str | None
    status: str
    updated_at: datetime


async def _sleep(seconds: float) -> None:
    """Indirection for tests to patch out real sleep."""
    await asyncio.sleep(seconds)


def _parse_iso(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)


def _issue_from_json(data: dict[str, Any]) -> Issue:
    return Issue(
        id=str(data["id"]),
        assignee_agent_id=data.get("assigneeAgentId"),
        execution_run_id=data.get("executionRunId"),
        status=str(data.get("status", "")),
        updated_at=_parse_iso(str(data.get("updatedAt", "1970-01-01T00:00:00Z"))),
    )


class PaperclipClient:
    """Thin httpx async wrapper with retry-on-5xx-and-429 + non-retry on 4xx."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            timeout=httpx.Timeout(connect=10.0, read=timeout, write=timeout, pool=timeout),
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        last_exc: Exception | None = None
        for attempt in range(MAX_RETRIES + 1):
            if attempt > 0:
                await _sleep(RETRY_DELAYS_SECONDS[attempt - 1])
            try:
                resp = await self._client.request(method, url, **kwargs)
            except httpx.RequestError as e:
                last_exc = e
                log.warning("paperclip_request_error attempt=%d url=%s error=%s", attempt, url, e)
                continue
            if resp.status_code < 400:
                return resp
            if resp.status_code in RETRY_STATUSES:
                log.warning(
                    "paperclip_retry status=%d attempt=%d url=%s", resp.status_code, attempt, url
                )
                last_exc = PaperclipError(
                    f"paperclip {method} {url} returned {resp.status_code}: {resp.text[:200]}"
                )
                continue
            # Terminal 4xx (not 429 which is in RETRY_STATUSES)
            raise PaperclipError(
                f"paperclip {method} {url} returned {resp.status_code}: {resp.text[:200]}"
            )
        raise PaperclipError(
            f"paperclip {method} {url} exhausted {MAX_RETRIES + 1} attempts: {last_exc}"
        ) from last_exc

    async def list_in_progress_issues(self, company_id: str) -> list[Issue]:
        resp = await self._request(
            "GET", f"/api/companies/{company_id}/issues?status=in_progress"
        )
        data = resp.json()
        if not isinstance(data, list):
            raise PaperclipError(f"expected list, got {type(data).__name__}")
        return [_issue_from_json(d) for d in data]

    async def get_issue(self, issue_id: str) -> Issue:
        resp = await self._request("GET", f"/api/issues/{issue_id}")
        return _issue_from_json(resp.json())

    async def patch_issue(self, issue_id: str, body: dict[str, Any]) -> None:
        await self._request("PATCH", f"/api/issues/{issue_id}", json=body)

    async def post_release(self, issue_id: str) -> None:
        await self._request("POST", f"/api/issues/{issue_id}/release")

    async def post_issue_comment(self, issue_id: str, body: str) -> None:
        await self._request(
            "POST", f"/api/issues/{issue_id}/comments", json={"body": body}
        )
