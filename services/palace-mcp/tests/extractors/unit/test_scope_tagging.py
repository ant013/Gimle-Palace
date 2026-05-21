from __future__ import annotations

import pytest

from palace_mcp.extractors.foundation.scope_tagging import ScopeTaggedWriter


class _FakeTx:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def run(self, query: str, **kwargs: object) -> None:
        self.calls.append((query, dict(kwargs)))


def test_normalize_props_requires_group_id() -> None:
    writer = ScopeTaggedWriter()

    with pytest.raises(ValueError, match="group_id is required"):
        writer.normalize_props({"project_id": "project/demo"})


@pytest.mark.asyncio
async def test_write_node_rejects_unknown_label() -> None:
    writer = ScopeTaggedWriter(default_group_id="project/demo")

    with pytest.raises(ValueError, match="not allowed"):
        await writer.write_node(_FakeTx(), "UnknownLabel", {})


def test_normalize_props_dual_writes_path_alias() -> None:
    writer = ScopeTaggedWriter(default_group_id="project/demo")

    props = writer.normalize_props({"project_id": "project/demo", "path": "src/a.py"})

    assert props["group_id"] == "project/demo"
    assert props["path"] == "src/a.py"
    assert props["file_path"] == "src/a.py"


def test_normalize_props_removes_legacy_path_when_requested() -> None:
    writer = ScopeTaggedWriter(
        default_group_id="project/demo",
        remove_legacy_path=True,
    )

    props = writer.normalize_props(
        {"project_id": "project/demo", "file_path": "src/a.py"}
    )

    assert props["group_id"] == "project/demo"
    assert props["file_path"] == "src/a.py"
    assert "path" not in props
