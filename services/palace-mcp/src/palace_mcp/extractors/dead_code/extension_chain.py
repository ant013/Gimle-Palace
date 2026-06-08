"""Step 3: Extension chain pass — protocol conformance existential check."""

from __future__ import annotations

from palace_mcp.extractors.dead_code.models import SymbolGraph


def find_alive_extensions(
    graph: SymbolGraph,
    dead_candidates: frozenset[str],
) -> frozenset[str]:
    """Return dead-candidate extensions that must be kept alive.

    An extension is ALIVE when it adds a protocol conformance and that
    protocol is referenced via existential anywhere in the codebase.
    An extension with only methods/properties on a dead type stays dead.
    """
    alive: set[str] = set()
    for qn in dead_candidates:
        sym = graph.symbols.get(qn)
        if sym is None or sym.kind != "extension":
            continue
        # Check if this extension adds a protocol conformance used as existential
        if sym.extends_protocol and graph.used_via_existential(sym.extends_protocol):
            alive.add(qn)
    return frozenset(alive)


def compute_extension_chain_findings(
    graph: SymbolGraph,
    dead_candidates: frozenset[str],
) -> list[tuple[str, list[str], list[dict[str, object]]]]:
    """Find dead extension chains: (target_type_qn, dead_ext_qns, conformance_checks).

    Returns tuples for extension chains where the target type is dead and
    all its extensions are also dead (none have existential-used conformances).
    """
    results: list[tuple[str, list[str], list[dict[str, object]]]] = []
    for type_qn in dead_candidates:
        sym = graph.symbols.get(type_qn)
        if sym is None or sym.kind not in (
            "class",
            "struct",
            "enum",
            "protocol",
            "actor",
        ):
            continue
        extensions = graph.extensions_of(type_qn)
        dead_exts = [e for e in extensions if e in dead_candidates]
        if not dead_exts:
            continue
        conformance_checks: list[dict[str, object]] = []
        for ext_qn in dead_exts:
            ext_sym = graph.symbols.get(ext_qn)
            if ext_sym and ext_sym.extends_protocol:
                protocol = ext_sym.extends_protocol
                conformance_checks.append(
                    {
                        "protocol": protocol,
                        "used_via_existential": graph.used_via_existential(protocol),
                    }
                )
        results.append((type_qn, dead_exts, conformance_checks))
    return results
