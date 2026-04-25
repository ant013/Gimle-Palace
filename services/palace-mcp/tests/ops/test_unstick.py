"""Unit tests for palace_mcp.ops.unstick.

Tests cover all response shapes per spec §5.1:
1. noop when no lock
2. dry_run returns candidates without kill
3. strict heuristic matches via timing (executionLockedAt)
4. permissive fallback when strict empty
5. 5-PID cap without force
6. local mode (no SSH)
7. audit episode write
8. lock_not_released on timeout
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
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

# ps output: PID 42 has been running ~90 minutes
_PS_IDLE_CLAUDE = """\
PID ELAPSED %CPU COMMAND
  42 01:30:00  0.0 claude --print --add-dir /tmp/paperclip-skills-XYZ/
 100  00:02:00  1.2 python3 server.py
"""

_PS_NO_CLAUDE = """\
PID ELAPSED %CPU COMMAND
 100  00:02:00  1.2 python3 server.py
"""

# executionLockedAt ~90 minutes ago → PID 42 should match strict heuristic
_LOCKED_AT_90MIN = (datetime.now(timezone.utc) - timedelta(minutes=90)).isoformat()


def _make_kwargs(
    *,
    api_url: str = "http://localhost:3100",
    api_key: str = "test-api-key",
    ops_host: str = "local",
    ssh_key: str = "/home/appuser/.ssh/palace_ops_id_ed25519",
    ssh_user: str = "anton",
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
        ssh_user=ssh_user,
        api_url=api_url,
        api_key=api_key,
        graphiti=graphiti,
        group_id=group_id,
    )


_FAKE_ISSUE_LOCKED = {
    "executionRunId": _FAKE_RUN_ID,
    "executionLockedAt": _LOCKED_AT_90MIN,
}
_FAKE_ISSUE_CLEAR = {"executionRunId": None, "executionLockedAt": None}


# ---------------------------------------------------------------------------
# Pure-function unit tests
# ---------------------------------------------------------------------------


def test_parse_etime_to_minutes_hms() -> None:
    assert _parse_etime_to_minutes("01:30:00") == pytest.approx(90.0)


def test_parse_etime_to_minutes_days() -> None:
    assert _parse_etime_to_minutes("1-02:00:00") == pytest.approx(1560.0)


def test_parse_ps_output_skips_header() -> None:
    rows = _parse_ps_output(_PS_IDLE_CLAUDE)
    assert len(rows) == 2
    assert rows[0]["pid"] == 42


def test_find_strict_candidates_matches_timing() -> None:
    """PID 42 with etime=01:30:00 matches executionLockedAt ~90min ago."""
    rows = _parse_ps_output(_PS_IDLE_CLAUDE)
    result = _find_strict_candidates(rows, _LOCKED_AT_90MIN)
    assert len(result) == 1
    assert result[0]["pid"] == 42


def test_find_strict_candidates_empty_when_timing_mismatch() -> None:
    """executionLockedAt very recent → etime=01:30:00 won't match."""
    locked_at_now = datetime.now(timezone.utc).isoformat()
    rows = _parse_ps_output(_PS_IDLE_CLAUDE)
    result = _find_strict_candidates(rows, locked_at_now)
    assert result == []


def test_find_strict_candidates_empty_on_invalid_locked_at() -> None:
    rows = _parse_ps_output(_PS_IDLE_CLAUDE)
    result = _find_strict_candidates(rows, "not-a-date")
    assert result == []


def test_find_permissive_candidates_returns_idle_claude() -> None:
    rows = _parse_ps_output(_PS_IDLE_CLAUDE)
    result = _find_permissive_candidates(rows)
    assert len(result) == 1
    assert result[0]["pid"] == 42


