"""Stable identifiers for the dead_symbol_binary_surface extractor."""

from __future__ import annotations

import hashlib

from palace_mcp.extractors.dead_symbol_binary_surface.models import (
    DeadSymbolEvidenceSource,
    DeadSymbolLanguage,
)


def dead_symbol_id_for(
    *,
    group_id: str,
    project: str,
    language: DeadSymbolLanguage,
    module_name: str,
    symbol_key: str,
    commit_sha: str,
    evidence_source: DeadSymbolEvidenceSource,
) -> str:
    """Build a stable 128-bit hex candidate ID.

    `schema_version` is intentionally excluded so schema migrations can update
    properties without forking candidate identity.
    """

    payload = "||".join(
        (
            group_id,
            project,
            language.value,
            module_name,
            symbol_key,
            commit_sha,
            evidence_source.value,
        )
    )
    return hashlib.blake2b(payload.encode("utf-8"), digest_size=16).hexdigest()
