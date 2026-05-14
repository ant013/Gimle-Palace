"""error_handling_policy extractor — GIM-257.

Scans Swift source files with semgrep custom rules, writes :ErrorFinding nodes,
and records a :CatchSite inventory for smoke/report coverage.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

from neo4j import AsyncManagedTransaction

from palace_mcp.extractors.base import (
    BaseExtractor,
    ExtractorConfigError,
    ExtractorRunContext,
    ExtractorStats,
)

if TYPE_CHECKING:
    from palace_mcp.audit.contracts import AuditContract, Severity

logger = logging.getLogger(__name__)

_RULES_DIR = Path(__file__).parent / "rules"
_SWIFT_GLOB = "*.swift"
_SUPPRESSION_MARKERS: tuple[str, str] = ("// ehp:ignore", "// MARK: deliberate")
_CATCH_BLOCK_RE = re.compile(
    r"catch(?:\s+[^{}]+)?\s*\{(?P<body>[^{}]*)\}", re.MULTILINE
)
_TRY_OPTIONAL_RE = re.compile(r"try\?\s*[^\n;]+")
_NIL_COALESCE_RE = re.compile(r"try\?\s*[^\n;]+?\?\?")
_SWALLOWING_KINDS: frozenset[str] = frozenset(
    {
        "empty_catch_block",
        "empty_catch_in_crypto_path",
        "try_optional_swallow",
        "try_optional_in_crypto_path",
        "catch_only_logs",
        "nil_coalesce_swallows_error",
    }
)

# Kinds affected by B8 critical-path severity tuning (try? usage variants)
_TRY_OPTIONAL_KINDS: frozenset[str] = frozenset(
    {
        "try_optional_swallow",
        "try_optional_in_crypto_path",
        "nil_coalesce_swallows_error",
    }
)

# B8 artifact §5 — verbatim regex for critical-path file detection
# Source: docs/research/2026-05-14-try-optional-critical-path-keywords.md
_B8_CRITICAL_PATH_RE = re.compile(
    r"\b(signer|crypto|hd[-_]?wallet|hmac|sign|auth|mnemonic|seed|pubkey|keystore|secp256k1|ed25519|ripemd160)\b",
    re.IGNORECASE,
)

_QUERY = """
CALL {
  MATCH (c:CatchSite {project_id: $project_id})
  RETURN count(c) AS catch_site_count,
         count(DISTINCT c.file) AS files_scanned,
         sum(CASE WHEN c.swallowed THEN 1 ELSE 0 END) AS swallowed_count,
         sum(CASE WHEN c.rethrows THEN 1 ELSE 0 END) AS rethrows_count
}
OPTIONAL MATCH (f:ErrorFinding {project_id: $project_id})
RETURN coalesce(f.kind, '') AS kind,
       coalesce(f.severity, 'informational') AS severity,
       coalesce(f.file, '') AS file,
       coalesce(f.start_line, 0) AS start_line,
       coalesce(f.end_line, 0) AS end_line,
       coalesce(f.message, '') AS message,
       catch_site_count,
       files_scanned,
       swallowed_count,
       rethrows_count,
       coalesce(f.run_id, '') AS finding_run_id,
       coalesce(f.source_context, 'other') AS source_context
ORDER BY
  CASE severity
    WHEN 'critical' THEN 0
    WHEN 'high' THEN 1
    WHEN 'medium' THEN 2
    WHEN 'low' THEN 3
    ELSE 4
  END,
  file,
  start_line,
  end_line
