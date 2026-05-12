"""Paperclip REST client — async httpx wrapper with retry + 429 backoff."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from gimle_watchdog.models import Agent, Comment


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
    issue_number: int = 0
    origin_kind: str | None = None
    parent_id: str | None = None


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
        issue_number=int(data.get("issueNumber") or 0),
        origin_kind=(str(data["originKind"]) if data.get("originKind") is not None else None),
        parent_id=(str(data["parentId"]) if data.get("parentId") is not None else None),
    )


def _comment_from_json(data: dict[str, Any]) -> Comment:
    raw_ts = str(data.get("createdAt", ""))
    # Parse without tz coercion first to detect naive timestamps.
    dt_raw = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
    if dt_raw.tzinfo is None:
        raise PaperclipError(f"comment createdAt is naive (server contract violation): {raw_ts!r}")
    dt = dt_raw.astimezone(timezone.utc)
    return Comment(
        id=str(data["id"]),
        body=str(data.get("body", "")),
        author_agent_id=data.get("authorAgentId"),
        created_at=dt,
    )


def _agent_from_json(data: dict[str, Any]) -> Agent:
    return Agent(
        id=str(data["id"]),
        name=str(data.get("name", "")),
        status=str(data.get("status", "")),
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
        self._last_response_date: datetime | None = None

    @property
    def last_response_date(self) -> datetime | None:
        """Server-clock anchor: parsed `Date` header from the most recent
        successful HTTP response. Used by the handoff detector to avoid
        local-clock skew per spec §4.2.1."""
        return self._last_response_date

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        retry_statuses = set(kwargs.pop("_retry_statuses", RETRY_STATUSES))
        retry_request_errors = bool(kwargs.pop("_retry_request_errors", True))
        max_retries = int(kwargs.pop("_max_retries", MAX_RETRIES))
        retry_delays = RETRY_DELAYS_SECONDS[:max_retries]
        last_exc: Exception | None = None
        for attempt in range(max_retries + 1):
            if attempt > 0:
                await _sleep(retry_delays[attempt - 1])
            try:
                resp = await self._client.request(method, url, **kwargs)
            except httpx.RequestError as e:
                last_exc = e
                log.warning("paperclip_request_error attempt=%d url=%s error=%s", attempt, url, e)
                if not retry_request_errors:
                    break
                continue
            if resp.status_code < 400:
                self._capture_response_date(resp)
                return resp
            if resp.status_code in retry_statuses:
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
            f"paperclip {method} {url} exhausted {max_retries + 1} attempts: {last_exc}"
        ) from last_exc

    def _capture_response_date(self, resp: httpx.Response) -> None:
        date_header = resp.headers.get("Date") or resp.headers.get("date")
        if not date_header:
            return
        try:
            parsed = parsedate_to_datetime(date_header)
        except (TypeError, ValueError):
            return
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        self._last_response_date = parsed.astimezone(timezone.utc)

    async def list_in_progress_issues(self, company_id: str) -> list[Issue]:
        resp = await self._request("GET", f"/api/companies/{company_id}/issues?status=in_progress")
        data = resp.json()
        if not isinstance(data, list):
            raise PaperclipError(f"expected list, got {type(data).__name__}")
        return [_issue_from_json(d) for d in data]

    async def list_active_issues(self, company_id: str) -> list[Issue]:
        """GET issues with status todo, in_progress, in_review, or blocked."""
        resp = await self._request(
            "GET",
            f"/api/companies/{company_id}/issues?status=todo,in_progress,in_review,blocked",
        )
        data = resp.json()
        if not isinstance(data, list):
            raise PaperclipError(f"expected list, got {type(data).__name__}")
        return [_issue_from_json(d) for d in data]

    async def list_done_issues(self, company_id: str) -> list[Issue]:
        """GET issues with status=done (for ownerless_completion detection)."""
        resp = await self._request(
            "GET",
            f"/api/companies/{company_id}/issues?status=done",
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

    async def post_issue_comment(self, issue_id: str, body: str) -> str | None:
        resp = await self._request(
            "POST",
            f"/api/issues/{issue_id}/comments",
            json={"body": body},
            _retry_statuses=frozenset(),
            _retry_request_errors=False,
            _max_retries=0,
        )
        data = resp.json()
        if isinstance(data, dict):
            return str(data.get("id", "")) or None
        return None

    async def list_recent_comments(self, issue_id: str, limit: int = 5) -> list[Comment]:
        """GET /api/issues/{issue_id}/comments?limit={N}. Returns tz-aware UTC Comment list."""
        resp = await self._request("GET", f"/api/issues/{issue_id}/comments?limit={limit}")
        data = resp.json()
        if not isinstance(data, list):
            raise PaperclipError(f"expected list from comments, got {type(data).__name__}")
        return [_comment_from_json(d) for d in data]

    async def list_company_agents(self, company_id: str) -> list[Agent]:
        """GET /api/companies/{company_id}/agents. Returns all hired Agent dataclasses."""
        resp = await self._request("GET", f"/api/companies/{company_id}/agents")
        data = resp.json()
        if not isinstance(data, list):
            raise PaperclipError(f"expected list from agents, got {type(data).__name__}")
        return [_agent_from_json(d) for d in data]
