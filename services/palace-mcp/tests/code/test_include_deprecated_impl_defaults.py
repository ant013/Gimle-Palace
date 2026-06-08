"""Pin `include_deprecated` defaults on user-facing `_impl` functions.

Slice 4b of GIM-1491 flipped MCP-layer defaults from True→False so deprecated
symbols stay hidden by default. OpusArchitectReviewer flagged a follow-up:
the underlying `_impl` functions in `code/` still defaulted to True, creating
a silent inconsistency for any caller that imports them directly (bypassing
the MCP tool layer).

This contract test fails if any of the four `_impl` defaults regresses,
preserving the single-source-of-truth across the MCP-tool and library APIs.
"""

from __future__ import annotations

import inspect

import pytest

from palace_mcp.code.find_hotspots import find_hotspots
from palace_mcp.code.find_owners import find_owners
from palace_mcp.code.find_semantic import semantic_search
from palace_mcp.code.list_functions import list_functions


@pytest.mark.parametrize(
    "func",
    [find_hotspots, find_owners, list_functions, semantic_search],
    ids=lambda f: f.__name__,
)
def test_impl_include_deprecated_default_is_false(func) -> None:
    sig = inspect.signature(func)
    assert "include_deprecated" in sig.parameters, (
        f"{func.__name__} no longer exposes include_deprecated — review the "
        "MCP-layer contract before merging"
    )
    default = sig.parameters["include_deprecated"].default
    assert default is False, (
        f"{func.__name__} default include_deprecated={default!r}; expected "
        "False to match MCP-layer defaults flipped in PR #396 (GIM-1491 "
        "Slice 4b). See OpusArchitectReviewer follow-up on GIM-1518."
    )
