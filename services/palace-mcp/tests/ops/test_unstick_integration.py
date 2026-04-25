"""Integration tests for palace_mcp.ops.unstick.

Mock-based: patches asyncio.create_subprocess_exec (SSH/ps/kill) and
httpx.AsyncClient (paperclip API). No real SSH or live paperclip needed.

Per spec §5.2 (CR NOTE: mock asyncio.create_subprocess_exec, not subprocess.run).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from palace_mcp.ops.unstick import unstick_issue

_FAKE_RUN_ID = "abc12345-dead-beef-cafe-111122223333"
_NEW_RUN_ID = "ffffffff-0000-1111-2222-333344445555"

# executionLockedAt ~90 minutes ago → PID 42 (etime=01:30:00) matches strict
_LOCKED_AT_90MIN = (datetime.now(timezone.utc) - timedelta(minutes=90)).isoformat()

_PS_CLAUDE_90MIN = (
    "PID ELAPSED %CPU COMMAND\n"
    "  42 01:30:00  0.0 claude --print --add-dir /tmp/paperclip-skills-XYZ/\n"
)


def _build_kwargs(graphiti: object = None) -> dict:
    return dict(
        dry_run=False,
        force=False,
        timeout_sec=10,
        ops_host="local",
        ssh_key="/home/appuser/.ssh/palace_ops_id_ed25519",
        ssh_user="anton",
        api_url="http://localhost:3100",
        graphiti=graphiti,
        group_id="project/test",
    )


def _make_fake_proc(stdout: str = "", rc: int = 0) -> MagicMock:
    proc = MagicMock()
    proc.returncode = rc
    proc.communicate = AsyncMock(return_value=(stdout.encode(), b""))
    return proc


def _make_http_client_mock(issue_responses: list[dict]) -> tuple[MagicMock, MagicMock]:
    """Return (mock_cls, mock_client) pre-wired with sequential API responses."""
    mock_client = AsyncMock()
    mock_cls = MagicMock()
    mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
    mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

    responses = iter(issue_responses)

    async def _get(*args: object, **kwargs: object) -> MagicMock:
        resp = MagicMock()
        resp.json.return_value = next(responses)
        resp.raise_for_status = MagicMock()
        return resp

    mock_client.get = _get
    return mock_cls, mock_client


# ---------------------------------------------------------------------------
# Test 1: full flow — kill then clear
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unstick_full_flow_kill_then_clear() -> None:
    """Paperclip returns stale lock; kill runs; lock clears; audit episode saved."""
    subprocess_calls: list[tuple[str, ...]] = []

    async def fake_create_subprocess(*args: str, **kwargs: object) -> MagicMock:
        subprocess_calls.append(args)
        stdout = _PS_CLAUDE_90MIN if "ps" in args else ""
        return _make_fake_proc(stdout=stdout)

    mock_graphiti = MagicMock()
    # First httpx call: initial issue fetch (locked)
    # Respawn-check call: issue is clear (same client context since poll mocked)
    mock_cls, _ = _make_http_client_mock(
        [
            {"executionRunId": _FAKE_RUN_ID, "executionLockedAt": _LOCKED_AT_90MIN},
            {"executionRunId": None, "executionLockedAt": None},  # respawn check
        ]
    )

    with (
        patch("palace_mcp.ops.unstick.httpx.AsyncClient", mock_cls),
        patch(
            "asyncio.create_subprocess_exec",
            side_effect=fake_create_subprocess,
        ),
        patch(
            "palace_mcp.ops.unstick.save_entity_node", new_callable=AsyncMock
        ) as mock_save,
        patch(
            "palace_mcp.ops.unstick._poll_until_cleared", new_callable=AsyncMock
        ) as mock_poll,
    ):
        mock_poll.return_value = True

        result = await unstick_issue(
            "issue-abc", **_build_kwargs(graphiti=mock_graphiti)
        )

    assert result["ok"] is True
    assert result["action"] == "killed"
    assert result["killed_pids"] == [42]
    assert result["heuristic"] == "strict"

    commands = [call[0] for call in subprocess_calls]
    assert "ps" in commands, "Expected ps command"
    assert "kill" in commands, "Expected kill command"

    mock_save.assert_awaited_once()
    node = mock_save.call_args.args[1]
    assert node.attributes["target_issue"] == "issue-abc"
    assert node.attributes["outcome"] == "killed"


# ---------------------------------------------------------------------------
# Test 2: paperclip respawns within poll window
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unstick_paperclip_respawns_within_poll_window() -> None:
    """After kill, paperclip starts a new run on same issue (new executionRunId).

    Tool should report {ok: True, action: killed_then_respawned, new_run_id: ...}.
    """

    async def fake_create_subprocess(*args: str, **kwargs: object) -> MagicMock:
        stdout = _PS_CLAUDE_90MIN if "ps" in args else ""
        return _make_fake_proc(stdout=stdout)

    # First httpx context: initial issue fetch (locked)
    # Second httpx context: respawn check after poll timeout → new run_id
    mock_cls, _ = _make_http_client_mock(
        [
            {"executionRunId": _FAKE_RUN_ID, "executionLockedAt": _LOCKED_AT_90MIN},
            {"executionRunId": _NEW_RUN_ID, "executionLockedAt": None},
        ]
    )

    with (
        patch("palace_mcp.ops.unstick.httpx.AsyncClient", mock_cls),
        patch(
            "asyncio.create_subprocess_exec",
            side_effect=fake_create_subprocess,
        ),
        patch(
            "palace_mcp.ops.unstick._poll_until_cleared",
            new_callable=AsyncMock,
        ) as mock_poll,
        patch("palace_mcp.ops.unstick.save_entity_node", new_callable=AsyncMock),
    ):
        mock_poll.return_value = False  # poll timeout → lock not cleared

        result = await unstick_issue("issue-abc", **_build_kwargs())

    assert result["ok"] is True
    assert result["action"] == "killed_then_respawned"
    assert result["new_run_id"] == _NEW_RUN_ID
    assert result["killed_pids"] == [42]
