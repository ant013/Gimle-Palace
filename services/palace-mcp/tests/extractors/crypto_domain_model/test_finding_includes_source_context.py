"""Unit tests for source_context emission in crypto_domain_model (Task 3.2).

Verifies:
1. _dedup_findings sets source_context on each deduped finding
2. _QUERY RETURN clause includes source_context column
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Helper: minimal raw semgrep-style finding
# ---------------------------------------------------------------------------


def _raw(
    path: str, kind: str = "crypto_key_exposure", severity: str = "WARNING"
) -> dict:
    return {
        "path": path,
        "check_id": kind,
        "start": {"line": 10},
        "end": {"line": 12},
        "extra": {
            "severity": severity,
            "message": "test message",
            "metadata": {"kind": kind},
        },
    }


# ---------------------------------------------------------------------------
# Task 3.2 RED — source_context in dedup output
# ---------------------------------------------------------------------------


def test_dedup_findings_sets_source_context_library() -> None:
    """Library paths classified as 'library'."""
    from palace_mcp.extractors.crypto_domain_model.extractor import _dedup_findings

    results = _dedup_findings([_raw("Sources/TronKit/Signer/Signer.swift")])
    assert len(results) == 1
    assert results[0]["source_context"] == "library"


def test_dedup_findings_sets_source_context_example() -> None:
    """Example paths classified as 'example'."""
    from palace_mcp.extractors.crypto_domain_model.extractor import _dedup_findings

    results = _dedup_findings([_raw("iOS Example/Sources/Crypto.swift")])
    assert results[0]["source_context"] == "example"


def test_dedup_findings_sets_source_context_test() -> None:
    """Test paths classified as 'test'."""
    from palace_mcp.extractors.crypto_domain_model.extractor import _dedup_findings

    results = _dedup_findings([_raw("Tests/CryptoTests.swift")])
    assert results[0]["source_context"] == "test"


def test_dedup_findings_sets_source_context_other() -> None:
    """Other paths classified as 'other'."""
    from palace_mcp.extractors.crypto_domain_model.extractor import _dedup_findings

    results = _dedup_findings([_raw("Scripts/generate.sh")])
    assert results[0]["source_context"] == "other"


def test_dedup_findings_mixed_contexts() -> None:
    """Each finding gets its own source_context based on its path."""
    from palace_mcp.extractors.crypto_domain_model.extractor import _dedup_findings

    raws = [
        _raw("Sources/Kit/Crypto.swift"),
        _raw("Tests/CryptoTests.swift", kind="other_rule"),
        _raw("iOS Example/App.swift", kind="example_rule"),
    ]
    results = _dedup_findings(raws)
    assert len(results) == 3
    by_kind = {r["kind"]: r["source_context"] for r in results}
    assert by_kind["crypto_key_exposure"] == "library"
    assert by_kind["other_rule"] == "test"
    assert by_kind["example_rule"] == "example"


# ---------------------------------------------------------------------------
# Task 3.2 RED — _QUERY returns source_context column (W1)
# ---------------------------------------------------------------------------


def test_query_includes_source_context_column() -> None:
    """_QUERY RETURN clause must include source_context column."""
    from palace_mcp.extractors.crypto_domain_model.extractor import _QUERY

    assert "source_context" in _QUERY, (
        "_QUERY does not include 'source_context' in RETURN — W1 violation"
    )
