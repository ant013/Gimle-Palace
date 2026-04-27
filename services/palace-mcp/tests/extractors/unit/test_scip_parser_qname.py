"""Tests for _extract_qualified_name() version-strip (Q1 FQN decision, GIM-105)."""

from __future__ import annotations

from palace_mcp.extractors.scip_parser import _extract_qualified_name


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
