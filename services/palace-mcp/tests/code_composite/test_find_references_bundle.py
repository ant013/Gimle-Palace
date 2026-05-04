"""Tests for bundle-aware palace.code.find_references (GIM-182 §5.2).

Covers:
- _resolve_slug: bundle slug → kind="bundle" + member_slugs
- _resolve_slug: project slug → kind="project"
- _resolve_slug: unknown slug → kind="none"
- find_references bundle path: merges occurrences, attaches bundle_health
- find_references bundle path: Tantivy failure → query_failed_slugs populated
- find_references project path: unchanged (no bundle_health in response)
- find_references none path: error envelope
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

# Patch targets: get_driver / get_settings are lazy-imported inside
# palace_code_find_references from palace_mcp.mcp_server, so we patch
# at the source module rather than at code_composite.
_PATCH_GET_DRIVER = "palace_mcp.mcp_server.get_driver"
_PATCH_GET_SETTINGS = "palace_mcp.mcp_server.get_settings"


# ---------------------------------------------------------------------------
# Helpers for mocking the Neo4j driver at the _resolve_slug level
# ---------------------------------------------------------------------------


def _driver_for_resolve_slug(
    kind: str,
    member_slugs: list[str],
) -> MagicMock:
    """Driver mock returning a single row from _resolve_slug's Cypher query."""

    class _Row:
        def __getitem__(self, key: str) -> Any:
            return {"kind": kind, "member_slugs": member_slugs}[key]

    result = MagicMock()
    result.single = AsyncMock(return_value=_Row())

    session = MagicMock()
    session.run = AsyncMock(return_value=result)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)

    driver = MagicMock()
    driver.session = MagicMock(return_value=session)
    return driver


# ---------------------------------------------------------------------------
# _resolve_slug unit tests (requires module-level function in code_composite)
# ---------------------------------------------------------------------------


class TestResolveSlug:
    """Unit tests for code_composite._resolve_slug."""

    async def test_bundle_slug_returns_bundle_kind_with_members(self) -> None:
        """Bundle name → kind='bundle' + member_slugs list."""
        from palace_mcp.code_composite import _resolve_slug

        driver = _driver_for_resolve_slug("bundle", ["evm-kit", "uwb-kit"])
        result = await _resolve_slug(driver, "uw-ios")
        assert result.kind == "bundle"
        assert set(result.member_slugs) == {"evm-kit", "uwb-kit"}

    async def test_project_slug_returns_project_kind(self) -> None:
        """Registered project slug → kind='project', member_slugs empty."""
        from palace_mcp.code_composite import _resolve_slug

        driver = _driver_for_resolve_slug("project", [])
        result = await _resolve_slug(driver, "gimle")
        assert result.kind == "project"
        assert result.member_slugs == []

    async def test_unknown_slug_returns_none_kind(self) -> None:
        """Unknown slug → kind='none'."""
        from palace_mcp.code_composite import _resolve_slug

        driver = _driver_for_resolve_slug("none", [])
        result = await _resolve_slug(driver, "does-not-exist")
        assert result.kind == "none"
        assert result.member_slugs == []

    async def test_bundle_with_no_members_returns_empty_member_slugs(self) -> None:
        """Empty bundle (no :CONTAINS edges) → kind='bundle', empty member_slugs."""
        from palace_mcp.code_composite import _resolve_slug

        driver = _driver_for_resolve_slug("bundle", [])
        result = await _resolve_slug(driver, "empty-bundle")
        assert result.kind == "bundle"
        assert result.member_slugs == []


# ---------------------------------------------------------------------------
# Capturing decorator helper for testing registered tools
# ---------------------------------------------------------------------------


def _register_and_capture(default_project: str = "gimle") -> dict[str, Any]:
    """Register code_composite tools and return captured {name: fn} map."""
    from palace_mcp.code_composite import register_code_composite_tools

    captured: dict[str, Any] = {}

    def fake_decorator(name: str, description: str):
        def inner(fn: Any) -> Any:
            captured[name] = fn
            return fn

        return inner

    register_code_composite_tools(fake_decorator, default_project=default_project)
    return captured


def _make_fake_bundle_status(
    name: str,
    members_total: int = 2,
    *,
    query_failed_slugs: tuple[str, ...] = (),
) -> Any:
    """Return a minimal BundleStatus-like object for patching."""
    from palace_mcp.memory.models import BundleStatus

    return BundleStatus(
        name=name,
        members_total=members_total,
        members_fresh_within_7d=members_total,
        members_stale=0,
        query_failed_slugs=query_failed_slugs,
        ingest_failed_slugs=(),
        never_ingested_slugs=(),
        stale_slugs=(),
        oldest_member_ingest_at=None,
        newest_member_ingest_at=None,
        as_of=datetime.now(timezone.utc),
    )


