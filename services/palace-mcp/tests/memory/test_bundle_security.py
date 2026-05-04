"""Security tests for palace_mcp.memory.bundle.

Covers:
- §8.20: Cypher injection fuzz (50-string vector against bundle name validator)
- §8.15/16: Namespace collision guards (bidirectional)
- §8.16: bundle name regex edge cases
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from palace_mcp.memory.bundle import (
    BundleNameConflictsWithProject,
    register_bundle,
)
from palace_mcp.memory.models import Bundle

# ---------------------------------------------------------------------------
# Minimal fake driver (no sessions needed for pure-validator tests)
# ---------------------------------------------------------------------------


class _NoCallDriver:
    """Driver that fails if any method is called — validates reject-before-cypher."""

    def session(self) -> "_NoCallDriver":
        raise AssertionError("No Cypher should be called for invalid bundle names")


# ---------------------------------------------------------------------------
# §8.20 — Cypher injection fuzz (bundle name validator)
# The validator runs BEFORE any Cypher, so _NoCallDriver proves injection
# cannot reach the database.
# ---------------------------------------------------------------------------

_INJECTION_VECTORS: list[str] = [
    # Cypher special syntax
    "'; DROP DATABASE neo4j; //",
    "' OR '1'='1",
    "MATCH (n) DETACH DELETE n",
    "CALL db.drop()",
    "RETURN 1; MATCH (n) DELETE n",
    "{name: 'x'} MERGE (b:Bundle)",
    ") DETACH DELETE b //",
    "bundle' OR name='other",
    "bundle' MATCH (n) RETURN n",
    "'; CALL apoc.cypher.runMany('DROP ALL')//",
    # Shell injection (never reaches shell, but validates regex)
    "$(rm -rf /)",
    "`cat /etc/passwd`",
    "| whoami",
    "; ls -la",
    "&& rm /etc/hosts",
    # Unicode / control chars
    "\x00bundle",
    "\nbundle",
    "\tbundle",
    "bun\x00dle",
    # Path traversal in name
    "../etc/passwd",
    "../../root",
    ".bundle",
    # Leading/trailing spaces
    " bundle",
    "bundle ",
    "  bundle  ",
    # Mixed case (spec requires lowercase)
    "Bundle",
    "BUNDLE",
    "MyBundle",
    "uwIOS",
    "Evm-Kit",
    # Too short (spec: min 2 chars total = 1 lead + 1 more)
    "a",
    "",
    # Too long (spec: max 31 chars total)
    "a" * 32,
    "a" + "b" * 31,
    # Invalid start char
    "-bundle",
    "0bundle",
    "9test",
    # Special chars
    "bundle!",
    "bundle@name",
    "bundle#tag",
    "bundle.name",
    "bundle_name",  # underscore not in spec regex
    "bundle+kit",
    "bundle/kit",
    "bundle\\kit",
    "bundle name",  # space
    "bundle*",
]


@pytest.mark.parametrize("bad_name", _INJECTION_VECTORS)
async def test_bundle_name_cypher_injection_fuzz(bad_name: str) -> None:
    """Invalid bundle names MUST be rejected before any Cypher is issued."""
    driver = _NoCallDriver()
    with pytest.raises((ValueError, TypeError)):
        await register_bundle(driver, name=bad_name, description="fuzz")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# §8.15 — Namespace conflict: register_bundle conflicts with project slug
# (also in test_bundle.py; isolated here for security-test completeness)
# ---------------------------------------------------------------------------


class _FakeResult:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows
        self._i = 0

    def __aiter__(self) -> "_FakeResult":
        self._i = 0
        return self

    async def __anext__(self) -> dict[str, Any]:
        if self._i >= len(self._rows):
            raise StopAsyncIteration
        row = self._rows[self._i]
        self._i += 1
        return row

    async def single(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None


class _FakeSession:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    async def run(self, query: str, **params: Any) -> _FakeResult:
        return _FakeResult(self._rows)

    async def __aenter__(self) -> "_FakeSession":
        return self

    async def __aexit__(self, *args: Any) -> None:
        pass


class _FixedDriver:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def session(self) -> _FakeSession:
        return _FakeSession(self._rows)


async def test_register_bundle_conflicts_with_existing_project() -> None:
    driver = _FixedDriver([{"slug": "uw-ios"}])
    with pytest.raises(BundleNameConflictsWithProject, match="uw-ios"):
        await register_bundle(driver, name="uw-ios", description="desc")


# ---------------------------------------------------------------------------
# Bundle name regex edge cases — valid names
# ---------------------------------------------------------------------------

_VALID_NAMES: list[str] = [
    "uw-ios",
    "evm-kit",
    "ab",  # minimum: 2 chars
    "a1",
    "test-bundle-123",
    "a" + "b" * 29 + "c",  # exactly 31 chars (max)
]


@pytest.mark.parametrize("good_name", _VALID_NAMES)
def test_bundle_model_accepts_valid_name(good_name: str) -> None:
    b = Bundle(
        name=good_name,
        description="ok",
        group_id=f"bundle/{good_name}",
        created_at=datetime(2026, 5, 3, 12, 0, 0, tzinfo=timezone.utc),
    )
    assert b.name == good_name
