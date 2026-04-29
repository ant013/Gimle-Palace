"""Tests for _extract_qualified_name() version-strip (Q1 FQN decision, GIM-105)."""

from __future__ import annotations

from palace_mcp.extractors.scip_parser import (
    _extract_qualified_name,
    _split_scip_top_level,
)


class TestExtractQualifiedName:
    def test_python_symbol_strips_version(self) -> None:
        """Same symbol from different versions must yield same qualified_name."""
        sym_v1 = "scip-python python requests 2.0.0 `requests.api`/get()."
        sym_v2 = "scip-python python requests 2.1.0 `requests.api`/get()."
        qn1 = _extract_qualified_name(sym_v1)
        qn2 = _extract_qualified_name(sym_v2)
        assert qn1 == qn2
        assert "2.0.0" not in qn1
        assert "2.1.0" not in qn2
        assert qn1 == "requests `requests.api`/get()."

    def test_typescript_symbol_strips_version(self) -> None:
        sym = "scip-typescript npm syntax 1.0.0 src/`class.ts`/Class#method()."
        qn = _extract_qualified_name(sym)
        assert "1.0.0" not in qn
        assert qn == "syntax src/`class.ts`/Class#method()."

    def test_scoped_npm_package(self) -> None:
        sym = "scip-typescript npm @example/a 1.0.0 src/`index.ts`/a()."
        qn = _extract_qualified_name(sym)
        assert qn == "@example/a src/`index.ts`/a()."

    def test_python_stdlib(self) -> None:
        sym = "scip-python python python-stdlib 3.11 builtins/int#"
        qn = _extract_qualified_name(sym)
        assert qn == "python-stdlib builtins/int#"

    def test_short_symbol_passthrough(self) -> None:
        """Malformed symbols with <5 parts pass through unchanged."""
        sym = "scip-python python only-three"
        qn = _extract_qualified_name(sym)
        assert qn == sym


class TestSplitScipTopLevel:
    """Backtick-aware top-level split (GIM-123).

    Preempts scip-clang and any future indexer that emits identifiers with
    embedded spaces wrapped in backticks (e.g. C++ operator overloads like
    ``operator T()``).
    """

    def test_naive_case_matches_split(self) -> None:
        # No backticks anywhere — output identical to str.split(' ').
        sym = "scip-python python pkg 1.0 a/b"
        assert _split_scip_top_level(sym) == ["scip-python", "python", "pkg", "1.0", "a/b"]

    def test_backtick_with_internal_dot_kept_whole(self) -> None:
        # Real scip-python pattern: dotted name in escape, no spaces.
        sym = "scip-python python requests 2.0.0 `requests.api`/get()."
        parts = _split_scip_top_level(sym)
        assert parts == [
            "scip-python",
            "python",
            "requests",
            "2.0.0",
            "`requests.api`/get().",
        ]

    def test_backtick_with_internal_space_kept_whole(self) -> None:
        # Hypothetical scip-clang pattern: operator with embedded space.
        sym = "scip-clang  . . `operator T()`#"
        parts = _split_scip_top_level(sym)
        # Expect 5 parts: scheme + empty manager + empty pkg + empty version + descriptor.
        assert parts == ["scip-clang", "", ".", ".", "`operator T()`#"]

    def test_doubled_backtick_is_literal(self) -> None:
        # Doubled backtick inside escape = literal backtick, doesn't toggle mode.
        # Token is a single escaped identifier "with ` quoted in".
        sym = "x y `weird``name with space` z"
        parts = _split_scip_top_level(sym)
        assert parts == ["x", "y", "`weird``name with space`", "z"]

    def test_extract_qualified_name_handles_embedded_space(self) -> None:
        # End-to-end: extract should not fragment escaped identifier with space.
        sym = "scip-clang  . . `operator T()`#"
        qn = _extract_qualified_name(sym)
        # parts[2]='.', parts[4:]=['`operator T()`#'] -> '. `operator T()`#'
        assert qn == ". `operator T()`#"
