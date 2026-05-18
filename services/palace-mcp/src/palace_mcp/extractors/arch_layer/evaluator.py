"""Rule evaluator for arch_layer extractor (GIM-243).

Evaluates the 5 V1 rule kinds against the parsed module DAG and
import evidence:

  forbidden_dependency           — manifest edge crosses layer boundary
  forbidden_module_glob_dependency — manifest edge matches source/dest globs
  no_circular_module_deps        — strongly-connected components > 1
  manifest_dep_actually_used     — manifest dep has no import evidence
  ast_dep_not_declared           — import evidence has no manifest edge
"""

from __future__ import annotations

import fnmatch
from collections import defaultdict

from palace_mcp.extractors.arch_layer.imports import ImportFact
from palace_mcp.extractors.arch_layer.models import ArchViolation, ModuleEdge
from palace_mcp.extractors.arch_layer.rules import RuleSet


def evaluate(
    *,
    project_id: str,
    run_id: str,
    modules: list[str],  # all module slugs
    module_layers: dict[str, str | None],  # slug -> layer name or None
    edges: list[ModuleEdge],
    import_facts: list[ImportFact],
    ruleset: RuleSet,
) -> list[ArchViolation]:
    """Evaluate all rules and return violations."""
    if not ruleset.rules_declared:
        return []

    violations: list[ArchViolation] = []

    # Build edge sets for efficient lookup
    manifest_edge_set: set[tuple[str, str]] = {(e.src_slug, e.dst_slug) for e in edges}
    import_edge_set: set[tuple[str, str]] = {
        (f.src_module, f.dst_module) for f in import_facts
    }
    # Group import facts by (src, dst) for evidence retrieval
    import_by_pair: dict[tuple[str, str], list[ImportFact]] = defaultdict(list)
    for f in import_facts:
        import_by_pair[(f.src_module, f.dst_module)].append(f)

    for rule in ruleset.rules:
        if rule.kind == "forbidden_dependency":
            violations.extend(
                _eval_forbidden_dependency(
                    rule_id=rule.rule_id,
                    kind=rule.kind,
                    severity=rule.severity,
                    message=rule.message,
                    project_id=project_id,
                    run_id=run_id,
                    from_layers=rule.from_layers,
                    to_layers=rule.to_layers,
                    edges=edges,
                    module_layers=module_layers,
                )
            )
        elif rule.kind == "forbidden_module_glob_dependency":
            violations.extend(
                _eval_glob_dependency(
                    rule_id=rule.rule_id,
                    kind=rule.kind,
                    severity=rule.severity,
                    message=rule.message,
                    project_id=project_id,
                    run_id=run_id,
                    from_globs=rule.from_globs,
                    to_globs=rule.to_globs,
                    edges=edges,
                )
            )
        elif rule.kind == "no_circular_module_deps":
            violations.extend(
                _eval_no_cycles(
                    rule_id=rule.rule_id,
                    severity=rule.severity,
                    project_id=project_id,
                    run_id=run_id,
                    modules=modules,
                    edges=edges,
                )
            )
        elif rule.kind == "manifest_dep_actually_used":
            violations.extend(
                _eval_manifest_dep_used(
                    rule_id=rule.rule_id,
                    severity=rule.severity,
                    project_id=project_id,
                    run_id=run_id,
                    edges=edges,
                    import_edge_set=import_edge_set,
                )
            )
        elif rule.kind == "ast_dep_not_declared":
            violations.extend(
                _eval_ast_not_declared(
                    rule_id=rule.rule_id,
                    severity=rule.severity,
                    project_id=project_id,
                    run_id=run_id,
                    import_facts=import_facts,
                    manifest_edge_set=manifest_edge_set,
                    import_by_pair=import_by_pair,
                )
            )

    return violations


def _eval_forbidden_dependency(
    *,
    rule_id: str,
    kind: str,
    severity: str,
    message: str,
    project_id: str,
    run_id: str,
    from_layers: tuple[str, ...],
    to_layers: tuple[str, ...],
    edges: list[ModuleEdge],
    module_layers: dict[str, str | None],
) -> list[ArchViolation]:
    violations = []
    for edge in edges:
        src_layer = module_layers.get(edge.src_slug)
        dst_layer = module_layers.get(edge.dst_slug)
        if src_layer in from_layers and dst_layer in to_layers:
            violations.append(
                ArchViolation(
                    project_id=project_id,
                    kind=kind,
                    severity=severity,
                    src_module=edge.src_slug,
                    dst_module=edge.dst_slug,
                    rule_id=rule_id,
                    message=message,
                    evidence=f"manifest edge: {edge.src_slug} -> {edge.dst_slug} [{edge.scope}]",
                    file=edge.declared_in,
                    start_line=0,
                    run_id=run_id,
                )
            )
    return violations


