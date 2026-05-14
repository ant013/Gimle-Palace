"""MCP wire-contract tests for palace.project.* analyze tools.

These tests go through the real streamable-HTTP transport via
streamablehttp_client. The MCP server runs in a fresh subprocess so the tests
do not mutate the in-process FastMCP registry used by the rest of the suite.
"""

from __future__ import annotations

import json
import socket
import subprocess
import sys
import tempfile
import textwrap
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

_PROJECT_ANALYZE_TOOLS = [
    "palace.project.analyze",
    "palace.project.analyze_status",
    "palace.project.analyze_resume",
]

_SERVER_SCRIPT = textwrap.dedent(
    """
    from __future__ import annotations

    import sys

    import uvicorn

    import palace_mcp.mcp_server as mcp_module
    from palace_mcp.project_analyze import (
        ActiveAnalysisRunExistsError,
        AnalysisCheckpoint,
        AnalysisRun,
        AnalysisRunStartResult,
        AnalysisRunStatus,
    )

    NOW = "2026-05-15T10:00:00+00:00"


    def make_run(
        *,
        run_id: str,
        status: AnalysisRunStatus,
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
            created_at=NOW,
            updated_at=NOW,
            started_at=NOW,
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


    class FakeService:
        async def start_run(
            self,
            *,
            slug: str,
            parent_mount: str,
            relative_path: str,
            language_profile: str,
            name: str | None = None,
            bundle: str | None = None,
            extractors: list[str] | None = None,
            depth: str = "full",
            continue_on_failure: bool = True,
            idempotency_key: str | None = None,
            force_new: bool = False,
        ) -> AnalysisRunStartResult:
            if idempotency_key == "different-key":
                raise ActiveAnalysisRunExistsError("run-existing")
            run = make_run(run_id="run-123", status=AnalysisRunStatus.PENDING)
            return AnalysisRunStartResult(run=run, active_run_reused=False)

        async def get_status(self, run_id: str) -> AnalysisRun:
            return make_run(run_id=run_id, status=AnalysisRunStatus.RESUMABLE)

        async def resume_run(self, run_id: str) -> AnalysisRun:
            return make_run(run_id=run_id, status=AnalysisRunStatus.RUNNING)


    def build_service() -> FakeService:
        return FakeService()


    mcp_module._driver = object()
    mcp_module._graphiti = object()
    mcp_module._project_analysis_tasks.clear()
    mcp_module._build_project_analysis_service = build_service
    mcp_module._schedule_project_analysis_execution = lambda **kwargs: True

    port = int(sys.argv[1])
    app = mcp_module.build_mcp_asgi_app()
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="error", access_log=False)
    """
)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_server(
    port: int,
    process: subprocess.Popen[str],
    *,
    timeout_seconds: float = 10.0,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if process.poll() is not None:
            stderr = process.stderr.read() if process.stderr is not None else ""
            raise RuntimeError(
                f"Test MCP server exited before startup with code {process.returncode}: {stderr}"
            )
        with socket.socket() as sock:
            sock.settimeout(0.2)
            try:
                sock.connect(("127.0.0.1", port))
            except OSError:
                time.sleep(0.05)
                continue
            return

    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=1)
    stderr = process.stderr.read() if process.stderr is not None else ""
    raise RuntimeError(
        f"Test MCP server did not start within {timeout_seconds} s: {stderr}"
    )


@pytest.fixture(scope="module")
def mcp_url() -> Iterator[str]:
    port = _free_port()
    with tempfile.NamedTemporaryFile(
        mode="w", suffix="_project_analyze_wire_server.py", delete=False
    ) as script_file:
        script_file.write(_SERVER_SCRIPT)
        script_path = Path(script_file.name)

    process = subprocess.Popen(
        [sys.executable, str(script_path), str(port)],
        cwd=Path(__file__).resolve().parents[2],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        _wait_for_server(port, process)
        yield f"http://127.0.0.1:{port}/"
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        script_path.unlink(missing_ok=True)


def test_wait_for_server_timeout_terminates_child() -> None:
    with tempfile.NamedTemporaryFile(
        mode="w", suffix="_project_analyze_wire_hang.py", delete=False
    ) as script_file:
        script_file.write(
            "import sys, time\n"
            "sys.stderr.write('booting...')\n"
            "sys.stderr.flush()\n"
            "time.sleep(30)\n"
        )
        script_path = Path(script_file.name)

    process = subprocess.Popen(
        [sys.executable, str(script_path)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        with pytest.raises(RuntimeError, match="did not start within"):
            _wait_for_server(_free_port(), process, timeout_seconds=0.1)
        assert process.poll() is not None
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        script_path.unlink(missing_ok=True)


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
