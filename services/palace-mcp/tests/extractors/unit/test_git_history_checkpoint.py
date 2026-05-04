from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
import pytest

from palace_mcp.extractors.git_history.checkpoint import (
    write_git_history_checkpoint,
    load_git_history_checkpoint,
)

UTC_TS = datetime(2026, 5, 3, 12, 0, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_write_checkpoint_phase1_only():
    driver = MagicMock()
    driver.execute_query = AsyncMock(return_value=MagicMock(records=[]))
    await write_git_history_checkpoint(
        driver,
        "project/gimle",
        last_commit_sha="0" * 40,
        last_pr_updated_at=None,
        last_phase_completed="phase1",
    )
    assert driver.execute_query.await_count == 1
    args = driver.execute_query.await_args
    assert args.kwargs["last_phase_completed"] == "phase1"


@pytest.mark.asyncio
async def test_write_checkpoint_phase2_advances_pr_timestamp():
    driver = MagicMock()
    driver.execute_query = AsyncMock(return_value=MagicMock(records=[]))
    await write_git_history_checkpoint(
        driver,
        "project/gimle",
        last_commit_sha="0" * 40,
        last_pr_updated_at=UTC_TS,
        last_phase_completed="phase2",
    )
    args = driver.execute_query.await_args
    assert args.kwargs["last_pr_updated_at"] == UTC_TS


@pytest.mark.asyncio
async def test_load_checkpoint_returns_default_when_absent():
    driver = MagicMock()
    driver.execute_query = AsyncMock(return_value=MagicMock(records=[]))
    ckpt = await load_git_history_checkpoint(driver, "project/gimle")
    assert ckpt.last_commit_sha is None
    assert ckpt.last_phase_completed == "none"


@pytest.mark.asyncio
async def test_load_checkpoint_returns_persisted_state():
    record = MagicMock()
    record.__getitem__ = lambda _self, key: {
        "project_id": "project/gimle",
        "last_commit_sha": "0" * 40,
        "last_pr_updated_at": UTC_TS,
        "last_phase_completed": "phase2",
        "updated_at": UTC_TS,
    }[key]
    driver = MagicMock()
    driver.execute_query = AsyncMock(return_value=MagicMock(records=[record]))
    ckpt = await load_git_history_checkpoint(driver, "project/gimle")
    assert ckpt.last_commit_sha == "0" * 40
    assert ckpt.last_phase_completed == "phase2"
