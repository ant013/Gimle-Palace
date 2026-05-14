"""Unit tests for source_context in code_ownership audit contract (Task 3.4).

Verifies:
1. audit_contract query returns source_context column (W1)
   W3: code_ownership uses f.path, so classify(finding["path"]) must be used
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


def test_code_ownership_query_uses_path_not_file() -> None:
    """code_ownership audit query must use f.path AS path (not f.file). W3."""
    from palace_mcp.extractors.code_ownership.extractor import CodeOwnershipExtractor

    extractor = CodeOwnershipExtractor()
    contract = extractor.audit_contract()
    assert contract is not None
    # W3: the key field is 'path', not 'file'
    assert "f.path AS path" in contract.query, (
        "W3: code_ownership query must return f.path AS path"
    )