""".strip()


@dataclass(frozen=True)
class ErrorFinding:
    """Normalized error-handling finding."""

    file: str
    start_line: int
    end_line: int
    kind: str
    severity: str
    message: str
    rule_id: str
    source_context: str = "other"


@dataclass(frozen=True)
class CatchSite:
    """Inventory row for catch/try? surfaces."""

    file: str
    start_line: int
    end_line: int
    kind: str
    swallowed: bool
    rethrows: bool
    module: str


_SEMGREP_SEVERITY_MAP: dict[str, str] = {
    "CRITICAL": "critical",
    "ERROR": "high",
    "WARNING": "medium",
    "INFO": "informational",
}

_SEVERITY_RANK: dict[str, int] = {
    "critical": 0,
    "high": 1,
    "medium": 2,
    "low": 3,
    "informational": 4,
}

_DELETE_EXISTING_SNAPSHOT = """
MATCH (n)
WHERE (n:CatchSite OR n:ErrorFinding) AND n.project_id = $project_id
DETACH DELETE n
"""

_WRITE_CATCH_SITE = """
CREATE (c:CatchSite)
SET c.project_id = $project_id,
    c.file = $file,
    c.start_line = $start_line,
    c.end_line = $end_line,
    c.kind = $kind,
    c.swallowed = $swallowed,
    c.rethrows = $rethrows,
    c.module = $module,
    c.run_id = $run_id
"""

_WRITE_ERROR_FINDING = """
CREATE (f:ErrorFinding)
SET f.project_id = $project_id,
    f.kind = $kind,
    f.file = $file,
    f.start_line = $start_line,
    f.end_line = $end_line,
    f.severity = $severity,
    f.message = $message,
    f.source_context = $source_context,
    f.run_id = $run_id
