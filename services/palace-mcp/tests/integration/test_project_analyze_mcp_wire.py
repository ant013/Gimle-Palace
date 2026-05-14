"""MCP wire-contract tests for palace.project.* analyze tools.

These tests go through the real streamable-HTTP transport via
streamablehttp_client. They validate MCP tool registration, request binding,
and structured error delivery for the new durable project-analyze surface.
"""

from __future__ import annotations

import json
import socket
import threading
import time
from collections.abc import Iterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from palace_mcp.project_analyze import (
    ActiveAnalysisRunExistsError,
    AnalysisCheckpoint,
    AnalysisRun,
    AnalysisRunStartResult,
    AnalysisRunStatus,
)

_NOW = "2026-05-15T10:00:00+00:00"
_PROJECT_ANALYZE_TOOLS = [
    "palace.project.analyze",
    "palace.project.analyze_status",
    "palace.project.analyze_resume",
]


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _TestServer:
    """Runs an ASGI app in a background daemon thread via uvicorn."""

    def __init__(self, app: object, port: int) -> None:
        import uvicorn

        config = uvicorn.Config(
            app,
            host="127.0.0.1",
            port=port,
            log_level="error",
            access_log=False,
        )
        self._server = uvicorn.Server(config)
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._server.run, daemon=True)
        self._thread.start()
        deadline = time.monotonic() + 5.0
        while not self._server.started:
            if time.monotonic() > deadline:
                raise RuntimeError("Test MCP server did not start within 5 s")
            time.sleep(0.05)

    def stop(self) -> None:
        self._server.should_exit = True
        if self._thread is not None:
            self._thread.join(timeout=5)


def _make_run(
    *,
    run_id: str = "run-123",
    status: AnalysisRunStatus = AnalysisRunStatus.PENDING,
    language_profile: str = "swift_kit",
) -> AnalysisRun:
    return AnalysisRun(
        run_id=run_id,
        slug="tron-kit",
        project_name="TronKit",
        parent_mount="hs",
        relative_path="TronKit.Swift",
        language_profile=language_profile,
        bundle=None,
        extractors=["code_ownership", "hotspot"],
        depth="full",
        continue_on_failure=True,
        idempotency_key="idem-1",
        status=status,
        created_at=_NOW,
        updated_at=_NOW,
        started_at=_NOW,
        finished_at=None,
        lease_owner=None,
        lease_expires_at=None,
        last_completed_extractor=None,
        checkpoints=[
            AnalysisCheckpoint(extractor="code_ownership", position=0),
            AnalysisCheckpoint(extractor="hotspot", position=1),
        ],
        overview={},
        audit=None,
        report_markdown=None,
        next_actions=[],
    )


@pytest.fixture(autouse=True)
def reset_project_analyze_state() -> Iterator[None]:
    import palace_mcp.mcp_server as mcp_module

    original_tasks = dict(mcp_module._project_analysis_tasks)
    mcp_module._project_analysis_tasks.clear()
    yield
    mcp_module._project_analysis_tasks.clear()
    mcp_module._project_analysis_tasks.update(original_tasks)


@pytest.fixture(scope="module")
def mcp_url() -> Iterator[str]:
    import palace_mcp.mcp_server as mcp_module

    original_driver = mcp_module._driver
    original_graphiti = mcp_module._graphiti
    app = mcp_module.build_mcp_asgi_app()
    port = _free_port()
    server = _TestServer(app, port)

    with (
        patch.object(mcp_module, "_driver", new=object()),
        patch.object(mcp_module, "_graphiti", new=object()),
        patch.object(
            mcp_module,
            "_schedule_project_analysis_execution",
            return_value=True,
        ),
    ):
        server.start()
        try:
            yield f"http://127.0.0.1:{port}/"
        finally:
            server.stop()
            mcp_module._driver = original_driver
            mcp_module._graphiti = original_graphiti


@pytest.mark.integration
async def test_project_analyze_tools_appear_in_tools_list(mcp_url: str) -> None:
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()

    names = [tool.name for tool in result.tools]
    for tool_name in _PROJECT_ANALYZE_TOOLS:
        assert tool_name in names, f"{tool_name} missing from tools/list. Got: {names}"

    for tool in result.tools:
        if tool.name in _PROJECT_ANALYZE_TOOLS:
            assert tool.inputSchema is not None, (
                f"{tool.name} has None inputSchema — wire binding broken"
            )


