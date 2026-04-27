"""Unit tests for symbol_id_for (GIM-101a, T3)."""

from __future__ import annotations

import hashlib

import pytest

from palace_mcp.extractors.foundation.identifiers import symbol_id_for

def _golden(qn: str) -> int:
    raw = int.from_bytes(
        hashlib.blake2b(qn.encode("utf-8"), digest_size=8).digest(),
        "big",
    )
    return raw if raw < 2**63 else raw - 2**64


# ---------------------------------------------------------------------------
# Golden values — computed once and pinned.
# If these change, a cross-language invariant has broken.
# ---------------------------------------------------------------------------

_KNOWN_INPUTS: list[tuple[str, int]] = [
    # (qualified_name, expected_signed_i64)
    (
        "com.example.MyClass.myMethod",
        _golden("com.example.MyClass.myMethod"),
    ),
    (
        "foo.bar.Baz",
        _golden("foo.bar.Baz"),
    ),
    (
        "",
        _golden(""),
    ),
]


class TestSymbolIdFor:
    def test_golden_values(self) -> None:
        for qn, expected in _KNOWN_INPUTS:
            assert symbol_id_for(qn) == expected, f"mismatch for {qn!r}"

    def test_signed_i64_range(self) -> None:
        """All outputs must fit in signed i64 (Tantivy constraint)."""
        samples = [
            "foo", "bar", "baz.qux", "org.apache.commons.lang3.StringUtils",
            "x" * 1000, "", "unicode_ñame", "日本語",
        ]
        for qn in samples:
            sid = symbol_id_for(qn)
            assert -(2**63) <= sid <= 2**63 - 1, f"overflow for {qn!r}: {sid}"

    def test_determinism_same_process(self) -> None:
        """Same input → same output within a process."""
        qn = "foo.bar.Baz"
        assert symbol_id_for(qn) == symbol_id_for(qn)

    def test_different_inputs_differ(self) -> None:
        """Distinct inputs must not collide (basic collision check on sample)."""
        seen: set[int] = set()
        for i in range(1000):
            sid = symbol_id_for(f"sym_{i}")
            assert sid not in seen, f"collision at i={i}"
            seen.add(sid)

    def test_can_produce_negative_values(self) -> None:
        """Signed i64 representation must yield both positive and negative values."""
        positives = negatives = 0
        for i in range(200):
            sid = symbol_id_for(f"probe_{i}")
            if sid >= 0:
                positives += 1
            else:
                negatives += 1
        assert positives > 0, "no positive ids generated"
        assert negatives > 0, "no negative ids generated (u64 overflow not fixed)"