def _make_bridge_mock(raw_results: list[dict[str, Any]]) -> MagicMock:
    bridge = MagicMock()
    bridge.__aenter__ = AsyncMock(return_value=bridge)
    bridge.__aexit__ = AsyncMock(return_value=None)
    bridge.search_by_symbol_id_async = AsyncMock(return_value=raw_results)
    return bridge


# ---------------------------------------------------------------------------
# palace_code_find_references — bundle path
# ---------------------------------------------------------------------------


class TestFindReferencesBundlePath:
    """Bundle slug → occurrences merged from all members + bundle_health attached."""

    def _get_fn(self) -> Any:
        captured = _register_and_capture()
        return captured["palace.code.find_references"]

    def _settings(self) -> MagicMock:
        s = MagicMock()
        s.palace_tantivy_index_path = "/tmp/fake-tantivy"
        s.palace_tantivy_heap_mb = 64
        return s

    async def test_bundle_path_returns_ok_with_bundle_health(self) -> None:
        """Bundle slug resolved → response has ok:True and bundle_health key."""
        from palace_mcp.code_composite import SlugResolution

        find_refs = self._get_fn()
        fake_health = _make_fake_bundle_status("uw-ios")

        raw_occ = {
            "file_path": "/repos/evm-kit/Sources/Core.swift",
            "line": 10,
            "col_start": 4,
            "col_end": 15,
            "kind": "definition",
            "symbol_qualified_name": "EvmKit.Address",
        }

        with (
            patch(_PATCH_GET_DRIVER, return_value=MagicMock()),
            patch(_PATCH_GET_SETTINGS, return_value=self._settings()),
            patch(
                "palace_mcp.code_composite._resolve_slug",
                new=AsyncMock(
                    return_value=SlugResolution(
                        kind="bundle", member_slugs=["evm-kit", "uwb-kit"]
                    )
                ),
            ),
            patch(
                "palace_mcp.code_composite.bundle_status",
                new=AsyncMock(return_value=fake_health),
            ),
            patch(
                "palace_mcp.code_composite.TantivyBridge",
                return_value=_make_bridge_mock([raw_occ]),
            ),
            patch("palace_mcp.code_composite.symbol_id_for", return_value=42),
        ):
            result = await find_refs("EvmKit.Address", "uw-ios", 100)

        assert result["ok"] is True
        assert "bundle_health" in result
        assert "occurrences" in result

    async def test_bundle_path_no_ingest_run_check_for_bundle_slug(self) -> None:
        """For bundle slug, _query_any_ingest_run_for_project is NOT called."""
        from palace_mcp.code_composite import SlugResolution

        find_refs = self._get_fn()
        fake_health = _make_fake_bundle_status("uw-ios")

        with (
            patch(_PATCH_GET_DRIVER, return_value=MagicMock()),
            patch(_PATCH_GET_SETTINGS, return_value=self._settings()),
            patch(
                "palace_mcp.code_composite._resolve_slug",
                new=AsyncMock(
                    return_value=SlugResolution(kind="bundle", member_slugs=["evm-kit"])
                ),
            ),
            patch(
                "palace_mcp.code_composite.bundle_status",
                new=AsyncMock(return_value=fake_health),
            ),
            patch(
                "palace_mcp.code_composite.TantivyBridge",
                return_value=_make_bridge_mock([]),
            ),
            patch("palace_mcp.code_composite.symbol_id_for", return_value=1),
            patch(
                "palace_mcp.code_composite._query_any_ingest_run_for_project"
            ) as mock_ingest_check,
        ):
            await find_refs("EvmKit.Address", "uw-ios", 100)

        mock_ingest_check.assert_not_called()

    async def test_bundle_path_tantivy_failure_populates_query_failed_slugs(
        self,
    ) -> None:
        """Tantivy search failure on bundle → query_failed_slugs = all member slugs."""
        from palace_mcp.code_composite import SlugResolution

        find_refs = self._get_fn()
        fake_health = _make_fake_bundle_status("uw-ios")

        failing_bridge = MagicMock()
        failing_bridge.__aenter__ = AsyncMock(return_value=failing_bridge)
        failing_bridge.__aexit__ = AsyncMock(return_value=None)
        failing_bridge.search_by_symbol_id_async = AsyncMock(
            side_effect=RuntimeError("tantivy index corrupted")
        )

        with (
            patch(_PATCH_GET_DRIVER, return_value=MagicMock()),
            patch(_PATCH_GET_SETTINGS, return_value=self._settings()),
            patch(
                "palace_mcp.code_composite._resolve_slug",
                new=AsyncMock(
                    return_value=SlugResolution(
                        kind="bundle", member_slugs=["evm-kit", "uwb-kit"]
                    )
                ),
            ),
            patch(
                "palace_mcp.code_composite.bundle_status",
                new=AsyncMock(return_value=fake_health),
            ),
            patch(
                "palace_mcp.code_composite.TantivyBridge", return_value=failing_bridge
            ),
            patch("palace_mcp.code_composite.symbol_id_for", return_value=42),
        ):
            result = await find_refs("EvmKit.Address", "uw-ios", 100)

        assert result["ok"] is True
        health = result["bundle_health"]
        assert set(health["query_failed_slugs"]) == {"evm-kit", "uwb-kit"}

    async def test_bundle_health_serialised_to_dict(self) -> None:
        """bundle_health in response is a plain dict (model_dump output)."""
        from palace_mcp.code_composite import SlugResolution

        find_refs = self._get_fn()
        fake_health = _make_fake_bundle_status("uw-ios")

        with (
            patch(_PATCH_GET_DRIVER, return_value=MagicMock()),
            patch(_PATCH_GET_SETTINGS, return_value=self._settings()),
            patch(
                "palace_mcp.code_composite._resolve_slug",
                new=AsyncMock(
                    return_value=SlugResolution(kind="bundle", member_slugs=["evm-kit"])
                ),
            ),
            patch(
                "palace_mcp.code_composite.bundle_status",
                new=AsyncMock(return_value=fake_health),
            ),
            patch(
                "palace_mcp.code_composite.TantivyBridge",
                return_value=_make_bridge_mock([]),
            ),
            patch("palace_mcp.code_composite.symbol_id_for", return_value=1),
        ):
            result = await find_refs("EvmKit.Address", "uw-ios", 100)

        assert isinstance(result["bundle_health"], dict)
        assert "name" in result["bundle_health"]
        assert "members_total" in result["bundle_health"]


