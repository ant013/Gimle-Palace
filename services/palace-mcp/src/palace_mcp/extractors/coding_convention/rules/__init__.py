from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Iterable

from palace_mcp.extractors.coding_convention.rules._base import ConventionRule


def load_rules() -> tuple[ConventionRule, ...]:
    discovered: list[ConventionRule] = []
    for module_info in sorted(pkgutil.iter_modules(__path__), key=lambda item: item.name):
        if module_info.name.startswith("_"):
            continue
        module = importlib.import_module(f"{__name__}.{module_info.name}")
        discovered.extend(getattr(module, "RULES", ()))
    return register_rules(discovered)


def register_rules(rules: Iterable[ConventionRule]) -> tuple[ConventionRule, ...]:
    ordered = sorted(rules, key=lambda rule: rule.kind)
    seen: set[str] = set()
    for rule in ordered:
        if rule.kind in seen:
            raise ValueError(f"Duplicate coding convention rule kind: {rule.kind}")
        seen.add(rule.kind)
    return tuple(ordered)


__all__ = ["ConventionRule", "load_rules", "register_rules"]
