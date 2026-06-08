"""Step 1 + 1b: entry seed identification."""

from __future__ import annotations

from palace_mcp.extractors.dead_code.models import SymbolGraph, SymbolNode


def identify_public_seeds(graph: SymbolGraph) -> frozenset[str]:
    """Step 1 — public/open entry points that are inherently alive.

    Includes: public/open symbols, @main / ApplicationDelegate entry points,
    symbols from test/app targets, and .swiftinterface-exported symbols.
    """
    seeds: set[str] = set()
    for qn, sym in graph.symbols.items():
        if sym.is_public or sym.is_open or sym.is_main_entry:
            seeds.add(qn)
    return frozenset(seeds)


def identify_dynamic_dispatch_seeds(graph: SymbolGraph) -> frozenset[str]:
    """Step 1b — dynamic-dispatch root set: symbols reachable only at runtime.

    All 9 G0d rev3.2 categories:
    - IBOutlet / IBAction
    - @objc / @objcMembers / dynamic
    - NSManaged (Core Data)
    - @propertyWrapper / @attached macro
    - Codable synthesis
    - @AppStorage / @SceneStorage / EnvironmentKey / PreferenceKey (SwiftUI)
    """
    seeds: set[str] = set()
    for qn, sym in graph.symbols.items():
        if _is_dynamic_dispatch_root(sym):
            seeds.add(qn)
    return frozenset(seeds)


def _is_dynamic_dispatch_root(sym: SymbolNode) -> bool:
    # Hard-exclude: these are accessed entirely by the runtime, never via static calls.
    # @objc/@dynamic on individual methods are annotation-risk flags (score cap in Step 6),
    # NOT full seeds — they may still be dead candidates with a low safe_to_delete_score.
    return (
        sym.is_iboutlet
        or sym.is_ibaction
        or sym.is_objc_members  # @objcMembers on class = all members accessible via ObjC
        or sym.is_ns_managed  # Core Data managed objects: accessed by class name at runtime
        or sym.is_property_wrapper
        or sym.is_codable
        or sym.is_swift_app_storage  # @AppStorage/@SceneStorage: accessed by SwiftUI runtime
        or sym.is_env_key  # EnvironmentKey/PreferenceKey: accessed by SwiftUI key lookup
    )


def compute_all_seeds(graph: SymbolGraph) -> frozenset[str]:
    """Union of public seeds and dynamic dispatch seeds."""
    return identify_public_seeds(graph) | identify_dynamic_dispatch_seeds(graph)
