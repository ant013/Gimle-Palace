"""Unit tests for palace_mcp.ops.unstick.

Tests cover all response shapes per spec §5.1:
1. noop when no lock
2. dry_run returns candidates without kill
3. strict heuristic matches run_id
4. permissive fallback when strict empty
5. 5-PID cap without force
6. local mode (no SSH)
7. audit episode write
8. lock_not_released on timeout
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from palace_mcp.ops.unstick import (
    _find_permissive_candidates,
    _find_strict_candidates,
    _parse_etime_to_minutes,
    _parse_ps_output,
    unstick_issue,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FAKE_RUN_ID = "abc12345-dead-beef-cafe-111122223333"

_PS_WITH_RUN_ID = f"""\
PID ELAPSED %CPU COMMAND
  42 01:30:00  0.0 claude --print --add-dir /tmp/paperclip-skills-XYZ/ --run-id {_FAKE_RUN_ID}
 100  00:02:00  1.2 python3 server.py
"""

_PS_IDLE_CLAUDE = """\
PID ELAPSED %CPU COMMAND
  42 01:30:00  0.0 claude --print --add-dir /tmp/paperclip-skills-XYZ/
 100  00:02:00  1.2 python3 server.py
"""

_PS_NO_CLAUDE = """\
PID ELAPSED %CPU COMMAND
 100  00:02:00  1.2 python3 server.py
