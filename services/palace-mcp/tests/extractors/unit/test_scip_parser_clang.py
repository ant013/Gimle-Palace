"""Clang-specific SCIP parser tests for C/C++ support."""

from __future__ import annotations

from typing import Any

import pytest

from palace_mcp.extractors.foundation.models import Language
from palace_mcp.extractors.scip_parser import (
    _extract_qualified_name,
    _language_from_path,
    iter_scip_occurrences,
)
from palace_mcp.proto import scip_pb2


def _build_index(
    *,
    language: str,
    relative_path: str,
    symbol: str,
    symbol_roles: int = 1,
) -> Any:
    index = scip_pb2.Index()  # type: ignore[attr-defined]
    metadata = scip_pb2.Metadata()  # type: ignore[attr-defined]
    metadata.version = scip_pb2.ProtocolVersion.UnspecifiedProtocolVersion  # type: ignore[attr-defined]
    metadata.tool_info.name = "scip-clang"
    metadata.tool_info.version = "0.4.0"
    metadata.project_root = "file:///test"
    index.metadata.CopyFrom(metadata)

    doc = index.documents.add()
    doc.relative_path = relative_path
    doc.language = language

    occ = doc.occurrences.add()
    occ.range.extend([1, 0, 8])
    occ.symbol = symbol
    occ.symbol_roles = symbol_roles
    return index


@pytest.mark.parametrize(
    ("symbol", "expected"),
    [
        (
            "scip-clang  . . util/Formatter#toString().",
            ". util/Formatter#toString().",
        ),
        (
            "scip-clang  . . math/Vector#`operator new`().",
            ". math/Vector#`operator new`().",
        ),
        (
            "scip-clang  . . math/Vector#`operator<<`().",
            ". math/Vector#`operator<<`().",
        ),
    ],
)
def test_extract_qualified_name_supports_empty_manager_and_backticks(
    symbol: str,
    expected: str,
) -> None:
    assert _extract_qualified_name(symbol) == expected


@pytest.mark.parametrize(
    ("relative_path", "expected"),
    [
        ("Sources/native/math.c", Language.C),
        ("Sources/native/math.cc", Language.CPP),
        ("Sources/native/math.cpp", Language.CPP),
        ("Sources/native/math.cxx", Language.CPP),
        ("Sources/native/math.m", Language.UNKNOWN),
        ("Sources/native/math.mm", Language.UNKNOWN),
        ("Sources/native/math.h", Language.UNKNOWN),
        ("Sources/native/math.hpp", Language.UNKNOWN),
    ],
)
def test_language_from_path_matches_clang_scope(
    relative_path: str,
    expected: Language,
) -> None:
    assert _language_from_path(relative_path) == expected


@pytest.mark.parametrize(
    ("doc_language", "relative_path", "expected"),
    [
        ("C", "Sources/native/math.h", Language.C),
        ("CPP", "Sources/native/math.hpp", Language.CPP),
        ("", "Sources/native/math.c", Language.C),
        ("", "Sources/native/math.cpp", Language.CPP),
        ("", "Sources/native/math.m", Language.UNKNOWN),
    ],
)
def test_iter_scip_occurrences_detects_native_languages(
    doc_language: str,
    relative_path: str,
    expected: Language,
) -> None:
    index = _build_index(
        language=doc_language,
        relative_path=relative_path,
        symbol="scip-clang  . . math/Vector#length().",
    )

    occs = list(iter_scip_occurrences(index, commit_sha="deadbeef", ingest_run_id="r1"))

    assert len(occs) == 1
    assert occs[0].language == expected
