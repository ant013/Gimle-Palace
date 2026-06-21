from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from palace_mcp.extractors.code_ownership.checkpoint import (
    delete_checkpoint,
    has_file_state_baseline,
)


def _mock_driver(single_value: object) -> MagicMock:
    result = AsyncMock()
    result.single = AsyncMock(return_value=single_value)
    session = AsyncMock()
    session.run = AsyncMock(return_value=result)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    driver = MagicMock()
    driver.session = MagicMock(return_value=session)
    return driver


@pytest.mark.asyncio
async def test_delete_checkpoint_executes_delete_query() -> None:
    driver = _mock_driver(None)

    await delete_checkpoint(driver, project_id="project/testproj")

    query = driver.session.return_value.run.call_args.args[0]
    assert "OwnershipCheckpoint" in query
    assert "DELETE c" in query


@pytest.mark.asyncio
async def test_has_file_state_baseline_returns_true_from_query_result() -> None:
    driver = _mock_driver({"has_baseline": True})

    result = await has_file_state_baseline(driver, project_id="project/testproj")

    assert result is True


@pytest.mark.asyncio
async def test_has_file_state_baseline_returns_false_without_rows() -> None:
    driver = _mock_driver(None)

    result = await has_file_state_baseline(driver, project_id="project/testproj")

    assert result is False