# ---------------------------------------------------------------------------
# palace_code_find_references — project path unchanged
# ---------------------------------------------------------------------------


class TestFindReferencesProjectPath:
    """Project slug → existing path unchanged (no bundle_health)."""

    def _get_fn(self) -> Any:
        captured = _register_and_capture()
        return captured["palace.code.find_references"]

    def _settings(self) -> MagicMock:
        s = MagicMock()
        s.palace_tantivy_index_path = "/tmp/fake-tantivy"
        s.palace_tantivy_heap_mb = 64
        return s

    async def test_project_path_no_bundle_health_in_response(self) -> None:
        """Project slug → response has no bundle_health key."""
        from palace_mcp.code_composite import SlugResolution

        find_refs = self._get_fn()
        ingest_run_row = {"run_id": "abc", "success": True, "extractor_name": "sym_py"}

        with (
            patch(_PATCH_GET_DRIVER, return_value=MagicMock()),
            patch(_PATCH_GET_SETTINGS, return_value=self._settings()),
            patch(
                "palace_mcp.code_composite._resolve_slug",
                new=AsyncMock(return_value=SlugResolution(kind="project")),
            ),
            patch(
                "palace_mcp.code_composite._query_any_ingest_run_for_project",
                new=AsyncMock(return_value=ingest_run_row),
            ),
            patch(
                "palace_mcp.code_composite._query_eviction_record",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "palace_mcp.code_composite.TantivyBridge",
                return_value=_make_bridge_mock([]),
            ),
            patch("palace_mcp.code_composite.symbol_id_for", return_value=1),
            patch("palace_mcp.code_router.get_cm_session", return_value=None),
        ):
            result = await find_refs("MyModule.func", "gimle", 100)

        assert result["ok"] is True
        assert "bundle_health" not in result


# ---------------------------------------------------------------------------
# palace_code_find_references — none path (unknown slug)
# ---------------------------------------------------------------------------


class TestFindReferencesNonePath:
    """Unknown slug → error envelope returned."""

    def _get_fn(self) -> Any:
        captured = _register_and_capture()
        return captured["palace.code.find_references"]

    async def test_unknown_slug_returns_error_envelope(self) -> None:
        """Unregistered slug → ok:False, error_code reflects not found."""
        from palace_mcp.code_composite import SlugResolution

        find_refs = self._get_fn()

        with (
            patch(_PATCH_GET_DRIVER, return_value=MagicMock()),
            patch(_PATCH_GET_SETTINGS, return_value=MagicMock()),
            patch(
                "palace_mcp.code_composite._resolve_slug",
                new=AsyncMock(return_value=SlugResolution(kind="none")),
            ),
        ):
            result = await find_refs("Foo.bar", "ghost-project", 100)

        assert result["ok"] is False
        assert "error_code" in result
