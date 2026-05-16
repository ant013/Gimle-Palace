"""Resolve {{a.b.c}} template refs against allowed sources per UAA spec §6.5.

Allowed sources:
  - manifest fields: project.*, domain.*, mcp.*, agent.*
  - host-local: bindings.*, paths.*, plugins.*

Unresolved {{vars}} raise UnresolvedTemplateError (no silent fallthrough).
"""
from __future__ import annotations

import re

ALLOWED_TOP_LEVEL = {
    "manifest", "bindings", "paths", "plugins", "agent",
    "project", "domain", "mcp",  # manifest.* shorthand
}

TEMPLATE_RE = re.compile(r"\{\{\s*([^}\s]+)\s*\}\}")


class UnresolvedTemplateError(Exception):
    pass


def _walk(data, key_path: list[str], full_ref: str):
    cur = data
    for k in key_path:
        if not isinstance(cur, dict) or k not in cur:
            raise UnresolvedTemplateError(
                f"unresolved placeholder: {{{{{full_ref}}}}}; missing key {k!r}",
            )
        cur = cur[k]
    if cur is None:
        raise UnresolvedTemplateError(
            f"unresolved placeholder: {{{{{full_ref}}}}}; key resolves to null",
        )
    return cur


def resolve(text: str, sources: dict) -> str:
    """Replace {{a.b.c}} with values from sources dict.

    Args:
        text: raw text containing {{...}} placeholders.
        sources: dict with allowed top-level keys mapping to nested dicts.
                 e.g. {"manifest": {"project": {"key": "synth"}}, "bindings": {...}}

    Returns:
        text with placeholders replaced.

    Raises:
        UnresolvedTemplateError on any placeholder that can't be resolved.
    """
    def _sub(m: re.Match) -> str:
        ref = m.group(1)
        parts = ref.split(".")
        top = parts[0]
        if top not in ALLOWED_TOP_LEVEL:
            raise UnresolvedTemplateError(
                f"unresolved placeholder: {{{{{ref}}}}}; unknown source {top!r} "
                f"(allowed: {sorted(ALLOWED_TOP_LEVEL)})",
            )
        # manifest shorthand: {{project.key}} == {{manifest.project.key}}
        if top in {"project", "domain", "mcp", "agent"}:
            data = sources.get("manifest", {})
            value = _walk(data, parts, ref)
        else:
            data = sources.get(top, {})
            value = _walk(data, parts[1:], ref)
        return str(value)

    return TEMPLATE_RE.sub(_sub, text)
