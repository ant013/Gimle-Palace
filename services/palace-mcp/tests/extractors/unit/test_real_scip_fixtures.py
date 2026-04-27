"""Integration tests using real .scip fixture files (ts-mini-project, py-mini-project).

These tests parse the pre-built SCIP binaries and verify actual symbol extraction
behaviour — both language detection and qualified_name format.

Markers:
  requires_scip_typescript — skipped if ts-mini-project/index.scip is missing
  requires_scip_python     — skipped if py-mini-project/index.scip is missing
"""

from __future__ import annotations

from pathlib import Path

import pytest

from palace_mcp.extractors.foundation.models import Language, SymbolKind
from palace_mcp.extractors.scip_parser import iter_scip_occurrences, parse_scip_file

FIXTURES = Path(__file__).parent.parent / "fixtures"
TS_SCIP = FIXTURES / "ts-mini-project" / "index.scip"
PY_SCIP = FIXTURES / "py-mini-project" / "index.scip"

requires_scip_typescript = pytest.mark.skipif(
    not TS_SCIP.exists(), reason="ts-mini-project/index.scip not present"
)
requires_scip_python = pytest.mark.skipif(
    not PY_SCIP.exists(), reason="py-mini-project/index.scip not present"
)


@requires_scip_typescript
class TestTsMiniProjectFixture:
    def test_parses_without_error(self) -> None:
        index = parse_scip_file(TS_SCIP)
        assert index is not None

    def test_yields_typescript_occurrences(self) -> None:
        index = parse_scip_file(TS_SCIP)
        occs = list(iter_scip_occurrences(index, commit_sha="test"))
        ts_occs = [o for o in occs if o.language == Language.TYPESCRIPT]
        assert len(ts_occs) > 0, "Expected at least one TypeScript occurrence"

    def test_has_def_occurrences(self) -> None:
        index = parse_scip_file(TS_SCIP)
        occs = list(iter_scip_occurrences(index, commit_sha="test"))
        defs = [o for o in occs if o.kind == SymbolKind.DEF]
        assert len(defs) > 0, "Expected at least one DEF occurrence"

    def test_greeter_class_def_present(self) -> None:
        index = parse_scip_file(TS_SCIP)
        occs = list(iter_scip_occurrences(index, commit_sha="test"))
        names = {o.symbol_qualified_name for o in occs if o.kind == SymbolKind.DEF}
        greeter_defs = [n for n in names if "Greeter" in n]
        assert greeter_defs, f"Expected Greeter def in {names!r}"

    def test_qualified_names_have_no_version(self) -> None:
        index = parse_scip_file(TS_SCIP)
        occs = list(iter_scip_occurrences(index, commit_sha="test"))
        for occ in occs:
            parts = occ.symbol_qualified_name.split(" ")
            for part in parts:
                assert not (part.count(".") >= 2 and part[0].isdigit()), (
                    f"Possible version token in qualified_name: {occ.symbol_qualified_name!r}"
                )

    def test_has_use_occurrences(self) -> None:
        index = parse_scip_file(TS_SCIP)
        occs = list(iter_scip_occurrences(index, commit_sha="test"))
        uses = [o for o in occs if o.kind == SymbolKind.USE]
        assert len(uses) > 0, "Expected at least one USE occurrence in index.ts"


@requires_scip_python
class TestPyMiniProjectFixture:
    def test_parses_without_error(self) -> None:
        index = parse_scip_file(PY_SCIP)
        assert index is not None

    def test_yields_python_occurrences(self) -> None:
        index = parse_scip_file(PY_SCIP)
        occs = list(iter_scip_occurrences(index, commit_sha="test"))
        py_occs = [o for o in occs if o.language == Language.PYTHON]
        assert len(py_occs) > 0, "Expected at least one Python occurrence"

    def test_has_def_occurrences(self) -> None:
        index = parse_scip_file(PY_SCIP)
        occs = list(iter_scip_occurrences(index, commit_sha="test"))
        defs = [o for o in occs if o.kind == SymbolKind.DEF]
        assert len(defs) > 0, "Expected at least one DEF occurrence"

    def test_greeter_class_def_present(self) -> None:
        index = parse_scip_file(PY_SCIP)
        occs = list(iter_scip_occurrences(index, commit_sha="test"))
        names = {o.symbol_qualified_name for o in occs if o.kind == SymbolKind.DEF}
        greeter_defs = [n for n in names if "Greeter" in n]
        assert greeter_defs, f"Expected Greeter def in {names!r}"

    def test_qualified_names_have_no_version(self) -> None:
        index = parse_scip_file(PY_SCIP)
        occs = list(iter_scip_occurrences(index, commit_sha="test"))
        for occ in occs:
            parts = occ.symbol_qualified_name.split(" ")
            for part in parts:
                assert not (part.count(".") >= 2 and part[0].isdigit()), (
                    f"Possible version token in qualified_name: {occ.symbol_qualified_name!r}"
                )
