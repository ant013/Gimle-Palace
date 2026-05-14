"""Unit tests for source_context + B8 critical-path tuning in error_handling_policy (Task 3.3).

Verifies:
1. Each ErrorFinding gets source_context from classify(file)
2. try_optional_swallow severity elevated to MEDIUM on critical-path files (B8 regex)
3. source_context=example/test overrides regex match back to LOW
4. _QUERY includes source_context column (W1)
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Helpers: build ErrorFinding-like objects directly via _normalise_results
# (we avoid calling semgrep — just build ErrorFinding dataclasses)
# ---------------------------------------------------------------------------


def _make_raw(path: str, kind: str = "try_optional_swallow", severity: str = "WARNING") -> dict:
    return {
        "path": path,
        "check_id": kind,
        "start": {"line": 10},
        "end": {"line": 10},
        "extra": {
            "severity": severity,
            "message": "test",
            "metadata": {"kind": kind},
        },
    }


def _normalise(path: str, kind: str = "try_optional_swallow", severity: str = "WARNING") -> object:
    from pathlib import Path
    from palace_mcp.extractors.error_handling_policy.extractor import (
        _normalise_results,
    )

    raws = [_make_raw(path, kind, severity)]
    results = _normalise_results(raws, repo_root=Path("/repo"))
    return results[0]


# ---------------------------------------------------------------------------
# Task 3.3 RED — source_context set in _normalise_results
# ---------------------------------------------------------------------------


def test_normalise_sets_source_context_library() -> None:
    f = _normalise("Sources/TronKit/Signer/Signer.swift")
    assert f.source_context == "library"  # type: ignore[attr-defined]


def test_normalise_sets_source_context_example() -> None:
    f = _normalise("iOS Example/Sources/Manager.swift")
    assert f.source_context == "example"  # type: ignore[attr-defined]


def test_normalise_sets_source_context_test() -> None:
    f = _normalise("Tests/CryptoTests.swift")
    assert f.source_context == "test"  # type: ignore[attr-defined]


def test_normalise_sets_source_context_other() -> None:
    f = _normalise("Scripts/build.sh")
    assert f.source_context == "other"  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Task 3.3 RED — B8 critical-path severity tuning (plan §GIM-283-4 Task 3.3)
# ---------------------------------------------------------------------------


def _apply_cp(findings: list) -> list:
    from palace_mcp.extractors.error_handling_policy.extractor import (
        _apply_critical_path_severity,
    )

    return _apply_critical_path_severity(findings)


def _lib_finding(path: str, kind: str = "try_optional_swallow", severity: str = "medium"):
    from palace_mcp.extractors.error_handling_policy.extractor import ErrorFinding

    return ErrorFinding(
        file=path,
        start_line=10,
        end_line=10,
        kind=kind,
        severity=severity,
        message="",
        rule_id=kind,
        source_context="library",  # type: ignore[call-arg]
    )


def _ctx_finding(path: str, source_context: str, kind: str = "try_optional_swallow", severity: str = "medium"):
    from palace_mcp.extractors.error_handling_policy.extractor import ErrorFinding

    return ErrorFinding(
        file=path,
        start_line=10,
        end_line=10,
        kind=kind,
        severity=severity,
        message="",
        rule_id=kind,
        source_context=source_context,  # type: ignore[call-arg]
    )


# Signer: matches \bsigner\b → MEDIUM (library context)
def test_critical_path_signer_medium() -> None:
    f = _lib_finding("Sources/TronKit/Crypto/Signer.swift", severity="low")
    result = _apply_cp([f])
    assert result[0].severity == "medium"


# HDWallet: matches hd[-_]?wallet (C1 fix) → MEDIUM
def test_critical_path_hd_wallet_medium() -> None:
    f = _lib_finding("Sources/TronKit/HDWallet/HDWalletKit.swift", severity="low")
    result = _apply_cp([f])
    assert result[0].severity == "medium"


# Auth: matches \bauth\b → MEDIUM
def test_critical_path_auth_medium() -> None:
    f = _lib_finding("Sources/TronKit/Network/Auth.swift", severity="low")
    result = _apply_cp([f])
    assert result[0].severity == "medium"


# Authorization: does NOT match \bauth\b (word boundary before 'o') → stays LOW
def test_false_positive_authorization_stays_low() -> None:
    f = _lib_finding("Sources/TronKit/UI/Authorization.swift", severity="low")
    result = _apply_cp([f])
    assert result[0].severity == "low"


# View: no keyword match → stays LOW
def test_no_keyword_view_stays_low() -> None:
    f = _lib_finding("Sources/TronKit/UI/View.swift", severity="low")
    result = _apply_cp([f])
    assert result[0].severity == "low"


# example context: signer path but example → LOW despite regex match
def test_example_context_overrides_regex_to_low() -> None:
    f = _ctx_finding("iOS Example/Sources/signer/Manager.swift", source_context="example", severity="low")
    result = _apply_cp([f])
    assert result[0].severity == "low"


# test context: crypto path but test → LOW despite regex match
def test_test_context_overrides_regex_to_low() -> None:
    f = _ctx_finding("Tests/CryptoTests.swift", source_context="test", severity="low")
    result = _apply_cp([f])
    assert result[0].severity == "low"


# Non try_optional kinds should not be affected by critical path logic
def test_non_try_optional_unaffected() -> None:
    f = _lib_finding("Sources/TronKit/Crypto/Signer.swift", kind="empty_catch_block", severity="medium")
    result = _apply_cp([f])
    assert result[0].severity == "medium"


# B8 keywords: mnemonic, seed, pubkey, keystore, secp256k1, ed25519, ripemd160
@pytest.mark.parametrize("path", [
    "Sources/Kit/Mnemonic.swift",
    "Sources/Kit/Seed.swift",
    "Sources/Kit/pubkey/PubKey.swift",
    "Sources/Kit/keystore/Keystore.swift",
    "Sources/Kit/secp256k1.swift",
    "Sources/Kit/ed25519.swift",
    "Sources/Kit/Ripemd160.swift",
    "Sources/Kit/HsCryptoKit/Crypto.swift",
    "Sources/Kit/hmac/HMAC.swift",
])
def test_b8_keywords_elevate_to_medium(path: str) -> None:
    f = _lib_finding(path, severity="low")
    result = _apply_cp([f])
    assert result[0].severity == "medium", f"Expected MEDIUM for {path!r}, got {result[0].severity!r}"


# ---------------------------------------------------------------------------
# Task 3.3 RED — _QUERY includes source_context column (W1)
# ---------------------------------------------------------------------------


def test_query_includes_source_context_column() -> None:
    from palace_mcp.extractors.error_handling_policy.extractor import _QUERY

    assert "source_context" in _QUERY, "_QUERY missing source_context column (W1)"
