"""Coding convention extractor scaffolding (Roadmap #6)."""

from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from graphiti_core import Graphiti

from palace_mcp.extractors.base import (
    BaseExtractor,
    ExtractorConfigError,
    ExtractorError,
    ExtractorRunContext,
    ExtractorRuntimeError,
    ExtractorStats,
)
from palace_mcp.extractors.coding_convention.models import (
    ConventionExtractionSummary,
    ConventionFinding,
    ConventionSignal,
    ConventionViolation,
)
from palace_mcp.extractors.coding_convention.neo4j_writer import (
    replace_project_snapshot,
)
from palace_mcp.extractors.coding_convention.rules import load_rules

if TYPE_CHECKING:
    from palace_mcp.audit.contracts import AuditContract

_STOP_DIRS: frozenset[str] = frozenset(
    {
        ".git",
        ".venv",
        ".build",
        "build",
        "dist",
        "node_modules",
        "Pods",
        "Carthage",
        "SourcePackages",
        "DerivedData",
        "__pycache__",
    }
)
_SUPPORTED_SUFFIXES: frozenset[str] = frozenset({".swift", ".kt"})
_MIN_SAMPLE_COUNT = 5


class CodingConventionExtractor(BaseExtractor):
    """Scaffold for project-specific coding convention extraction."""

    name: ClassVar[str] = "coding_convention"
    description: ClassVar[str] = (
        "Detect dominant Swift and Kotlin coding conventions together with outliers."
    )
    constraints: ClassVar[list[str]] = []
    indexes: ClassVar[list[str]] = [
        "CREATE INDEX convention_lookup IF NOT EXISTS "
        "FOR (c:Convention) ON (c.project_id, c.module, c.kind)",
        "CREATE INDEX convention_violation_severity IF NOT EXISTS "
        "FOR (v:ConventionViolation) ON (v.project_id, v.severity)",
    ]

    def audit_contract(self) -> "AuditContract":
        from palace_mcp.audit.contracts import AuditContract, Severity

        def severity_from_outlier_ratio(raw_value: object) -> Severity:
            if isinstance(raw_value, (int, float)):
                ratio = float(raw_value)
            elif isinstance(raw_value, str) and raw_value:
                ratio = float(raw_value)
            else:
                ratio = 0.0
            if ratio >= 0.1:
                return Severity.HIGH
            if ratio > 0:
                return Severity.MEDIUM
            return Severity.LOW

        return AuditContract(
            extractor_name="coding_convention",
            template_name="coding_convention.md",
            query="""
MATCH (c:Convention {project_id: $project})
OPTIONAL MATCH (v:ConventionViolation {
  project_id: $project,
  module: c.module,
  kind: c.kind
})
WITH c, collect(v {
  .file,
  .start_line,
  .end_line,
  .message,
  .severity
}) AS violations,
CASE
  WHEN c.sample_count < 5 THEN 0.0
  WHEN c.sample_count = 0 THEN 0.0
  ELSE toFloat(c.outliers) / toFloat(c.sample_count)
END AS outlier_ratio
RETURN c.module AS module,
       c.kind AS kind,
       c.dominant_choice AS dominant_choice,
       c.confidence AS confidence,
       c.sample_count AS sample_count,
       c.outliers AS outliers,
       violations AS violations,
       outlier_ratio AS outlier_ratio,
       coalesce(c.source_context, 'other') AS source_context
ORDER BY outlier_ratio DESC, c.module, c.kind
LIMIT 100
""".strip(),
            severity_column="outlier_ratio",
            severity_mapper=severity_from_outlier_ratio,
        )

    async def run(
        self, *, graphiti: Graphiti, ctx: ExtractorRunContext
    ) -> ExtractorStats:
        del graphiti
        from palace_mcp.mcp_server import get_driver

        driver = get_driver()
        if driver is None:
            raise ExtractorConfigError(
                "Neo4j driver not available for coding_convention"
            )

        try:
            summary = collect_conventions(
                project_id=ctx.project_slug,
                repo_path=ctx.repo_path,
                run_id=ctx.run_id,
            )
            await replace_project_snapshot(
                driver,
                project_id=ctx.project_slug,
                findings=summary.findings,
                violations=summary.violations,
            )
        except ExtractorError:
            raise
        except OSError as exc:
            raise ExtractorRuntimeError(str(exc)) from exc
        except Exception as exc:
            raise ExtractorRuntimeError(str(exc)) from exc

        return ExtractorStats(
            nodes_written=len(summary.findings) + len(summary.violations),
            edges_written=0,
        )


