from __future__ import annotations

from collections.abc import Iterable
from unittest.mock import AsyncMock, MagicMock

import pytest

from palace_mcp.code.native_detect_changes import FALLBACK_TO_CM
from palace_mcp.code.native_get_architecture import native_get_architecture


class _RowsResult:
    def __init__(self, rows: Iterable[dict[str, object]]) -> None:
        self._rows = list(rows)

    async def data(self) -> list[dict[str, object]]:
        return list(self._rows)


def _mock_driver(
    *row_sets: list[dict[str, object]], error: Exception | None = None
) -> object:
    session = AsyncMock()
    if error is not None:
        session.run = AsyncMock(side_effect=error)
    else:
        session.run = AsyncMock(side_effect=[_RowsResult(rows) for rows in row_sets])
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    driver = MagicMock()
    driver.session = MagicMock(return_value=session)
    return driver


@pytest.mark.asyncio
async def test_get_architecture_returns_native_sections(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    driver = _mock_driver(
        [{"language": "swift"}, {"language": "python"}],
        [
            {
                "slug": "WalletCore",
                "name": "WalletCore",
                "kind": "swift_target",
                "manifest_path": "Package.swift",
                "source_root": "Sources/WalletCore",
            }
        ],
        [{"module_name": "WalletUI"}],
        [
            {
                "purl": "pkg:github/acme/wallet@1.2.3",
                "ecosystem": "github",
                "resolved_version": "1.2.3",
                "scope": "main",
                "declared_in": "Package.swift",
                "declared_version_constraint": "^1.2.0",
            }
        ],
        [
            {
                "qualified_name": "WalletApp.App.main()",
                "file_path": "App.swift",
                "module_name": "WalletApp",
                "kind": "function",
            }
        ],
        [{"name": "ui", "rule_source": ".palace/architecture-rules.yaml"}],
        [{"type": "DEPENDS_ON"}, {"type": "CALLS"}],
    )
    monkeypatch.setattr("palace_mcp.mcp_server.get_driver", lambda: driver)

    result = await native_get_architecture(project="gimle")

    assert result["project"] == "gimle"
    assert result["languages"] == ["python", "swift"]
    assert [package["name"] for package in result["packages"]] == [
        "WalletCore",
        "WalletUI",
    ]
    assert result["dependencies"] == [
        {
            "purl": "pkg:github/acme/wallet@1.2.3",
            "ecosystem": "github",
            "resolved_version": "1.2.3",
            "scope": "main",
            "declared_in": "Package.swift",
            "declared_version_constraint": "^1.2.0",
        }
    ]
    assert result["entry_points"] == [
        {
            "qualified_name": "WalletApp.App.main()",
            "file_path": "App.swift",
            "module_name": "WalletApp",
            "kind": "function",
        }
    ]
    assert result["routes"] == []
    assert "Phase 2" in result["route_note"]
    assert result["layers"] == [
        {"name": "ui", "rule_source": ".palace/architecture-rules.yaml"}
    ]
    assert result["edge_types"] == [{"type": "CALLS"}, {"type": "DEPENDS_ON"}]
    assert result["hotspots"] == []
    assert result["boundaries"] == []
    assert result["clusters"] == []


@pytest.mark.asyncio
async def test_get_architecture_returns_empty_lists_for_missing_optional_sections(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "palace_mcp.mcp_server.get_driver",
        lambda: _mock_driver([], [], [], [], [], [], []),
    )

    result = await native_get_architecture(project="gimle")

    assert result == {
        "project": "gimle",
        "languages": [],
        "packages": [],
        "dependencies": [],
        "entry_points": [],
        "routes": [],
        "route_note": (
            "routes require Phase 2 extractor support; native get_architecture returns []"
        ),
        "hotspots": [],
        "boundaries": [],
        "layers": [],
        "clusters": [],
        "edge_types": [],
    }


@pytest.mark.asyncio
async def test_get_architecture_falls_back_to_cm_without_project() -> None:
    result = await native_get_architecture()

    assert result is FALLBACK_TO_CM
