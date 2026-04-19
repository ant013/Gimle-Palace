"""Tests for memory.projects.validate_slug — unified slug format check.

Spec §5.1. Single source of truth for slug format across the graph
(register_project) and git (path_resolver) layers.
"""

from __future__ import annotations

import pytest

from palace_mcp.memory.project_tools import register_project
from palace_mcp.memory.projects import InvalidSlug, validate_slug


@pytest.mark.parametrize(
    "slug",
    ["gimle", "medic", "g123", "g-mle", "a", "a-b-c", "0prefix", "x" * 63],
)
def test_valid_slugs_accepted(slug: str) -> None:
    validate_slug(slug)  # does not raise


@pytest.mark.parametrize(
    "slug,reason",
    [
        ("", "empty"),
        ("A", "uppercase"),
        ("Gimle", "uppercase first"),
        ("gim LE", "space"),
        ("gimle/sub", "slash"),
        ("../etc", "traversal"),
        ("-prefix", "dash prefix"),
        ("gimle.", "dot"),
        ("gimle_us", "underscore"),
        ("x" * 64, "too long"),
        ("gim\nle", "newline"),
        ("gim\x00le", "nul"),
    ],
)
def test_invalid_slugs_rejected(slug: str, reason: str) -> None:
    with pytest.raises(InvalidSlug):
        validate_slug(slug)


@pytest.mark.asyncio
async def test_register_project_rejects_invalid_slug() -> None:
    from unittest.mock import AsyncMock

    driver = AsyncMock()
    with pytest.raises(InvalidSlug):
        await register_project(driver, slug="../etc", name="hack", tags=[])
    # driver.session() must never have been called — rejection pre-Cypher.
    driver.session.assert_not_called()
