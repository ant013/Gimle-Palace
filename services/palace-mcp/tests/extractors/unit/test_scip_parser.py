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
    _extract_qualified_name,
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


@pytest.mark.parametrize(
    "symbol, expected",
    [
        # Standard class in TS: scheme manager package version descriptor...
        (
            "scip-typescript npm ts-mini-project 1.0.0 src/`Cache.ts`/Cache#",
            "ts-mini-project src/`Cache.ts`/Cache#",
        ),
        # Generic type-param descriptor — [K] bracket notation kept verbatim
        (
            "scip-typescript npm ts-mini-project 1.0.0 src/`Cache.ts`/Cache#[K]",
            "ts-mini-project src/`Cache.ts`/Cache#[K]",
        ),
        # Default export class — same format as named, no special marker
        (
            "scip-typescript npm ts-mini-project 1.0.0 src/`Logger.ts`/Logger#",
            "ts-mini-project src/`Logger.ts`/Logger#",
        ),
        # JSX component in .tsx — descriptor contains backtick-quoted path
        (
            "scip-typescript npm ts-mini-project 1.0.0 src/`Button.tsx`/Button.",
            "ts-mini-project src/`Button.tsx`/Button.",
        ),
        # JS interop (legacy.js) — same extraction logic as TS
        (
            "scip-typescript npm ts-mini-project 1.0.0 src/`legacy.js`/helper().",
            "ts-mini-project src/`legacy.js`/helper().",
        ),
        # Short symbol (< 5 parts) → passthrough unchanged
        (
            "local 1",
            "local 1",
        ),
        # Python symbol — scip-python uses different scheme
        (
            "scip-python python pymini . `src.pymini.cache`/Cache#",
            "pymini `src.pymini.cache`/Cache#",
        ),
    ],
)
class TestExtractQualifiedName:
    def test_extract(self, symbol: str, expected: str) -> None:
        result = _extract_qualified_name(symbol)
        assert result == expected

    def test_no_empty_result(self, symbol: str, expected: str) -> None:
        result = _extract_qualified_name(symbol)
        assert result, "qualified_name must not be empty"


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
