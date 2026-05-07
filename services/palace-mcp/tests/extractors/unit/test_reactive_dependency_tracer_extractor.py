"""Unit tests for reactive_dependency_tracer extractor orchestrator."""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from palace_mcp.extractors.base import ExtractorRunContext
from palace_mcp.extractors.foundation.errors import ExtractorError, ExtractorErrorCode
from palace_mcp.extractors.reactive_dependency_tracer.extractor import (
    ReactiveDependencyTracerExtractor,
)
from palace_mcp.extractors.reactive_dependency_tracer.models import (
    ReactiveDiagnosticCode,
)
from palace_mcp.extractors.reactive_dependency_tracer.neo4j_writer import (
    ReactiveWriteSummary,
)


def _make_ctx(repo_path: Path) -> ExtractorRunContext:
    return ExtractorRunContext(
        project_slug="reactive-mini",
        group_id="project/reactive-mini",
        repo_path=repo_path,
        run_id="test-run",
        duration_ms=0,
        logger=logging.getLogger("test"),
    )


def _fixture_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    source = (
        Path(__file__).resolve().parents[1]
        / "fixtures"
        / "reactive-dependency-swift-mini"
    )
    repo.mkdir()
    for path in source.rglob("*"):
        target = repo / path.relative_to(source)
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    (repo / ".git").mkdir()
    (repo / ".git" / "HEAD").write_text(
        "0123456789abcdef0123456789abcdef01234567\n", encoding="utf-8"
    )
    return repo


@pytest.mark.asyncio
async def test_extractor_happy_path(tmp_path: Path) -> None:
    repo = _fixture_repo(tmp_path)
    extractor = ReactiveDependencyTracerExtractor()
    ctx = _make_ctx(repo)
    graphiti = MagicMock()

    mock_write = AsyncMock(
        return_value=ReactiveWriteSummary(nodes_created=5, relationships_created=3)
    )
    with (
        patch("palace_mcp.mcp_server.get_driver", return_value=MagicMock()),
        patch(
            "palace_mcp.extractors.reactive_dependency_tracer.extractor.ensure_custom_schema",
            new_callable=AsyncMock,
        ),
        patch(
            "palace_mcp.extractors.reactive_dependency_tracer.extractor.write_reactive_graph",
            mock_write,
        ),
    ):
        stats = await extractor.run(graphiti=graphiti, ctx=ctx)

    assert stats.nodes_written == 5
    assert stats.edges_written == 3
    batches = mock_write.await_args.kwargs["batches"]
    assert any(batch.components for batch in batches)


@pytest.mark.asyncio
async def test_extractor_missing_helper_json_writes_structured_skip(
    tmp_path: Path,
) -> None:
    repo = _fixture_repo(tmp_path)
    (repo / "reactive_facts.json").unlink()
    extractor = ReactiveDependencyTracerExtractor()
    ctx = _make_ctx(repo)

    async def _capture_write(*, driver, batches):  # type: ignore[no-untyped-def]
        assert any(
            any(
                diagnostic.diagnostic_code
                is ReactiveDiagnosticCode.SWIFT_HELPER_UNAVAILABLE
                for diagnostic in batch.diagnostics
            )
            for batch in batches
        )
        return ReactiveWriteSummary(nodes_created=1, relationships_created=0)

    with (
        patch("palace_mcp.mcp_server.get_driver", return_value=MagicMock()),
        patch(
            "palace_mcp.extractors.reactive_dependency_tracer.extractor.ensure_custom_schema",
            new_callable=AsyncMock,
        ),
        patch(
            "palace_mcp.extractors.reactive_dependency_tracer.extractor.write_reactive_graph",
            side_effect=_capture_write,
        ),
    ):
        stats = await extractor.run(graphiti=MagicMock(), ctx=ctx)

    assert stats.nodes_written == 1
    assert stats.edges_written == 0


@pytest.mark.asyncio
async def test_extractor_parse_failure_writes_structured_skip(tmp_path: Path) -> None:
    repo = _fixture_repo(tmp_path)
    (repo / "reactive_facts.json").write_text("{not-json", encoding="utf-8")
    extractor = ReactiveDependencyTracerExtractor()
    ctx = _make_ctx(repo)

    async def _capture_write(*, driver, batches):  # type: ignore[no-untyped-def]
        assert any(
            any(
                diagnostic.diagnostic_code is ReactiveDiagnosticCode.SWIFT_PARSE_FAILED
                for diagnostic in batch.diagnostics
            )
            for batch in batches
        )
        return ReactiveWriteSummary(nodes_created=1, relationships_created=0)

    with (
        patch("palace_mcp.mcp_server.get_driver", return_value=MagicMock()),
        patch(
            "palace_mcp.extractors.reactive_dependency_tracer.extractor.ensure_custom_schema",
            new_callable=AsyncMock,
        ),
        patch(
            "palace_mcp.extractors.reactive_dependency_tracer.extractor.write_reactive_graph",
            side_effect=_capture_write,
        ),
    ):
        stats = await extractor.run(graphiti=MagicMock(), ctx=ctx)

    assert stats.nodes_written == 1


@pytest.mark.asyncio
async def test_extractor_requires_driver(tmp_path: Path) -> None:
    repo = _fixture_repo(tmp_path)
    extractor = ReactiveDependencyTracerExtractor()

    with patch("palace_mcp.mcp_server.get_driver", return_value=None):
        with pytest.raises(ExtractorError) as exc_info:
            await extractor.run(graphiti=MagicMock(), ctx=_make_ctx(repo))

    assert exc_info.value.error_code is ExtractorErrorCode.SCHEMA_BOOTSTRAP_FAILED
