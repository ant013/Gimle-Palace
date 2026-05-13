"""Architecture rule-file loader for arch_layer extractor (GIM-243).

Rule file search order (first match wins):
  1. <repo_root>/.palace/architecture-rules.yaml
  2. <repo_root>/docs/architecture-rules.yaml

When no file is found: returns empty RuleSet with rules_declared=False.
Invalid YAML: raises ExtractorConfigError (operator must fix the file).
Unknown rule kinds: recorded as loader_warnings, not hard failures.
"""

from __future__ import annotations

import fnmatch
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from palace_mcp.extractors.base import ExtractorConfigError

logger = logging.getLogger(__name__)

_RULE_SEARCH_PATHS = [
    ".palace/architecture-rules.yaml",
    "docs/architecture-rules.yaml",
]

_KNOWN_RULE_KINDS = frozenset(
    {
        "forbidden_dependency",
        "forbidden_module_glob_dependency",
        "no_circular_module_deps",
        "manifest_dep_actually_used",
        "ast_dep_not_declared",
    }
)

_DEFAULT_SEVERITY: dict[str, str] = {
    "forbidden_dependency": "high",
    "forbidden_module_glob_dependency": "high",
    "no_circular_module_deps": "high",
    "ast_dep_not_declared": "high",
    "manifest_dep_actually_used": "low",
}


@dataclass(frozen=True)
class LayerDef:
    name: str
    module_globs: tuple[str, ...]


@dataclass(frozen=True)
class RuleDef:
    rule_id: str
    kind: str
    severity: str
    from_layers: tuple[str, ...]
    to_layers: tuple[str, ...]
    from_globs: tuple[str, ...]  # for glob-based rules
    to_globs: tuple[str, ...]
    message: str


@dataclass
class RuleSet:
    layers: list[LayerDef] = field(default_factory=list)
    rules: list[RuleDef] = field(default_factory=list)
    rules_declared: bool = False
    rule_source: str = ""  # path to the file that was loaded
    loader_warnings: list[str] = field(default_factory=list)

    def layer_for_module(self, module_name: str) -> str | None:
        """Return first layer name whose globs match module_name, or None."""
        for layer in self.layers:
            for glob in layer.module_globs:
                if fnmatch.fnmatch(module_name, glob):
                    return layer.name
        return None


def load_rules(repo_path: Path) -> RuleSet:
    """Load rule file from repo_path using the search path priority order."""
    rule_file: Path | None = None
    for rel in _RULE_SEARCH_PATHS:
        candidate = repo_path / rel
        if candidate.is_file():
            rule_file = candidate
            break

    if rule_file is None:
        return RuleSet()

    rule_source = str(rule_file.relative_to(repo_path))
    try:
        raw = yaml.safe_load(rule_file.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ExtractorConfigError(
            f"arch_layer: invalid YAML in rule file {rule_source}: {exc}"
        ) from exc

    if not isinstance(raw, dict):
        raise ExtractorConfigError(
            f"arch_layer: rule file {rule_source} must be a YAML mapping"
        )

    rs = RuleSet(rules_declared=True, rule_source=rule_source)
    rs.layers = _parse_layers(raw.get("layers", []), rule_source, rs.loader_warnings)
    rs.rules = _parse_rules(raw.get("rules", []), rule_source, rs.loader_warnings)
    return rs


def _parse_layers(raw: Any, rule_source: str, warnings: list[str]) -> list[LayerDef]:
    if not isinstance(raw, list):
        warnings.append(
            f"{rule_source}: 'layers' must be a list; got {type(raw).__name__}"
        )
        return []
    layers = []
    for item in raw:
        if not isinstance(item, dict) or "name" not in item:
            warnings.append(f"{rule_source}: layer entry missing 'name': {item!r}")
            continue
        globs = item.get("module_globs", [])
        if not isinstance(globs, list):
            globs = []
        layers.append(
            LayerDef(name=str(item["name"]), module_globs=tuple(str(g) for g in globs))
        )
    return layers


def _parse_rules(raw: Any, rule_source: str, warnings: list[str]) -> list[RuleDef]:
    if not isinstance(raw, list):
        warnings.append(
            f"{rule_source}: 'rules' must be a list; got {type(raw).__name__}"
        )
        return []
    rules = []
    for item in raw:
        if not isinstance(item, dict):
            warnings.append(f"{rule_source}: rule entry is not a mapping: {item!r}")
            continue
        kind = str(item.get("kind", ""))
        rule_id = str(item.get("id", "unknown"))
        if kind not in _KNOWN_RULE_KINDS:
            warnings.append(
                f"{rule_source}: unknown rule kind {kind!r} in rule {rule_id!r} — skipped"
            )
            continue
        severity = str(
            item.get("severity", _DEFAULT_SEVERITY.get(kind, "informational"))
        )
        from_layers = tuple(str(x) for x in item.get("from_layers", []))
        to_layers = tuple(str(x) for x in item.get("to_layers", []))
        from_globs = tuple(str(x) for x in item.get("from_globs", []))
        to_globs = tuple(str(x) for x in item.get("to_globs", []))
        message = str(item.get("message", f"Rule {rule_id} violated"))
        rules.append(
            RuleDef(
                rule_id=rule_id,
                kind=kind,
                severity=severity,
                from_layers=from_layers,
                to_layers=to_layers,
                from_globs=from_globs,
                to_globs=to_globs,
                message=message,
            )
        )
    return rules