"""


def _ehp_severity(raw: object) -> "Severity":
    from palace_mcp.audit.contracts import Severity

    mapping = {
        "CRITICAL": Severity.CRITICAL,
        "critical": Severity.CRITICAL,
        "ERROR": Severity.HIGH,
        "error": Severity.HIGH,
        "HIGH": Severity.HIGH,
        "high": Severity.HIGH,
        "WARNING": Severity.MEDIUM,
        "warning": Severity.MEDIUM,
        "MEDIUM": Severity.MEDIUM,
        "medium": Severity.MEDIUM,
        "LOW": Severity.LOW,
        "low": Severity.LOW,
        "INFO": Severity.INFORMATIONAL,
        "info": Severity.INFORMATIONAL,
        "INFORMATIONAL": Severity.INFORMATIONAL,
        "informational": Severity.INFORMATIONAL,
    }
    return mapping.get(str(raw), Severity.INFORMATIONAL)


class ErrorHandlingPolicyExtractor(BaseExtractor):
    """Error-handling anti-pattern extractor for Swift projects."""

    name: ClassVar[str] = "error_handling_policy"
    description: ClassVar[str] = (
        "Detect Swift error-handling anti-patterns and index catch/try? surfaces."
    )
    constraints: ClassVar[list[str]] = [
        "CREATE CONSTRAINT error_finding_unique IF NOT EXISTS "
        "FOR (f:ErrorFinding) REQUIRE "
        "(f.project_id, f.kind, f.file, f.start_line, f.end_line) IS UNIQUE",
        "CREATE CONSTRAINT catch_site_unique IF NOT EXISTS "
        "FOR (c:CatchSite) REQUIRE "
        "(c.project_id, c.file, c.start_line, c.end_line, c.kind) IS UNIQUE",
    ]
    indexes: ClassVar[list[str]] = [
        "CREATE INDEX error_finding_project IF NOT EXISTS "
        "FOR (f:ErrorFinding) ON (f.project_id)",
        "CREATE INDEX error_finding_severity IF NOT EXISTS "
        "FOR (f:ErrorFinding) ON (f.severity)",
        "CREATE INDEX catch_site_project IF NOT EXISTS "
        "FOR (c:CatchSite) ON (c.project_id)",
        "CREATE INDEX catch_site_module IF NOT EXISTS "
        "FOR (c:CatchSite) ON (c.project_id, c.module)",
    ]

    def audit_contract(self) -> "AuditContract":
        from palace_mcp.audit.contracts import AuditContract

        return AuditContract(
            extractor_name="error_handling_policy",
            template_name="error_handling_policy.md",
            query=_QUERY,
            severity_column="severity",
            severity_mapper=_ehp_severity,
        )

    async def run(
        self, *, graphiti: object, ctx: ExtractorRunContext
    ) -> ExtractorStats:
        from palace_mcp.mcp_server import get_settings

        settings = get_settings()
        assert settings is not None, "Palace settings not initialised"
        driver = graphiti.driver  # type: ignore[attr-defined]
        timeout_s = int(
            getattr(
                settings,
                "palace_error_handling_semgrep_timeout_s",
                getattr(settings, "palace_crypto_semgrep_timeout_s", 120),
            )
        )

        if not _RULES_DIR.exists():
            raise ExtractorConfigError(
                f"semgrep rules directory not found: {_RULES_DIR}"
            )

        rule_files = sorted(_RULES_DIR.glob("*.yaml")) + sorted(
            _RULES_DIR.glob("*.yml")
        )
        if not rule_files:
            raise ExtractorConfigError(f"no YAML rule files found in {_RULES_DIR}")

        logger.info(
            "error_handling_policy: running semgrep",
            extra={
                "project": ctx.project_slug,
                "rules_count": len(rule_files),
                "repo_path": str(ctx.repo_path),
            },
        )

        raw_findings = await _run_semgrep(
            rules_dir=_RULES_DIR,
            target=ctx.repo_path,
            timeout_s=timeout_s,
        )
        findings = _dedup_findings(
            _normalise_results(raw_findings, repo_root=ctx.repo_path)
        )
        findings = _apply_suppressions(repo_root=ctx.repo_path, findings=findings)
        findings = _apply_critical_path_severity(findings)
        catch_sites = _collect_catch_sites(ctx.repo_path)
        catch_sites = _mark_swallowed_sites(catch_sites=catch_sites, findings=findings)

        await _write_snapshot(
            driver,
            project_id=ctx.group_id,
            run_id=ctx.run_id,
            catch_sites=catch_sites,
            findings=findings,
        )

        logger.info(
            "error_handling_policy: complete",
            extra={
                "project": ctx.project_slug,
                "raw_findings": len(raw_findings),
                "findings_written": len(findings),
                "catch_sites_written": len(catch_sites),
            },
        )
        return ExtractorStats(
            nodes_written=len(findings) + len(catch_sites),
            edges_written=0,
        )


async def _run_semgrep(
    *,
    rules_dir: Path,
    target: Path,
    timeout_s: int,
) -> list[dict[str, Any]]:
    """Invoke semgrep as async subprocess and return raw results."""

    proc = await asyncio.create_subprocess_exec(
        "semgrep",
        "--config",
        str(rules_dir),
        "--json",
        "--quiet",
        str(target),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout_b, stderr_b = await asyncio.wait_for(
            proc.communicate(), timeout=timeout_s
        )
    except TimeoutError:
        proc.kill()
        await proc.wait()
        raise ExtractorConfigError(f"semgrep timed out after {timeout_s}s on {target}")

    if proc.returncode not in (0, 1):
        stderr_text = stderr_b.decode("utf-8", errors="replace")[:500]
        raise ExtractorConfigError(f"semgrep exited {proc.returncode}: {stderr_text}")

    try:
        output = json.loads(stdout_b.decode("utf-8", errors="replace"))
    except json.JSONDecodeError as exc:
        raise ExtractorConfigError(f"semgrep output not valid JSON: {exc}") from exc

    results = output.get("results", [])
    if not isinstance(results, list):
        raise ExtractorConfigError("semgrep output missing results list")
    return [item for item in results if isinstance(item, dict)]


def _normalise_severity(semgrep_severity: str) -> str:
    return _SEMGREP_SEVERITY_MAP.get(semgrep_severity.upper(), "informational")


def _normalise_results(
    raw: list[dict[str, Any]], *, repo_root: Path
) -> list[ErrorFinding]:
    from palace_mcp.extractors.foundation.source_context import classify

    findings: list[ErrorFinding] = []
    for result in raw:
        extra = result.get("extra", {})
        metadata = extra.get("metadata", {}) if isinstance(extra, dict) else {}
        start = result.get("start", {})
        end = result.get("end", {})
        path = _relative_file(repo_root, str(result.get("path", "")))
        start_line = int(start.get("line", 1)) if isinstance(start, dict) else 1
        end_line = (
            int(end.get("line", start_line)) if isinstance(end, dict) else start_line
        )
        rule_id = str(result.get("check_id", "unknown"))
        kind = str(metadata.get("kind", rule_id))
        severity = _normalise_severity(str(extra.get("severity", "INFO")))
        message = str(extra.get("message", ""))
        findings.append(
            ErrorFinding(
                file=path,
                start_line=start_line,
                end_line=end_line,
                kind=kind,
                severity=severity,
                message=message,
                rule_id=rule_id,
                source_context=classify(path),
            )
        )
    return findings


def _relative_file(repo_root: Path, path_str: str) -> str:
    raw_path = Path(path_str)
    if raw_path.is_absolute():
        try:
            return raw_path.relative_to(repo_root).as_posix()
        except ValueError:
            return raw_path.as_posix()
    return raw_path.as_posix()


def _dedup_findings(raw: list[ErrorFinding]) -> list[ErrorFinding]:
    """Coalesce same (file, line range, kind) keeping highest severity."""

    best: dict[tuple[str, int, int, str], ErrorFinding] = {}
    for finding in raw:
        key = (finding.file, finding.start_line, finding.end_line, finding.kind)
        existing = best.get(key)
        if existing is None or (
            _SEVERITY_RANK.get(finding.severity, 99)
            < _SEVERITY_RANK.get(existing.severity, 99)
        ):
            best[key] = finding
    return sorted(
        best.values(),
        key=lambda finding: (
            finding.file,
            finding.start_line,
            finding.end_line,
            finding.kind,
        ),
    )


def _apply_suppressions(
    *, repo_root: Path, findings: list[ErrorFinding]
) -> list[ErrorFinding]:
    """Downgrade findings with deliberate suppression markers."""

    updated: list[ErrorFinding] = []
    for finding in findings:
        if _has_suppression_marker(repo_root=repo_root, finding=finding):
            updated.append(replace(finding, severity="informational"))
            continue
        updated.append(finding)
    return updated


def _apply_critical_path_severity(findings: list[ErrorFinding]) -> list[ErrorFinding]:
    """Tune try? severity via B8 critical-path regex (GIM-283-4 Task 3.3).

    Applies only to try_optional_swallow / try_optional_in_crypto_path /
    nil_coalesce_swallows_error kinds.  Example/test source_context always
    forces LOW regardless of the path regex match.
    """
    result: list[ErrorFinding] = []
    for finding in findings:
        if finding.kind not in _TRY_OPTIONAL_KINDS:
            result.append(finding)
            continue
        if finding.source_context in {"example", "test"}:
            result.append(replace(finding, severity="low"))
            continue
        if _B8_CRITICAL_PATH_RE.search(finding.file):
            result.append(replace(finding, severity="medium"))
        else:
            result.append(replace(finding, severity="low"))
    return result


def _has_suppression_marker(*, repo_root: Path, finding: ErrorFinding) -> bool:
    target = repo_root / finding.file
    if not target.exists():
        return False

    start_line = max(1, finding.start_line - 1)
    end_line = max(finding.start_line, finding.end_line)
    with target.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if line_number > end_line:
                break
            if line_number < start_line:
                continue
            if any(marker in line for marker in _SUPPRESSION_MARKERS):
                return True
    return False


def _collect_catch_sites(repo_root: Path) -> list[CatchSite]:
    sites: list[CatchSite] = []
    for path in sorted(repo_root.rglob(_SWIFT_GLOB)):
        rel_path = path.relative_to(repo_root).as_posix()
        text = path.read_text(encoding="utf-8")
        module = _infer_module(rel_path)
        sites.extend(
            _collect_catch_block_sites(text=text, rel_path=rel_path, module=module)
        )
        sites.extend(
            _collect_try_optional_sites(text=text, rel_path=rel_path, module=module)
        )
    return _dedup_catch_sites(sites)


def _collect_catch_block_sites(
    *, text: str, rel_path: str, module: str
) -> list[CatchSite]:
    sites: list[CatchSite] = []
    for match in _CATCH_BLOCK_RE.finditer(text):
        body = match.group("body")
        start_line = _line_number(text, match.start())
        end_line = _line_number(text, match.end())
        sites.append(
            CatchSite(
                file=rel_path,
                start_line=start_line,
                end_line=end_line,
                kind="catch",
                swallowed=False,
                rethrows="throw" in body or "rethrow" in body,
                module=module,
            )
        )
    return sites


def _collect_try_optional_sites(
    *, text: str, rel_path: str, module: str
) -> list[CatchSite]:
    sites: list[CatchSite] = []
    for match in _TRY_OPTIONAL_RE.finditer(text):
        site_kind = (
            "nil_coalesce_try_optional" if "??" in match.group(0) else "try_optional"
        )
        sites.append(
            CatchSite(
                file=rel_path,
                start_line=_line_number(text, match.start()),
                end_line=_line_number(text, match.end()),
                kind=site_kind,
                swallowed=False,
                rethrows=False,
                module=module,
            )
        )
    return sites


def _dedup_catch_sites(sites: list[CatchSite]) -> list[CatchSite]:
    unique: dict[tuple[str, int, int, str], CatchSite] = {}
    for site in sites:
        unique[(site.file, site.start_line, site.end_line, site.kind)] = site
    return sorted(
        unique.values(),
        key=lambda site: (site.file, site.start_line, site.end_line, site.kind),
    )


def _line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _infer_module(rel_path: str) -> str:
    parts = Path(rel_path).parts
    for anchor in ("Sources", "Tests"):
        if anchor in parts:
            index = parts.index(anchor)
            if index + 1 < len(parts):
                return parts[index + 1]
    return Path(rel_path).parent.name or "root"


def _mark_swallowed_sites(
    *, catch_sites: list[CatchSite], findings: list[ErrorFinding]
) -> list[CatchSite]:
    updated: list[CatchSite] = []
    for site in catch_sites:
        swallowed = any(
            _finding_marks_swallowed(site=site, finding=finding) for finding in findings
        )
        updated.append(replace(site, swallowed=swallowed))
    return updated


def _finding_marks_swallowed(*, site: CatchSite, finding: ErrorFinding) -> bool:
    site_kind = _site_kind_for_finding(finding.kind)
    if site_kind is None:
        return False
    if finding.kind not in _SWALLOWING_KINDS:
        return False
    if site.file != finding.file or site.kind != site_kind:
        return False
    return not (
        site.end_line < finding.start_line or finding.end_line < site.start_line
    )


def _site_kind_for_finding(kind: str) -> str | None:
    if kind == "nil_coalesce_swallows_error":
        return "nil_coalesce_try_optional"
    if kind in {"try_optional_swallow", "try_optional_in_crypto_path"}:
        return "try_optional"
    if kind in {
        "empty_catch_block",
        "empty_catch_in_crypto_path",
        "catch_only_logs",
    }:
        return "catch"
    return None


async def _write_snapshot(
    driver: Any,
    *,
    project_id: str,
    run_id: str,
    catch_sites: list[CatchSite],
    findings: list[ErrorFinding],
) -> None:
    async with driver.session() as session:
        await session.execute_write(
            _replace_snapshot_tx,
            project_id,
            run_id,
            catch_sites,
            findings,
        )


async def _replace_snapshot_tx(
    tx: AsyncManagedTransaction,
    project_id: str,
    run_id: str,
    catch_sites: list[CatchSite],
    findings: list[ErrorFinding],
) -> None:
    delete_cursor = await tx.run(_DELETE_EXISTING_SNAPSHOT, project_id=project_id)
    await delete_cursor.consume()

    for site in catch_sites:
        cursor = await tx.run(
            _WRITE_CATCH_SITE,
            project_id=project_id,
            file=site.file,
            start_line=site.start_line,
            end_line=site.end_line,
            kind=site.kind,
            swallowed=site.swallowed,
            rethrows=site.rethrows,
            module=site.module,
            run_id=run_id,
        )
        await cursor.consume()

    for finding in findings:
        cursor = await tx.run(
            _WRITE_ERROR_FINDING,
            project_id=project_id,
            kind=finding.kind,
            file=finding.file,
            start_line=finding.start_line,
            end_line=finding.end_line,
            severity=finding.severity,
            message=finding.message,
            source_context=finding.source_context,
            run_id=run_id,
        )
        await cursor.consume()
