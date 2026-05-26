"""Unit tests for extractor runner (spec §3.4)."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Generator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from graphiti_core import Graphiti

from palace_mcp.extractors import registry
from palace_mcp.extractors.base import (
    BaseExtractor,
    ExtractorConfigError,
    ExtractorOutcome,
    ExtractorRunContext,
    ExtractorStats,
)
from palace_mcp.extractors.foundation.errors import (
    ExtractorError as FoundationExtractorError,
    ExtractorErrorCode,
)
from palace_mcp.extractors.embedding_symbol import (
    EmbeddingSymbolExtractor,
    _embedding_text,
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


class _LongTimeout(BaseExtractor):
    name = "__test_long_timeout"
    description = "uses extractor-specific timeout"
    timeout_s = 12.5

    async def run(
        self, *, graphiti: Graphiti, ctx: ExtractorRunContext
    ) -> ExtractorStats:
        return ExtractorStats(nodes_written=1)


class _ScipPathEcho(BaseExtractor):
    name = "__test_scip_path_echo"
    description = "captures scip path override"

    def __init__(self) -> None:
        self.seen_scip_path: Path | None = None

    async def run(
        self, *, graphiti: Graphiti, ctx: ExtractorRunContext
    ) -> ExtractorStats:
        self.seen_scip_path = ctx.scip_path
        return ExtractorStats(nodes_written=1)


class _Skipped(BaseExtractor):
    name = "__test_skipped"
    description = "returns a successful skipped outcome"

    async def run(
        self, *, graphiti: Graphiti, ctx: ExtractorRunContext
    ) -> ExtractorStats:
        return ExtractorStats(
            outcome=ExtractorOutcome.SKIPPED,
            message="missing prerequisite fixture",
            next_action="Provide the fixture and rerun the extractor.",
        )


class _EmbeddingBackend:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def embed_text(self, text: str) -> list[float]:
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        return [[0.25] for _ in texts]


@pytest.fixture(autouse=True)
def _isolate_registry() -> Generator[None, None, None]:
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
async def test_parent_mount_project_path_resolves_without_git_in_subdir(
    tmp_path: Path, mock_graphiti: MagicMock
) -> None:
    registry.register(_Ok())
    mounted_repo = tmp_path / "repos-hs" / "TronKit.Swift"
    mounted_repo.mkdir(parents=True)
    driver, _ = _make_session_mock(
        {
            "p": {
                "name": "tronkit-swift",
                "parent_mount": "hs",
                "relative_path": "TronKit.Swift",
            }
        }
    )

    with patch("palace_mcp.extractors.runner.REPOS_ROOT", tmp_path / "repos"):
        res = await run_extractor(
            name="__test_ok",
            project="tronkit-swift",
            driver=driver,
            graphiti=mock_graphiti,
        )

    assert res["ok"] is True
    assert res["project"] == "tronkit-swift"


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
    assert res["outcome"] == "ok"


@pytest.mark.asyncio
async def test_success_response_preserves_skipped_outcome_metadata(
    mock_driver: MagicMock, tmp_path: Path, mock_graphiti: MagicMock
) -> None:
    registry.register(_Skipped())
    with patch("palace_mcp.extractors.runner.REPOS_ROOT", tmp_path / "repos"):
        res = await run_extractor(
            name="__test_skipped",
            project="testproj",
            driver=mock_driver,
            graphiti=mock_graphiti,
        )

    assert res["ok"] is True
    assert res["success"] is True
    assert res["outcome"] == "skipped"
    assert res["message"] == "missing prerequisite fixture"
    assert res["next_action"] == "Provide the fixture and rerun the extractor."


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


@pytest.mark.asyncio
async def test_extractor_timeout_overrides_runner_default(
    mock_driver: MagicMock, tmp_path: Path, mock_graphiti: MagicMock
) -> None:
    registry.register(_LongTimeout())
    seen_timeout: float | None = None

    async def fake_wait_for(coro: Awaitable[object], timeout: float) -> object:
        nonlocal seen_timeout
        seen_timeout = timeout
        return await coro

    with (
        patch("palace_mcp.extractors.runner.REPOS_ROOT", tmp_path / "repos"),
        patch("palace_mcp.extractors.runner.asyncio.wait_for", fake_wait_for),
    ):
        res = await run_extractor(
            name="__test_long_timeout",
            project="testproj",
            driver=mock_driver,
            graphiti=mock_graphiti,
            timeout_s=0.05,
        )

    assert res["ok"] is True
    assert seen_timeout == 12.5


@pytest.mark.asyncio
async def test_run_extractor_passes_scip_path_into_context(
    mock_driver: MagicMock, tmp_path: Path, mock_graphiti: MagicMock
) -> None:
    extractor = _ScipPathEcho()
    registry.register(extractor)
    scip_path = tmp_path / "scip" / "index.scip"

    with patch("palace_mcp.extractors.runner.REPOS_ROOT", tmp_path / "repos"):
        res = await run_extractor(
            name="__test_scip_path_echo",
            project="testproj",
            driver=mock_driver,
            graphiti=mock_graphiti,
            scip_path=str(scip_path),
        )

    assert res["ok"] is True
    assert extractor.seen_scip_path == scip_path


@pytest.mark.asyncio
async def test_run_extractor_resolves_relative_scip_path_inside_mounted_repo(
    tmp_path: Path, mock_graphiti: MagicMock
) -> None:
    extractor = _ScipPathEcho()
    registry.register(extractor)
    mounted_repo = tmp_path / "repos-macbook" / "repos" / "testproj"
    mounted_repo.mkdir(parents=True)
    driver, _ = _make_session_mock(
        {
            "p": {
                "name": "testproj",
                "parent_mount": "macbook",
                "relative_path": "repos/testproj",
            }
        }
    )

    with patch("palace_mcp.extractors.runner.REPOS_ROOT", tmp_path / "repos"):
        res = await run_extractor(
            name="__test_scip_path_echo",
            project="testproj",
            driver=driver,
            graphiti=mock_graphiti,
            scip_path="scip/index.scip",
        )

    assert res["ok"] is True
    assert extractor.seen_scip_path == mounted_repo / "scip" / "index.scip"


@pytest.mark.asyncio
async def test_embedding_symbol_run_extractor_wiring(
    mock_driver: MagicMock, tmp_path: Path, mock_graphiti: MagicMock
) -> None:
    backend = _EmbeddingBackend()
    registry.EXTRACTORS["embedding_symbol"] = EmbeddingSymbolExtractor(backend=backend)
    mock_graphiti.driver = mock_driver
    load_rows = [
        {
            "qualified_name": "demo.symbol",
            "kind": "function",
            "file_path": "src/demo.py",
            "module_name": "demo",
            "embedding_input_hash": None,
            "has_embedding": False,
        }
    ]

    with (
        patch("palace_mcp.extractors.runner.REPOS_ROOT", tmp_path / "repos"),
        patch(
            "palace_mcp.extractors.embedding_symbol._load_symbol_rows",
            new=AsyncMock(return_value=load_rows),
        ),
        patch(
            "palace_mcp.extractors.embedding_symbol._write_embeddings",
            new=AsyncMock(),
        ) as write_embeddings,
    ):
        res = await run_extractor(
            name="embedding_symbol",
            project="testproj",
            driver=mock_driver,
            graphiti=mock_graphiti,
        )

    assert res["ok"] is True
    assert res["success"] is True
    assert res["extractor"] == "embedding_symbol"
    assert res["nodes_written"] == 1
    assert backend.calls == [[_embedding_text(load_rows[0])]]
    write_embeddings.assert_awaited_once()
