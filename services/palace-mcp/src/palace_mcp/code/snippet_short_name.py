"""Helpers for deriving short symbol names for snippet lookup."""

from __future__ import annotations

from urllib.parse import unquote


def snippet_short_name(value: str) -> str:
    raw = value.strip()
    if not raw:
        return ""
    decoded = unquote(raw)
    candidate = decoded.rsplit(".", 1)[-1].rsplit("/", 1)[-1]
    return candidate.rstrip("#().:")


def snippet_short_name_candidates(value: str) -> list[str]:
    short_name = snippet_short_name(value)
    if not short_name:
        return []
    candidates = [short_name]
    if "(" in short_name:
        candidates.append(short_name.split("(", 1)[0])
    return list(dict.fromkeys(candidate for candidate in candidates if candidate))
