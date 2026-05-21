"""Unit tests for source_context in code_ownership audit contract (Task 3.4).

Verifies:
1. audit_contract query returns source_context column (W1)
   W3: code_ownership returns the path field via file_path/path dual-read
"""

from __future__ import annotations


def test_code_ownership_query_includes_source_context() -> None:
    """code_ownership audit_contract query must return source_context column."""
    from palace_mcp.extractors.code_ownership.extractor import CodeOwnershipExtractor

    extractor = CodeOwnershipExtractor()
    contract = extractor.audit_contract()
    assert contract is not None
    assert "source_context" in contract.query, (
        "code_ownership audit query missing source_context column (W1/W3)"
    )


def test_code_ownership_query_dual_reads_file_path() -> None:
    """code_ownership audit query must dual-read file_path/path for migration."""
    from palace_mcp.extractors.code_ownership.extractor import CodeOwnershipExtractor

    extractor = CodeOwnershipExtractor()
    contract = extractor.audit_contract()
    assert contract is not None
    assert "coalesce(f.file_path, f.path) AS path" in contract.query, (
        "code_ownership audit query must dual-read file_path/path"
    )
