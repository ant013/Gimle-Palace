"""Shared fixtures for integration tests."""

from __future__ import annotations

import asyncio
import os
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import pytest
import uvicorn
from fastapi import FastAPI, HTTPException, Request


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    skip_marker = pytest.mark.skip(reason="PAPERCLIP_API_KEY not set")
    for item in items:
        if "requires_paperclip" in item.keywords and not os.environ.get("PAPERCLIP_API_KEY"):
            item.add_marker(skip_marker)


@dataclass
class MockPaperclipState:
    issues: dict[str, dict[str, Any]] = field(default_factory=dict)
    comments_posted: list[tuple[str, str]] = field(default_factory=list)


def build_mock_app(state: MockPaperclipState) -> FastAPI:
    app = FastAPI()

    @app.get("/api/companies/{company_id}/issues")
    async def list_issues(company_id: str, status: str = "") -> list[dict[str, Any]]:
        return [
            dict(issue, id=iid)
            for iid, issue in state.issues.items()
            if issue.get("status") == status or not status
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
        return dict(state.issues[issue_id], id=issue_id)

    @app.post("/api/issues/{issue_id}/release")
    async def release_issue(issue_id: str) -> dict[str, Any]:
        if issue_id not in state.issues:
            raise HTTPException(404, "not found")
        state.issues[issue_id]["assigneeAgentId"] = None
        state.issues[issue_id]["executionRunId"] = None
        return {"ok": True}

    @app.post("/api/issues/{issue_id}/comments")
    async def post_comment(issue_id: str, request: Request) -> dict[str, Any]:
        body = await request.json()
        state.comments_posted.append((issue_id, body.get("body", "")))
        return {"id": f"comment-{len(state.comments_posted)}"}

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