"""


def _make_kwargs(
    *,
    api_url: str = "http://localhost:3100",
    ops_host: str = "local",
    ssh_key: str = "/home/appuser/.ssh/id_ed25519",
    graphiti: Any = None,
    group_id: str = "project/test",
    dry_run: bool = False,
    force: bool = False,
    timeout_sec: int = 10,
) -> dict[str, Any]:
    return dict(
        dry_run=dry_run,
        force=force,
        timeout_sec=timeout_sec,
        ops_host=ops_host,
        ssh_key=ssh_key,
        api_url=api_url,
        graphiti=graphiti,
        group_id=group_id,
    )


# ---------------------------------------------------------------------------
# Pure-function unit tests
# ---------------------------------------------------------------------------


def test_parse_etime_to_minutes_hms() -> None:
    assert _parse_etime_to_minutes("01:30:00") == pytest.approx(90.0)


def test_parse_etime_to_minutes_days() -> None:
    assert _parse_etime_to_minutes("1-02:00:00") == pytest.approx(1560.0)


def test_parse_ps_output_skips_header() -> None:
    rows = _parse_ps_output(_PS_WITH_RUN_ID)
    assert len(rows) == 2
    assert rows[0]["pid"] == 42


def test_find_strict_candidates_matches_run_id() -> None:
    rows = _parse_ps_output(_PS_WITH_RUN_ID)
    result = _find_strict_candidates(rows, _FAKE_RUN_ID)
    assert len(result) == 1
    assert result[0]["pid"] == 42


def test_find_strict_candidates_empty_when_no_match() -> None:
    rows = _parse_ps_output(_PS_IDLE_CLAUDE)
    result = _find_strict_candidates(rows, _FAKE_RUN_ID)
    assert result == []


def test_find_permissive_candidates_returns_idle_claude() -> None:
    rows = _parse_ps_output(_PS_IDLE_CLAUDE)
    result = _find_permissive_candidates(rows)
    assert len(result) == 1
    assert result[0]["pid"] == 42


def test_find_permissive_candidates_excludes_active() -> None:
    # Active = low etime (2 min) but has claude --print
    ps_active = "PID ELAPSED %CPU COMMAND\n  42 00:02:00  0.0 claude --print foo\n"
    rows = _parse_ps_output(ps_active)
    result = _find_permissive_candidates(rows)
    assert result == []


# ---------------------------------------------------------------------------
# unstick_issue async tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unstick_noop_when_no_lock() -> None:
    """Issue with executionRunId=None returns noop immediately."""
    with patch(
        "palace_mcp.ops.unstick._get_execution_run_id", new_callable=AsyncMock
    ) as mock_get:
        mock_get.return_value = None
        result = await unstick_issue("issue-1", **_make_kwargs())

    assert result == {"ok": True, "action": "noop", "issue_id": "issue-1"}
    mock_get.assert_awaited_once()


@pytest.mark.asyncio
async def test_unstick_dry_run_returns_candidates_no_kill() -> None:
    """dry_run=True returns candidate PIDs without invoking kill."""
    with (
        patch(
            "palace_mcp.ops.unstick._get_execution_run_id", new_callable=AsyncMock
        ) as mock_get,
        patch(
            "palace_mcp.ops.unstick._get_ps_output", new_callable=AsyncMock
        ) as mock_ps,
        patch(
            "palace_mcp.ops.unstick._send_sigterm", new_callable=AsyncMock
        ) as mock_kill,
    ):
        mock_get.return_value = _FAKE_RUN_ID
        mock_ps.return_value = _PS_WITH_RUN_ID

        result = await unstick_issue("issue-1", **_make_kwargs(dry_run=True))

    assert result["ok"] is True
    assert result["action"] == "dry_run"
    assert 42 in result["candidates"]
    mock_kill.assert_not_called()


@pytest.mark.asyncio
async def test_unstick_strict_heuristic_matches_run_id() -> None:
    """Strict heuristic finds the PID containing run_id in command."""
    with (
        patch(
            "palace_mcp.ops.unstick._get_execution_run_id", new_callable=AsyncMock
        ) as mock_get,
        patch(
            "palace_mcp.ops.unstick._get_ps_output", new_callable=AsyncMock
        ) as mock_ps,
        patch("palace_mcp.ops.unstick._send_sigterm", new_callable=AsyncMock),
        patch(
            "palace_mcp.ops.unstick._poll_until_cleared", new_callable=AsyncMock
        ) as mock_poll,
    ):
        mock_get.return_value = _FAKE_RUN_ID
        mock_ps.return_value = _PS_WITH_RUN_ID
        mock_poll.return_value = True

        result = await unstick_issue("issue-1", **_make_kwargs())

    assert result["ok"] is True
    assert result["heuristic"] == "strict"
    assert result["killed_pids"] == [42]


@pytest.mark.asyncio
async def test_unstick_permissive_fallback_when_strict_empty() -> None:
    """When strict yields no candidates, permissive returns idle candidates."""
    with (
        patch(
            "palace_mcp.ops.unstick._get_execution_run_id", new_callable=AsyncMock
        ) as mock_get,
        patch(
            "palace_mcp.ops.unstick._get_ps_output", new_callable=AsyncMock
        ) as mock_ps,
        patch("palace_mcp.ops.unstick._send_sigterm", new_callable=AsyncMock),
        patch(
            "palace_mcp.ops.unstick._poll_until_cleared", new_callable=AsyncMock
        ) as mock_poll,
    ):
        mock_get.return_value = _FAKE_RUN_ID
        # ps output has idle claude --print but no run_id match
        mock_ps.return_value = _PS_IDLE_CLAUDE
        mock_poll.return_value = True

        result = await unstick_issue("issue-1", **_make_kwargs())

    assert result["ok"] is True
    assert result["heuristic"] == "permissive"
    assert result["killed_pids"] == [42]


@pytest.mark.asyncio
async def test_unstick_refuses_more_than_five_candidates_without_force() -> None:
    """6 candidates → returns error unless force=True."""
    # Build ps output with 6 idle claude processes
    lines = ["PID ELAPSED %CPU COMMAND"]
    for pid in range(10, 16):
        lines.append(f"  {pid} 01:30:00  0.0 claude --print --add-dir /tmp/foo/")
    ps_output = "\n".join(lines) + "\n"

    with (
        patch(
            "palace_mcp.ops.unstick._get_execution_run_id", new_callable=AsyncMock
        ) as mock_get,
        patch(
            "palace_mcp.ops.unstick._get_ps_output", new_callable=AsyncMock
        ) as mock_ps,
    ):
        mock_get.return_value = _FAKE_RUN_ID
        mock_ps.return_value = ps_output

        result = await unstick_issue("issue-1", **_make_kwargs(force=False))

    assert result["ok"] is False
    assert result["error"] == "too_many_candidates"


@pytest.mark.asyncio
async def test_unstick_local_mode_no_ssh() -> None:
    """PALACE_OPS_HOST=local uses direct subprocess (no SSH wrapper)."""
    with (
        patch(
            "palace_mcp.ops.unstick._get_execution_run_id", new_callable=AsyncMock
        ) as mock_get,
        patch(
            "palace_mcp.ops.unstick._run_subprocess", new_callable=AsyncMock
        ) as mock_sub,
        patch(
            "palace_mcp.ops.unstick._poll_until_cleared", new_callable=AsyncMock
        ) as mock_poll,
    ):
        mock_get.return_value = _FAKE_RUN_ID
        mock_sub.return_value = (_PS_WITH_RUN_ID, "", 0)
        mock_poll.return_value = True

        result = await unstick_issue(
            "issue-1", **_make_kwargs(ops_host="local", dry_run=True)
        )

    assert result["ok"] is True
    # Verify no "ssh" arg was used
    for call in mock_sub.call_args_list:
        assert call.args[0] != "ssh", "Expected no SSH call in local mode"


@pytest.mark.asyncio
async def test_unstick_writes_audit_episode() -> None:
    """After kill+clear, an Episode node is saved to Graphiti."""
    mock_graphiti = MagicMock()

    with (
        patch(
            "palace_mcp.ops.unstick._get_execution_run_id", new_callable=AsyncMock
        ) as mock_get,
        patch(
            "palace_mcp.ops.unstick._get_ps_output", new_callable=AsyncMock
        ) as mock_ps,
        patch("palace_mcp.ops.unstick._send_sigterm", new_callable=AsyncMock),
        patch(
            "palace_mcp.ops.unstick._poll_until_cleared", new_callable=AsyncMock
        ) as mock_poll,
        patch(
            "palace_mcp.ops.unstick.save_entity_node", new_callable=AsyncMock
        ) as mock_save,
    ):
        mock_get.return_value = _FAKE_RUN_ID
        mock_ps.return_value = _PS_WITH_RUN_ID
        mock_poll.return_value = True

        result = await unstick_issue("issue-1", **_make_kwargs(graphiti=mock_graphiti))

    assert result["ok"] is True
    mock_save.assert_awaited_once()
    # Verify the Episode node carries the right metadata
    node = mock_save.call_args.args[1]
    assert node.attributes["kind"] == "ops.unstick_issue"
    assert node.attributes["target_issue"] == "issue-1"
    assert 42 in node.attributes["killed_pids"]


@pytest.mark.asyncio
async def test_unstick_returns_lock_not_released_when_timeout() -> None:
    """Paperclip never clears lock → {ok: False, error: lock_not_released}."""
    with (
        patch(
            "palace_mcp.ops.unstick._get_execution_run_id", new_callable=AsyncMock
        ) as mock_get,
        patch(
            "palace_mcp.ops.unstick._get_ps_output", new_callable=AsyncMock
        ) as mock_ps,
        patch("palace_mcp.ops.unstick._send_sigterm", new_callable=AsyncMock),
        patch(
            "palace_mcp.ops.unstick._poll_until_cleared", new_callable=AsyncMock
        ) as mock_poll,
    ):
        mock_get.return_value = _FAKE_RUN_ID
        mock_ps.return_value = _PS_WITH_RUN_ID
        mock_poll.return_value = False

        result = await unstick_issue("issue-1", **_make_kwargs())

    assert result["ok"] is False
    assert result["error"] == "lock_not_released"
    assert result["stale_run_id"] == _FAKE_RUN_ID