def collect_conventions(
    *, project_id: str, repo_path: Path, run_id: str
) -> ConventionExtractionSummary:
    from palace_mcp.extractors.foundation.source_context import classify

    grouped: dict[tuple[str, str], list[ConventionSignal]] = defaultdict(list)
    rules = load_rules()

    for path in _iter_source_files(repo_path):
        rel_path = path.relative_to(repo_path).as_posix()
        module = _infer_module(rel_path, project_id)
        text = path.read_text(encoding="utf-8")
        for rule in rules:
            for signal in rule.collect(module=module, rel_path=rel_path, text=text):
                grouped[(signal.module, signal.kind)].append(signal)

    findings: list[ConventionFinding] = []
    violations: list[ConventionViolation] = []
    for (module, kind), signals in sorted(grouped.items()):
        counts = Counter(signal.choice for signal in signals)
        dominant_choice, dominant_count = max(
            counts.items(), key=lambda item: (item[1], item[0])
        )
        sample_count = len(signals)
        if sample_count < _MIN_SAMPLE_COUNT:
            continue
        outliers = sample_count - dominant_count
        # Classify module source_context from first signal's file path
        module_ctx = classify(signals[0].file)
        findings.append(
            ConventionFinding(
                project_id=project_id,
                module=module,
                kind=kind,
                dominant_choice=dominant_choice,
                confidence="heuristic",
                sample_count=sample_count,
                outliers=outliers,
                run_id=run_id,
                source_context=module_ctx,
            )
        )
        severity = _violation_severity(sample_count=sample_count, outliers=outliers)
        for signal in signals:
            if signal.choice == dominant_choice:
                continue
            violations.append(
                ConventionViolation(
                    project_id=project_id,
                    module=module,
                    kind=kind,
                    file=signal.file,
                    start_line=signal.start_line,
                    end_line=signal.end_line,
                    message=signal.message,
                    severity=severity,
                    run_id=run_id,
                    source_context=classify(signal.file),
                )
            )

    return ConventionExtractionSummary(findings=findings, violations=violations)


def _iter_source_files(repo_path: Path) -> list[Path]:
    files: list[Path] = []
    for path in repo_path.rglob("*"):
        if not path.is_file() or path.suffix not in _SUPPORTED_SUFFIXES:
            continue
        rel = path.relative_to(repo_path)
        if any(part in _STOP_DIRS for part in rel.parts):
            continue
        files.append(path)
    return sorted(files)


def _infer_module(rel_path: str, fallback: str) -> str:
    parts = rel_path.split("/")
    if "Sources" in parts:
        idx = parts.index("Sources")
        if idx + 1 < len(parts):
            return parts[idx + 1]
    if "Tests" in parts:
        idx = parts.index("Tests")
        if idx + 1 < len(parts):
            return parts[idx + 1]
    if "Modules" in parts:
        idx = parts.index("Modules")
        if idx + 1 < len(parts) - 1:
            return parts[idx + 1]
        if idx > 0:
            return parts[idx - 1]
    if "src" in parts:
        idx = parts.index("src")
        if idx > 0:
            return parts[idx - 1]
    return parts[0] if parts else fallback


def _violation_severity(*, sample_count: int, outliers: int) -> str:
    if outliers == 0:
        return "low"
    if sample_count >= 5 and (outliers / sample_count) >= 0.1:
        return "high"
    return "medium"
