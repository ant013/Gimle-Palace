"""crypto_domain_model extractor — Roadmap #40, GIM-239.

Scans Swift source files with semgrep custom rules and writes
:CryptoFinding nodes to Neo4j for the audit report pipeline.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

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

_QUERY = """
MATCH (f:CryptoFinding {project_id: $project_id})
RETURN f.kind AS kind,
       f.severity AS severity,
       f.file AS file,
       f.start_line AS start_line,
       f.end_line AS end_line,
       f.message AS message,
       f.run_id AS run_id
ORDER BY
  CASE f.severity
    WHEN 'critical' THEN 0
    WHEN 'high' THEN 1
    WHEN 'medium' THEN 2
    WHEN 'low' THEN 3
    ELSE 4
  END,
  f.file,
  f.start_line
""".strip()


def _crypto_severity(raw: Any) -> "Severity":
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
        "INFO": Severity.INFORMATIONAL,
        "info": Severity.INFORMATIONAL,
        "LOW": Severity.LOW,
        "low": Severity.LOW,
    }
    return mapping.get(str(raw), Severity.INFORMATIONAL)


class CryptoDomainModelExtractor(BaseExtractor):
    name: ClassVar[str] = "crypto_domain_model"
    description: ClassVar[str] = (
        "Roadmap #40 — Crypto Domain Model. "
        "Runs semgrep custom rules on Swift source and writes :CryptoFinding nodes."
    )
    constraints: ClassVar[list[str]] = [
        "CREATE CONSTRAINT crypto_finding_unique IF NOT EXISTS "
        "FOR (f:CryptoFinding) REQUIRE "
        "(f.project_id, f.kind, f.file, f.start_line, f.end_line) IS UNIQUE",
    ]
    indexes: ClassVar[list[str]] = [
        "CREATE INDEX crypto_finding_project IF NOT EXISTS "
        "FOR (f:CryptoFinding) ON (f.project_id)",
        "CREATE INDEX crypto_finding_severity IF NOT EXISTS "
        "FOR (f:CryptoFinding) ON (f.severity)",
    ]

    def audit_contract(self) -> "AuditContract":
        from palace_mcp.audit.contracts import AuditContract

        return AuditContract(
            extractor_name="crypto_domain_model",
            template_name="crypto_domain_model.md",
            query=_QUERY,
            severity_column="severity",
            severity_mapper=_crypto_severity,
        )

    async def run(  # fmt: skip
        self, *, graphiti: object, ctx: ExtractorRunContext
    ) -> ExtractorStats:
        from palace_mcp.mcp_server import get_settings

        settings = get_settings()
        assert settings is not None, "Palace settings not initialised"
        driver = graphiti.driver  # type: ignore[attr-defined]

        timeout_s: int = getattr(settings, "palace_crypto_semgrep_timeout_s", 120)

        if not _RULES_DIR.exists():
            raise ExtractorConfigError(
                f"semgrep rules directory not found: {_RULES_DIR}"
            )

        rule_files = list(_RULES_DIR.glob("*.yaml")) + list(_RULES_DIR.glob("*.yml"))
        if not rule_files:
            raise ExtractorConfigError(f"no YAML rule files found in {_RULES_DIR}")

        logger.info(
            "crypto_domain_model: running semgrep",
            extra={
                "project": ctx.project_slug,
                "rules_count": len(rule_files),
                "repo_path": str(ctx.repo_path),
            },
        )

        findings = await _run_semgrep(
            rules_dir=_RULES_DIR,
            target=ctx.repo_path,
            timeout_s=timeout_s,
        )

        # Deduplicate: coalesce per (file, start_line, end_line, kind), keep
        # highest severity (D5 decision).
        deduped = _dedup_findings(findings)

        nodes_written = 0
        for finding in deduped:
            await _write_finding(
                driver,
                project_id=ctx.group_id,
                run_id=ctx.run_id,
                finding=finding,
            )
            nodes_written += 1

        logger.info(
            "crypto_domain_model: complete",
            extra={
                "project": ctx.project_slug,
                "raw_findings": len(findings),
                "written": nodes_written,
            },
        )
        return ExtractorStats(nodes_written=nodes_written, edges_written=0)


async def _run_semgrep(
    *,
    rules_dir: Path,
    target: Path,
    timeout_s: int,
) -> list[dict[str, Any]]:
    """Invoke semgrep as async subprocess; return list of raw result dicts."""
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
        raise ExtractorConfigError(
            f"semgrep timed out after {timeout_s}s on {target}"
        )

    if proc.returncode not in (0, 1):
        stderr_text = stderr_b.decode("utf-8", errors="replace")[:500]
        raise ExtractorConfigError(
            f"semgrep exited {proc.returncode}: {stderr_text}"
        )

    try:
        output = json.loads(stdout_b.decode("utf-8", errors="replace"))
    except json.JSONDecodeError as exc:
        raise ExtractorConfigError(f"semgrep output not valid JSON: {exc}") from exc

    results: list[dict[str, Any]] = output.get("results", [])
    return results


_SEMGREP_SEVERITY_MAP: dict[str, str] = {
    "ERROR": "high",
    "WARNING": "medium",
    "INFO": "informational",
}


def _normalise_severity(semgrep_severity: str) -> str:
    return _SEMGREP_SEVERITY_MAP.get(semgrep_severity.upper(), "informational")


_SEVERITY_RANK: dict[str, int] = {
    "critical": 0,
    "high": 1,
    "medium": 2,
    "low": 3,
    "informational": 4,
}


def _dedup_findings(
    raw: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Coalesce findings per (file, start_line, end_line, kind), keep highest severity."""
    best: dict[tuple[str, int, int, str], dict[str, Any]] = {}
    for r in raw:
        path = r.get("path", "")
        start = r.get("start", {}).get("line", 0)
        end = r.get("end", {}).get("line", start)
        rule_id = r.get("check_id", "unknown")
        # Extract kind from metadata if present
        kind = r.get("extra", {}).get("metadata", {}).get("kind", rule_id)
        raw_sev = r.get("extra", {}).get("severity", "WARNING")
        severity = _normalise_severity(raw_sev)
        key = (path, start, end, kind)
        existing = best.get(key)
        if existing is None or (
            _SEVERITY_RANK.get(severity, 99)
            < _SEVERITY_RANK.get(existing["severity"], 99)
        ):
            best[key] = {
                "path": path,
                "start_line": start,
                "end_line": end,
                "kind": kind,
                "severity": severity,
                "message": r.get("extra", {}).get("message", ""),
                "rule_id": rule_id,
            }
    return list(best.values())


async def _write_finding(
    driver: Any,
    *,
    project_id: str,
    run_id: str,
    finding: dict[str, Any],
) -> None:
    async with driver.session() as session:
        await session.run(
            """
MERGE (f:CryptoFinding {
    project_id: $project_id,
    kind: $kind,
    file: $file,
    start_line: $start_line,
    end_line: $end_line
})
SET f.severity = $severity,
    f.message = $message,
    f.run_id = $run_id
""",
            project_id=project_id,
            kind=finding["kind"],
            file=finding["path"],
            start_line=finding["start_line"],
            end_line=finding["end_line"],
            severity=finding["severity"],
            message=finding["message"],
            run_id=run_id,
        )
