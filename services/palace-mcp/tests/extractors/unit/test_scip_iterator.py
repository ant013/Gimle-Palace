"""Tests for SCIP occurrence iteration."""

from __future__ import annotations

from pathlib import Path

from palace_mcp.extractors.foundation.models import SymbolKind
from palace_mcp.extractors.scip_parser import iter_scip_occurrences, parse_scip_file
from palace_mcp.proto import scip_pb2
from tests.extractors.fixtures.scip_factory import build_minimal_scip_index, write_scip_fixture


class TestIterScipOccurrences:
    def test_single_def(self, tmp_path: Path) -> None:
        index = build_minimal_scip_index(
            symbols=[("scip-python python example . MyClass .", 1)],
        )
        path = write_scip_fixture(index, tmp_path / "test.scip")
        parsed = parse_scip_file(path)
        occs = list(iter_scip_occurrences(parsed, commit_sha="abc123"))
        assert len(occs) == 1
        assert occs[0].kind == SymbolKind.DEF
        assert "MyClass" in occs[0].symbol_qualified_name
        assert occs[0].file_path == "src/example.py"
        assert occs[0].commit_sha == "abc123"

    def test_multiple_roles(self, tmp_path: Path) -> None:
        index = build_minimal_scip_index(
            symbols=[
                ("scip-python python example . func_a .", 1),
                ("scip-python python example . func_b .", 0),
            ],
        )
        path = write_scip_fixture(index, tmp_path / "test.scip")
        parsed = parse_scip_file(path)
        occs = list(iter_scip_occurrences(parsed, commit_sha="def456"))
        assert len(occs) == 2
        kinds = {o.kind for o in occs}
        assert SymbolKind.DEF in kinds or SymbolKind.USE in kinds

    def test_empty_index_yields_nothing(self, tmp_path: Path) -> None:
        index = scip_pb2.Index()  # type: ignore[attr-defined]
        path = write_scip_fixture(index, tmp_path / "empty.scip")
        parsed = parse_scip_file(path)
        occs = list(iter_scip_occurrences(parsed, commit_sha="000"))
        assert occs == []

    def test_vendor_path_detected(self, tmp_path: Path) -> None:
        index = build_minimal_scip_index(
            relative_path=".venv/lib/something.py",
            symbols=[("scip-python python venv . pkg .", 0)],
        )
        path = write_scip_fixture(index, tmp_path / "vendor.scip")
        parsed = parse_scip_file(path)
        occs = list(iter_scip_occurrences(parsed, commit_sha="v1"))
        assert len(occs) == 1
        assert ".venv/" in occs[0].file_path

    def test_local_symbols_skipped(self, tmp_path: Path) -> None:
        index = build_minimal_scip_index(
            symbols=[
                ("local x", 1),
                ("scip-python python example . real_func .", 1),
            ],
        )
        path = write_scip_fixture(index, tmp_path / "local.scip")
        parsed = parse_scip_file(path)
        occs = list(iter_scip_occurrences(parsed, commit_sha="l1"))
        assert len(occs) == 1
        assert "real_func" in occs[0].symbol_qualified_name
