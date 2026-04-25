"""Integration tests for palace_mcp.ops.unstick.

Mock-based: patches asyncio.create_subprocess_exec (SSH/ps/kill) and
httpx.AsyncClient (paperclip API). No real SSH or live paperclip needed.

Per spec §5.2 (CR NOTE: mock asyncio.create_subprocess_exec, not subprocess.run).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from palace_mcp.ops.unstick import unstick_issue

_FAKE_RUN_ID = "abc12345-dead-beef-cafe-111122223333"
_NEW_RUN_ID = "ffffffff-0000-1111-2222-333344445555"


def _ps_with_run_id() -> str:
    return (
        "PID ELAPSED %CPU COMMAND\n"
        f"  42 01:30:00  0.0 claude --print --run-id {_FAKE_RUN_ID}\n"
    )


def _build_kwargs(graphiti: object = None) -> dict:
    return dict(
        dry_run=False,
        force=False,
        timeout_sec=10,
        ops_host="local",
        ssh_key="/home/appuser/.ssh/id_ed25519",
        api_url="http://localhost:3100",
        graphiti=graphiti,
        group_id="project/test",
    )


# ---------------------------------------------------------------------------
# Helper: fake subprocess factory
# ---------------------------------------------------------------------------


def _make_fake_proc(stdout: str = "", rc: int = 0) -> MagicMock:
    proc = MagicMock()
    proc.returncode = rc
    proc.communicate = AsyncMock(return_value=(stdout.encode(), b""))
    return proc


# ---------------------------------------------------------------------------
# Test 1: full flow — kill then clear
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unstick_full_flow_kill_then_clear() -> None:
    """Paperclip first returns stale lock; after kill, lock clears on second poll."""

    # API call sequence: first returns stale run_id, then None (cleared)
    api_call_count = 0

    async def fake_get_run_id(api_url: str, issue_id: str) -> str | None:
        nonlocal api_call_count
        api_call_count += 1
        if api_call_count == 1:
            return _FAKE_RUN_ID
        # second call (first poll) → cleared
        return None

    subprocess_calls: list[tuple[str, ...]] = []

    async def fake_create_subprocess(*args: str, **kwargs: object) -> MagicMock:
        subprocess_calls.append(args)
        stdout = _ps_with_run_id() if "ps" in args else ""
        return _make_fake_proc(stdout=stdout)

    mock_graphiti = MagicMock()

    with (
        patch(
            "palace_mcp.ops.unstick._get_execution_run_id",
            side_effect=fake_get_run_id,
        ),
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

    # Verify subprocess sequence: ps + kill
    commands = [call[0] for call in subprocess_calls]
    assert "ps" in commands, "Expected ps command"
    assert "kill" in commands, "Expected kill command"

    # Verify audit episode saved
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

    async def fake_poll(api_url: str, issue_id: str, timeout_sec: int) -> bool:
        # Simulate timeout — lock never cleared (respawn will be detected after)
        return False

    # After poll timeout, check for respawn: returns new run_id
    get_run_id_calls = 0

    async def fake_get_run_id(api_url: str, issue_id: str) -> str | None:
        nonlocal get_run_id_calls
        get_run_id_calls += 1
        if get_run_id_calls == 1:
            return _FAKE_RUN_ID  # initial call
        # called after poll timeout to check for respawn
        return _NEW_RUN_ID

    async def fake_create_subprocess(*args: str, **kwargs: object) -> MagicMock:
        stdout = _ps_with_run_id() if "ps" in args else ""
        return _make_fake_proc(stdout=stdout)

    with (
        patch(
            "palace_mcp.ops.unstick._get_execution_run_id",
            side_effect=fake_get_run_id,
        ),
        patch(
            "asyncio.create_subprocess_exec",
            side_effect=fake_create_subprocess,
        ),
        patch(
            "palace_mcp.ops.unstick._poll_until_cleared",
            side_effect=fake_poll,
        ),
        patch("palace_mcp.ops.unstick.save_entity_node", new_callable=AsyncMock),
    ):
        result = await unstick_issue("issue-abc", **_build_kwargs())

    assert result["ok"] is True
    assert result["action"] == "killed_then_respawned"
    assert result["new_run_id"] == _NEW_RUN_ID
    assert result["killed_pids"] == [42]
