"""Unit tests for DependencySurfaceExtractor orchestrator — Task 8."""

from __future__ import annotations

import logging
import textwrap
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from palace_mcp.extractors.base import ExtractorRunContext
from palace_mcp.extractors.dependency_surface.extractor import DependencySurfaceExtractor

_PYPROJECT_TOML = textwrap.dedent(
    """
    [project]
    name = "x"
    dependencies = ["neo4j>=5.0", "graphiti-core==0.28.2"]
    """
)

_UV_LOCK = textwrap.dedent(
    """
    version = 1
    [[package]]
    name = "neo4j"
    version = "5.28.2"

    [[package]]
    name = "graphiti-core"
    version = "0.28.2"
    """
)


def _make_ctx(repo_path: Path) -> ExtractorRunContext:
    return ExtractorRunContext(
        project_slug="x",
        group_id="project/x",
        repo_path=repo_path,
        run_id="test-run",
        duration_ms=0,
        logger=logging.getLogger("test"),
    )


def _mock_writer(nodes: int, edges: int) -> AsyncMock:
    mock = AsyncMock(return_value=(nodes, edges))
    return mock


@pytest.mark.asyncio
async def test_extractor_no_manifests_returns_zero(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    extractor = DependencySurfaceExtractor()
    mock_driver = MagicMock()
    graphiti = MagicMock()
    ctx = _make_ctx(tmp_path)

    with (
        patch(
            "palace_mcp.mcp_server.get_driver",
            return_value=mock_driver,
        ),
        patch(
            "palace_mcp.extractors.dependency_surface.extractor.ensure_custom_schema",
            new_callable=AsyncMock,
        ),
        patch(
            "palace_mcp.extractors.dependency_surface.extractor.write_to_neo4j",
            new_callable=AsyncMock,
            return_value=(0, 0),
        ),
        caplog.at_level(logging.WARNING),
    ):
        stats = await extractor.run(graphiti=graphiti, ctx=ctx)

    assert stats.nodes_written == 0
    assert stats.edges_written == 0


@pytest.mark.asyncio
async def test_extractor_python_only(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(_PYPROJECT_TOML)
    (tmp_path / "uv.lock").write_text(_UV_LOCK)

    extractor = DependencySurfaceExtractor()
    graphiti = MagicMock()
    ctx = _make_ctx(tmp_path)

    mock_write = _mock_writer(2, 2)
    with (
        patch(
            "palace_mcp.mcp_server.get_driver",
            return_value=MagicMock(),
        ),
        patch(
            "palace_mcp.extractors.dependency_surface.extractor.ensure_custom_schema",
            new_callable=AsyncMock,
        ),
        patch(
            "palace_mcp.extractors.dependency_surface.extractor.write_to_neo4j",
            mock_write,
        ),
    ):
        stats = await extractor.run(graphiti=graphiti, ctx=ctx)

    assert stats.nodes_written == 2
    assert stats.edges_written == 2


@pytest.mark.asyncio
async def test_extractor_all_three_ecosystems(tmp_path: Path) -> None:
    # Setup SPM
    (tmp_path / "Package.swift").write_text(
        textwrap.dedent(
            """
            // swift-tools-version: 5.9
            import PackageDescription
            let package = Package(
                name: "X",
                dependencies: [
                    .package(url: "https://github.com/apple/swift-log.git", from: "1.4.0"),
                    .package(url: "https://github.com/apple/swift-collections", exact: "1.1.4"),
                ],
                targets: [.target(name: "X")]
            )
            """
        )
    )
    # Setup Gradle
    (tmp_path / "gradle").mkdir()
    (tmp_path / "gradle" / "libs.versions.toml").write_text(
        textwrap.dedent(
            """
            [versions]
            appcompat = "1.7.1"
            retrofit = "3.0.0"

            [libraries]
            androidx-appcompat = { group = "androidx.appcompat", name = "appcompat", version.ref = "appcompat" }
            retrofit2 = { group = "com.squareup.retrofit2", name = "retrofit", version.ref = "retrofit" }
            """
        )
    )
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "build.gradle.kts").write_text(
        "dependencies { implementation(libs.androidx.appcompat) \n testImplementation(libs.retrofit2) }"
    )
    # Setup Python
    (tmp_path / "pyproject.toml").write_text(_PYPROJECT_TOML)
    (tmp_path / "uv.lock").write_text(_UV_LOCK)

    extractor = DependencySurfaceExtractor()
    graphiti = MagicMock()
    ctx = _make_ctx(tmp_path)

    # 2 SPM (unresolved, no Package.resolved) + 2 Gradle + 2 Python = 6 total
    call_count: list[int] = []

    async def mock_write(driver, deps, *, project_slug, group_id):  # type: ignore[no-untyped-def]
        count = len(list(deps))
        call_count.append(count)
        return count, count

    with (
        patch(
            "palace_mcp.mcp_server.get_driver",
            return_value=MagicMock(),
        ),
        patch(
            "palace_mcp.extractors.dependency_surface.extractor.ensure_custom_schema",
            new_callable=AsyncMock,
        ),
        patch(
            "palace_mcp.extractors.dependency_surface.extractor.write_to_neo4j",
            side_effect=mock_write,
        ),
    ):
        stats = await extractor.run(graphiti=graphiti, ctx=ctx)

    assert stats.nodes_written == 6
    assert stats.edges_written == 6


@pytest.mark.asyncio
async def test_extractor_partial_failure_continues(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    # Only Python present; Gradle parser will raise (no libs.versions.toml but build.gradle.kts present)
    (tmp_path / "pyproject.toml").write_text(_PYPROJECT_TOML)
    (tmp_path / "uv.lock").write_text(_UV_LOCK)

    # Gradle build.gradle.kts present but no libs.versions.toml — triggers warning, no crash
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "build.gradle.kts").write_text(
        "dependencies { implementation(libs.some.dep) }"
    )

    extractor = DependencySurfaceExtractor()
    graphiti = MagicMock()
    ctx = _make_ctx(tmp_path)

    async def mock_write(driver, deps, *, project_slug, group_id):  # type: ignore[no-untyped-def]
        count = len(list(deps))
        return count, count

    with (
        patch(
            "palace_mcp.mcp_server.get_driver",
            return_value=MagicMock(),
        ),
        patch(
            "palace_mcp.extractors.dependency_surface.extractor.ensure_custom_schema",
            new_callable=AsyncMock,
        ),
        patch(
            "palace_mcp.extractors.dependency_surface.extractor.write_to_neo4j",
            side_effect=mock_write,
        ),
    ):
        stats = await extractor.run(graphiti=graphiti, ctx=ctx)

    # Python 2 deps succeed; Gradle warns (no toml) but yields 0 deps — no crash
    assert stats.nodes_written >= 2
