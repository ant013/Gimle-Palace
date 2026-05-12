"""localization_accessibility extractor — GIM-275.

Parses iOS .xcstrings / Localizable.strings and Android strings.xml,
then runs semgrep rules for hard-coded string detection and a11y gaps.
Writes :LocaleResource, :HardcodedString, :A11yMissing nodes.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from palace_mcp.extractors.base import (
    BaseExtractor,
    ExtractorRunContext,
    ExtractorStats,
)
from palace_mcp.extractors.localization_accessibility import neo4j_writer
from palace_mcp.extractors.localization_accessibility.parsers.android_strings import (
    parse_android_strings_xml,
)
from palace_mcp.extractors.localization_accessibility.parsers.coverage import (
    LocaleResource,
    compute_coverage,
)
from palace_mcp.extractors.localization_accessibility.parsers.localizable_strings import (
    parse_localizable_strings,
)
from palace_mcp.extractors.localization_accessibility.parsers.xcstrings import (
    parse_xcstrings,
)
from palace_mcp.extractors.localization_accessibility.rules.allowlist import (
    load_allowlist,
)
from palace_mcp.extractors.localization_accessibility.rules.semgrep_runner import (
    SemgrepFinding,
    normalise_findings,
    run_semgrep,
)

if TYPE_CHECKING:
    from palace_mcp.audit.contracts import AuditContract

logger = logging.getLogger(__name__)

_RULES_DIR = Path(__file__).parent / "semgrep_rules"

# locale extracted from "values-XX" directory name
_ANDROID_LOCALE_RE = re.compile(r"values-([a-z]{2,3}(?:-r[A-Z]{2})?)")

_AUDIT_QUERY = """
OPTIONAL MATCH (lr:LocaleResource {project_id: $project_id})
WITH [x IN collect({locale: lr.locale, key_count: lr.key_count,
                    coverage_pct: lr.coverage_pct, surface: lr.surface,
                    source: lr.source}) WHERE x.locale IS NOT NULL] AS locales
OPTIONAL MATCH (h:HardcodedString {project_id: $project_id})
WITH locales, collect({file: h.file, start_line: h.start_line,
                        literal: h.literal, context: h.context,
                        severity: h.severity, message: h.message}) AS hardcoded
OPTIONAL MATCH (a:A11yMissing {project_id: $project_id})
RETURN locales,
       hardcoded,
       collect({file: a.file, start_line: a.start_line,
                control_kind: a.control_kind, surface: a.surface,
                severity: a.severity, message: a.message}) AS a11y_missing
