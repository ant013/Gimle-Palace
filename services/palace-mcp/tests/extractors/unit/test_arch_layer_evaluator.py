"""Unit tests for arch_layer rule evaluator (GIM-243)."""

from __future__ import annotations


from palace_mcp.extractors.arch_layer.evaluator import evaluate
from palace_mcp.extractors.arch_layer.imports import ImportFact
from palace_mcp.extractors.arch_layer.models import ModuleEdge
from palace_mcp.extractors.arch_layer.rules import LayerDef, RuleDef, RuleSet

_PROJECT = "project/test"
_RUN = "run-1"


def _make_ruleset(*rules: RuleDef, layers: list[LayerDef] | None = None) -> RuleSet:
    rs = RuleSet(rules_declared=True, rule_source=".palace/architecture-rules.yaml")
    rs.layers = layers or [
        LayerDef(name="core", module_globs=("Core", "WalletCore")),
        LayerDef(name="ui", module_globs=("UI", "WalletUI")),
    ]
    rs.rules = list(rules)
    return rs


def _edge(src: str, dst: str, scope: str = "target_dep") -> ModuleEdge:
    return ModuleEdge(
        src_slug=src,
        dst_slug=dst,
        scope=scope,
        declared_in="Package.swift",
        evidence_kind="manifest",
        run_id=_RUN,
    )


def _import_fact(
    src: str, dst: str, file: str = "UI/View.swift", line: int = 1
) -> ImportFact:
    return ImportFact(
        src_module=src,
        dst_module=dst,
        file=file,
        line=line,
        raw_import=f"import {dst}",
    )


class TestNoRules:
    def test_empty_ruleset_returns_no_violations(self) -> None:
        rs = RuleSet()  # rules_declared=False
        result = evaluate(
            project_id=_PROJECT,
            run_id=_RUN,
            modules=["A", "B"],
            module_layers={},
            edges=[_edge("A", "B")],
            import_facts=[],
            ruleset=rs,
        )
        assert result == []


class TestForbiddenDependency:
    def test_violation_when_core_depends_on_ui(self) -> None:
        rs = _make_ruleset(
            RuleDef(
                rule_id="r1",
                kind="forbidden_dependency",
                severity="high",
                from_layers=("core",),
                to_layers=("ui",),
                from_globs=(),
                to_globs=(),
                message="bad",
            ),
        )
        module_layers = {"WalletCore": "core", "WalletUI": "ui"}
        violations = evaluate(
            project_id=_PROJECT,
            run_id=_RUN,
            modules=["WalletCore", "WalletUI"],
            module_layers=module_layers,
            edges=[_edge("WalletCore", "WalletUI")],
            import_facts=[],
            ruleset=rs,
        )
        assert len(violations) == 1
        assert violations[0].kind == "forbidden_dependency"
        assert violations[0].severity == "high"

    def test_no_violation_when_ui_depends_on_core(self) -> None:
        rs = _make_ruleset(
            RuleDef(
                rule_id="r1",
                kind="forbidden_dependency",
                severity="high",
                from_layers=("core",),
                to_layers=("ui",),
                from_globs=(),
                to_globs=(),
                message="bad",
            ),
        )
        module_layers = {"WalletCore": "core", "WalletUI": "ui"}
        violations = evaluate(
            project_id=_PROJECT,
            run_id=_RUN,
            modules=["WalletCore", "WalletUI"],
            module_layers=module_layers,
            edges=[_edge("WalletUI", "WalletCore")],
            import_facts=[],
            ruleset=rs,
        )
        assert violations == []


class TestForbiddenGlobDependency:
    def test_glob_match_creates_violation(self) -> None:
        rs = _make_ruleset(
            RuleDef(
                rule_id="r2",
                kind="forbidden_module_glob_dependency",
                severity="high",
                from_layers=(),
                to_layers=(),
                from_globs=("*Core*",),
                to_globs=("*UI*",),
                message="bad glob",
            ),
        )
        violations = evaluate(
            project_id=_PROJECT,
            run_id=_RUN,
            modules=["WalletCore", "WalletUI"],
            module_layers={},
            edges=[_edge("WalletCore", "WalletUI")],
            import_facts=[],
            ruleset=rs,
        )
        assert len(violations) == 1

    def test_non_matching_glob_no_violation(self) -> None:
        rs = _make_ruleset(
            RuleDef(
                rule_id="r2",
                kind="forbidden_module_glob_dependency",
                severity="high",
                from_layers=(),
                to_layers=(),
                from_globs=("*Data*",),
                to_globs=("*UI*",),
                message="bad glob",
            ),
        )
        violations = evaluate(
            project_id=_PROJECT,
            run_id=_RUN,
            modules=["WalletCore", "WalletUI"],
            module_layers={},
            edges=[_edge("WalletCore", "WalletUI")],
            import_facts=[],
            ruleset=rs,
        )
        assert violations == []


