"""Unit tests for reactive_dependency_tracer extractor orchestrator."""

from __future__ import annotations

import logging
import json
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
from palace_mcp.extractors.reactive_dependency_tracer.swift_helper_contract import (
    MAX_FILES_PER_RUN,
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
        patch(
            "palace_mcp.extractors.reactive_dependency_tracer.extractor._lookup_component_symbol_keys",
            new_callable=AsyncMock,
            return_value={"counter_component": "App.CounterView"},
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
async def test_extractor_preserves_valid_files_when_one_helper_file_is_invalid(
    tmp_path: Path,
) -> None:
    repo = _fixture_repo(tmp_path)
    fixture_path = repo / "reactive_facts.json"
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    payload["files"].append(
        {
            "path": "Sources/App/Bad.swift",
            "module_name": "App",
            "parse_status": "ok",
            "components": [
                {
                    "component_ref": "bad_component",
                    "module_name": "App",
                    "component_kind": "swiftui_view",
                    "qualified_name": "App.BadView",
                    "display_name": "BadView",
                    "range": {
                        "start_line": 1,
                        "start_col": 1,
                        "end_line": 3,
                        "end_col": 1,
                    },
                    "resolution_status": "syntax_exact",
                }
            ],
            "states": [],
            "effects": [],
            "edges": [
                {
                    "edge_ref": "bad_edge",
                    "edge_kind": "triggers_effect",
                    "from_ref": "bad_component",
                    "to_ref": "missing",
                    "owner_component_ref": "bad_component",
                    "access_path": "broken",
                    "binding_kind": None,
                    "trigger_expression_kind": "on_change_of",
                    "range": {
                        "start_line": 2,
                        "start_col": 1,
                        "end_line": 2,
                        "end_col": 8,
                    },
                    "confidence_hint": "high",
                    "resolution_status": "syntax_exact",
                }
            ],
            "diagnostics": [],
        }
    )
    fixture_path.write_text(json.dumps(payload), encoding="utf-8")
    extractor = ReactiveDependencyTracerExtractor()
    ctx = _make_ctx(repo)

    async def _capture_write(*, driver, batches):  # type: ignore[no-untyped-def]
        assert any(batch.components for batch in batches)
        assert any(
            any(
                diagnostic.file_path == "Sources/App/Bad.swift"
                and diagnostic.diagnostic_code
                is ReactiveDiagnosticCode.SWIFT_PARSE_FAILED
                for diagnostic in batch.diagnostics
            )
            for batch in batches
        )
        return ReactiveWriteSummary(nodes_created=7, relationships_created=5)

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
        patch(
            "palace_mcp.extractors.reactive_dependency_tracer.extractor._lookup_component_symbol_keys",
            new_callable=AsyncMock,
            return_value={},
        ),
    ):
        stats = await extractor.run(graphiti=MagicMock(), ctx=ctx)

    assert stats.nodes_written == 7
    assert stats.edges_written == 5


@pytest.mark.asyncio
async def test_extractor_unsupported_schema_writes_version_diagnostic(
    tmp_path: Path,
) -> None:
    repo = _fixture_repo(tmp_path)
    fixture_path = repo / "reactive_facts.json"
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    payload["schema_version"] = 2
    fixture_path.write_text(json.dumps(payload), encoding="utf-8")
    extractor = ReactiveDependencyTracerExtractor()
    ctx = _make_ctx(repo)

    async def _capture_write(*, driver, batches):  # type: ignore[no-untyped-def]
        assert any(
            any(
                diagnostic.diagnostic_code
                is ReactiveDiagnosticCode.SWIFT_HELPER_VERSION_UNSUPPORTED
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
async def test_extractor_rejects_helper_payload_over_max_files_per_run(
    tmp_path: Path,
) -> None:
    repo = _fixture_repo(tmp_path)
    fixture_path = repo / "reactive_facts.json"
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    payload["files"] = [payload["files"][0]] * (MAX_FILES_PER_RUN + 1)
    fixture_path.write_text(json.dumps(payload), encoding="utf-8")
    extractor = ReactiveDependencyTracerExtractor()
    ctx = _make_ctx(repo)

    async def _capture_write(*, driver, batches):  # type: ignore[no-untyped-def]
        assert any(
            any(
                diagnostic.diagnostic_code is ReactiveDiagnosticCode.SWIFT_PARSE_FAILED
                and diagnostic.file_path is None
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
