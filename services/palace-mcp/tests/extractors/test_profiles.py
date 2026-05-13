"""Unit tests for extractors/foundation/profiles.py (Tasks 2.0 + 2.1).

RED tests — fail until profiles.py is implemented.
"""

from __future__ import annotations

import pytest
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock


# ---------------------------------------------------------------------------
# Helpers: minimal async driver fixture that returns a language_profile
# ---------------------------------------------------------------------------


def _make_driver_with_profile(language_profile: str | None) -> Any:
    """Return a mock Neo4j async driver whose first query returns language_profile."""

    class _SingleRow:
        def __init__(self, value: str | None) -> None:
            self._value = value

        def __getitem__(self, key: str) -> str | None:
            assert key == "language_profile"
            return self._value

    class _AsyncResult:
        def __init__(self, value: str | None) -> None:
            self._row = _SingleRow(value)
            self._returned = False

        async def single(self) -> _SingleRow | None:
            if self._value is not None:
                return self._row
            return None

        @property
        def _value(self) -> str | None:
            return self._row._value

    session = AsyncMock()
    session.run = AsyncMock(return_value=_AsyncResult(language_profile))
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    driver = MagicMock()
    driver.session = MagicMock(return_value=session)
    return driver


# ---------------------------------------------------------------------------
# Task 2.0 RED — resolve_profile ordering
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_profile_explicit_wins(tmp_path: Path) -> None:
    """Explicit :Project.language_profile beats manifest inference."""
    from palace_mcp.extractors.foundation.profiles import resolve_profile

    # Driver returns "swift_kit" for the project
    driver = _make_driver_with_profile("swift_kit")
    # tmp_path has no Package.swift — would be "python_service" if inferred from pyproject
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'")

    profile = await resolve_profile(driver, "tron-kit", repo_path=tmp_path)
    assert profile.name == "swift_kit"


@pytest.mark.asyncio
async def test_resolve_profile_manifest_inference(tmp_path: Path) -> None:
    """Package.swift → swift_kit when no :Project.language_profile."""
    from palace_mcp.extractors.foundation.profiles import resolve_profile

    driver = _make_driver_with_profile(None)
    (tmp_path / "Package.swift").write_text("// swift-tools-version:5.9")

    profile = await resolve_profile(driver, "tron-kit", repo_path=tmp_path)
    assert profile.name == "swift_kit"


@pytest.mark.asyncio
async def test_resolve_profile_pyproject_infers_python_service(tmp_path: Path) -> None:
    """pyproject.toml → python_service when no :Project.language_profile."""
    from palace_mcp.extractors.foundation.profiles import resolve_profile

    driver = _make_driver_with_profile(None)
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'")

    profile = await resolve_profile(driver, "gimle", repo_path=tmp_path)
    assert profile.name == "python_service"


@pytest.mark.asyncio
async def test_resolve_profile_unknown_raises(tmp_path: Path) -> None:
    """No language_profile + no recognized manifest → raises ValueError."""
    from palace_mcp.extractors.foundation.profiles import resolve_profile

    driver = _make_driver_with_profile(None)
    # empty tmp_path — no manifest files

    with pytest.raises(ValueError, match="unknown_language_profile"):
        await resolve_profile(driver, "no-manifest", repo_path=tmp_path)


@pytest.mark.asyncio
async def test_resolve_profile_invalid_profile_name_raises(tmp_path: Path) -> None:
    """Unknown language_profile value in Neo4j → raises ValueError."""
    from palace_mcp.extractors.foundation.profiles import resolve_profile

    driver = _make_driver_with_profile("ruby_gem")  # not in PROFILES

    with pytest.raises(ValueError, match="unknown_language_profile"):
        await resolve_profile(driver, "some-gem", repo_path=tmp_path)


# ---------------------------------------------------------------------------
# Task 2.1 RED — LanguageProfile + PROFILES dict
# ---------------------------------------------------------------------------


def test_swift_kit_profile_returns_audit_extractors() -> None:
    """PROFILES['swift_kit'].audit_extractors is non-empty frozenset."""
    from palace_mcp.extractors.foundation.profiles import PROFILES

    assert "swift_kit" in PROFILES
    profile = PROFILES["swift_kit"]
    assert isinstance(profile.audit_extractors, frozenset)
    assert len(profile.audit_extractors) > 0


def test_swift_kit_includes_expected_extractors() -> None:
    """swift_kit profile includes the core audit extractors listed in the spec."""
    from palace_mcp.extractors.foundation.profiles import PROFILES

    expected = {
        "arch_layer",
        "code_ownership",
        "coding_convention",
        "crypto_domain_model",
        "cross_module_contract",
        "cross_repo_version_skew",
        "dead_symbol_binary_surface",
        "dependency_surface",
        "error_handling_policy",
        "hotspot",
        "localization_accessibility",
        "public_api_surface",
        "reactive_dependency_tracer",
    }
    actual = PROFILES["swift_kit"].audit_extractors
    assert expected.issubset(actual), f"Missing: {expected - actual}"


def test_python_service_profile_exists() -> None:
    """PROFILES contains 'python_service'."""
    from palace_mcp.extractors.foundation.profiles import PROFILES

    assert "python_service" in PROFILES
    assert len(PROFILES["python_service"].audit_extractors) > 0


def test_android_kit_profile_exists() -> None:
    """PROFILES contains 'android_kit'."""
    from palace_mcp.extractors.foundation.profiles import PROFILES

    assert "android_kit" in PROFILES


def test_profile_name_matches_key() -> None:
    """Each PROFILES[k].name == k."""
    from palace_mcp.extractors.foundation.profiles import PROFILES

    for k, p in PROFILES.items():
        assert p.name == k, f"PROFILES[{k!r}].name = {p.name!r}"


def test_swift_kit_includes_new_extractors() -> None:
    """Regression: testability_di + reactive_dependency_tracer must stay in swift_kit profile.

    Both were added via GIM-284 (PR #163). This test guards against removal.
    Already satisfied on develop @ 0ac5e02 — kept as regression guard (W1).
    """
    from palace_mcp.extractors.foundation.profiles import PROFILES

    actual = PROFILES["swift_kit"].audit_extractors
    assert "testability_di" in actual, "testability_di missing from swift_kit profile"
    assert "reactive_dependency_tracer" in actual, (
        "reactive_dependency_tracer missing from swift_kit profile"
    )


def test_audit_extractors_is_frozen() -> None:
    """audit_extractors is immutable (frozenset)."""
    from palace_mcp.extractors.foundation.profiles import PROFILES

    profile = PROFILES["swift_kit"]
    with pytest.raises((TypeError, AttributeError)):
        profile.audit_extractors.add("new_extractor")  # type: ignore[union-attr]
