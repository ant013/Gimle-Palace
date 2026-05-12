"""Unit tests for crypto_domain_model extractor (GIM-239)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_RULES_DIR = (
    Path(__file__).parent.parent.parent.parent
    / "src"
    / "palace_mcp"
    / "extractors"
    / "crypto_domain_model"
    / "rules"
)
_FIXTURES_DIR = (
    Path(__file__).parent.parent / "fixtures" / "crypto-domain-mini-project" / "Sources"
)


def test_crypto_domain_model_registered() -> None:
    """B.1: extractor must be present in EXTRACTORS dict."""
    from palace_mcp.extractors.registry import EXTRACTORS

    extractor = EXTRACTORS.get("crypto_domain_model")
    assert extractor is not None
    assert extractor.name == "crypto_domain_model"


def test_audit_contract_returns_valid_contract() -> None:
    """B.2: audit_contract() returns AuditContract with required fields."""
    from palace_mcp.audit.contracts import AuditContract
    from palace_mcp.extractors.registry import EXTRACTORS

    extractor = EXTRACTORS["crypto_domain_model"]
    contract = extractor.audit_contract()

    assert contract is not None
    assert isinstance(contract, AuditContract)
    assert contract.extractor_name == "crypto_domain_model"
    assert contract.template_name == "crypto_domain_model.md"
    assert "$project_id" in contract.query
    assert contract.severity_column == "severity"
    assert contract.severity_mapper is not None


def test_audit_contract_severity_mapper_covers_all_levels() -> None:
    """B.2: severity_mapper maps known severity strings to Severity enum."""
    from palace_mcp.audit.contracts import Severity
    from palace_mcp.extractors.registry import EXTRACTORS

    extractor = EXTRACTORS["crypto_domain_model"]
    mapper = extractor.audit_contract().severity_mapper
    assert mapper is not None

    assert mapper("ERROR") == Severity.HIGH
    assert mapper("WARNING") == Severity.MEDIUM
    assert mapper("INFO") == Severity.INFORMATIONAL
    assert mapper("CRITICAL") == Severity.CRITICAL
    assert mapper("unknown_value") == Severity.INFORMATIONAL


def test_template_renders_without_error() -> None:
    """B.3: audit template renders without Jinja2 errors for findings + empty."""
    from pathlib import Path

    import jinja2

    template_path = (
        Path(__file__).parent.parent.parent.parent
        / "src"
        / "palace_mcp"
        / "audit"
        / "templates"
        / "crypto_domain_model.md"
    )
    assert template_path.exists(), f"Template not found: {template_path}"

    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(template_path.parent)),
        autoescape=False,
        undefined=jinja2.StrictUndefined,
    )
    tmpl = env.get_template("crypto_domain_model.md")

    # Non-empty case — summary_stats carries kit_name; _severity is added by renderer
    rendered_findings = tmpl.render(
        summary_stats={"kit_name": "TronKit"},
        findings=[
            {
                "severity": "HIGH",
                "_severity": "high",
                "kind": "private_key_string_storage",
                "file": "Sources/Core/Manager.swift",
                "start_line": 79,
                "message": "Mnemonic stored in UserDefaults",
            }
        ],
        run_id="test-run-123",
        completed_at="2026-05-08T00:00:00Z",
    )
    assert "TronKit" in rendered_findings
    assert "private_key_string_storage" in rendered_findings

    # Empty-findings case
    rendered_empty = tmpl.render(
        summary_stats={"kit_name": "CleanKit"},
        findings=[],
        run_id="test-run-456",
        completed_at="2026-05-08T00:00:00Z",
        files_scanned=97,
        rules_active=6,
    )
    assert "0 issues" in rendered_empty or "found 0" in rendered_empty


def _semgrep_bin() -> str:
    """Return path to semgrep binary in the active venv."""
    import shutil

    venv_semgrep = Path(sys.executable).parent / "semgrep"
    if venv_semgrep.exists():
        return str(venv_semgrep)
    found = shutil.which("semgrep")
    assert found is not None, "semgrep not found; run: uv add semgrep"
    return found


def _semgrep_findings(target: Path) -> list[dict]:
    """Run semgrep against a single file; return parsed results list."""
    result = subprocess.run(
        [
            _semgrep_bin(),
            "--config",
            str(_RULES_DIR),
            "--json",
            "--quiet",
            str(target),
        ],
        capture_output=True,
        text=True,
    )
    # semgrep exits 0 (no findings) or 1 (findings found) — both are OK
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return []
    return data.get("results", [])


def _rule_ids(findings: list[dict]) -> set[str]:
    return {f.get("check_id", "").split(".")[-1] for f in findings}


# ── C.1 private_key_string_storage ──────────────────────────────────────────


def test_private_key_bad_fires() -> None:
    """C.1: words_joined_userdefaults fires on PrivateKeyBad.swift."""
    findings = _semgrep_findings(_FIXTURES_DIR / "Bad" / "PrivateKeyBad.swift")
    rule_ids = _rule_ids(findings)
    assert "words_joined_userdefaults" in rule_ids


def test_private_key_good_no_findings() -> None:
    """C.1: no crypto-security rules fire on PrivateKeyGood.swift."""
    findings = _semgrep_findings(_FIXTURES_DIR / "Good" / "PrivateKeyGood.swift")
    rule_ids = _rule_ids(findings)
    assert "words_joined_userdefaults" not in rule_ids
    assert "mnemonic_userdefaults_storage" not in rule_ids


# ── C.2 decimal_raw_uint_arithmetic ─────────────────────────────────────────


def test_decimal_arith_bad_fires() -> None:
    """C.2: decimal_raw_uint_arithmetic_div fires on DecimalArithBad.swift."""
    findings = _semgrep_findings(_FIXTURES_DIR / "Bad" / "DecimalArithBad.swift")
    rule_ids = _rule_ids(findings)
    assert "decimal_raw_uint_arithmetic_div" in rule_ids


def test_decimal_arith_good_no_findings() -> None:
    """C.2: no arithmetic rules fire on DecimalArithGood.swift."""
    findings = _semgrep_findings(_FIXTURES_DIR / "Good" / "DecimalArithGood.swift")
    rule_ids = _rule_ids(findings)
    assert "decimal_raw_uint_arithmetic_div" not in rule_ids
    assert "decimal_raw_uint_arithmetic_mul" not in rule_ids


# ── C.3 bignum_overflow_unguarded ────────────────────────────────────────────


def test_bignum_bad_fires() -> None:
    """C.3: bignum_overflow_unguarded fires on BigNumBad.swift."""
    findings = _semgrep_findings(_FIXTURES_DIR / "Bad" / "BigNumBad.swift")
    rule_ids = _rule_ids(findings)
    assert "bignum_overflow_unguarded" in rule_ids


def test_bignum_good_no_findings() -> None:
    """C.3: no overflow rules fire on BigNumGood.swift."""
    findings = _semgrep_findings(_FIXTURES_DIR / "Good" / "BigNumGood.swift")
    rule_ids = _rule_ids(findings)
    assert "bignum_overflow_unguarded" not in rule_ids
    assert "bignum_overflow_unguarded_sub" not in rule_ids


# ── Dedup logic (D5) ─────────────────────────────────────────────────────────


def test_dedup_keeps_highest_severity() -> None:
    """D5: _dedup_findings coalesces same (file,line,kind) keeping highest severity."""
    from palace_mcp.extractors.crypto_domain_model.extractor import _dedup_findings

    raw = [
        {
            "path": "Foo.swift",
            "start": {"line": 10},
            "end": {"line": 10},
            "check_id": "rule_a",
            "extra": {
                "severity": "WARNING",
                "message": "low sev",
                "metadata": {"kind": "test_kind"},
            },
        },
        {
            "path": "Foo.swift",
            "start": {"line": 10},
            "end": {"line": 10},
            "check_id": "rule_a",
            "extra": {
                "severity": "ERROR",
                "message": "high sev",
                "metadata": {"kind": "test_kind"},
            },
        },
    ]
    result = _dedup_findings(raw)
    assert len(result) == 1
    assert result[0]["severity"] == "high"


# ── C.4 address_no_checksum_validation ──────────────────────────────────────


def test_address_checksum_bad_fires() -> None:
    """C.4: address_no_checksum_validation fires on AddressChecksumBad.swift."""
    findings = _semgrep_findings(_FIXTURES_DIR / "Bad" / "AddressChecksumBad.swift")
    rule_ids = _rule_ids(findings)
    assert "address_no_checksum_validation" in rule_ids


def test_address_checksum_good_no_findings() -> None:
    """C.4: no address rules fire on AddressChecksumGood.swift."""
    findings = _semgrep_findings(_FIXTURES_DIR / "Good" / "AddressChecksumGood.swift")
    rule_ids = _rule_ids(findings)
    assert "address_no_checksum_validation" not in rule_ids


# ── C.5 wei_eth_unit_mix ─────────────────────────────────────────────────────


def test_wei_eth_mix_bad_fires() -> None:
    """C.5: wei_eth_unit_mix_string fires on WeiEthMixBad.swift."""
    findings = _semgrep_findings(_FIXTURES_DIR / "Bad" / "WeiEthMixBad.swift")
    rule_ids = _rule_ids(findings)
    assert "wei_eth_unit_mix_string" in rule_ids


def test_wei_eth_mix_good_no_findings() -> None:
    """C.5: no unit-mix rules fire on WeiEthMixGood.swift."""
    findings = _semgrep_findings(_FIXTURES_DIR / "Good" / "WeiEthMixGood.swift")
    rule_ids = _rule_ids(findings)
    assert "wei_eth_unit_mix_string" not in rule_ids


def test_dedup_different_lines_not_coalesced() -> None:
    """D5: findings at different lines must NOT be merged."""
    from palace_mcp.extractors.crypto_domain_model.extractor import _dedup_findings

    raw = [
        {
            "path": "Foo.swift",
            "start": {"line": 10},
            "end": {"line": 10},
            "check_id": "rule_a",
            "extra": {"severity": "WARNING", "message": "x", "metadata": {"kind": "k"}},
        },
        {
            "path": "Foo.swift",
            "start": {"line": 20},
            "end": {"line": 20},
            "check_id": "rule_a",
            "extra": {"severity": "WARNING", "message": "y", "metadata": {"kind": "k"}},
        },
    ]
    result = _dedup_findings(raw)
    assert len(result) == 2
