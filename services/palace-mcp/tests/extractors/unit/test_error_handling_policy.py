"""Unit tests for error_handling_policy extractor (GIM-257)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from palace_mcp.audit.contracts import AuditContract, Severity
from palace_mcp.extractors.error_handling_policy.extractor import (
    CatchSite,
    ErrorFinding,
    ErrorHandlingPolicyExtractor,
    _apply_suppressions,
    _collect_catch_sites,
    _dedup_findings,
    _ehp_severity,
    _DELETE_EXISTING_SNAPSHOT,
    _WRITE_CATCH_SITE,
    _WRITE_ERROR_FINDING,
    _write_snapshot,
)

_RULES_DIR = (
    Path(__file__).parent.parent.parent.parent
    / "src"
    / "palace_mcp"
    / "extractors"
    / "error_handling_policy"
    / "rules"
)
_FIXTURE_ROOT = (
    Path(__file__).parent.parent / "fixtures" / "error-handling-mini-project"
)
_FIXTURES_DIR = _FIXTURE_ROOT / "Sources"


def _semgrep_bin() -> str:
    import shutil

    venv_semgrep = Path(sys.executable).parent / "semgrep"
    if venv_semgrep.exists():
        return str(venv_semgrep)
    found = shutil.which("semgrep")
    assert found is not None, "semgrep not found; run: uv add semgrep"
    return found


def _semgrep_findings(target: Path) -> list[dict]:
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
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return []
    return data.get("results", [])


def _rule_ids(findings: list[dict]) -> set[str]:
    return {str(f.get("check_id", "")).split(".")[-1] for f in findings}


def test_error_handling_policy_registered() -> None:
    from palace_mcp.extractors.registry import EXTRACTORS

    extractor = EXTRACTORS.get("error_handling_policy")
    assert extractor is not None
    assert extractor.name == "error_handling_policy"


def test_audit_contract_returns_valid_contract() -> None:
    contract = ErrorHandlingPolicyExtractor().audit_contract()

    assert isinstance(contract, AuditContract)
    assert contract.extractor_name == "error_handling_policy"
    assert contract.template_name == "error_handling_policy.md"
    assert "$project_id" in contract.query
    assert "CatchSite" in contract.query
    assert "ErrorFinding" in contract.query
    assert contract.severity_column == "severity"
    assert contract.severity_mapper is not None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("CRITICAL", Severity.CRITICAL),
        ("ERROR", Severity.HIGH),
        ("WARNING", Severity.MEDIUM),
        ("LOW", Severity.LOW),
        ("INFO", Severity.INFORMATIONAL),
        ("unknown", Severity.INFORMATIONAL),
    ],
)
def test_severity_mapper_covers_known_levels(raw: str, expected: Severity) -> None:
    assert _ehp_severity(raw) == expected


@pytest.mark.parametrize(
    ("file_name", "expected_rule"),
    [
        ("EmptyCatch.swift", "empty_catch_block"),
        ("CatchOnlyLogs.swift", "catch_only_logs"),
        ("CatchOnlyLogs.swift", "generic_catch_all"),
        ("CatchOnlyLogs.swift", "error_as_string"),
        ("TryOptionalSwallow.swift", "try_optional_swallow"),
        ("TryOptionalSwallow.swift", "nil_coalesce_swallows_error"),
        ("CryptoSigner.swift", "empty_catch_in_crypto_path"),
        ("CryptoSigner.swift", "try_optional_in_crypto_path"),
    ],
)
def test_bad_fixtures_fire_expected_rules(file_name: str, expected_rule: str) -> None:
    findings = _semgrep_findings(_FIXTURES_DIR / "Bad" / file_name)
    assert expected_rule in _rule_ids(findings)


@pytest.mark.parametrize(
    ("file_name", "disallowed_rules"),
    [
        (
            "ProperCatch.swift",
            {
                "empty_catch_block",
                "empty_catch_in_crypto_path",
                "catch_only_logs",
                "generic_catch_all",
                "try_optional_swallow",
                "try_optional_in_crypto_path",
                "nil_coalesce_swallows_error",
            },
        ),
        ("TypedErrors.swift", {"error_as_string"}),
    ],
)
def test_good_fixtures_do_not_fire_bad_rules(
    file_name: str, disallowed_rules: set[str]
) -> None:
    findings = _semgrep_findings(_FIXTURES_DIR / "Good" / file_name)
    rule_ids = _rule_ids(findings)
    assert disallowed_rules.isdisjoint(rule_ids)


def test_dedup_keeps_highest_severity() -> None:
    findings = [
        ErrorFinding(
            file="Foo.swift",
            start_line=10,
            end_line=10,
            kind="empty_catch_block",
            severity="medium",
            message="m",
            rule_id="rule.medium",
        ),
        ErrorFinding(
            file="Foo.swift",
            start_line=10,
            end_line=10,
            kind="empty_catch_block",
            severity="high",
            message="h",
            rule_id="rule.high",
        ),
    ]

    result = _dedup_findings(findings)
    assert len(result) == 1
    assert result[0].severity == "high"


def test_collect_catch_sites_indexes_catch_and_try_optional_inventory() -> None:
    sites = _collect_catch_sites(_FIXTURE_ROOT)

    assert any(site.kind == "catch" for site in sites)
    assert any(site.kind == "try_optional" for site in sites)
    assert any(site.kind == "nil_coalesce_try_optional" for site in sites)
    assert len(sites) == 11


def test_suppression_comment_downgrades_finding(tmp_path: Path) -> None:
    path = tmp_path / "Suppressed.swift"
    path.write_text(
        "\n".join(
            [
                "func demo() {",
                "  do {",
                "    try risky()",
                "  }",
                "  // ehp:ignore",
                "  catch { }",
                "}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    findings = [
        ErrorFinding(
            file="Suppressed.swift",
            start_line=6,
            end_line=6,
            kind="empty_catch_block",
            severity="high",
            message="ignored",
            rule_id="empty_catch_block",
        )
    ]

    result = _apply_suppressions(repo_root=tmp_path, findings=findings)
    assert result[0].severity == "informational"


def test_deliberate_marker_downgrades_finding(tmp_path: Path) -> None:
    path = tmp_path / "Deliberate.swift"
    path.write_text(
        "\n".join(
            [
                "func demo() {",
                "  do {",
                "    try risky()",
                "  }",
                "  // MARK: deliberate",
                "  catch { }",
                "}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    findings = [
        ErrorFinding(
            file="Deliberate.swift",
            start_line=6,
            end_line=6,
            kind="empty_catch_block",
            severity="high",
            message="ignored",
            rule_id="empty_catch_block",
        )
    ]

    result = _apply_suppressions(repo_root=tmp_path, findings=findings)
    assert result[0].severity == "informational"


def test_suppression_scan_is_bounded(tmp_path: Path) -> None:
    target = tmp_path / "Bounded.swift"
    target.write_text(
        "\n".join(
            [
                "func demo() {",
                "  do {",
                "    try risky()",
                "  }",
                "  catch { }",
                "}",
                "// ehp:ignore",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    findings = [
        ErrorFinding(
            file="Bounded.swift",
            start_line=5,
            end_line=5,
            kind="empty_catch_block",
            severity="high",
            message="not ignored",
            rule_id="empty_catch_block",
        )
    ]

    result = _apply_suppressions(repo_root=tmp_path, findings=findings)
    assert result[0].severity == "high"


def test_catch_site_dataclass_remains_hashable() -> None:
    site = CatchSite(
        file="Sources/Bad/EmptyCatch.swift",
        start_line=4,
        end_line=4,
        kind="catch",
        swallowed=True,
        rethrows=False,
        module="Bad",
    )
    assert {site}


class _FakeResult:
    async def consume(self) -> None:
        return None


class _FakeTx:
    def __init__(self) -> None:
        self.queries: list[str] = []

    async def run(self, query: str, **_: object) -> _FakeResult:
        self.queries.append(query)
        return _FakeResult()


class _FakeSession:
    def __init__(self, tx: _FakeTx) -> None:
        self.tx = tx
        self.execute_write_calls = 0

    async def __aenter__(self) -> "_FakeSession":
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> bool:
        return False

    async def execute_write(self, fn: Any, *args: object, **kwargs: object) -> None:
        self.execute_write_calls += 1
        await fn(self.tx, *args, **kwargs)


class _FakeDriver:
    def __init__(self, session: _FakeSession) -> None:
        self._session = session

    def session(self) -> _FakeSession:
        return self._session


@pytest.mark.asyncio
async def test_write_snapshot_uses_single_execute_write_and_delete_then_create() -> None:
    tx = _FakeTx()
    session = _FakeSession(tx)
    driver = _FakeDriver(session)

    await _write_snapshot(
        driver,
        project_id="project/ehp",
        run_id="run-1",
        catch_sites=[
            CatchSite(
                file="Sources/Bad/EmptyCatch.swift",
                start_line=4,
                end_line=4,
                kind="catch",
                swallowed=True,
                rethrows=False,
                module="Bad",
            )
        ],
        findings=[
            ErrorFinding(
                file="Sources/Bad/EmptyCatch.swift",
                start_line=4,
                end_line=4,
                kind="empty_catch_block",
                severity="high",
                message="swallowed",
                rule_id="empty_catch_block",
            )
        ],
    )

    assert session.execute_write_calls == 1
    assert tx.queries == [
        _DELETE_EXISTING_SNAPSHOT,
        _WRITE_CATCH_SITE,
        _WRITE_ERROR_FINDING,
    ]
