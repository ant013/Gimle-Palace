"""Shared fixtures for integration tests."""

from __future__ import annotations

import asyncio
import os
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
import uvicorn
from fastapi import FastAPI, HTTPException, Request

from gimle_watchdog.config import Config
from gimle_watchdog.paperclip import PaperclipClient


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    skip_marker = pytest.mark.skip(reason="PAPERCLIP_API_KEY not set")
    for item in items:
        if "requires_paperclip" in item.keywords and not os.environ.get("PAPERCLIP_API_KEY"):
            item.add_marker(skip_marker)


@dataclass
class MockPaperclipState:
    issues: dict[str, dict[str, Any]] = field(default_factory=dict)
    comments_posted: list[tuple[str, str]] = field(default_factory=list)
    # issue_id → list of comment dicts (for GET /comments)
    issue_comments: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    # company_id → list of agent dicts (for GET /agents)
    agents: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    companies: list[dict[str, Any]] = field(default_factory=list)


def build_mock_app(state: MockPaperclipState) -> FastAPI:
    app = FastAPI()

    @app.get("/api/companies/{company_id}/issues")
    async def list_issues(company_id: str, status: str = "") -> list[dict[str, Any]]:
        # Support comma-separated status filter (e.g. "todo,in_progress,in_review")
        wanted = {s.strip() for s in status.split(",") if s.strip()}
        return [
            dict(issue, id=iid)
            for iid, issue in state.issues.items()
            if not wanted or issue.get("status") in wanted
        ]

    @app.get("/api/issues/{issue_id}")
    async def get_issue(issue_id: str) -> dict[str, Any]:
        if issue_id not in state.issues:
            raise HTTPException(404, "not found")
        return dict(state.issues[issue_id], id=issue_id)

    @app.patch("/api/issues/{issue_id}")
    async def patch_issue(issue_id: str, request: Request) -> dict[str, Any]:
        if issue_id not in state.issues:
            raise HTTPException(404, "not found")
        body = await request.json()
        if "assigneeAgentId" in body:
            state.issues[issue_id]["assigneeAgentId"] = body["assigneeAgentId"]
            # Simulate paperclip spawning a new run on assignment event
            state.issues[issue_id]["executionRunId"] = f"run-{issue_id}-new"
            state.issues[issue_id]["updatedAt"] = (
                datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            )
        if "status" in body:
            state.issues[issue_id]["status"] = body["status"]
            state.issues[issue_id]["updatedAt"] = (
                datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            )
        return dict(state.issues[issue_id], id=issue_id)

    @app.post("/api/issues/{issue_id}/release")
    async def release_issue(issue_id: str) -> dict[str, Any]:
        if issue_id not in state.issues:
            raise HTTPException(404, "not found")
        state.issues[issue_id]["assigneeAgentId"] = None
        state.issues[issue_id]["executionRunId"] = None
        return {"ok": True}

    @app.get("/api/issues/{issue_id}/comments")
    async def list_comments(issue_id: str, limit: int = 5) -> list[dict[str, Any]]:
        comments = state.issue_comments.get(issue_id, [])
        return comments[-limit:] if limit else comments

    @app.post("/api/issues/{issue_id}/comments")
    async def post_comment(issue_id: str, request: Request) -> dict[str, Any]:
        body = await request.json()
        state.comments_posted.append((issue_id, body.get("body", "")))
        return {"id": f"comment-{len(state.comments_posted)}"}

    @app.get("/api/companies/{company_id}/agents")
    async def list_agents(company_id: str) -> list[dict[str, Any]]:
        return state.agents.get(company_id, [])

    @app.get("/api/companies")
    async def list_companies() -> list[dict[str, Any]]:
        return list(state.companies)

    return app


@contextmanager
def _run_server(app: FastAPI, host: str = "127.0.0.1", port: int = 0):  # type: ignore[misc]
    config = uvicorn.Config(app, host=host, port=port, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=asyncio.run, args=(server.serve(),), daemon=True)
    thread.start()
    for _ in range(50):
        if server.started:
            break
        time.sleep(0.05)
    try:
        actual_port = server.servers[0].sockets[0].getsockname()[1]
        yield f"http://{host}:{actual_port}"
    finally:
        server.should_exit = True
        thread.join(timeout=5)


@pytest.fixture
def mock_paperclip():  # type: ignore[misc]
    state = MockPaperclipState()
    app = build_mock_app(state)
    with _run_server(app) as base_url:
        yield base_url, state


@pytest.fixture
def observe_only_config() -> Config:
    from tests._factories import _make_config

    return _make_config()


@pytest.fixture
def recovery_only_config() -> Config:
    from tests._factories import _make_config

    return _make_config(recovery_enabled=True)


@pytest.fixture
def alert_only_config() -> Config:
    from tests._factories import _make_config

    return _make_config(any_alert=True)


@pytest.fixture
def full_watchdog_config() -> Config:
    from tests._factories import _make_config

    return _make_config(recovery_enabled=True, any_alert=True)


@pytest.fixture
def full_alert_config(full_watchdog_config: Config) -> Config:
    return full_watchdog_config


@pytest.fixture
def unsafe_auto_repair_config() -> Config:
    from tests._factories import _make_config

    return _make_config(auto_repair=True)


@pytest.fixture
def observe_only_config_file(tmp_path: Path) -> Path:
    cfg_path = tmp_path / "observe-only.yaml"
    cfg_path.write_text(
        """
version: 1
paperclip: {base_url: http://test, api_key_source: "inline:k"}
companies:
  - id: 9d8f432c-0000-4000-8000-000000000001
    name: Test
    thresholds:
      died_min: 30
      hang_etime_min: 45
      idle_cpu_ratio_max: 0.01
      hang_stream_idle_max_s: 300
      recover_max_age_min: 180
daemon:
  poll_interval_seconds: 60
  recovery_enabled: false
cooldowns:
  per_issue_seconds: 60
  per_agent_cap: 10
  per_agent_window_seconds: 3600
logging:
  path: /tmp/test-watchdog.log
  level: INFO
  rotate_max_bytes: 1000000
  rotate_backup_count: 3
escalation:
  post_comment_on_issue: false
  comment_marker: "[test]"
handoff:
  handoff_alert_enabled: false
  handoff_cross_team_enabled: false
  handoff_ownerless_enabled: false
  handoff_infra_block_enabled: false
  handoff_stale_bundle_enabled: false
  handoff_auto_repair_enabled: false
"""
    )
    return cfg_path


@pytest.fixture
async def fake_paperclip_client(mock_paperclip):
    base_url, state = mock_paperclip
    state.companies = [
        {"id": "9d8f432c-0000-4000-8000-000000000001", "name": "Test", "archived": False}
    ]
    client = PaperclipClient(base_url=base_url, api_key="test")
    try:
        yield client
    finally:
        await client.aclose()
