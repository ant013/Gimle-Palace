"""Step 5: Severity ranking (pure function)."""

from __future__ import annotations

from palace_mcp.extractors.dead_code.models import FindingKind, Severity


def rank_severity(finding_kind: FindingKind | str) -> Severity:
    """Map finding kind to severity per spec §G0d rev3.2 Step 5.

    critical: dead module
    high: SCC cluster (>= 3 classes)
    medium: extension chain
    low: single symbol
    """
    kind = FindingKind(finding_kind) if isinstance(finding_kind, str) else finding_kind
    return _SEVERITY_MAP[kind]


_SEVERITY_MAP: dict[FindingKind, Severity] = {
    FindingKind.DEAD_MODULE: Severity.CRITICAL,
    FindingKind.DEAD_SCC_CLUSTER: Severity.HIGH,
    FindingKind.DEAD_EXTENSION_CHAIN: Severity.MEDIUM,
    FindingKind.DEAD_SYMBOL: Severity.LOW,
}
