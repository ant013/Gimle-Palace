from __future__ import annotations

from palace_mcp.code.list_passthrough_projects import (
    build_passthrough_project_listing,
)
from palace_mcp.code_router import _PASSTHROUGH_TOOLS


def test_build_passthrough_project_listing_returns_current_tool_split() -> None:
    assert build_passthrough_project_listing(_PASSTHROUGH_TOOLS) == {
        "native": [
            "palace.code.search_graph",
            "palace.code.trace_call_path",
            "palace.code.query_graph",
            "palace.code.detect_changes",
            "palace.code.get_architecture",
            "palace.code.get_code_snippet",
        ],
        "cm_only": ["palace.code.search_code"],
    }
