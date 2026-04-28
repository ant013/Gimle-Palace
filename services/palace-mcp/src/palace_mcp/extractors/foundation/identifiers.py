"""Deterministic symbol identifier — blake2b → signed i64 (GIM-101a, T3).

Python-pro Finding F-A: blake2b raw u64 overflows Tantivy i64 on ~50% of
hashes. Fixed by reinterpreting as two's-complement signed i64.

Python-pro Finding F-B: byte order documented as big-endian (network order).
All language bindings that implement symbol_id_for MUST use big-endian +
signed-i64 reinterpretation, or cross-language symbol_id joins produce
silent zero matches.
"""

from __future__ import annotations

import hashlib


def symbol_id_for(qualified_name: str) -> int:
    """Return a 64-bit deterministic signed i64 identifier for qualified_name.

    Input format: version-stripped qualified_name '<package-name> <descriptor-chain>'
    (Q1 FQN decision, GIM-105 Variant B). The version token is stripped by
    _extract_qualified_name() before this call so symbols from different library
    versions map to the same identifier.

    Byte order: big-endian (network order). Survives process restart.

    Cross-language invariant: Kotlin, Swift, Rust extractors (Slices 102+)
    MUST use big-endian + signed-i64 interpretation when reimplementing this
    function. Unsigned u64 interpretation breaks on ~50% of hashes because
    Tantivy stores integer fast fields as i64.
    """
    raw = int.from_bytes(
        hashlib.blake2b(qualified_name.encode("utf-8"), digest_size=8).digest(),
        "big",
    )
    # Reinterpret raw u64 as signed i64 via two's-complement (F-A fix).
    return raw if raw < 2**63 else raw - 2**64
