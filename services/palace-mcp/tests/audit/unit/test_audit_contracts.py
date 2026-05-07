"""Unit tests for audit_contract() on all 7 extractors (S1.6).

Each test asserts:
- audit_contract() returns non-None AuditContract.
- extractor_name matches the registry key.
- template_name points to an existing file in audit/templates/.
- query is a non-empty string containing 'MATCH'.
- severity_column is a non-empty string.
"""

from __future__ import annotations


from palace_mcp.audit.contracts import AuditContract
from palace_mcp.audit.renderer import _TEMPLATES_DIR


def _assert_valid_contract(contract: AuditContract | None, expected_name: str) -> None:
    assert contract is not None, f"{expected_name}: audit_contract() returned None"
    assert isinstance(contract, AuditContract)
    assert contract.extractor_name == expected_name
    assert contract.template_name, "template_name must be non-empty"
    template_path = _TEMPLATES_DIR / contract.template_name
    assert template_path.exists(), (
        f"template {contract.template_name!r} not found at {template_path}"
    )
    assert "MATCH" in contract.query, "query must contain MATCH clause"
    assert contract.severity_column, "severity_column must be non-empty"
    assert contract.max_findings > 0


class TestHotspotAuditContract:
    def test_returns_valid_contract(self) -> None:
        from palace_mcp.extractors.hotspot.extractor import HotspotExtractor

        contract = HotspotExtractor().audit_contract()
        _assert_valid_contract(contract, "hotspot")
        assert "hotspot.md" in contract.template_name  # type: ignore[union-attr]


class TestDeadSymbolAuditContract:
    def test_returns_valid_contract(self) -> None:
        from palace_mcp.extractors.dead_symbol_binary_surface.extractor import (
            DeadSymbolBinarySurfaceExtractor,
        )

        contract = DeadSymbolBinarySurfaceExtractor().audit_contract()
        _assert_valid_contract(contract, "dead_symbol_binary_surface")


class TestDependencySurfaceAuditContract:
    def test_returns_valid_contract(self) -> None:
        from palace_mcp.extractors.dependency_surface.extractor import (
            DependencySurfaceExtractor,
        )

        contract = DependencySurfaceExtractor().audit_contract()
        _assert_valid_contract(contract, "dependency_surface")


class TestCodeOwnershipAuditContract:
    def test_returns_valid_contract(self) -> None:
        from palace_mcp.extractors.code_ownership.extractor import (
            CodeOwnershipExtractor,
        )

        contract = CodeOwnershipExtractor().audit_contract()
        _assert_valid_contract(contract, "code_ownership")


class TestCrossRepoVersionSkewAuditContract:
    def test_returns_valid_contract(self) -> None:
        from palace_mcp.extractors.cross_repo_version_skew.extractor import (
            CrossRepoVersionSkewExtractor,
        )

        contract = CrossRepoVersionSkewExtractor().audit_contract()
        _assert_valid_contract(contract, "cross_repo_version_skew")


class TestPublicApiSurfaceAuditContract:
    def test_returns_valid_contract(self) -> None:
        from palace_mcp.extractors.public_api_surface import PublicApiSurfaceExtractor

        contract = PublicApiSurfaceExtractor().audit_contract()
        _assert_valid_contract(contract, "public_api_surface")


class TestCrossModuleContractAuditContract:
    def test_returns_valid_contract(self) -> None:
        from palace_mcp.extractors.cross_module_contract import (
            CrossModuleContractExtractor,
        )

        contract = CrossModuleContractExtractor().audit_contract()
        _assert_valid_contract(contract, "cross_module_contract")


class TestBaseExtractorDefaultReturnsNone:
    def test_heartbeat_has_no_contract(self) -> None:
        """Heartbeat extractor does not participate in audits."""
        from palace_mcp.extractors.heartbeat import HeartbeatExtractor

        assert HeartbeatExtractor().audit_contract() is None
