"""Unit tests for extractor runner (spec §3.4)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from graphiti_core import Graphiti

from palace_mcp.extractors import registry
from palace_mcp.extractors.base import (
    BaseExtractor,
    ExtractorConfigError,
    ExtractorRunContext,
    ExtractorStats,
)
from palace_mcp.extractors.foundation.errors import (
    ExtractorError as FoundationExtractorError,
    ExtractorErrorCode,
)
from palace_mcp.extractors.runner import run_extractor


class _Ok(BaseExtractor):
    name = "__test_ok"
    description = "returns stats"

    async def run(
        self, *, graphiti: Graphiti, ctx: ExtractorRunContext
    ) -> ExtractorStats:
        return ExtractorStats(nodes_written=5, edges_written=2)


class _ConfigFail(BaseExtractor):
    name = "__test_config_fail"
    description = "raises ExtractorConfigError"

    async def run(
        self, *, graphiti: Graphiti, ctx: ExtractorRunContext
    ) -> ExtractorStats:
        raise ExtractorConfigError("missing tool X")


class _Unhandled(BaseExtractor):
    name = "__test_unhandled"
    description = "raises generic Exception"

    async def run(
        self, *, graphiti: Graphiti, ctx: ExtractorRunContext
    ) -> ExtractorStats:
        raise RuntimeError("boom")


class _FoundationFail(BaseExtractor):
    name = "__test_foundation_fail"
    description = "raises foundation ExtractorError"

    async def run(
        self, *, graphiti: Graphiti, ctx: ExtractorRunContext
    ) -> ExtractorStats:
        raise FoundationExtractorError(
            error_code=ExtractorErrorCode.PUBLIC_API_ARTIFACTS_REQUIRED,
            message="artifacts missing",
            recoverable=False,
            action="manual_cleanup",
        )


class _Slow(BaseExtractor):
    name = "__test_slow"
    description = "takes too long"

    async def run(
        self, *, graphiti: Graphiti, ctx: ExtractorRunContext
    ) -> ExtractorStats:
        await asyncio.sleep(10.0)
        return ExtractorStats()


@pytest.fixture(autouse=True)
def _isolate_registry() -> None:
    snap = dict(registry.EXTRACTORS)
    yield
    registry.EXTRACTORS.clear()
    registry.EXTRACTORS.update(snap)


def _make_session_mock(single_value: object) -> tuple[MagicMock, AsyncMock]:
    """Return (driver_mock, session_mock). neo4j driver.session() is sync."""
    result = AsyncMock()
    result.single = AsyncMock(return_value=single_value)

    session = AsyncMock()
    session.run = AsyncMock(return_value=result)

    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=session)
    cm.__aexit__ = AsyncMock(return_value=None)

    driver = MagicMock()
    driver.session = MagicMock(return_value=cm)
    return driver, session


@pytest.fixture
def mock_driver(tmp_path: Path) -> MagicMock:
    """Driver that returns :Project row when queried."""
    repo = tmp_path / "repos" / "testproj"
    repo.mkdir(parents=True)
    (repo / ".git").mkdir()

    driver, _ = _make_session_mock({"p": {"name": "testproj"}})
    return driver


@pytest.fixture
def mock_graphiti() -> MagicMock:
    return MagicMock(spec=Graphiti)


@pytest.mark.asyncio
async def test_invalid_slug_returns_error(
    mock_driver: MagicMock, mock_graphiti: MagicMock
) -> None:
    res = await run_extractor(
        name="__test_ok", project="../etc", driver=mock_driver, graphiti=mock_graphiti
    )
    assert res["ok"] is False
    assert res["error_code"] == "invalid_slug"
    mock_driver.session.assert_not_called()


@pytest.mark.asyncio
async def test_unknown_extractor_returns_error(
    mock_driver: MagicMock, mock_graphiti: MagicMock
) -> None:
    res = await run_extractor(
        name="does_not_exist",
        project="testproj",
        driver=mock_driver,
        graphiti=mock_graphiti,
    )
    assert res["ok"] is False
    assert res["error_code"] == "unknown_extractor"


@pytest.mark.asyncio
async def test_project_not_registered_returns_error(
    tmp_path: Path, mock_graphiti: MagicMock
) -> None:
    registry.register(_Ok())
    driver, _ = _make_session_mock(None)

    with patch("palace_mcp.extractors.runner.REPOS_ROOT", tmp_path / "repos"):
        res = await run_extractor(
            name="__test_ok", project="testproj", driver=driver, graphiti=mock_graphiti
        )

    assert res["ok"] is False
    assert res["error_code"] == "project_not_registered"


@pytest.mark.asyncio
async def test_repo_not_mounted_returns_error(
    tmp_path: Path, mock_graphiti: MagicMock
) -> None:
    registry.register(_Ok())
    driver, _ = _make_session_mock({"p": {"name": "testproj"}})

    with patch("palace_mcp.extractors.runner.REPOS_ROOT", tmp_path / "no_such"):
        res = await run_extractor(
            name="__test_ok", project="testproj", driver=driver, graphiti=mock_graphiti
        )

    assert res["ok"] is False
    assert res["error_code"] == "repo_not_mounted"


@pytest.mark.asyncio
async def test_happy_path_success(
    mock_driver: MagicMock, tmp_path: Path, mock_graphiti: MagicMock
) -> None:
    registry.register(_Ok())
    with patch("palace_mcp.extractors.runner.REPOS_ROOT", tmp_path / "repos"):
        res = await run_extractor(
            name="__test_ok",
            project="testproj",
            driver=mock_driver,
            graphiti=mock_graphiti,
        )

    assert res["ok"] is True
    assert res["success"] is True
    assert res["nodes_written"] == 5
    assert res["edges_written"] == 2
    assert res["extractor"] == "__test_ok"
    assert res["project"] == "testproj"
    assert "run_id" in res
    assert res["duration_ms"] >= 0


@pytest.mark.asyncio
async def test_extractor_config_error_returns_mapped_code(
    mock_driver: MagicMock, tmp_path: Path, mock_graphiti: MagicMock
) -> None:
    registry.register(_ConfigFail())
    with patch("palace_mcp.extractors.runner.REPOS_ROOT", tmp_path / "repos"):
        res = await run_extractor(
            name="__test_config_fail",
            project="testproj",
            driver=mock_driver,
            graphiti=mock_graphiti,
        )
    assert res["ok"] is False
    assert res["error_code"] == "extractor_config_error"


@pytest.mark.asyncio
async def test_unhandled_exception_returns_unknown(
    mock_driver: MagicMock, tmp_path: Path, mock_graphiti: MagicMock
) -> None:
    registry.register(_Unhandled())
    with patch("palace_mcp.extractors.runner.REPOS_ROOT", tmp_path / "repos"):
        res = await run_extractor(
            name="__test_unhandled",
            project="testproj",
            driver=mock_driver,
            graphiti=mock_graphiti,
        )
    assert res["ok"] is False
    assert res["error_code"] == "unknown"
    assert "RuntimeError" in res.get("message", "")


@pytest.mark.asyncio
async def test_foundation_extractor_error_preserves_exact_code(
    mock_driver: MagicMock, tmp_path: Path, mock_graphiti: MagicMock
) -> None:
    registry.register(_FoundationFail())
    with patch("palace_mcp.extractors.runner.REPOS_ROOT", tmp_path / "repos"):
        res = await run_extractor(
            name="__test_foundation_fail",
            project="testproj",
            driver=mock_driver,
            graphiti=mock_graphiti,
        )
    assert res["ok"] is False
    assert res["error_code"] == "public_api_artifacts_required"
    assert res["message"] == "artifacts missing"


@pytest.mark.asyncio
async def test_timeout_returns_runtime_error(
    mock_driver: MagicMock, tmp_path: Path, mock_graphiti: MagicMock
) -> None:
    registry.register(_Slow())
    with patch("palace_mcp.extractors.runner.REPOS_ROOT", tmp_path / "repos"):
        res = await run_extractor(
            name="__test_slow",
            project="testproj",
            driver=mock_driver,
            graphiti=mock_graphiti,
            timeout_s=0.05,
        )
    assert res["ok"] is False
    assert res["error_code"] == "extractor_runtime_error"
    assert "timeout" in res["message"].lower()
