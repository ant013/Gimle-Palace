"""callHierarchy resolution via sourcekit-lsp subprocess.

Phase 2 spike: bypasses HNSW vector ranking by using exact LSP call-graph
navigation. Given a symbol name, resolves it to a file+position via the
graph (or filesystem fallback), then queries sourcekit-lsp for incomingCalls.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from palace_mcp.lsp.client import LspClient, LspError, _path_to_uri

logger = logging.getLogger(__name__)

_DEFAULT_BINARY = "/usr/bin/sourcekit-lsp"

# Candidate binary paths tried in order when auto-detecting.
# The macOS SDK stub at /usr/bin/sourcekit-lsp lacks -index-store-path support
# (Xcode 26+). Prefer swiftly-managed or xcrun-resolved binaries.
_BINARY_SEARCH_ORDER = [
    Path.home() / ".swiftly" / "bin" / "sourcekit-lsp",
    Path("/usr/local/bin/sourcekit-lsp"),
]


def detect_sourcekit_lsp_binary() -> str:
    """Return the best available sourcekit-lsp binary path.

    Preference order:
    1. ~/.swiftly/bin/sourcekit-lsp (swiftly-managed, supports -index-store-path)
    2. xcrun --find sourcekit-lsp if it is NOT the /usr/bin stub
    3. /usr/bin/sourcekit-lsp (fallback; may lack flag support)

    Caller should override via PALACE_SOURCEKIT_LSP_BINARY env/config when
    this auto-detection doesn't find the right binary.
    """
    for candidate in _BINARY_SEARCH_ORDER:
        if candidate.exists():
            return str(candidate)

    # Try xcrun — prefer it if it resolves to something other than the CLT stub
    xcrun_result = shutil.which("xcrun")
    if xcrun_result:
        try:
            path = subprocess.check_output(
                ["xcrun", "--find", "sourcekit-lsp"],
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip()
            if path and path != "/usr/bin/sourcekit-lsp":
                return path
        except subprocess.SubprocessError:
            pass

    return _DEFAULT_BINARY
_DEFAULT_TIMEOUT = 60.0
_POLL_INTERVAL = 1.0
_POLL_MAX_ATTEMPTS = 30  # 30s total polling for index warming


class CallHierarchyResult:
    """Structured result from a callHierarchy query."""

    def __init__(
        self,
        symbol_name: str,
        file_uri: str,
        incoming_calls: list[dict[str, Any]],
        latency_s: float,
        cold_start: bool,
    ) -> None:
        self.symbol_name = symbol_name
        self.file_uri = file_uri
        self.incoming_calls = incoming_calls
        self.latency_s = latency_s
        self.cold_start = cold_start

    def to_dict(self) -> dict[str, Any]:
        callers = []
        for call in self.incoming_calls:
            caller = call.get("from", {})
            from_ranges = call.get("fromRanges", [])
            callers.append(
                {
                    "caller_name": caller.get("name"),
                    "caller_kind": caller.get("kind"),
                    "caller_file": caller.get("uri", "").replace("file://", ""),
                    "caller_line": caller.get("selectionRange", {}).get("start", {}).get("line"),
                    "call_ranges": from_ranges,
                }
            )
        return {
            "symbol_name": self.symbol_name,
            "source_file": self.file_uri.replace("file://", ""),
            "incoming_call_count": len(callers),
            "callers": callers,
            "latency_s": round(self.latency_s, 3),
            "cold_start": self.cold_start,
        }


async def resolve_call_hierarchy(
    *,
    symbol_name: str,
    file_path: str,
    line_start: int,
    workspace_root: str,
    binary: str | None = None,
    scratch_path: str | None = None,
    index_store_path: str | None = None,
    index_db_path: str | None = None,
    timeout_s: float = _DEFAULT_TIMEOUT,
    max_results: int = 200,
) -> CallHierarchyResult:
    """Full call-hierarchy resolution for one symbol.

    Args:
        symbol_name: Human-readable name (for result labelling).
        file_path: Absolute path to the Swift file defining the symbol.
        line_start: 1-based line number of the symbol definition.
        workspace_root: Absolute path to the workspace root passed to sourcekit-lsp.
        binary: Path to sourcekit-lsp binary.
        scratch_path: Optional --scratch-path for sourcekit-lsp build cache.
        index_store_path: Optional pre-built index store path (-index-store-path).
            Bypasses the build system; use when project was pre-indexed via
            ``swiftc -index-store-path`` or Xcode build.
        index_db_path: Optional index database path (-index-db-path).
        timeout_s: Per-LSP-request timeout in seconds.
        max_results: Maximum number of incoming call entries to return.
    """
    t0 = time.perf_counter()
    file_uri = _path_to_uri(file_path)

    # LSP positions are 0-based
    lsp_line = max(0, line_start - 1)

    # Determine character offset: position within "struct/class SymbolName"
    # We read the line to find the exact column.
    lsp_char = _find_symbol_column(file_path, lsp_line, symbol_name)

    resolved_binary = binary or detect_sourcekit_lsp_binary()
    file_content = Path(file_path).read_text(encoding="utf-8")

    async with LspClient(
        binary=resolved_binary,
        workspace_root=workspace_root,
        scratch_path=scratch_path,
        index_store_path=index_store_path,
        index_db_path=index_db_path,
    ) as client:
        await client.did_open(file_uri, file_content)

        # Poll prepareCallHierarchy until we get a non-empty result or timeout
        items: list[dict[str, Any]] = []
        cold_start = False
        for attempt in range(_POLL_MAX_ATTEMPTS):
            try:
                items = await client.prepare_call_hierarchy(file_uri, lsp_line, lsp_char)
            except LspError as exc:
                logger.debug("prepareCallHierarchy attempt %d error: %s", attempt, exc)
                items = []

            if items:
                break
            if attempt == 0:
                cold_start = True
            logger.debug(
                "prepareCallHierarchy attempt %d: empty, waiting %ss",
                attempt,
                _POLL_INTERVAL,
            )
            await asyncio.sleep(_POLL_INTERVAL)
        else:
            logger.warning(
                "prepareCallHierarchy returned empty after %d attempts for %s",
                _POLL_MAX_ATTEMPTS,
                symbol_name,
            )

        all_calls: list[dict[str, Any]] = []
        for item in items:
            try:
                calls = await client.incoming_calls(item)
                all_calls.extend(calls)
                if len(all_calls) >= max_results:
                    all_calls = all_calls[:max_results]
                    break
            except LspError as exc:
                logger.warning("incomingCalls error for %s: %s", symbol_name, exc)

    latency = time.perf_counter() - t0
    return CallHierarchyResult(
        symbol_name=symbol_name,
        file_uri=file_uri,
        incoming_calls=all_calls,
        latency_s=latency,
        cold_start=cold_start,
    )


def _find_symbol_column(file_path: str, lsp_line: int, symbol_name: str) -> int:
    """Return the 0-based character offset of symbol_name on lsp_line."""
    try:
        with open(file_path, encoding="utf-8") as f:
            lines = f.readlines()
        if lsp_line < len(lines):
            line_text = lines[lsp_line]
            idx = line_text.find(symbol_name)
            if idx >= 0:
                return idx
    except OSError:
        pass
    return 7  # fallback: "struct " prefix is 7 chars
