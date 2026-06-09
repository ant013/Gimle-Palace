"""Unit tests for arch_layer summary sentinel (DEFECT-3 from walker GIM-1574).

When the extractor runs successfully it must always leave at least one
:Layer and one :ArchRule node in Neo4j (a summary sentinel), so the
operator can distinguish "ran successfully with no findings" from
"never ran". Verified by checking that the summary fields exist on the
models and the audit-supplement query filters them out.
"""

from __future__ import annotations

from palace_mcp.audit.fetcher import _ARCH_LAYER_SUPPLEMENT
from palace_mcp.code.native_get_architecture import _LAYERS_QUERY
from palace_mcp.extractors.arch_layer.models import ArchRule, Layer


def test_layer_model_has_summary_fields() -> None:
    layer = Layer(
        project_id="project/test",
        name="__summary__",
        rule_source="unconfigured",
        run_id="r1",
        summary=True,
        scanned_modules=4,
        scanned_at="2026-06-09T00:00:00+00:00",
    )
    assert layer.summary is True
    assert layer.scanned_modules == 4


def test_layer_model_summary_default_false() -> None:
    layer = Layer(
        project_id="project/test",
        name="core",
        rule_source=".palace/architecture-rules.yaml",
        run_id="r1",
    )
    assert layer.summary is False
    assert layer.scanned_modules is None


def test_arch_rule_model_has_summary_fields() -> None:
    rule = ArchRule(
        project_id="project/test",
        rule_id="__summary__",
        kind="summary",
        severity="informational",
        rule_source="unconfigured",
        run_id="r1",
        summary=True,
        scanned_at="2026-06-09T00:00:00+00:00",
    )
    assert rule.summary is True


def test_arch_rule_model_summary_default_false() -> None:
    rule = ArchRule(
        project_id="project/test",
        rule_id="core_no_ui",
        kind="forbidden_dependency",
        severity="high",
        rule_source=".palace/architecture-rules.yaml",
        run_id="r1",
    )
    assert rule.summary is False


def test_arch_layer_supplement_filters_sentinel() -> None:
    """rules_declared must remain false when only the summary sentinel exists."""
    assert "coalesce(r.summary, false) = false" in _ARCH_LAYER_SUPPLEMENT


def test_native_get_architecture_layers_query_filters_sentinel() -> None:
    """native get_architecture must hide the summary :Layer from operators."""
    assert "coalesce(l.summary, false) = false" in _LAYERS_QUERY
