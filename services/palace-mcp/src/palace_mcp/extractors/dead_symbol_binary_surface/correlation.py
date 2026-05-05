"""Correlation helpers for dead_symbol_binary_surface."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from palace_mcp.extractors.dead_symbol_binary_surface.identifiers import (
    dead_symbol_id_for,
)
from palace_mcp.extractors.dead_symbol_binary_surface.models import (
    BinarySurfaceRecord,
    BinarySurfaceSource,
    CandidateState,
    Confidence,
    DeadSymbolCandidate,
    DeadSymbolEvidenceMode,
    DeadSymbolEvidenceSource,
    SkipReason,
    SurfaceKind,
)
from palace_mcp.extractors.dead_symbol_binary_surface.parsers.periphery import (
    PeripheryFinding,
)
from palace_mcp.extractors.foundation.identifiers import symbol_id_for
from palace_mcp.extractors.foundation.models import (
    PublicApiSymbol,
    PublicApiVisibility,
    SymbolOccurrenceShadow,
)


@dataclass(frozen=True)
class BlockedContractSymbol:
    """Copied per-symbol provenance for GIM-192 contract blockers."""

    public_symbol_id: str
    contract_snapshot_id: str
    consumer_module_name: str
    producer_module_name: str
    commit_sha: str
    use_count: int
    evidence_paths_sample: tuple[str, ...]


@dataclass(frozen=True)
class CorrelationResult:
    """Pure correlation output before writer/orchestrator logic."""

    candidate: DeadSymbolCandidate | None
    binary_surface: BinarySurfaceRecord | None
    backed_symbol_id: int | None
    backed_public_api_symbol_id: str | None
    blocked_contract_symbols: tuple[BlockedContractSymbol, ...]


def correlate_finding(
    *,
    finding: PeripheryFinding,
    group_id: str,
    project: str,
    commit_sha: str,
    public_api_symbols: tuple[PublicApiSymbol, ...],
    symbol_shadows: tuple[SymbolOccurrenceShadow, ...],
    blocked_contract_symbols: tuple[BlockedContractSymbol, ...],
) -> CorrelationResult:
    """Correlate one parsed dead-symbol finding against indexed facts."""

    if finding.candidate_state is CandidateState.SKIPPED:
        candidate = _build_candidate(
            finding=finding,
            group_id=group_id,
            project=project,
            commit_sha=commit_sha,
            confidence=Confidence.LOW,
            candidate_state=CandidateState.SKIPPED,
            skip_reason=finding.skip_reason,
        )
        return CorrelationResult(
            candidate=candidate,
            binary_surface=None,
            backed_symbol_id=None,
            backed_public_api_symbol_id=None,
            blocked_contract_symbols=(),
        )

    public_matches = _matching_public_api_symbols(
        finding=finding,
        public_api_symbols=public_api_symbols,
    )
    shadow_matches = _matching_symbol_shadows(
        finding=finding,
        symbol_shadows=symbol_shadows,
    )

    if len(public_matches) > 1 or len(shadow_matches) > 1:
        candidate = _build_candidate(
            finding=finding,
            group_id=group_id,
            project=project,
            commit_sha=commit_sha,
            confidence=Confidence.LOW,
            candidate_state=CandidateState.SKIPPED,
            skip_reason=SkipReason.AMBIGUOUS_SYMBOL_MATCH,
        )
        return CorrelationResult(
            candidate=candidate,
            binary_surface=None,
            backed_symbol_id=None,
            backed_public_api_symbol_id=None,
            blocked_contract_symbols=(),
        )

    public_match = public_matches[0] if public_matches else None
    shadow_match = shadow_matches[0] if shadow_matches else None
    matching_blockers = _matching_blocked_contracts(
        public_symbol_id=public_match.id if public_match is not None else None,
        blocked_contract_symbols=blocked_contract_symbols,
    )

    if not finding.symbol_key:
        if finding.source_file and finding.source_line > 0:
            candidate = _build_candidate(
                finding=finding,
                group_id=group_id,
                project=project,
                commit_sha=commit_sha,
                confidence=Confidence.LOW,
                candidate_state=CandidateState.UNUSED_CANDIDATE,
                skip_reason=None,
            )
            return CorrelationResult(
                candidate=candidate,
                binary_surface=None,
                backed_symbol_id=None,
                backed_public_api_symbol_id=None,
                blocked_contract_symbols=(),
            )
        candidate = _build_candidate(
            finding=finding,
            group_id=group_id,
            project=project,
            commit_sha=commit_sha,
            confidence=Confidence.LOW,
            candidate_state=CandidateState.SKIPPED,
            skip_reason=SkipReason.MISSING_SYMBOL_KEY,
        )
        return CorrelationResult(
            candidate=candidate,
            binary_surface=None,
            backed_symbol_id=None,
            backed_public_api_symbol_id=None,
            blocked_contract_symbols=(),
        )

    candidate_state = CandidateState.UNUSED_CANDIDATE
    skip_reason: SkipReason | None = None
    binary_surface: BinarySurfaceRecord | None = None
    confidence = Confidence.HIGH if (public_match or shadow_match) else Confidence.LOW

    if public_match is not None and public_match.visibility in (
        PublicApiVisibility.PUBLIC,
        PublicApiVisibility.OPEN,
    ):
        candidate_state = CandidateState.RETAINED_PUBLIC_API
        skip_reason = SkipReason.PUBLIC_API_RETAINED
        binary_surface = _build_binary_surface(
            finding=finding,
            group_id=group_id,
            project=project,
            commit_sha=commit_sha,
        )

    if matching_blockers:
        skip_reason = SkipReason.CROSS_MODULE_CONTRACT_CONSUMED

    candidate = _build_candidate(
        finding=finding,
        group_id=group_id,
        project=project,
        commit_sha=commit_sha,
        confidence=confidence,
        candidate_state=candidate_state,
        skip_reason=skip_reason,
    )
    return CorrelationResult(
        candidate=candidate,
        binary_surface=binary_surface,
        backed_symbol_id=shadow_match.symbol_id if shadow_match is not None else None,
        backed_public_api_symbol_id=public_match.id
        if public_match is not None
        else None,
        blocked_contract_symbols=matching_blockers,
    )


def _matching_public_api_symbols(
    *,
    finding: PeripheryFinding,
    public_api_symbols: tuple[PublicApiSymbol, ...],
) -> tuple[PublicApiSymbol, ...]:
    return tuple(
        symbol
        for symbol in public_api_symbols
        if symbol.symbol_qualified_name == finding.symbol_key
        and symbol.language.value == finding.language.value
        and symbol.module_name == finding.module_name
    )


def _matching_symbol_shadows(
    *,
    finding: PeripheryFinding,
    symbol_shadows: tuple[SymbolOccurrenceShadow, ...],
) -> tuple[SymbolOccurrenceShadow, ...]:
    if not finding.symbol_key:
        return ()
    expected_symbol_id = symbol_id_for(finding.symbol_key)
    return tuple(
        shadow
        for shadow in symbol_shadows
        if shadow.symbol_id == expected_symbol_id
        and shadow.symbol_qualified_name == finding.symbol_key
        and (shadow.language is None or shadow.language.value == finding.language.value)
    )


def _matching_blocked_contracts(
    *,
    public_symbol_id: str | None,
    blocked_contract_symbols: tuple[BlockedContractSymbol, ...],
) -> tuple[BlockedContractSymbol, ...]:
    if public_symbol_id is None:
        return ()
    return tuple(
        edge
        for edge in blocked_contract_symbols
        if edge.public_symbol_id == public_symbol_id
    )


def _build_candidate(
    *,
    finding: PeripheryFinding,
    group_id: str,
    project: str,
    commit_sha: str,
    confidence: Confidence,
    candidate_state: CandidateState,
    skip_reason: SkipReason | None,
) -> DeadSymbolCandidate:
    symbol_key = _candidate_symbol_key(finding)
    return DeadSymbolCandidate(
        id=dead_symbol_id_for(
            group_id=group_id,
            project=project,
            language=finding.language,
            module_name=finding.module_name,
            symbol_key=symbol_key,
            commit_sha=commit_sha,
            evidence_source=DeadSymbolEvidenceSource.PERIPHERY,
        ),
        group_id=group_id,
        project=project,
        module_name=finding.module_name,
        language=finding.language,
        commit_sha=commit_sha,
        symbol_key=symbol_key,
        display_name=finding.display_name,
        kind=finding.kind,
        source_file=finding.source_file or None,
        source_line=finding.source_line if finding.source_line > 0 else None,
        evidence_source=DeadSymbolEvidenceSource.PERIPHERY,
        evidence_mode=DeadSymbolEvidenceMode.STATIC,
        confidence=confidence,
        candidate_state=candidate_state,
        skip_reason=skip_reason,
    )


def _build_binary_surface(
    *,
    finding: PeripheryFinding,
    group_id: str,
    project: str,
    commit_sha: str,
) -> BinarySurfaceRecord:
    payload = "||".join(
        (
            group_id,
            project,
            finding.module_name,
            finding.symbol_key,
            commit_sha,
            SurfaceKind.PUBLIC_API.value,
        )
    )
    return BinarySurfaceRecord(
        id=hashlib.blake2b(payload.encode("utf-8"), digest_size=16).hexdigest(),
        group_id=group_id,
        project=project,
        module_name=finding.module_name,
        language=finding.language,
        commit_sha=commit_sha,
        symbol_key=_candidate_symbol_key(finding),
        surface_kind=SurfaceKind.PUBLIC_API,
        retention_reason="public/open API symbol retained from public_api_surface",
        source=BinarySurfaceSource.PUBLIC_API_SURFACE,
    )


def _candidate_symbol_key(finding: PeripheryFinding) -> str:
    if finding.symbol_key:
        return finding.symbol_key
    if finding.source_file and finding.source_line > 0:
        return f"{finding.display_name}@{finding.source_file}:{finding.source_line}"
    return f"missing::{finding.display_name}"
