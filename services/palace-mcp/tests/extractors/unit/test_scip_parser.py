"""Tests for SCIP parser and FindScipPath resolver."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from palace_mcp.extractors.scip_parser import (
    FindScipPath,
    ScipFileTooLargeError,
    ScipParseError,
    ScipPathRequiredError,
    parse_scip_file,
)


class TestFindScipPath:
    def test_override_takes_precedence(self) -> None:
        settings = MagicMock()
        settings.palace_scip_index_paths = {"gimle": "/default/path.scip"}
        result = FindScipPath.resolve("gimle", settings, override="/override/path.scip")
        assert result == Path("/override/path.scip")

    def test_settings_dict_lookup(self) -> None:
        settings = MagicMock()
        settings.palace_scip_index_paths = {"gimle": "/repos/gimle/scip/index.scip"}
        result = FindScipPath.resolve("gimle", settings)
        assert result == Path("/repos/gimle/scip/index.scip")

    def test_missing_project_raises(self) -> None:
        settings = MagicMock()
        settings.palace_scip_index_paths = {}
        with pytest.raises(ScipPathRequiredError) as exc_info:
            FindScipPath.resolve("unknown_project", settings)
        assert "unknown_project" in str(exc_info.value)
        assert exc_info.value.error_code == "scip_path_required"


class TestParseScipFile:
    def test_file_too_large_raises(self, tmp_path: Path) -> None:
        big_file = tmp_path / "big.scip"
        big_file.write_bytes(b"\x00" * (2 * 1024 * 1024))
        with pytest.raises(ScipFileTooLargeError) as exc_info:
            parse_scip_file(big_file, max_size_mb=1)
        assert exc_info.value.cap_mb == 1

    def test_corrupt_protobuf_raises(self, tmp_path: Path) -> None:
        bad_file = tmp_path / "bad.scip"
        bad_file.write_bytes(b"\xff\xfe\xfd\xfc" * 100)
        with pytest.raises(ScipParseError):
            parse_scip_file(bad_file)

    def test_valid_empty_index(self, tmp_path: Path) -> None:
        empty_file = tmp_path / "empty.scip"
        empty_file.write_bytes(b"")
        result = parse_scip_file(empty_file)
        assert len(result.documents) == 0

    def test_nonexistent_file_raises(self, tmp_path: Path) -> None:
        missing = tmp_path / "missing.scip"
        with pytest.raises(FileNotFoundError):
            parse_scip_file(missing)
