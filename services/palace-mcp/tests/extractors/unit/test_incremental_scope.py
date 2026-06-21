from __future__ import annotations

from palace_mcp.extractors.foundation.incremental_scope import (
    AUDIT_EXTRACTOR_SCOPE_KINDS,
    AuditScopeKind,
    FILE_SCOPED_AUDIT_EXTRACTORS,
    _READ_FILE_COMMITS_CYPHER,
)


def test_audit_scope_inventory_matches_phase2_contract() -> None:
    assert AUDIT_EXTRACTOR_SCOPE_KINDS == {
        "code_ownership": AuditScopeKind.FILE,
        "crypto_domain_model": AuditScopeKind.FILE,
        "error_handling_policy": AuditScopeKind.FILE,
        "coding_convention": AuditScopeKind.MODULE,
        "testability_di": AuditScopeKind.MODULE,
        "localization_accessibility": AuditScopeKind.MIXED,
        "dead_symbol_binary_surface": AuditScopeKind.PROJECT,
    }


def test_file_scoped_audit_extractors_are_only_true_file_local_writers() -> None:
    assert FILE_SCOPED_AUDIT_EXTRACTORS == frozenset(
        {
            "code_ownership",
            "crypto_domain_model",
            "error_handling_policy",
        }
    )


def test_read_existing_commit_sha_coalesces_last_seen_in_commit() -> None:
    assert "last_seen_in_commit" in _READ_FILE_COMMITS_CYPHER
    assert "coalesce(f.last_seen_in_commit, f.commit_sha)" in _READ_FILE_COMMITS_CYPHER
