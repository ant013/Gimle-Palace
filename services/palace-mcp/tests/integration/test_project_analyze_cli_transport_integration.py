"""Live MCP transport integration for the project analyze CLI helpers."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import textwrap
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

import palace_mcp.cli as cli

_SERVER_SCRIPT = textwrap.dedent(
    """
    from __future__ import annotations

    import contextlib
    import sys
    from fastapi import FastAPI
    import uvicorn

    import palace_mcp.mcp_server as mcp_module
    from palace_mcp.project_analyze import (
        AnalysisCheckpoint,
        AnalysisCheckpointStatus,
        AnalysisRun,
        AnalysisRunStartResult,
        AnalysisRunStatus,
    )

    NOW = "2026-05-15T10:00:00+00:00"
    status_calls = 0


    def make_run(run_id: str, status: AnalysisRunStatus) -> AnalysisRun:
        return AnalysisRun(
            run_id=run_id,
            slug="tron-kit",
            project_name="TronKit",
            parent_mount="hs-stage",
            relative_path="TronKit.Swift",
            language_profile="swift_kit",
            bundle="uw-ios",
            extractors=["symbol_index_swift", "code_ownership"],
            depth="full",
            continue_on_failure=True,
            idempotency_key="idem-1",
            status=status,
            created_at=NOW,
            updated_at=NOW,
            started_at=NOW,
            finished_at=NOW if status == AnalysisRunStatus.SUCCEEDED_WITH_FAILURES else None,
            lease_owner=None,
            lease_expires_at=None,
            last_completed_extractor="code_ownership" if status == AnalysisRunStatus.SUCCEEDED_WITH_FAILURES else None,
            checkpoints=[
                AnalysisCheckpoint(
                    extractor="symbol_index_swift",
                    position=0,
                    status=AnalysisCheckpointStatus.OK,
                ),
                AnalysisCheckpoint(
                    extractor="code_ownership",
                    position=1,
                    status=(
                        AnalysisCheckpointStatus.RUN_FAILED
                        if status == AnalysisRunStatus.SUCCEEDED_WITH_FAILURES
                        else AnalysisCheckpointStatus.NOT_ATTEMPTED
                    ),
                    error_code="ownership_diff_failed"
                    if status == AnalysisRunStatus.SUCCEEDED_WITH_FAILURES
                    else None,
                ),
            ],
            overview={"OK": 1, "RUN_FAILED": 1}
            if status == AnalysisRunStatus.SUCCEEDED_WITH_FAILURES
            else {},
            audit=None,
            report_markdown="# staged run\\n"
            if status == AnalysisRunStatus.SUCCEEDED_WITH_FAILURES
            else None,
            next_actions=[]
            if status == AnalysisRunStatus.SUCCEEDED_WITH_FAILURES
            else ["resume after code_ownership repair"],
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
            assert parent_mount == "hs-stage"
            assert relative_path == "TronKit.Swift"
            assert language_profile == "swift_kit"
            assert bundle == "uw-ios"
            return AnalysisRunStartResult(
                run=make_run("run-123", AnalysisRunStatus.RUNNING),
                active_run_reused=False,
            )

        async def get_status(self, run_id: str) -> AnalysisRun:
            global status_calls
            status_calls += 1
            if status_calls == 1:
                return make_run(run_id, AnalysisRunStatus.RESUMABLE)
            return make_run(run_id, AnalysisRunStatus.SUCCEEDED_WITH_FAILURES)

        async def resume_run(self, run_id: str) -> AnalysisRun:
            return make_run(run_id, AnalysisRunStatus.RUNNING)


    def build_service() -> FakeService:
        return FakeService()


    app = FastAPI()


    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}


    mcp_module._driver = object()
    mcp_module._graphiti = object()
    mcp_module._project_analysis_tasks.clear()
    mcp_module._build_project_analysis_service = build_service
    mcp_module._schedule_project_analysis_execution = lambda **kwargs: False
    mcp_app = mcp_module.build_mcp_asgi_app()


    @contextlib.asynccontextmanager
    async def lifespan(_app: FastAPI):
        async with mcp_module._mcp.session_manager.run():
            yield


    app.router.lifespan_context = lifespan
    app.mount("/mcp", mcp_app)

    port = int(sys.argv[1])
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="error", access_log=False)
    """
)


def _free_port() -> int:
    import socket

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_server(
    port: int,
    process: subprocess.Popen[str],
    *,
    timeout_seconds: float = 10.0,
) -> None:
    import socket

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
def live_mcp_url() -> Iterator[str]:
    port = _free_port()
    with tempfile.NamedTemporaryFile(
        mode="w", suffix="_project_analyze_cli_server.py", delete=False
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
        yield f"http://127.0.0.1:{port}/mcp"
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        script_path.unlink(missing_ok=True)


@pytest.mark.integration
def test_wait_for_mcp_ready_accepts_live_healthz_and_session(
    live_mcp_url: str,
) -> None:
    assert cli.wait_for_mcp_ready(live_mcp_url, timeout_seconds=5) == live_mcp_url


@pytest.mark.integration
@pytest.mark.asyncio
async def test_run_project_analyze_to_terminal_reaches_terminal_status_over_live_mcp(
    live_mcp_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _no_sleep(_seconds: object) -> None:
        return None

    monkeypatch.setattr(cli.asyncio, "sleep", _no_sleep)

    payload = await cli._run_project_analyze_to_terminal(
        url=live_mcp_url,
        request_payload={
            "slug": "tron-kit",
            "parent_mount": "hs-stage",
            "relative_path": "TronKit.Swift",
            "language_profile": "swift_kit",
            "bundle": "uw-ios",
            "depth": "full",
            "extractors": ["symbol_index_swift", "code_ownership"],
            "idempotency_key": "idem-1",
        },
    )

    assert payload["ok"] is True
    assert payload["run_id"] == "run-123"
    assert payload["status"] == "SUCCEEDED_WITH_FAILURES"
    run = payload["run"]
    assert isinstance(run, dict)
    assert run["parent_mount"] == "hs-stage"
    assert run["relative_path"] == "TronKit.Swift"
    assert run["bundle"] == "uw-ios"
    assert run["language_profile"] == "swift_kit"
    assert run["overview"] == {"OK": 1, "RUN_FAILED": 1}
    checkpoints = run["checkpoints"]
    assert isinstance(checkpoints, list)
    assert [checkpoint["extractor"] for checkpoint in checkpoints] == [
        "symbol_index_swift",
        "code_ownership",
    ]