@pytest.mark.integration
async def test_project_analyze_wire_returns_ok_payload(mcp_url: str) -> None:
    import palace_mcp.mcp_server as mcp_module

    run = _make_run()
    service = MagicMock()
    service.start_run = AsyncMock(
        return_value=AnalysisRunStartResult(run=run, active_run_reused=False)
    )

    with patch.object(
        mcp_module,
        "_build_project_analysis_service",
        return_value=service,
    ):
        async with streamablehttp_client(mcp_url) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "palace.project.analyze",
                    {
                        "slug": "tron-kit",
                        "parent_mount": "hs",
                        "relative_path": "TronKit.Swift",
                        "language_profile": "swift_kit",
                        "idempotency_key": "idem-1",
                    },
                )

    assert result.isError is False
    payload = json.loads(result.content[0].text)
    assert payload["ok"] is True
    assert payload["run_id"] == "run-123"
    assert payload["background_execution_scheduled"] is True


@pytest.mark.integration
async def test_project_analyze_status_wire_returns_ok_payload(mcp_url: str) -> None:
    import palace_mcp.mcp_server as mcp_module

    run = _make_run(status=AnalysisRunStatus.RESUMABLE)
    service = MagicMock()
    service.get_status = AsyncMock(return_value=run)

    with patch.object(
        mcp_module,
        "_build_project_analysis_service",
        return_value=service,
    ):
        async with streamablehttp_client(mcp_url) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "palace.project.analyze_status",
                    {"run_id": "run-123"},
                )

    assert result.isError is False
    payload = json.loads(result.content[0].text)
    assert payload["ok"] is True
    assert payload["status"] == "RESUMABLE"
    assert payload["run_id"] == "run-123"


@pytest.mark.integration
async def test_project_analyze_resume_wire_returns_ok_payload(mcp_url: str) -> None:
    import palace_mcp.mcp_server as mcp_module

    run = _make_run(status=AnalysisRunStatus.RUNNING)
    service = MagicMock()
    service.resume_run = AsyncMock(return_value=run)

    with patch.object(
        mcp_module,
        "_build_project_analysis_service",
        return_value=service,
    ):
        async with streamablehttp_client(mcp_url) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "palace.project.analyze_resume",
                    {"run_id": "run-123"},
                )

    assert result.isError is False
    payload = json.loads(result.content[0].text)
    assert payload["ok"] is True
    assert payload["status"] == "RUNNING"
    assert payload["background_execution_scheduled"] is True


@pytest.mark.integration
async def test_project_analyze_wire_invalid_depth_returns_mcp_error(
    mcp_url: str,
) -> None:
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "palace.project.analyze",
                {
                    "slug": "tron-kit",
                    "parent_mount": "hs",
                    "relative_path": "TronKit.Swift",
                    "language_profile": "swift_kit",
                    "depth": "invalid-depth",
                },
            )

    assert result.isError is True
    error_text = " ".join(
        content.text for content in result.content if hasattr(content, "text")
    )
    assert "validation" in error_text.lower() or "invalid" in error_text.lower()


@pytest.mark.integration
async def test_project_analyze_wire_conflict_returns_error_envelope(
    mcp_url: str,
) -> None:
    import palace_mcp.mcp_server as mcp_module

    service = MagicMock()
    service.start_run = AsyncMock(
        side_effect=ActiveAnalysisRunExistsError("run-existing")
    )

    with patch.object(
        mcp_module,
        "_build_project_analysis_service",
        return_value=service,
    ):
        async with streamablehttp_client(mcp_url) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "palace.project.analyze",
                    {
                        "slug": "tron-kit",
                        "parent_mount": "hs",
                        "relative_path": "TronKit.Swift",
                        "language_profile": "swift_kit",
                        "idempotency_key": "different-key",
                    },
                )

    assert result.isError is False
    payload = json.loads(result.content[0].text)
    assert payload["ok"] is False
    assert payload["error_code"] == "ACTIVE_ANALYSIS_RUN_EXISTS"
    assert payload["run_id"] == "run-existing"