def test_find_permissive_candidates_excludes_active() -> None:
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
    with patch("palace_mcp.ops.unstick.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_resp = MagicMock()
        mock_resp.json.return_value = _FAKE_ISSUE_CLEAR
        mock_client.get = AsyncMock(return_value=mock_resp)

        result = await unstick_issue("issue-1", **_make_kwargs())

    assert result == {"ok": True, "action": "noop", "issue_id": "issue-1"}


@pytest.mark.asyncio
async def test_unstick_dry_run_returns_candidates_no_kill() -> None:
    """dry_run=True returns candidate PIDs without invoking kill."""
    with (
        patch("palace_mcp.ops.unstick.httpx.AsyncClient") as mock_cls,
        patch(
            "palace_mcp.ops.unstick._get_ps_output", new_callable=AsyncMock
        ) as mock_ps,
        patch(
            "palace_mcp.ops.unstick._send_sigterm", new_callable=AsyncMock
        ) as mock_kill,
    ):
        mock_client = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_resp = MagicMock()
        mock_resp.json.return_value = _FAKE_ISSUE_LOCKED
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_ps.return_value = _PS_IDLE_CLAUDE

        result = await unstick_issue("issue-1", **_make_kwargs(dry_run=True))

    assert result["ok"] is True
    assert result["action"] == "dry_run"
    assert 42 in result["candidates"]
    mock_kill.assert_not_called()


@pytest.mark.asyncio
async def test_unstick_strict_heuristic_matches_timing() -> None:
    """Strict heuristic finds PID whose etime matches executionLockedAt ±60s."""
    with (
        patch("palace_mcp.ops.unstick.httpx.AsyncClient") as mock_cls,
        patch(
            "palace_mcp.ops.unstick._get_ps_output", new_callable=AsyncMock
        ) as mock_ps,
        patch("palace_mcp.ops.unstick._send_sigterm", new_callable=AsyncMock),
        patch(
            "palace_mcp.ops.unstick._poll_until_cleared", new_callable=AsyncMock
        ) as mock_poll,
    ):
        mock_client = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_resp = MagicMock()
        mock_resp.json.return_value = _FAKE_ISSUE_LOCKED
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_ps.return_value = _PS_IDLE_CLAUDE
        mock_poll.return_value = True

        result = await unstick_issue("issue-1", **_make_kwargs())

    assert result["ok"] is True
    assert result["heuristic"] == "strict"
    assert result["killed_pids"] == [42]


@pytest.mark.asyncio
async def test_unstick_permissive_fallback_when_strict_empty() -> None:
    """When strict yields no candidates (timing mismatch), permissive fallback."""
    # executionLockedAt just now → strict won't match the 90-min etime proc
    issue_locked_just_now = {
        "executionRunId": _FAKE_RUN_ID,
        "executionLockedAt": datetime.now(timezone.utc).isoformat(),
    }
    with (
        patch("palace_mcp.ops.unstick.httpx.AsyncClient") as mock_cls,
        patch(
            "palace_mcp.ops.unstick._get_ps_output", new_callable=AsyncMock
        ) as mock_ps,
        patch("palace_mcp.ops.unstick._send_sigterm", new_callable=AsyncMock),
        patch(
            "palace_mcp.ops.unstick._poll_until_cleared", new_callable=AsyncMock
        ) as mock_poll,
    ):
        mock_client = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_resp = MagicMock()
        mock_resp.json.return_value = issue_locked_just_now
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_ps.return_value = _PS_IDLE_CLAUDE
        mock_poll.return_value = True

        result = await unstick_issue("issue-1", **_make_kwargs())

    assert result["ok"] is True
    assert result["heuristic"] == "permissive"
    assert result["killed_pids"] == [42]


@pytest.mark.asyncio
async def test_unstick_refuses_more_than_five_candidates_without_force() -> None:
    """6 candidates → returns error unless force=True."""
    lines = ["PID ELAPSED %CPU COMMAND"]
    for pid in range(10, 16):
        lines.append(f"  {pid} 01:30:00  0.0 claude --print --add-dir /tmp/foo/")
    ps_output = "\n".join(lines) + "\n"

    with (
        patch("palace_mcp.ops.unstick.httpx.AsyncClient") as mock_cls,
        patch(
            "palace_mcp.ops.unstick._get_ps_output", new_callable=AsyncMock
        ) as mock_ps,
    ):
        mock_client = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_resp = MagicMock()
        mock_resp.json.return_value = _FAKE_ISSUE_LOCKED
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_ps.return_value = ps_output

        result = await unstick_issue("issue-1", **_make_kwargs(force=False))

    assert result["ok"] is False
    assert result["error"] == "too_many_candidates"


@pytest.mark.asyncio
async def test_unstick_local_mode_no_ssh() -> None:
    """PALACE_OPS_HOST=local uses direct subprocess (no SSH wrapper)."""
    with (
        patch("palace_mcp.ops.unstick.httpx.AsyncClient") as mock_cls,
        patch(
            "palace_mcp.ops.unstick._run_subprocess", new_callable=AsyncMock
        ) as mock_sub,
        patch(
            "palace_mcp.ops.unstick._poll_until_cleared", new_callable=AsyncMock
        ) as mock_poll,
    ):
        mock_client = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_resp = MagicMock()
        mock_resp.json.return_value = _FAKE_ISSUE_LOCKED
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_sub.return_value = (_PS_IDLE_CLAUDE, "", 0)
        mock_poll.return_value = True

        result = await unstick_issue(
            "issue-1", **_make_kwargs(ops_host="local", dry_run=True)
        )

    assert result["ok"] is True
    for call in mock_sub.call_args_list:
        assert call.args[0] != "ssh", "Expected no SSH call in local mode"


@pytest.mark.asyncio
async def test_unstick_writes_audit_episode() -> None:
    """After kill+clear, an Episode node is saved to Graphiti."""
    mock_graphiti = MagicMock()

    with (
        patch("palace_mcp.ops.unstick.httpx.AsyncClient") as mock_cls,
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
        mock_client = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_resp = MagicMock()
        mock_resp.json.return_value = _FAKE_ISSUE_LOCKED
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_ps.return_value = _PS_IDLE_CLAUDE
        mock_poll.return_value = True

        result = await unstick_issue("issue-1", **_make_kwargs(graphiti=mock_graphiti))

    assert result["ok"] is True
    mock_save.assert_awaited_once()
    node = mock_save.call_args.args[1]
    assert node.attributes["kind"] == "ops.unstick_issue"
    assert node.attributes["target_issue"] == "issue-1"
    assert 42 in node.attributes["killed_pids"]


@pytest.mark.asyncio
async def test_unstick_returns_lock_not_released_when_timeout() -> None:
    """Paperclip never clears lock → {ok: False, error: lock_not_released}."""
    with (
        patch("palace_mcp.ops.unstick.httpx.AsyncClient") as mock_cls,
        patch(
            "palace_mcp.ops.unstick._get_ps_output", new_callable=AsyncMock
        ) as mock_ps,
        patch("palace_mcp.ops.unstick._send_sigterm", new_callable=AsyncMock),
        patch(
            "palace_mcp.ops.unstick._poll_until_cleared", new_callable=AsyncMock
        ) as mock_poll,
    ):
        mock_client = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_resp = MagicMock()
        mock_resp.json.return_value = _FAKE_ISSUE_LOCKED
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_ps.return_value = _PS_IDLE_CLAUDE
        mock_poll.return_value = False

        result = await unstick_issue("issue-1", **_make_kwargs())

    assert result["ok"] is False
    assert result["error"] == "lock_not_released"
    assert result["stale_run_id"] == _FAKE_RUN_ID
