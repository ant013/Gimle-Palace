"""CI fixture: >64 MiB synthetic .scip decode round-trip.

Validates that protobuf>=4.25 upb backend handles large SCIP files
without hitting the 64 MiB pure-Python recursion limit.
"""

from __future__ import annotations

from math import ceil
from pathlib import Path
from typing import Any

import pytest

from palace_mcp.extractors.scip_parser import parse_scip_file
from palace_mcp.proto import scip_pb2

TARGET_BYTES = 70 * 1024 * 1024
SYMBOLS_PER_DOC = 500


def _build_base_index() -> Any:
    index = scip_pb2.Index()  # type: ignore[attr-defined]
    metadata = scip_pb2.Metadata()  # type: ignore[attr-defined]
    metadata.version = scip_pb2.ProtocolVersion.UnspecifiedProtocolVersion  # type: ignore[attr-defined]
    metadata.tool_info.name = "ci-stress"
    metadata.tool_info.version = "1.0.0"
    metadata.project_root = "file:///ci-test"
    index.metadata.CopyFrom(metadata)
    return index


def _append_document(index: Any, doc_number: int) -> None:
    doc = index.documents.add()
    doc.relative_path = f"src/generated/module_{doc_number}.py"
    doc.language = "python"
    for occurrence_number in range(SYMBOLS_PER_DOC):
        occurrence = doc.occurrences.add()
        occurrence.range.extend([occurrence_number, 0, 80])
        occurrence.symbol = (
            f"scip-python python gen . mod{doc_number} . func{occurrence_number} ."
        )
        occurrence.symbol_roles = 1 if occurrence_number % 5 == 0 else 0


def _build_large_index(target_bytes: int) -> tuple[Any, int]:
    base_index = _build_base_index()
    base_size = len(base_index.SerializeToString())

    probe_index = _build_base_index()
    _append_document(probe_index, 0)
    bytes_per_doc = len(probe_index.SerializeToString()) - base_size
    required_docs = ceil((target_bytes - base_size) / bytes_per_doc) + 32

    index = _build_base_index()
    for doc_number in range(required_docs):
        _append_document(index, doc_number)

    return index, required_docs


@pytest.mark.slow
def test_large_scip_decode_roundtrip_above_64mb(tmp_path: Path) -> None:
    """Build a >64 MiB SCIP Index, serialize, parse back, verify counts."""
    index, doc_count = _build_large_index(TARGET_BYTES)
    scip_file = tmp_path / "large.scip"
    data = index.SerializeToString()
    scip_file.write_bytes(data)
    actual_mb = len(data) // (1024 * 1024)
    assert actual_mb >= 64, f"Fixture only {actual_mb} MiB, need >= 64"

    parsed = parse_scip_file(scip_file, max_size_mb=500)
    assert len(parsed.documents) == doc_count
    total_occs = sum(len(d.occurrences) for d in parsed.documents)
    assert total_occs == doc_count * SYMBOLS_PER_DOC
