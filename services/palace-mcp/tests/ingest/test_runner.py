"""Runner unit tests using AsyncMock for Neo4j driver and httpx.MockTransport for client."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from palace_mcp.ingest.paperclip_client import PaperclipClient
from palace_mcp.ingest.runner import run_ingest


def _make_mock_driver(session_mock: MagicMock) -> MagicMock:
    """Build a minimal AsyncDriver mock that yields session_mock from session()."""
    driver = MagicMock()
    driver.session.return_value.__aenter__ = AsyncMock(return_value=session_mock)
    driver.session.return_value.__aexit__ = AsyncMock(return_value=None)
    return driver


def _make_session(project_found: bool = True) -> MagicMock:
    session = MagicMock()
    session.execute_write = AsyncMock(return_value=None)
    # Mock session.run for project validation query
    row = MagicMock() if project_found else None
    run_result = MagicMock()
    run_result.single = AsyncMock(return_value=row)
    session.run = AsyncMock(return_value=run_result)
    return session


def _paperclip_handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if "/agents" in path:
        return httpx.Response(
            200,
            json=[
                {
                    "id": "a1",
                    "name": "A",
                    "urlKey": "a",
                    "role": "",
                    "createdAt": "2026-01-01T00:00:00Z",
                    "updatedAt": "2026-01-01T00:00:00Z",
                }
            ],
        )
    if "/comments" in path:
        return httpx.Response(
            200,
            json=[
                {
                    "id": "c1",
                    "body": "hi",
                    "issueId": "i1",
                    "authorAgentId": None,
                    "createdAt": "2026-01-01T00:00:00Z",
                }
            ],
        )
    if "/issues" in path:
        return httpx.Response(
            200,
            json={
                "issues": [
                    {
                        "id": "i1",
                        "identifier": "GIM-1",
                        "title": "T",
                        "status": "done",
                        "createdAt": "2026-01-01T00:00:00Z",
                        "updatedAt": "2026-01-01T00:00:00Z",
                    }
                ]
            },
        )
    return httpx.Response(404)


@pytest.mark.asyncio
async def test_run_ingest_happy_path_calls_all_write_paths() -> None:
    session = _make_session()
    driver = _make_mock_driver(session)

    transport = httpx.MockTransport(_paperclip_handler)
    async with PaperclipClient(
        base_url="https://pc", token="t", company_id="co-1", transport=transport
    ) as client:
        result = await run_ingest(client=client, driver=driver, group_id="project/test")

    assert result["errors"] == []
    # execute_write is called: create_ingest_run, agents, issues, comments, gc*3, finalize
    assert session.execute_write.call_count >= 7


class TestRunIngestGroupId:
    """Task 8: group_id must be threaded through every write path."""

    @pytest.mark.asyncio
    async def test_run_ingest_accepts_group_id_kwarg(self) -> None:
        session = _make_session()
        driver = _make_mock_driver(session)
        transport = httpx.MockTransport(_paperclip_handler)
        async with PaperclipClient(
            base_url="https://pc", token="t", company_id="co-1", transport=transport
        ) as client:
            result = await run_ingest(
                client=client, driver=driver, group_id="project/test"
            )
        assert result["errors"] == []

    @pytest.mark.asyncio
    async def test_run_ingest_passes_group_id_to_create_ingest_run(self) -> None:
        session = _make_session()
        driver = _make_mock_driver(session)
        transport = httpx.MockTransport(_paperclip_handler)
        async with PaperclipClient(
            base_url="https://pc", token="t", company_id="co-1", transport=transport
        ) as client:
            await run_ingest(client=client, driver=driver, group_id="project/test")

        all_kwargs = [c.kwargs for c in session.execute_write.call_args_list]
        group_ids = [kw["group_id"] for kw in all_kwargs if "group_id" in kw]
        assert group_ids, "group_id not passed to any execute_write call"
        assert all(gid == "project/test" for gid in group_ids)

    @pytest.mark.asyncio
    async def test_run_ingest_passes_group_id_to_gc(self) -> None:
        session = _make_session()
        driver = _make_mock_driver(session)
        transport = httpx.MockTransport(_paperclip_handler)
        async with PaperclipClient(
            base_url="https://pc", token="t", company_id="co-1", transport=transport
        ) as client:
            await run_ingest(client=client, driver=driver, group_id="project/scoped")

        gc_kwargs = [
            c.kwargs
            for c in session.execute_write.call_args_list
            if "label" in c.kwargs
        ]
        assert len(gc_kwargs) == 3, f"Expected 3 GC calls, got {len(gc_kwargs)}"
        assert all(kw.get("group_id") == "project/scoped" for kw in gc_kwargs)


class TestRunIngestProjectValidation:
    """Task 10: run_ingest validates :Project exists before writing."""

    @pytest.mark.asyncio
    async def test_rejects_unregistered_project(self) -> None:
        from palace_mcp.memory.projects import UnknownProjectError

        session = _make_session(project_found=False)
        driver = _make_mock_driver(session)
        transport = httpx.MockTransport(_paperclip_handler)
        async with PaperclipClient(
            base_url="https://pc", token="t", company_id="co-1", transport=transport
        ) as client:
            with pytest.raises(UnknownProjectError, match="ghost"):
                await run_ingest(client=client, driver=driver, group_id="project/ghost")

    @pytest.mark.asyncio
    async def test_accepts_registered_project(self) -> None:
        session = _make_session(project_found=True)

        driver = _make_mock_driver(session)
        transport = httpx.MockTransport(_paperclip_handler)
        async with PaperclipClient(
            base_url="https://pc", token="t", company_id="co-1", transport=transport
        ) as client:
            result = await run_ingest(
                client=client, driver=driver, group_id="project/gimle"
            )
        assert result["errors"] == []


@pytest.mark.asyncio
async def test_run_ingest_records_error_on_exception() -> None:
    session = _make_session()
    # Make upsert raise on second call (agents OK, issues fail)
    call_count = 0

    async def side_effect(fn: Any, *args: Any, **kwargs: Any) -> None:
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise RuntimeError("neo4j down")

    session.execute_write.side_effect = side_effect
    driver = _make_mock_driver(session)

    transport = httpx.MockTransport(_paperclip_handler)
    async with PaperclipClient(
        base_url="https://pc", token="t", company_id="co-1", transport=transport
    ) as client:
        with pytest.raises(RuntimeError):
            await run_ingest(client=client, driver=driver, group_id="project/test")