""".strip()


class LocalizationAccessibilityExtractor(BaseExtractor):
    """Extract locale coverage + a11y gaps from iOS and Android source."""

    name: ClassVar[str] = "localization_accessibility"
    description: ClassVar[str] = (
        "Roadmap #9 — Localization & Accessibility. "
        "Parses .xcstrings / Localizable.strings / strings.xml and runs semgrep "
        "rules for hard-coded strings and missing a11y labels. "
        "Writes :LocaleResource, :HardcodedString, :A11yMissing nodes."
    )
    constraints: ClassVar[list[str]] = []
    indexes: ClassVar[list[str]] = [
        "CREATE INDEX locale_resource_project IF NOT EXISTS "
        "FOR (lr:LocaleResource) ON (lr.project_id, lr.locale)",
        "CREATE INDEX hardcoded_string_project IF NOT EXISTS "
        "FOR (h:HardcodedString) ON (h.project_id, h.severity)",
        "CREATE INDEX a11y_missing_project IF NOT EXISTS "
        "FOR (a:A11yMissing) ON (a.project_id, a.severity)",
    ]

    async def run(
        self,
        *,
        graphiti: object,
        ctx: ExtractorRunContext,
    ) -> ExtractorStats:
        driver = graphiti.driver  # type: ignore[attr-defined]

        # --- Locale resource parsing ---
        raw_resources = _collect_locale_resources(ctx.repo_path)
        locale_coverages = compute_coverage(raw_resources, base_locale="en")

        logger.info(
            "localization_accessibility: locale resources collected",
            extra={
                "project": ctx.project_slug,
                "locales": len(locale_coverages),
            },
        )

        # --- Semgrep detection ---
        allowlist = load_allowlist(ctx.repo_path)
        all_findings: list[SemgrepFinding] = []

        if _RULES_DIR.exists() and any(_RULES_DIR.glob("*.yaml")):
            raw = await run_semgrep(
                rules_dir=_RULES_DIR,
                target=ctx.repo_path,
                timeout_s=180,
            )
            all_findings = normalise_findings(raw, repo_root=ctx.repo_path)
            if allowlist:
                # f.literal is the full matched source line (e.g. Text("Bitcoin")),
                # so check substring containment rather than exact match.
                all_findings = [
                    f for f in all_findings
                    if not any(al in f.literal for al in allowlist)
                ]
        else:
            logger.warning(
                "localization_accessibility: semgrep rules directory empty or absent; "
                "skipping hard-coded + a11y detection",
                extra={"rules_dir": str(_RULES_DIR)},
            )

        hardcoded = [
            f for f in all_findings if f.check_kind == "hardcoded_string"
        ]
        a11y_missing = [
            f for f in all_findings if f.check_kind == "a11y_missing"
        ]

        logger.info(
            "localization_accessibility: semgrep complete",
            extra={
                "project": ctx.project_slug,
                "hardcoded": len(hardcoded),
                "a11y_missing": len(a11y_missing),
            },
        )

        # --- Write to Neo4j ---
        nodes, edges = await neo4j_writer.write_snapshot(
            driver,
            project_id=ctx.group_id,
            run_id=ctx.run_id,
            locale_coverages=locale_coverages,
            hardcoded=hardcoded,
            a11y_missing=a11y_missing,
        )

        return ExtractorStats(nodes_written=nodes, edges_written=edges)

    def audit_contract(self) -> "AuditContract":
        from palace_mcp.audit.contracts import AuditContract, Severity

        def _severity_mapper(v: object) -> Severity:
            mapping = {
                "high": Severity.HIGH,
                "medium": Severity.MEDIUM,
                "low": Severity.LOW,
                "critical": Severity.CRITICAL,
            }
            return mapping.get(str(v).lower(), Severity.INFORMATIONAL)

        return AuditContract(
            extractor_name="localization_accessibility",
            template_name="localization_accessibility.md",
            query=_AUDIT_QUERY,
            severity_column="severity",
            severity_mapper=_severity_mapper,
        )


# ---------------------------------------------------------------------------
# File discovery helpers
# ---------------------------------------------------------------------------


def _collect_locale_resources(repo_root: Path) -> list[LocaleResource]:
    resources: list[LocaleResource] = []

    # iOS .xcstrings (Xcode 15+)
    for path in sorted(repo_root.rglob("*.xcstrings")):
        try:
            catalog = json.loads(path.read_text(encoding="utf-8"))
            rel = path.relative_to(repo_root).as_posix()
            resources.extend(parse_xcstrings(catalog, source_file=rel))
        except Exception:
            logger.debug("localization_accessibility: skipping xcstrings %s", path)

    # iOS legacy Localizable.strings (per-locale .lproj dirs)
    for path in sorted(repo_root.rglob("Localizable.strings")):
        locale = _locale_from_lproj(path)
        if locale is None:
            continue
        try:
            content = path.read_text(encoding="utf-8")
            rel = path.relative_to(repo_root).as_posix()
            resources.append(
                parse_localizable_strings(content, locale=locale, source_file=rel)
            )
        except Exception:
            logger.debug("localization_accessibility: skipping strings %s", path)

    # Android strings.xml per locale directory
    for path in sorted(repo_root.rglob("strings.xml")):
        # must be under res/values or res/values-XX
        parts = path.parts
        if "res" not in parts:
            continue
        values_dir = path.parent.name
        if values_dir == "values":
            locale = "en"
        else:
            m = _ANDROID_LOCALE_RE.match(values_dir)
            if m is None:
                continue
            locale = m.group(1)
        try:
            content = path.read_text(encoding="utf-8")
            rel = path.relative_to(repo_root).as_posix()
            resources.append(
                parse_android_strings_xml(content, locale=locale, source_file=rel)
            )
        except Exception:
            logger.debug("localization_accessibility: skipping strings.xml %s", path)

    return resources


def _locale_from_lproj(path: Path) -> str | None:
    """Extract locale code from a .lproj parent directory name."""
    parent = path.parent.name
    if parent.endswith(".lproj"):
        return parent[: -len(".lproj")]
    return None
