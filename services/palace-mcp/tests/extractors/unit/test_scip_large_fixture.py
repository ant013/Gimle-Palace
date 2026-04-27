"""CI fixture: 250 MiB synthetic .scip decode round-trip.

Validates that protobuf>=4.25 upb backend handles large SCIP files
without hitting the 64 MiB pure-Python recursion limit.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from palace_mcp.proto import scip_pb2
from palace_mcp.extractors.scip_parser import parse_scip_file


@pytest.mark.slow
def test_250mb_scip_decode_roundtrip(tmp_path: Path) -> None:
    """Build a ~250 MiB SCIP Index, serialize, parse back, verify counts."""
    index = scip_pb2.Index()  # type: ignore[attr-defined]
    metadata = scip_pb2.Metadata()  # type: ignore[attr-defined]
    metadata.version = scip_pb2.ProtocolVersion.UnspecifiedProtocolVersion  # type: ignore[attr-defined]
    metadata.tool_info.name = "ci-stress"
    metadata.tool_info.version = "1.0.0"
    metadata.project_root = "file:///ci-test"
    index.metadata.CopyFrom(metadata)

    target_bytes = 250 * 1024 * 1024
    symbols_per_doc = 500
    doc_count = 0

    while index.ByteSize() < target_bytes:
        doc = index.documents.add()
        doc.relative_path = f"src/generated/module_{doc_count}.py"
        doc.language = "python"
        for j in range(symbols_per_doc):
            occ = doc.occurrences.add()
            occ.range.extend([j, 0, 80])
            occ.symbol = f"scip-python python gen . mod{doc_count} . func{j} ."
            occ.symbol_roles = 1 if j % 5 == 0 else 0
        doc_count += 1

    scip_file = tmp_path / "large.scip"
    data = index.SerializeToString()
    scip_file.write_bytes(data)
    actual_mb = len(data) // (1024 * 1024)
    assert actual_mb >= 200, f"Fixture only {actual_mb} MiB, need >= 200"

    parsed = parse_scip_file(scip_file, max_size_mb=500)
    assert len(parsed.documents) == doc_count
    total_occs = sum(len(d.occurrences) for d in parsed.documents)
    assert total_occs == doc_count * symbols_per_doc
