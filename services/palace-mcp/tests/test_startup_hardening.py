"""Tests for Patterns #5 and #11: startup hardening.

Pattern #5 — Lazy init: no blocking external calls during startup.
Pattern #11 — Fire-and-forget slow init: ensure_constraints is not awaited
              in lifespan; it is scheduled as a background task with error
              logging on failure.
"""

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _mock_graphiti_runtime() -> None:
    """Isolate startup-hardening tests from graphiti-core and extractor schema."""
    mock_graphiti = MagicMock()
    with (
        patch("palace_mcp.main.build_graphiti", return_value=mock_graphiti),
        patch("palace_mcp.main.ensure_graphiti_schema", new_callable=AsyncMock),
        patch("palace_mcp.main.close_graphiti", new_callable=AsyncMock),
        patch("palace_mcp.main.ensure_extractors_schema", new_callable=AsyncMock),
    ):
        yield  # type: ignore[misc]


@pytest.fixture(autouse=True)
def _stub_required_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Settings requires NEO4J_PASSWORD + OPENAI_API_KEY. Tests that
    exercise ``lifespan`` must have both present in env.
    """
    monkeypatch.setenv("NEO4J_PASSWORD", "test-pw")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")


class TestFireAndForgetConstraints:
    """Pattern #11: ensure_constraints must be fire-and-forget, not blocking."""

    @pytest.mark.asyncio
    async def test_lifespan_does_not_await_ensure_constraints(self) -> None:
        """Lifespan completes even when ensure_constraints hangs indefinitely.

        If ensure_constraints were awaited directly, a never-resolving coroutine
        would block the lifespan forever. Fire-and-forget means lifespan yields
        within a short timeout.
        """
        from palace_mcp.main import lifespan

        # Simulate a Neo4j driver — connectivity check passes, close is a no-op.
        mock_driver = AsyncMock()
        mock_driver.verify_connectivity = AsyncMock(return_value=None)
        mock_driver.close = AsyncMock(return_value=None)

        # ensure_schema hangs forever — if awaited, lifespan never yields.
        never_resolving: asyncio.Future[None] = asyncio.get_event_loop().create_future()

        async def hanging_constraints(
            _driver: object, *, default_group_id: str
        ) -> None:
            await never_resolving

        mock_app = MagicMock()
        mock_app.state = MagicMock()
        # Provide a minimal mock for the MCP sub-app lifespan.
        from contextlib import asynccontextmanager
        from collections.abc import AsyncGenerator

        @asynccontextmanager
        async def _noop_lifespan(app: object) -> AsyncGenerator[None, None]:
            yield

        with (
            patch(
                "palace_mcp.main.AsyncGraphDatabase.driver", return_value=mock_driver
            ),
            patch("palace_mcp.main.ensure_schema", side_effect=hanging_constraints),
            patch(
                "palace_mcp.main._mcp_asgi_app.router.lifespan_context",
                return_value=_noop_lifespan(None),
            ),
        ):
            async with asyncio.timeout(2.0):
                async with lifespan(mock_app):
                    pass  # Lifespan must yield here, not hang

    @pytest.mark.asyncio
    async def test_ensure_constraints_failure_logs_error_not_crash(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """If background ensure_constraints raises, the app logs an error but stays up."""
        from palace_mcp.main import lifespan

        mock_driver = AsyncMock()
        mock_driver.verify_connectivity = AsyncMock(return_value=None)
        mock_driver.close = AsyncMock(return_value=None)

        async def failing_constraints(
            _driver: object, *, default_group_id: str
        ) -> None:
            raise RuntimeError("neo4j not ready")

        mock_app = MagicMock()
        mock_app.state = MagicMock()
        from contextlib import asynccontextmanager
        from collections.abc import AsyncGenerator

        @asynccontextmanager
        async def _noop_lifespan(app: object) -> AsyncGenerator[None, None]:
            yield

        with (
            patch(
                "palace_mcp.main.AsyncGraphDatabase.driver", return_value=mock_driver
            ),
            patch("palace_mcp.main.ensure_schema", side_effect=failing_constraints),
            patch(
                "palace_mcp.main._mcp_asgi_app.router.lifespan_context",
                return_value=_noop_lifespan(None),
            ),
            caplog.at_level(logging.ERROR, logger="palace_mcp.main"),
        ):
            async with asyncio.timeout(2.0):
                async with lifespan(mock_app):
                    # Give the background task time to run and fail.
                    await asyncio.sleep(0.05)

        # App stayed up (no exception propagated), error was logged.
        error_records = [r for r in caplog.records if r.levelno >= logging.ERROR]
        assert any(
            "neo4j not ready" in r.getMessage() or "ensure_schema" in r.getMessage()
            for r in error_records
        ), (
            f"Expected an error log about constraint failure, got: {[r.getMessage() for r in error_records]}"
        )


class TestEnsureSchemaWiredInLifespan:
    """Task 4 (GIM-52): lifespan calls ensure_schema with default_group_id."""

    @pytest.mark.asyncio
    async def test_lifespan_calls_ensure_schema_with_default_group_id(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """ensure_schema must be called once, fire-and-forget, with default_group_id."""
        from collections.abc import AsyncGenerator
        from contextlib import asynccontextmanager

        from palace_mcp.main import lifespan

        calls: list[tuple[object, str]] = []

        async def fake_ensure_schema(driver: object, *, default_group_id: str) -> None:
            calls.append((driver, default_group_id))

        mock_driver = AsyncMock()
        mock_driver.verify_connectivity = AsyncMock(return_value=None)
        mock_driver.close = AsyncMock(return_value=None)

        mock_app = MagicMock()
        mock_app.state = MagicMock()

        @asynccontextmanager
        async def _noop_lifespan(app: object) -> AsyncGenerator[None, None]:
            yield

        with (
            patch(
                "palace_mcp.main.AsyncGraphDatabase.driver", return_value=mock_driver
            ),
            patch("palace_mcp.main.ensure_schema", side_effect=fake_ensure_schema),
            patch(
                "palace_mcp.main._mcp_asgi_app.router.lifespan_context",
                return_value=_noop_lifespan(None),
            ),
        ):
            async with asyncio.timeout(2.0):
                async with lifespan(mock_app):
                    # Give background task time to run.
                    await asyncio.sleep(0.05)

        assert len(calls) == 1, f"ensure_schema should be called once, got {len(calls)}"
        assert calls[0][1] == "project/gimle"


class TestNoBlockingExternalCallsAtStartup:
    """Pattern #5: startup must not block on external calls.

    Verified implicitly by the fire-and-forget tests above: if constraints
    run as a background task, the startup path contains no blocking external
    calls. The driver creation itself is a local object — no network call
    until a session is opened.
    """

    @pytest.mark.asyncio
    async def test_lifespan_config_uses_settings_defaults(self) -> None:
        """Pattern #6+#5: lifespan reads config via Settings (defaults present),
        never calls os.environ[] directly in the startup critical path.
        """
        from palace_mcp.main import lifespan

        mock_driver = AsyncMock()
        mock_driver.verify_connectivity = AsyncMock(return_value=None)
        mock_driver.close = AsyncMock(return_value=None)

        async def noop_constraints(_driver: object, *, default_group_id: str) -> None:
            pass

        mock_app = MagicMock()
        mock_app.state = MagicMock()
        from contextlib import asynccontextmanager
        from collections.abc import AsyncGenerator

        @asynccontextmanager
        async def _noop_lifespan(app: object) -> AsyncGenerator[None, None]:
            yield

        # Only NEO4J_PASSWORD is required (no default). NEO4J_URI should use default.
        import os

        env_override = {"NEO4J_PASSWORD": "test-pw"}
        with (
            patch.dict(os.environ, env_override),
            patch(
                "palace_mcp.main.AsyncGraphDatabase.driver", return_value=mock_driver
            ) as driver_call,
            patch("palace_mcp.main.ensure_schema", side_effect=noop_constraints),
            patch(
                "palace_mcp.main._mcp_asgi_app.router.lifespan_context",
                return_value=_noop_lifespan(None),
            ),
        ):
            async with asyncio.timeout(2.0):
                async with lifespan(mock_app):
                    pass

        # Driver was constructed — startup completed without KeyError.
        driver_call.assert_called_once()
        call_kwargs = driver_call.call_args
        # uri arg (positional or keyword)
        uri = call_kwargs.args[0] if call_kwargs.args else call_kwargs.kwargs.get("uri")
        assert uri == "bolt://neo4j:7687"  # default from Settings
