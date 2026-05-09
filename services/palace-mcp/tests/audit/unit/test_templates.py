"""Unit tests for per-extractor Jinja2 section templates (S1.2).

14 tests: 7 empty-case + 7 with-findings-case, one per extractor template.
"""

from __future__ import annotations

from palace_mcp.audit.contracts import AuditSectionData
from palace_mcp.audit.renderer import render_section

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _section(name: str, findings: list[dict], stats: dict) -> AuditSectionData:
    return AuditSectionData(
        extractor_name=name,
        run_id=f"run-{name[:4]}",
        project="test-project",
        completed_at="2026-05-07T00:00:00+00:00",
        findings=findings,
        summary_stats=stats,
    )


# ---------------------------------------------------------------------------
# hotspot
# ---------------------------------------------------------------------------

HOTSPOT_STATS_EMPTY = {"file_count": 0, "max_score": 0.0, "window_days": 90}
HOTSPOT_FINDING = {
    "path": "src/heavy.py",
    "hotspot_score": 4.2,
    "ccn_total": 35,
    "churn_count": 18,
    "sev": "critical",
}
HOTSPOT_STATS_FULL = {"file_count": 1, "max_score": 4.2, "window_days": 90}


class TestHotspotTemplate:
    def test_empty(self) -> None:
        rendered = render_section(
            _section("hotspot", [], HOTSPOT_STATS_EMPTY), "sev", 100
        )
        assert "No findings" in rendered
        assert "hotspot" in rendered

    def test_with_findings(self) -> None:
        rendered = render_section(
            _section("hotspot", [HOTSPOT_FINDING], HOTSPOT_STATS_FULL), "sev", 100
        )
        assert "src/heavy.py" in rendered
        assert "4.20" in rendered
        assert "CRITICAL" in rendered


# ---------------------------------------------------------------------------
# dead_symbol_binary_surface
# ---------------------------------------------------------------------------

DEAD_STATS_EMPTY = {
    "total": 0,
    "confirmed_dead": 0,
    "unused_candidate": 0,
    "skipped": 0,
}
DEAD_FINDING = {
    "id": "abc123",
    "display_name": "OldClass",
    "kind": "class",
    "module_name": "CoreModule",
    "language": "swift",
    "candidate_state": "CONFIRMED_DEAD",
    "confidence": 0.95,
    "source_file": "Core/OldClass.swift",
    "source_line": 42,
    "commit_sha": "deadbeef",
    "evidence_source": "periphery",
    "sev": "high",
}
DEAD_STATS_FULL = {"total": 1, "confirmed_dead": 1, "unused_candidate": 0, "skipped": 0}


class TestDeadSymbolTemplate:
    def test_empty(self) -> None:
        rendered = render_section(
            _section("dead_symbol_binary_surface", [], DEAD_STATS_EMPTY), "sev", 100
        )
        assert "No findings" in rendered

    def test_with_findings(self) -> None:
        rendered = render_section(
            _section("dead_symbol_binary_surface", [DEAD_FINDING], DEAD_STATS_FULL),
            "sev",
            100,
        )
        assert "OldClass" in rendered
        assert "CONFIRMED_DEAD" in rendered
        assert "HIGH" in rendered


# ---------------------------------------------------------------------------
# dependency_surface
# ---------------------------------------------------------------------------

DEP_STATS_EMPTY = {"total": 0, "scopes": []}
DEP_FINDING = {
    "purl": "pkg:swift/alamofire@5.9.1",
    "scope": "compile",
    "declared_in": "Package.swift",
    "declared_version_constraint": "5.9.1",
    "sev": "informational",
}
DEP_STATS_FULL = {"total": 1, "scopes": ["compile"]}


class TestDependencyTemplate:
    def test_empty(self) -> None:
        rendered = render_section(
            _section("dependency_surface", [], DEP_STATS_EMPTY), "sev", 100
        )
        assert "No findings" in rendered

    def test_with_findings(self) -> None:
        rendered = render_section(
            _section("dependency_surface", [DEP_FINDING], DEP_STATS_FULL), "sev", 100
        )
        assert "alamofire" in rendered
        assert "Package.swift" in rendered


# ---------------------------------------------------------------------------
# code_ownership
# ---------------------------------------------------------------------------

OWN_STATS_EMPTY = {"files_analysed": 0, "diffuse_ownership_count": 0}
OWN_FINDING = {
    "path": "src/shared/utils.py",
    "top_owner_email": "alice@example.com",
    "top_owner_weight": 0.15,
    "total_authors": 8,
    "sev": "medium",
}
OWN_STATS_FULL = {"files_analysed": 20, "diffuse_ownership_count": 1}


class TestCodeOwnershipTemplate:
    def test_empty(self) -> None:
        rendered = render_section(
            _section("code_ownership", [], OWN_STATS_EMPTY), "sev", 100
        )
        assert "No findings" in rendered

    def test_with_findings(self) -> None:
        rendered = render_section(
            _section("code_ownership", [OWN_FINDING], OWN_STATS_FULL), "sev", 100
        )
        assert "src/shared/utils.py" in rendered
        assert "alice@example.com" in rendered
        assert "MEDIUM" in rendered


# ---------------------------------------------------------------------------
# cross_repo_version_skew
# ---------------------------------------------------------------------------

