"""F1B spike tests: sourcekit-lsp callHierarchy end-to-end on UW iOS.

Acceptance criteria (GIM-1166):
- BalanceData query returns >= 30 references
- End-to-end latency < 10s (warm run)
- Runs against actual UW iOS project on iMac (not a mock)

Run with:
    pytest tests/lsp/test_call_hierarchy_spike.py -v -s --timeout=120

Marked @pytest.mark.slow — excluded from CI; run manually on iMac.

Index requirements
------------------
On the iMac (full Xcode), build the UW iOS project first:
    xcodebuild -workspace UnstoppableWallet.xcworkspace -scheme UnstoppableWallet build
    export PALACE_SOURCEKIT_INDEX_STORE_PATH=~/Library/Developer/Xcode/DerivedData/UnstoppableWallet-.../Index.noindex/DataStore

On developer machines (CLT only, no Xcode), use the synthetic fixture:
    make tests/lsp/fixtures/balance-spike  (or run _build_synthetic_fixture())
    UW_IOS_PATH=/tmp/balance-spike SOURCEKIT_INDEX_STORE_PATH=/tmp/balance-spike-index pytest ...
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

import pytest

# UW iOS project on the iMac
_UW_IOS_PATH = os.environ.get(
    "UW_IOS_PATH",
    "/Users/Shared/Ios/unstoppable-wallet-ios",
)
_WORKSPACE_ROOT = str(Path(_UW_IOS_PATH) / "UnstoppableWallet")
_BALANCE_DATA_FILE = str(
    Path(_UW_IOS_PATH)
    / "UnstoppableWallet/UnstoppableWallet/Models/BalanceData.swift"
)
def _resolve_binary() -> str:
    """Return SOURCEKIT_LSP_BINARY env var, or auto-detect best available binary."""
    from palace_mcp.lsp.call_hierarchy import detect_sourcekit_lsp_binary

    return os.environ.get("SOURCEKIT_LSP_BINARY") or detect_sourcekit_lsp_binary()


_SOURCEKIT_LSP_BINARY = _resolve_binary()
_SOURCEKIT_INDEX_STORE_PATH = os.environ.get("SOURCEKIT_INDEX_STORE_PATH", "")

# Synthetic fixture paths (CLT-only machines without Xcode)
_SYNTHETIC_PKG = "/tmp/balance-spike"
_SYNTHETIC_INDEX = "/tmp/balance-spike-index"
_SYNTHETIC_BALANCE_DATA = f"{_SYNTHETIC_PKG}/Sources/BalanceSpike/BalanceData.swift"
_SYNTHETIC_WORKSPACE = f"{_SYNTHETIC_PKG}/Sources/BalanceSpike"


def _skip_if_no_workspace() -> None:
    if not Path(_BALANCE_DATA_FILE).exists():
        pytest.skip(
            f"UW iOS source not found at {_BALANCE_DATA_FILE}. "
            "Set UW_IOS_PATH to the project root (e.g. ~/Ios/unstoppable-wallet-ios)."
        )
    if not Path(_SOURCEKIT_LSP_BINARY).exists():
        pytest.skip(f"sourcekit-lsp not found at {_SOURCEKIT_LSP_BINARY}")


def _ensure_synthetic_fixture() -> bool:
    """Build the synthetic BalanceData fixture if not already built.

    Returns True if the fixture is ready (built or already exists).
    This provides a fast index (< 5s) for CLT-only machines without Xcode.
    """
    balance_data = Path(_SYNTHETIC_BALANCE_DATA)
    index_dir = Path(_SYNTHETIC_INDEX)

    if not balance_data.exists():
        return False  # Fixture sources not found

    # Check if index already has units
    units_dir = index_dir / "v5" / "units"
    if units_dir.exists() and any(units_dir.iterdir()):
        return True  # Already built

    # Build the index via swiftc
    sdk = subprocess.check_output(
        ["xcrun", "--show-sdk-path"], text=True
    ).strip()
    swift_files = list(Path(_SYNTHETIC_PKG + "/Sources/BalanceSpike").glob("*.swift"))
    if not swift_files:
        return False

    result = subprocess.run(
        [
            "swiftc",
            *[str(f) for f in swift_files],
            "-module-name", "BalanceSpike",
            "-index-store-path", _SYNTHETIC_INDEX,
            "-parse-as-library",
            "-emit-module",
            "-emit-module-path", f"{_SYNTHETIC_INDEX}/BalanceSpike.swiftmodule",
            "-sdk", sdk,
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    return result.returncode == 0


def _skip_if_no_synthetic() -> None:
    if not Path(_SOURCEKIT_LSP_BINARY).exists():
        pytest.skip(f"sourcekit-lsp not found at {_SOURCEKIT_LSP_BINARY}")
    if not Path(_SYNTHETIC_BALANCE_DATA).exists():
        pytest.skip(f"Synthetic fixture not found at {_SYNTHETIC_BALANCE_DATA}")
    ok = _ensure_synthetic_fixture()
    if not ok:
        pytest.skip("Synthetic fixture index build failed")


# ---------------------------------------------------------------------------
# Unit tests (no LSP subprocess)
# ---------------------------------------------------------------------------


class TestLspClientProtocol:
    """Tests for Content-Length framing helpers."""

    def test_path_to_uri(self) -> None:
        from palace_mcp.lsp.client import _path_to_uri

        assert _path_to_uri("/foo/bar") == "file:///foo/bar"
        assert _path_to_uri("/foo/bar/") == "file:///foo/bar"

    def test_parse_content_length(self) -> None:
        from palace_mcp.lsp.client import _parse_content_length

        header = b"Content-Length: 42\r\nContent-Type: application/json\r\n\r\n"
        assert _parse_content_length(header) == 42

    def test_parse_content_length_missing(self) -> None:
        from palace_mcp.lsp.client import _parse_content_length

        assert _parse_content_length(b"Content-Type: text/plain\r\n\r\n") is None

    def test_find_symbol_column(self) -> None:
        from palace_mcp.lsp.call_hierarchy import _find_symbol_column

        _skip_if_no_workspace()
        # BalanceData.swift line 3 (0-indexed line 2): "struct BalanceData: Hashable {"
        col = _find_symbol_column(_BALANCE_DATA_FILE, 2, "BalanceData")
        assert col == 7  # "struct " = 7 chars


class TestWorkspaceInference:
    """Tests for workspace root inference."""

    def test_infers_xcodeproj_parent(self) -> None:
        from palace_mcp.lsp.tool import _infer_workspace_root

        _skip_if_no_workspace()
        root = _infer_workspace_root(_BALANCE_DATA_FILE)
        assert root is not None
        assert Path(root).exists()

    def test_filesystem_fallback(self) -> None:
        from palace_mcp.lsp.tool import _filesystem_fallback

        _skip_if_no_workspace()
        file_path, line = _filesystem_fallback("BalanceData", _WORKSPACE_ROOT)
        assert file_path is not None
        assert "BalanceData.swift" in file_path
        assert line >= 1


# ---------------------------------------------------------------------------
# Integration spike test (requires live sourcekit-lsp + UW iOS project)
# ---------------------------------------------------------------------------


@pytest.mark.slow
@pytest.mark.asyncio
async def test_balance_data_call_hierarchy_spike() -> None:
    """Spike: BalanceData returns >= 30 incoming callers via sourcekit-lsp.

    This is the primary acceptance criterion for GIM-1166 F1B spike.
    Warm run should complete in < 10s.

    On the iMac (with Xcode + pre-built index):
        export SOURCEKIT_INDEX_STORE_PATH=~/Library/Developer/Xcode/DerivedData/UnstoppableWallet-.../Index.noindex/DataStore
        pytest tests/lsp/test_call_hierarchy_spike.py::test_balance_data_call_hierarchy_spike -v -s

    On CLT-only machines: test_balance_data_call_hierarchy_spike_synthetic covers the concept.
    """
    _skip_if_no_workspace()

    from palace_mcp.lsp.call_hierarchy import resolve_call_hierarchy

    # Use pre-built index store if available (speeds up warm run dramatically)
    index_store = _SOURCEKIT_INDEX_STORE_PATH or None

    result = await resolve_call_hierarchy(
        symbol_name="BalanceData",
        file_path=_BALANCE_DATA_FILE,
        line_start=3,  # "struct BalanceData: Hashable {" is line 3
        workspace_root=_WORKSPACE_ROOT,
        binary=_SOURCEKIT_LSP_BINARY,
        index_store_path=index_store,
        max_results=200,
    )

    _print_spike_results(result)
    payload = result.to_dict()

    # Acceptance criteria
    assert payload["incoming_call_count"] >= 30, (
        f"Expected >= 30 callers, got {payload['incoming_call_count']}. "
        "sourcekit-lsp needs a warm index — build the project first:\n"
        "  xcodebuild -workspace UnstoppableWallet.xcworkspace -scheme UnstoppableWallet build\n"
        "Then set SOURCEKIT_INDEX_STORE_PATH to the DerivedData index store."
    )
    assert result.latency_s < 60.0, f"Total latency {result.latency_s:.1f}s exceeds hard cap"
    if not result.cold_start:
        assert result.latency_s < 10.0, f"Warm latency {result.latency_s:.2f}s exceeds 10s SLO"


@pytest.mark.slow
@pytest.mark.asyncio
async def test_balance_data_call_hierarchy_spike_synthetic() -> None:
    """Spike (CLT-only): BalanceData callHierarchy with synthetic pre-built index.

    Proves the LSP call hierarchy architecture end-to-end on this machine
    without requiring Xcode or a full iOS build.

    The synthetic fixture has 35 Adapter files that all use BalanceData,
    pre-compiled via swiftc -index-store-path.
    """
    _skip_if_no_synthetic()

    from palace_mcp.lsp.call_hierarchy import resolve_call_hierarchy

    result = await resolve_call_hierarchy(
        symbol_name="BalanceData",
        file_path=_SYNTHETIC_BALANCE_DATA,
        line_start=1,  # "public struct BalanceData: Hashable {" is line 1
        workspace_root=_SYNTHETIC_WORKSPACE,
        binary=_SOURCEKIT_LSP_BINARY,
        index_store_path=_SYNTHETIC_INDEX,
        max_results=200,
    )

    _print_spike_results(result)
    payload = result.to_dict()

    print(f"\nProves architecture: {payload['incoming_call_count']} callers found")
    assert payload["incoming_call_count"] >= 30, (
        f"Expected >= 30 callers from synthetic fixture, got {payload['incoming_call_count']}"
    )
    assert result.latency_s < 10.0, (
        f"Synthetic fixture should be fast; got {result.latency_s:.2f}s"
    )


@pytest.mark.slow
@pytest.mark.asyncio
async def test_lsp_client_initializes() -> None:
    """Verify sourcekit-lsp starts and initializes without error."""
    _skip_if_no_workspace()

    from palace_mcp.lsp.client import LspClient

    async with LspClient(
        binary=_SOURCEKIT_LSP_BINARY,
        workspace_root=_WORKSPACE_ROOT,
    ) as client:
        assert client._proc is not None
        assert client._proc.returncode is None


def _print_spike_results(result: Any) -> None:
    payload = result.to_dict()
    print("\n--- Spike Results ---")
    print(f"Symbol: {payload['symbol_name']}")
    print(f"Source: {payload['source_file']}")
    print(f"Incoming callers: {payload['incoming_call_count']}")
    print(f"Latency: {payload['latency_s']:.2f}s")
    print(f"Cold start: {result.cold_start}")
    if result.incoming_calls:
        print("Sample callers:")
        for call in result.incoming_calls[:5]:
            caller = call.get("from", {})
            print(f"  - {caller.get('name')} in {caller.get('uri', '').split('/')[-1]}")
