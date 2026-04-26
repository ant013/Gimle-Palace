"""Unit tests for palace_mcp.memory.prime.core."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from palace_mcp.memory.prime.core import detect_slice_id, render_universal_core
from palace_mcp.memory.prime.deps import PrimingDeps


# ── detect_slice_id ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_detect_slice_id_parses_feature_branch() -> None:
    """git output 'feature/GIM-96' → 'GIM-96'."""
    with patch(
        "palace_mcp.memory.prime.core.asyncio.create_subprocess_exec"
    ) as mock_exec:
        proc = AsyncMock()
        proc.communicate.return_value = (b"feature/GIM-96\n", b"")
        mock_exec.return_value = proc

        result = await detect_slice_id("/repos/gimle")

    assert result == "GIM-96"


@pytest.mark.asyncio
async def test_detect_slice_id_parses_alpha_suffix() -> None:
    """feature/GIM-95a → 'GIM-95a'."""
    with patch(
        "palace_mcp.memory.prime.core.asyncio.create_subprocess_exec"
    ) as mock_exec:
        proc = AsyncMock()
        proc.communicate.return_value = (b"feature/GIM-95a\n", b"")
        mock_exec.return_value = proc

        result = await detect_slice_id("/repos/gimle")

    assert result == "GIM-95a"


@pytest.mark.asyncio
async def test_detect_slice_id_returns_none_for_develop() -> None:
    """develop branch does not match feature pattern → None."""
    with patch(
        "palace_mcp.memory.prime.core.asyncio.create_subprocess_exec"
    ) as mock_exec:
        proc = AsyncMock()
        proc.communicate.return_value = (b"develop\n", b"")
        mock_exec.return_value = proc

        result = await detect_slice_id("/repos/gimle")

    assert result is None


@pytest.mark.asyncio
async def test_detect_slice_id_returns_none_for_detached_head() -> None:
    with patch(
        "palace_mcp.memory.prime.core.asyncio.create_subprocess_exec"
    ) as mock_exec:
        proc = AsyncMock()
        proc.communicate.return_value = (b"HEAD\n", b"")
        mock_exec.return_value = proc

        result = await detect_slice_id("/repos/gimle")

    assert result is None


@pytest.mark.asyncio
async def test_detect_slice_id_returns_none_on_subprocess_error() -> None:
    with patch(
        "palace_mcp.memory.prime.core.asyncio.create_subprocess_exec",
        side_effect=OSError("git not found"),
    ):
        result = await detect_slice_id("/repos/gimle")

    assert result is None


@pytest.mark.asyncio
async def test_detect_slice_id_returns_none_on_timeout() -> None:
    with patch(
        "palace_mcp.memory.prime.core.asyncio.create_subprocess_exec"
    ) as mock_exec:
        proc = MagicMock()
        # communicate raises TimeoutError on first call, returns drain tuple on second
        proc.communicate = AsyncMock(side_effect=[asyncio.TimeoutError(), (b"", b"")])
        proc.kill = MagicMock()  # sync kill is fine; we don't await it
        mock_exec.return_value = proc

        result = await detect_slice_id("/repos/gimle")

    assert result is None


# ── render_universal_core ──────────────────────────────────────────────────────


def _make_deps(driver: MagicMock) -> PrimingDeps:
    settings = MagicMock()
    settings.palace_git_workspace = "/repos/gimle"
    settings.paperclip_api_url = "http://localhost:3000"
    from pathlib import Path

    return PrimingDeps(
        graphiti=MagicMock(),
        driver=driver,
        settings=settings,
        default_group_id="project/gimle",
        role_prime_dir=Path("/nonexistent"),
    )


@pytest.mark.asyncio
async def test_render_universal_core_contains_role_and_slice() -> None:
    driver = MagicMock()
    deps = _make_deps(driver)

    with (
        patch(
            "palace_mcp.memory.prime.core.perform_lookup",
            new_callable=AsyncMock,
            return_value=MagicMock(items=[]),
        ),
        patch(
            "palace_mcp.memory.prime.core.get_health",
            new_callable=AsyncMock,
            return_value=MagicMock(
                neo4j_reachable=True,
                code_graph_reachable=True,
                bridge=None,
            ),
        ),
    ):
        content = await render_universal_core(deps, "pythonengineer", "GIM-96")

    assert "pythonengineer" in content
    assert "GIM-96" in content
    assert "<standing-instruction>" in content


@pytest.mark.asyncio
async def test_render_universal_core_no_slice_id_shows_fallback_header() -> None:
    driver = MagicMock()
    deps = _make_deps(driver)

    with (
        patch(
            "palace_mcp.memory.prime.core.perform_lookup",
            new_callable=AsyncMock,
            return_value=MagicMock(items=[]),
        ),
        patch(
            "palace_mcp.memory.prime.core.get_health",
            new_callable=AsyncMock,
            return_value=MagicMock(
                neo4j_reachable=True,
                code_graph_reachable=True,
                bridge=None,
            ),
        ),
    ):
        content = await render_universal_core(deps, "cto", None)

    assert "cto" in content
    assert "no slice context" in content.lower()


@pytest.mark.asyncio
async def test_render_universal_core_wraps_decisions_in_untrusted_band() -> None:
    driver = MagicMock()
    deps = _make_deps(driver)

    decision_item = MagicMock()
    decision_item.properties = {
        "uuid": "abc-123",
        "decision_maker_claimed": "CTO",
        "confidence": "high",
        "created_at": "2026-04-01",
        "body": "Use async Neo4j driver everywhere.",
    }

    with (
        patch(
            "palace_mcp.memory.prime.core.perform_lookup",
            new_callable=AsyncMock,
            return_value=MagicMock(items=[decision_item]),
        ),
        patch(
            "palace_mcp.memory.prime.core.get_health",
            new_callable=AsyncMock,
            return_value=MagicMock(
                neo4j_reachable=True,
                code_graph_reachable=True,
                bridge=None,
            ),
        ),
    ):
        content = await render_universal_core(deps, "cto", "GIM-96")

    assert '<untrusted-decision uuid="abc-123"' in content
    assert "Use async Neo4j driver everywhere." in content
    assert "</untrusted-decision>" in content


@pytest.mark.asyncio
async def test_render_universal_core_health_failure_graceful() -> None:
    driver = MagicMock()
    deps = _make_deps(driver)

    with (
        patch(
            "palace_mcp.memory.prime.core.perform_lookup",
            new_callable=AsyncMock,
            return_value=MagicMock(items=[]),
        ),
        patch(
            "palace_mcp.memory.prime.core.get_health",
            new_callable=AsyncMock,
            side_effect=Exception("connection refused"),
        ),
    ):
        content = await render_universal_core(deps, "operator", "GIM-96")

    assert "unavailable" in content
