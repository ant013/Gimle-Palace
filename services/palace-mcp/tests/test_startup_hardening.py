"""Tests for startup hardening patterns.

Pattern #5 — Lazy init: no blocking external calls during startup.
Pattern #6 — Config merge: Settings reads defaults without KeyError.
Pattern #11 — Fire-and-forget helper remains usable.
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@asynccontextmanager
async def _noop_lifespan(app: object) -> AsyncGenerator[None, None]:
    yield


def _make_mock_graphiti() -> MagicMock:
    """Mock Graphiti instance with no-op driver."""
    graphiti = MagicMock()
    graphiti.driver = MagicMock()
    graphiti.driver.verify_connectivity = AsyncMock(return_value=None)
    graphiti.close = AsyncMock(return_value=None)
    return graphiti


class TestLifespanCompletes:
    """Lifespan must not block on external calls during startup."""

    @pytest.mark.asyncio
    async def test_lifespan_yields_without_blocking(self) -> None:
        """Lifespan completes within a short timeout (no blocking network I/O)."""
        from palace_mcp.main import lifespan

        mock_graphiti = _make_mock_graphiti()
        mock_app = MagicMock()
        mock_app.state = MagicMock()

        with (
            patch("palace_mcp.main.build_graphiti", return_value=mock_graphiti),
            patch(
                "palace_mcp.main._mcp_asgi_app.router.lifespan_context",
                return_value=_noop_lifespan(None),
            ),
        ):
            async with asyncio.timeout(2.0):
                async with lifespan(mock_app):
                    pass  # lifespan must yield quickly

        mock_graphiti.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_lifespan_sets_graphiti_on_app_state(self) -> None:
        """Lifespan stores graphiti on app.state.graphiti."""
        from palace_mcp.main import lifespan

        mock_graphiti = _make_mock_graphiti()
        mock_app = MagicMock()
        mock_app.state = MagicMock()

        with (
            patch("palace_mcp.main.build_graphiti", return_value=mock_graphiti),
            patch(
                "palace_mcp.main._mcp_asgi_app.router.lifespan_context",
                return_value=_noop_lifespan(None),
            ),
        ):
            async with lifespan(mock_app):
                assert mock_app.state.graphiti is mock_graphiti

    @pytest.mark.asyncio
    async def test_lifespan_config_uses_settings_defaults(self) -> None:
        """Pattern #6+#5: lifespan reads config via Settings (defaults present),
        never calls os.environ[] directly in the startup critical path.
        """
        from palace_mcp.main import lifespan
        import os

        mock_graphiti = _make_mock_graphiti()
        mock_app = MagicMock()
        mock_app.state = MagicMock()

        env_override = {"NEO4J_PASSWORD": "test-pw"}
        captured: list[object] = []

        def capture_build_graphiti(settings: object) -> MagicMock:
            captured.append(settings)
            return mock_graphiti

        with (
            patch.dict(os.environ, env_override),
            patch("palace_mcp.main.build_graphiti", side_effect=capture_build_graphiti),
            patch(
                "palace_mcp.main._mcp_asgi_app.router.lifespan_context",
                return_value=_noop_lifespan(None),
            ),
        ):
            async with asyncio.timeout(2.0):
                async with lifespan(mock_app):
                    pass

        assert len(captured) == 1
        settings = captured[0]
        assert settings.neo4j_uri == "bolt://neo4j:7687"  # type: ignore[union-attr]


class TestFireAndForget:
    """Pattern #11: _fire_and_forget helper schedules background tasks safely."""

    @pytest.mark.asyncio
    async def test_fire_and_forget_runs_coro(self) -> None:
        """_fire_and_forget executes the coroutine as a background task."""
        from palace_mcp.main import _fire_and_forget

        completed: list[bool] = []

        async def _coro() -> None:
            completed.append(True)

        _fire_and_forget(_coro())
        await asyncio.sleep(0.05)
        assert completed == [True]

    @pytest.mark.asyncio
    async def test_fire_and_forget_logs_error_on_failure(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """_fire_and_forget logs errors without propagating them."""
        from palace_mcp.main import _fire_and_forget

        async def _failing() -> None:
            raise RuntimeError("background task failed!")

        with caplog.at_level(logging.ERROR, logger="palace_mcp.main"):
            _fire_and_forget(_failing())
            await asyncio.sleep(0.05)

        assert any("background task failed!" in r.getMessage() for r in caplog.records)