SKEW_STATS_EMPTY = {"total": 0, "major": 0, "minor": 0, "patch": 0}
SKEW_FINDING = {
    "purl": "pkg:maven/com.squareup.okhttp3/okhttp",
    "versions": ["4.9.3", "5.0.0-alpha"],
    "member_count": 3,
    "sev": "high",
}
SKEW_STATS_FULL = {"total": 1, "major": 1, "minor": 0, "patch": 0}


class TestCrossRepoVersionSkewTemplate:
    def test_empty(self) -> None:
        rendered = render_section(
            _section("cross_repo_version_skew", [], SKEW_STATS_EMPTY), "sev", 100
        )
        assert "No findings" in rendered

    def test_with_findings(self) -> None:
        rendered = render_section(
            _section("cross_repo_version_skew", [SKEW_FINDING], SKEW_STATS_FULL),
            "sev",
            100,
        )
        assert "okhttp" in rendered
        assert "HIGH" in rendered


# ---------------------------------------------------------------------------
# public_api_surface
# ---------------------------------------------------------------------------

API_STATS_EMPTY = {"total": 0, "module_count": 0}
API_FINDING = {
    "module_name": "CoreKit",
    "fqn": "CoreKit.WalletManager",
    "display_name": "WalletManager",
    "kind": "class",
    "visibility": "public",
    "language": "swift",
    "commit_sha": "abc123",
    "sev": "informational",
}
API_STATS_FULL = {"total": 1, "module_count": 1}


class TestPublicApiTemplate:
    def test_empty(self) -> None:
        rendered = render_section(
            _section("public_api_surface", [], API_STATS_EMPTY), "sev", 100
        )
        assert "No findings" in rendered

    def test_with_findings(self) -> None:
        rendered = render_section(
            _section("public_api_surface", [API_FINDING], API_STATS_FULL), "sev", 100
        )
        assert "WalletManager" in rendered
        assert "CoreKit" in rendered


# ---------------------------------------------------------------------------
# cross_module_contract
# ---------------------------------------------------------------------------

CMC_STATS_EMPTY = {"total": 0, "breaking": 0, "signature_changes": 0}
CMC_FINDING = {
    "consumer_module": "AppModule",
    "producer_module": "CoreModule",
    "language": "kotlin",
    "from_commit": "aaa",
    "to_commit": "bbb",
    "removed_count": 2,
    "added_count": 0,
    "signature_changed_count": 1,
    "affected_use_count": 15,
    "sev": "high",
}
CMC_STATS_FULL = {"total": 1, "breaking": 1, "signature_changes": 1}


class TestCrossModuleContractTemplate:
    def test_empty(self) -> None:
        rendered = render_section(
            _section("cross_module_contract", [], CMC_STATS_EMPTY), "sev", 100
        )
        assert "No findings" in rendered

    def test_with_findings(self) -> None:
        rendered = render_section(
            _section("cross_module_contract", [CMC_FINDING], CMC_STATS_FULL), "sev", 100
        )
        assert "AppModule" in rendered
        assert "CoreModule" in rendered
        assert "HIGH" in rendered


# ---------------------------------------------------------------------------
# arch_layer
# ---------------------------------------------------------------------------

ARCH_LAYER_STATS_EMPTY_NO_RULES = {
    "module_count": 2,
    "edge_count": 1,
    "rule_count": 0,
    "parser_warning_count": 0,
    "rule_source": "",
    "rules_declared": False,
}

ARCH_LAYER_STATS_EMPTY_WITH_RULES = {
    "module_count": 2,
    "edge_count": 1,
    "rule_count": 2,
    "parser_warning_count": 0,
    "rule_source": ".palace/architecture-rules.yaml",
    "rules_declared": True,
}

ARCH_LAYER_FINDING = {
    "kind": "forbidden_dependency",
    "severity": "high",
    "src_module": "WalletCore",
    "dst_module": "WalletUI",
    "rule_id": "core_no_ui_import",
    "message": "Core module must not depend on UI module",
    "evidence": "manifest edge: WalletCore -> WalletUI [target_dep]",
    "file": "Package.swift",
    "start_line": 0,
    "run_id": "run-arch-1",
}

ARCH_LAYER_STATS_FULL = {
    **ARCH_LAYER_STATS_EMPTY_WITH_RULES,
    "module_count": 2,
    "edge_count": 1,
    "rule_count": 2,
}


class TestArchLayerTemplate:
    def test_empty_no_rules(self) -> None:
        rendered = render_section(
            _section("arch_layer", [], ARCH_LAYER_STATS_EMPTY_NO_RULES),
            "severity",
            100,
        )
        assert "no architecture rules declared" in rendered.lower()

    def test_empty_with_rules(self) -> None:
        rendered = render_section(
            _section("arch_layer", [], ARCH_LAYER_STATS_EMPTY_WITH_RULES),
            "severity",
            100,
        )
        assert "No architecture violations" in rendered or "rules pass" in rendered

    def test_with_findings(self) -> None:
        rendered = render_section(
            _section("arch_layer", [ARCH_LAYER_FINDING], ARCH_LAYER_STATS_FULL),
            "severity",
            100,
        )
        assert "WalletCore" in rendered
        assert "WalletUI" in rendered
        assert "core_no_ui_import" in rendered
        assert "HIGH" in rendered
