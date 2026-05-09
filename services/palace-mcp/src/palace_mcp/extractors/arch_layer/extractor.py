"""arch_layer extractor — GIM-243.

Composes rule loader, parsers, import scanner, evaluator and Neo4j writer.
Dual-ecosystem dispatch: runs both SPM and Gradle parsers independently;
modules are keyed by kind (swift_target / gradle_module) to avoid slug
collisions when both manifest types exist in the same repo.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, ClassVar

from palace_mcp.extractors.arch_layer.evaluator import evaluate
from palace_mcp.extractors.arch_layer.imports import scan_imports
from palace_mcp.extractors.arch_layer.models import (
    ArchRule,
    ArchViolation,
    Layer,
    Module,
    ModuleEdge,
)
from palace_mcp.extractors.arch_layer.parsers.gradle import parse_gradle
from palace_mcp.extractors.arch_layer.parsers.spm import parse_spm
from palace_mcp.extractors.arch_layer.rules import load_rules
from palace_mcp.extractors.base import (
    BaseExtractor,
    ExtractorConfigError,
    ExtractorRunContext,
    ExtractorRuntimeError,
    ExtractorStats,
)

if TYPE_CHECKING:
    from palace_mcp.audit.contracts import AuditContract, Severity

logger = logging.getLogger(__name__)

_QUERY = """
MATCH (v:ArchViolation {project_id: $project_id})
RETURN v.kind       AS kind,
       v.severity   AS severity,
       v.src_module AS src_module,
       v.dst_module AS dst_module,
       v.rule_id    AS rule_id,
       v.message    AS message,
       v.evidence   AS evidence,
       v.file       AS file,
       v.start_line AS start_line,
       v.run_id     AS run_id
ORDER BY
  CASE v.severity
    WHEN 'critical' THEN 0
    WHEN 'high'     THEN 1
    WHEN 'medium'   THEN 2
    WHEN 'low'      THEN 3
    ELSE 4
  END,
  v.src_module,
  v.dst_module
