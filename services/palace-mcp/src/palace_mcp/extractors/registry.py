"""Extractor registry — module-level dict of registered extractors.

Production registration is import-time (EXTRACTORS dict literal). Runtime
register() is test-only (for fixtures). Single-event-loop semantics mean
no thread-safety needed.
"""

from __future__ import annotations

from palace_mcp.extractors.base import BaseExtractor
from palace_mcp.extractors.code_ownership.extractor import CodeOwnershipExtractor
from palace_mcp.extractors.codebase_memory_bridge import CodebaseMemoryBridgeExtractor
from palace_mcp.extractors.cross_repo_version_skew.extractor import (
    CrossRepoVersionSkewExtractor,
)
from palace_mcp.extractors.cross_module_contract import CrossModuleContractExtractor
from palace_mcp.extractors.dead_symbol_binary_surface.extractor import (
    DeadSymbolBinarySurfaceExtractor,
)
from palace_mcp.extractors.dependency_surface.extractor import (
    DependencySurfaceExtractor,
)
from palace_mcp.extractors.git_history.extractor import GitHistoryExtractor
from palace_mcp.extractors.heartbeat import HeartbeatExtractor
from palace_mcp.extractors.hotspot.extractor import HotspotExtractor
from palace_mcp.extractors.public_api_surface import PublicApiSurfaceExtractor
from palace_mcp.extractors.reactive_dependency_tracer.extractor import (
    ReactiveDependencyTracerExtractor,
)
from palace_mcp.extractors.symbol_index_clang import SymbolIndexClang
from palace_mcp.extractors.symbol_index_java import SymbolIndexJava
from palace_mcp.extractors.symbol_index_python import SymbolIndexPython
from palace_mcp.extractors.symbol_index_solidity import SymbolIndexSolidity
from palace_mcp.extractors.symbol_index_swift import SymbolIndexSwift
from palace_mcp.extractors.symbol_index_typescript import SymbolIndexTypeScript

EXTRACTORS: dict[str, BaseExtractor] = {
    "heartbeat": HeartbeatExtractor(),
    "code_ownership": CodeOwnershipExtractor(),
    "codebase_memory_bridge": CodebaseMemoryBridgeExtractor(),
    "cross_module_contract": CrossModuleContractExtractor(),
    "dead_symbol_binary_surface": DeadSymbolBinarySurfaceExtractor(),
    "public_api_surface": PublicApiSurfaceExtractor(),
    "symbol_index_python": SymbolIndexPython(),
    "symbol_index_typescript": SymbolIndexTypeScript(),
    "symbol_index_java": SymbolIndexJava(),
    "symbol_index_solidity": SymbolIndexSolidity(),
    "symbol_index_swift": SymbolIndexSwift(),
    "symbol_index_clang": SymbolIndexClang(),
    "dependency_surface": DependencySurfaceExtractor(),
    "reactive_dependency_tracer": ReactiveDependencyTracerExtractor(),
    "git_history": GitHistoryExtractor(),
    "hotspot": HotspotExtractor(),
    "cross_repo_version_skew": CrossRepoVersionSkewExtractor(),
}


def register(extractor: BaseExtractor) -> None:
    """Add an extractor to the registry.

    Production use: module-level (import-time). Test use: in fixture.
    Raises ValueError if name already registered.
    """
    if extractor.name in EXTRACTORS:
        raise ValueError(f"extractor already registered: {extractor.name!r}")
    EXTRACTORS[extractor.name] = extractor


def get(name: str) -> BaseExtractor | None:
    """Look up extractor by name. Returns None if not registered."""
    return EXTRACTORS.get(name)


def list_all() -> list[BaseExtractor]:
    """All registered extractors, in insertion order."""
    return list(EXTRACTORS.values())