class TestNoCircularDeps:
    def test_cycle_detected(self) -> None:
        rs = _make_ruleset(
            RuleDef(
                rule_id="r3",
                kind="no_circular_module_deps",
                severity="high",
                from_layers=(),
                to_layers=(),
                from_globs=(),
                to_globs=(),
                message="cycle",
            ),
        )
        violations = evaluate(
            project_id=_PROJECT,
            run_id=_RUN,
            modules=["A", "B", "C"],
            module_layers={},
            edges=[_edge("A", "B"), _edge("B", "A")],
            import_facts=[],
            ruleset=rs,
        )
        assert len(violations) == 1
        assert violations[0].kind == "no_circular_module_deps"

    def test_no_cycle_no_violation(self) -> None:
        rs = _make_ruleset(
            RuleDef(
                rule_id="r3",
                kind="no_circular_module_deps",
                severity="high",
                from_layers=(),
                to_layers=(),
                from_globs=(),
                to_globs=(),
                message="cycle",
            ),
        )
        violations = evaluate(
            project_id=_PROJECT,
            run_id=_RUN,
            modules=["A", "B", "C"],
            module_layers={},
            edges=[_edge("A", "B"), _edge("B", "C")],
            import_facts=[],
            ruleset=rs,
        )
        assert violations == []

    def test_cycle_result_is_deterministic(self) -> None:
        rs = _make_ruleset(
            RuleDef(
                rule_id="r3",
                kind="no_circular_module_deps",
                severity="high",
                from_layers=(),
                to_layers=(),
                from_globs=(),
                to_globs=(),
                message="",
            ),
        )
        violations1 = evaluate(
            project_id=_PROJECT,
            run_id=_RUN,
            modules=["X", "Y"],
            module_layers={},
            edges=[_edge("X", "Y"), _edge("Y", "X")],
            import_facts=[],
            ruleset=rs,
        )
        violations2 = evaluate(
            project_id=_PROJECT,
            run_id=_RUN,
            modules=["X", "Y"],
            module_layers={},
            edges=[_edge("X", "Y"), _edge("Y", "X")],
            import_facts=[],
            ruleset=rs,
        )
        assert len(violations1) == len(violations2) == 1
        assert violations1[0].evidence == violations2[0].evidence


class TestManifestDepActuallyUsed:
    def test_unused_manifest_dep_creates_violation(self) -> None:
        rs = _make_ruleset(
            RuleDef(
                rule_id="r4",
                kind="manifest_dep_actually_used",
                severity="low",
                from_layers=(),
                to_layers=(),
                from_globs=(),
                to_globs=(),
                message="unused",
            ),
        )
        violations = evaluate(
            project_id=_PROJECT,
            run_id=_RUN,
            modules=["A", "B"],
            module_layers={},
            edges=[_edge("A", "B")],
            import_facts=[],  # no imports → no evidence
            ruleset=rs,
        )
        assert len(violations) == 1
        assert violations[0].kind == "manifest_dep_actually_used"
        assert violations[0].severity == "low"

    def test_used_manifest_dep_no_violation(self) -> None:
        rs = _make_ruleset(
            RuleDef(
                rule_id="r4",
                kind="manifest_dep_actually_used",
                severity="low",
                from_layers=(),
                to_layers=(),
                from_globs=(),
                to_globs=(),
                message="unused",
            ),
        )
        violations = evaluate(
            project_id=_PROJECT,
            run_id=_RUN,
            modules=["A", "B"],
            module_layers={},
            edges=[_edge("A", "B")],
            import_facts=[_import_fact("A", "B")],
            ruleset=rs,
        )
        assert violations == []


class TestAstDepNotDeclared:
    def test_undeclared_import_creates_violation(self) -> None:
        rs = _make_ruleset(
            RuleDef(
                rule_id="r5",
                kind="ast_dep_not_declared",
                severity="high",
                from_layers=(),
                to_layers=(),
                from_globs=(),
                to_globs=(),
                message="undeclared",
            ),
        )
        violations = evaluate(
            project_id=_PROJECT,
            run_id=_RUN,
            modules=["A", "B"],
            module_layers={},
            edges=[],  # no manifest edges
            import_facts=[_import_fact("A", "B")],
            ruleset=rs,
        )
        assert len(violations) == 1
        assert violations[0].kind == "ast_dep_not_declared"
        assert violations[0].severity == "high"

    def test_declared_import_no_violation(self) -> None:
        rs = _make_ruleset(
            RuleDef(
                rule_id="r5",
                kind="ast_dep_not_declared",
                severity="high",
                from_layers=(),
                to_layers=(),
                from_globs=(),
                to_globs=(),
                message="undeclared",
            ),
        )
        violations = evaluate(
            project_id=_PROJECT,
            run_id=_RUN,
            modules=["A", "B"],
            module_layers={},
            edges=[_edge("A", "B")],  # manifest edge present
            import_facts=[_import_fact("A", "B")],
            ruleset=rs,
        )
        assert violations == []

    def test_duplicate_import_facts_deduplicated(self) -> None:
        rs = _make_ruleset(
            RuleDef(
                rule_id="r5",
                kind="ast_dep_not_declared",
                severity="high",
                from_layers=(),
                to_layers=(),
                from_globs=(),
                to_globs=(),
                message="",
            ),
        )
        violations = evaluate(
            project_id=_PROJECT,
            run_id=_RUN,
            modules=["A", "B"],
            module_layers={},
            edges=[],
            import_facts=[
                _import_fact("A", "B"),
                _import_fact("A", "B", file="other.swift", line=5),
            ],
            ruleset=rs,
        )
        assert len(violations) == 1  # deduped to one