""".strip()


def _arch_severity(raw: Any) -> "Severity":
    from palace_mcp.audit.contracts import Severity

    mapping: dict[str, Severity] = {
        "critical": Severity.CRITICAL,
        "high": Severity.HIGH,
        "medium": Severity.MEDIUM,
        "low": Severity.LOW,
        "informational": Severity.INFORMATIONAL,
    }
    return mapping.get(str(raw).lower(), Severity.INFORMATIONAL)


class ArchLayerExtractor(BaseExtractor):
    name: ClassVar[str] = "arch_layer"
    description: ClassVar[str] = (
        "GIM-243 — Architecture Layer. "
        "Builds module DAG for SwiftPM/Gradle projects, evaluates layer rules, "
        "and writes :Module/:Layer/:ArchRule/:ArchViolation nodes to Neo4j."
    )
    constraints: ClassVar[list[str]] = [
        "CREATE CONSTRAINT arch_module_unique IF NOT EXISTS "
        "FOR (m:Module) REQUIRE (m.project_id, m.slug) IS UNIQUE",
        "CREATE CONSTRAINT arch_layer_unique IF NOT EXISTS "
        "FOR (l:Layer) REQUIRE (l.project_id, l.name) IS UNIQUE",
        "CREATE CONSTRAINT arch_rule_unique IF NOT EXISTS "
        "FOR (r:ArchRule) REQUIRE (r.project_id, r.rule_id) IS UNIQUE",
        "CREATE CONSTRAINT arch_violation_unique IF NOT EXISTS "
        "FOR (v:ArchViolation) REQUIRE "
        "(v.project_id, v.rule_id, v.src_module, v.dst_module, v.evidence) IS UNIQUE",
    ]
    indexes: ClassVar[list[str]] = [
        "CREATE INDEX arch_violation_project IF NOT EXISTS "
        "FOR (v:ArchViolation) ON (v.project_id)",
        "CREATE INDEX arch_violation_severity IF NOT EXISTS "
        "FOR (v:ArchViolation) ON (v.severity)",
    ]

    def audit_contract(self) -> "AuditContract":
        from palace_mcp.audit.contracts import AuditContract

        return AuditContract(
            extractor_name="arch_layer",
            template_name="arch_layer.md",
            query=_QUERY,
            severity_column="severity",
            severity_mapper=_arch_severity,
        )

    async def run(
        self, *, graphiti: object, ctx: ExtractorRunContext
    ) -> ExtractorStats:
        from palace_mcp.mcp_server import get_driver

        driver = get_driver()
        if driver is None:
            raise ExtractorConfigError(
                "Neo4j driver not available for arch_layer"
            )

        try:
            result = await _run_extraction(ctx=ctx, driver=driver)
        except ExtractorConfigError:
            raise
        except OSError as exc:
            raise ExtractorRuntimeError(str(exc)) from exc
        except Exception as exc:
            raise ExtractorRuntimeError(str(exc)) from exc

        return result


async def _run_extraction(*, ctx: ExtractorRunContext, driver: Any) -> ExtractorStats:
    from palace_mcp.extractors.arch_layer.neo4j_writer import replace_project_snapshot

    repo_path = ctx.repo_path
    project_id = ctx.group_id
    run_id = ctx.run_id

    # Load rules (may be empty if no rule file)
    ruleset = load_rules(repo_path)
    for loader_warn in ruleset.loader_warnings:
        logger.warning("arch_layer rule loader: %s", loader_warn)

    # Parse both ecosystems independently (advisory note 1: dual-ecosystem dispatch)
    spm_result = parse_spm(repo_path, project_id=project_id, run_id=run_id)
    gradle_result = parse_gradle(repo_path, project_id=project_id, run_id=run_id)

    parser_warnings = list(spm_result.warnings) + list(gradle_result.warnings)
    for pw in parser_warnings:
        logger.info("arch_layer parser: %s", pw.message)

    all_modules: list[Module] = list(spm_result.modules) + list(gradle_result.modules)
    all_edges: list[ModuleEdge] = list(spm_result.edges) + list(gradle_result.edges)

    if not all_modules:
        logger.warning(
            "arch_layer: no modules found in %s — no Neo4j writes",
            repo_path,
        )
        return ExtractorStats(nodes_written=0, edges_written=0)

    # Build module_source_roots for import scanner
    module_source_roots = {
        m.slug: m.source_root for m in all_modules if m.source_root
    }
    swift_modules = frozenset(m.slug for m in all_modules if m.kind == "swift_target")
    gradle_modules = frozenset(m.slug for m in all_modules if m.kind == "gradle_module")

    import_result = scan_imports(
        repo_path,
        swift_modules=swift_modules,
        gradle_modules=gradle_modules,
        module_source_roots=module_source_roots,
    )
    for iw in import_result.warnings:
        logger.info("arch_layer import scanner: %s", iw.message)

    # Build layers from ruleset
    all_module_names = [m.slug for m in all_modules]
    module_layers: dict[str, str | None] = {
        slug: ruleset.layer_for_module(slug) for slug in all_module_names
    }

    layers: list[Layer] = [
        Layer(
            project_id=project_id,
            name=ld.name,
            rule_source=ruleset.rule_source,
            run_id=run_id,
        )
        for ld in ruleset.layers
    ]

    arch_rules: list[ArchRule] = [
        ArchRule(
            project_id=project_id,
            rule_id=rd.rule_id,
            kind=rd.kind,
            severity=rd.severity,
            rule_source=ruleset.rule_source,
            run_id=run_id,
        )
        for rd in ruleset.rules
    ]

    violations: list[ArchViolation] = evaluate(
        project_id=project_id,
        run_id=run_id,
        modules=all_module_names,
        module_layers=module_layers,
        edges=all_edges,
        import_facts=list(import_result.facts),
        ruleset=ruleset,
    )

    logger.info(
        "arch_layer: writing snapshot",
        extra={
            "project": ctx.project_slug,
            "modules": len(all_modules),
            "layers": len(layers),
            "rules": len(arch_rules),
            "violations": len(violations),
            "edges": len(all_edges),
            "parser_warnings": len(parser_warnings),
            "import_warnings": len(import_result.warnings),
            "rules_declared": ruleset.rules_declared,
        },
    )

    nodes_written, edges_written = await replace_project_snapshot(
        driver,
        project_id=project_id,
        modules=all_modules,
        layers=layers,
        rules=arch_rules,
        violations=violations,
        edges=all_edges,
        module_layers=module_layers,
        run_id=run_id,
    )

    return ExtractorStats(nodes_written=nodes_written, edges_written=edges_written)