def _eval_glob_dependency(
    *,
    rule_id: str,
    kind: str,
    severity: str,
    message: str,
    project_id: str,
    run_id: str,
    from_globs: tuple[str, ...],
    to_globs: tuple[str, ...],
    edges: list[ModuleEdge],
) -> list[ArchViolation]:
    violations = []
    for edge in edges:
        src_matches = any(fnmatch.fnmatch(edge.src_slug, g) for g in from_globs)
        dst_matches = any(fnmatch.fnmatch(edge.dst_slug, g) for g in to_globs)
        if src_matches and dst_matches:
            violations.append(
                ArchViolation(
                    project_id=project_id,
                    kind=kind,
                    severity=severity,
                    src_module=edge.src_slug,
                    dst_module=edge.dst_slug,
                    rule_id=rule_id,
                    message=message,
                    evidence=f"manifest edge: {edge.src_slug} -> {edge.dst_slug} [{edge.scope}]",
                    file=edge.declared_in,
                    start_line=0,
                    run_id=run_id,
                )
            )
    return violations


def _eval_no_cycles(
    *,
    rule_id: str,
    severity: str,
    project_id: str,
    run_id: str,
    modules: list[str],
    edges: list[ModuleEdge],
) -> list[ArchViolation]:
    """Detect strongly-connected components with size > 1 (Tarjan's algorithm)."""
    adj: dict[str, list[str]] = defaultdict(list)
    for e in edges:
        adj[e.src_slug].append(e.dst_slug)

    index_counter = [0]
    stack: list[str] = []
    lowlink: dict[str, int] = {}
    index: dict[str, int] = {}
    on_stack: dict[str, bool] = {}
    sccs: list[list[str]] = []

    def strongconnect(v: str) -> None:
        index[v] = lowlink[v] = index_counter[0]
        index_counter[0] += 1
        stack.append(v)
        on_stack[v] = True

        for w in adj.get(v, []):
            if w not in index:
                strongconnect(w)
                lowlink[v] = min(lowlink[v], lowlink[w])
            elif on_stack.get(w, False):
                lowlink[v] = min(lowlink[v], index[w])

        if lowlink[v] == index[v]:
            scc: list[str] = []
            while True:
                w = stack.pop()
                on_stack[w] = False
                scc.append(w)
                if w == v:
                    break
            sccs.append(scc)

    for node in modules:
        if node not in index:
            strongconnect(node)

    violations = []
    for scc in sccs:
        if len(scc) <= 1:
            continue
        cycle_desc = " -> ".join(sorted(scc)) + " (cycle)"
        violations.append(
            ArchViolation(
                project_id=project_id,
                kind="no_circular_module_deps",
                severity=severity,
                src_module=scc[0],
                dst_module=scc[-1],
                rule_id=rule_id,
                message=f"Circular module dependency detected: {cycle_desc}",
                evidence=cycle_desc,
                file="",
                start_line=0,
                run_id=run_id,
            )
        )
    return violations


def _eval_manifest_dep_used(
    *,
    rule_id: str,
    severity: str,
    project_id: str,
    run_id: str,
    edges: list[ModuleEdge],
    import_edge_set: set[tuple[str, str]],
) -> list[ArchViolation]:
    violations = []
    for edge in edges:
        pair = (edge.src_slug, edge.dst_slug)
        if pair not in import_edge_set:
            violations.append(
                ArchViolation(
                    project_id=project_id,
                    kind="manifest_dep_actually_used",
                    severity=severity,
                    src_module=edge.src_slug,
                    dst_module=edge.dst_slug,
                    rule_id=rule_id,
                    message=(
                        f"Module {edge.src_slug!r} declares dependency on "
                        f"{edge.dst_slug!r} but no import evidence found"
                    ),
                    evidence=f"manifest edge: {edge.src_slug} -> {edge.dst_slug}; no imports found",
                    file=edge.declared_in,
                    start_line=0,
                    run_id=run_id,
                )
            )
    return violations


def _eval_ast_not_declared(
    *,
    rule_id: str,
    severity: str,
    project_id: str,
    run_id: str,
    import_facts: list[ImportFact],
    manifest_edge_set: set[tuple[str, str]],
    import_by_pair: dict[tuple[str, str], list[ImportFact]],
) -> list[ArchViolation]:
    seen: set[tuple[str, str]] = set()
    violations = []
    for fact in import_facts:
        pair = (fact.src_module, fact.dst_module)
        if pair in manifest_edge_set or pair in seen:
            continue
        seen.add(pair)
        first = import_by_pair[pair][0]
        violations.append(
            ArchViolation(
                project_id=project_id,
                kind="ast_dep_not_declared",
                severity=severity,
                src_module=fact.src_module,
                dst_module=fact.dst_module,
                rule_id=rule_id,
                message=(
                    f"Module {fact.src_module!r} imports {fact.dst_module!r} "
                    "but no manifest dependency declared"
                ),
                evidence=f"{first.raw_import} at {first.file}:{first.line}",
                file=first.file,
                start_line=first.line,
                run_id=run_id,
            )
        )
    return violations
