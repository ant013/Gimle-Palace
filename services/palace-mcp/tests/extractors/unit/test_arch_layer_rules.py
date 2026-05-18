"""Unit tests for arch_layer rule loader (GIM-243)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from palace_mcp.extractors.arch_layer.rules import RuleSet, load_rules
from palace_mcp.extractors.base import ExtractorConfigError

_FIXTURE = Path(__file__).parent.parent / "fixtures" / "arch-layer-mini-project"


class TestLoadRulesNoFile:
    def test_missing_file_returns_empty_ruleset(self, tmp_path: Path) -> None:
        rs = load_rules(tmp_path)
        assert rs.rules_declared is False
        assert rs.layers == []
        assert rs.rules == []
        assert rs.rule_source == ""

    def test_missing_file_no_warnings(self, tmp_path: Path) -> None:
        rs = load_rules(tmp_path)
        assert rs.loader_warnings == []


class TestLoadRulesValidFile:
    def test_fixture_loads_layers(self) -> None:
        rs = load_rules(_FIXTURE)
        assert rs.rules_declared is True
        layer_names = [la.name for la in rs.layers]
        assert "core" in layer_names
        assert "ui" in layer_names

    def test_fixture_loads_rules(self) -> None:
        rs = load_rules(_FIXTURE)
        rule_ids = [r.rule_id for r in rs.rules]
        assert "core_no_ui_import" in rule_ids

    def test_fixture_rule_source(self) -> None:
        rs = load_rules(_FIXTURE)
        assert ".palace/architecture-rules.yaml" in rs.rule_source

    def test_layer_for_module(self) -> None:
        rs = load_rules(_FIXTURE)
        assert rs.layer_for_module("WalletCore") == "core"
        assert rs.layer_for_module("WalletUI") == "ui"
        assert rs.layer_for_module("Unknown") is None


class TestLoadRulesInvalidYAML:
    def test_invalid_yaml_raises_config_error(self, tmp_path: Path) -> None:
        rule_file = tmp_path / ".palace" / "architecture-rules.yaml"
        rule_file.parent.mkdir()
        rule_file.write_text("{invalid yaml: [unclosed", encoding="utf-8")
        with pytest.raises(ExtractorConfigError, match="invalid YAML"):
            load_rules(tmp_path)

    def test_non_mapping_raises_config_error(self, tmp_path: Path) -> None:
        rule_file = tmp_path / ".palace" / "architecture-rules.yaml"
        rule_file.parent.mkdir()
        rule_file.write_text("- not_a_mapping\n", encoding="utf-8")
        with pytest.raises(ExtractorConfigError, match="must be a YAML mapping"):
            load_rules(tmp_path)


class TestLoadRulesUnknownKind:
    def test_unknown_kind_produces_warning(self, tmp_path: Path) -> None:
        rule_file = tmp_path / ".palace" / "architecture-rules.yaml"
        rule_file.parent.mkdir()
        rule_file.write_text(
            yaml.dump(
                {
                    "layers": [{"name": "core", "module_globs": ["Core"]}],
                    "rules": [
                        {
                            "id": "bad_rule",
                            "kind": "unsupported_future_rule",
                            "severity": "high",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        rs = load_rules(tmp_path)
        assert any("unsupported_future_rule" in w for w in rs.loader_warnings)
        assert rs.rules == []  # skipped

    def test_unknown_kind_does_not_crash(self, tmp_path: Path) -> None:
        rule_file = tmp_path / ".palace" / "architecture-rules.yaml"
        rule_file.parent.mkdir()
        rule_file.write_text(
            yaml.dump(
                {
                    "layers": [],
                    "rules": [{"id": "r", "kind": "mystery_kind"}],
                }
            ),
            encoding="utf-8",
        )
        rs = load_rules(tmp_path)
        assert isinstance(rs, RuleSet)


class TestSearchPriority:
    def test_palace_takes_precedence_over_docs(self, tmp_path: Path) -> None:
        palace_dir = tmp_path / ".palace"
        palace_dir.mkdir()
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()

        (palace_dir / "architecture-rules.yaml").write_text(
            yaml.dump(
                {
                    "layers": [{"name": "palace_layer", "module_globs": ["*"]}],
                    "rules": [],
                }
            ),
            encoding="utf-8",
        )
        (docs_dir / "architecture-rules.yaml").write_text(
            yaml.dump(
                {"layers": [{"name": "docs_layer", "module_globs": ["*"]}], "rules": []}
            ),
            encoding="utf-8",
        )
        rs = load_rules(tmp_path)
        layer_names = [la.name for la in rs.layers]
        assert "palace_layer" in layer_names
        assert "docs_layer" not in layer_names
