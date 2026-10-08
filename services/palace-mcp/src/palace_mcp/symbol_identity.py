"""Shared symbol identity helpers for Palace code tools and ingest."""

from __future__ import annotations

from urllib.parse import unquote

_KIND_ALIASES: dict[str, str] = {
    "project": "project",
    "file": "file",
    "module": "module",
    "route": "route",
    "function": "function",
    "method": "method",
    "abstractmethod": "method",
    "protocolmethod": "method",
    "staticmethod": "method",
    "purevirtualmethod": "method",
    "traitmethod": "method",
    "subscript": "method",
    "class": "class",
    "struct": "struct",
    "protocol": "protocol",
    "interface": "protocol",
    "trait": "protocol",
    "property": "property",
    "field": "property",
    "variable": "property",
    "staticproperty": "property",
    "staticfield": "property",
    "staticvariable": "property",
    "enummember": "property",
    "enum": "enum",
    "type": "type",
    "typealias": "typealias",
    "associatedtype": "typealias",
    "extension": "extension",
    "constructor": "initializer",
    "initializer": "initializer",
    "getter": "accessor",
    "setter": "accessor",
    "accessor": "accessor",
    "actor": "actor",
}

_KIND_TO_LABEL: dict[str, str] = {
    "project": "Project",
    "file": "File",
    "module": "Module",
    "route": "Route",
    "function": "Function",
    "method": "Method",
    "class": "Class",
    "struct": "Struct",
    "protocol": "Protocol",
    "property": "Property",
    "enum": "Enum",
    "type": "Type",
    "typealias": "TypeAlias",
    "extension": "Extension",
    "initializer": "Initializer",
    "accessor": "Accessor",
    "actor": "Actor",
}


def _normalize_kind_key(value: str | None) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    return raw.replace("-", "").replace("_", "").replace(" ", "").lower()


def canonical_symbol_kind(kind: str | None) -> str:
    raw = (kind or "").strip()
    if not raw:
        return ""
    return _KIND_ALIASES.get(_normalize_kind_key(raw), raw.lower())


def canonical_symbol_label(kind_or_label: str | None) -> str:
    raw = (kind_or_label or "").strip()
    if not raw:
        return ""
    canonical_kind = canonical_symbol_kind(raw)
    return _KIND_TO_LABEL.get(canonical_kind, raw)


def _split_scip_top_level(symbol: str) -> list[str]:
    parts: list[str] = []
    cur: list[str] = []
    in_escape = False
    i = 0
    n = len(symbol)
    while i < n:
        char = symbol[i]
        if char == "`":
            if in_escape and i + 1 < n and symbol[i + 1] == "`":
                cur.append("``")
                i += 2
                continue
            cur.append(char)
            in_escape = not in_escape
            i += 1
            continue
        if char == " " and not in_escape:
            parts.append("".join(cur))
            cur = []
            i += 1
            continue
        cur.append(char)
        i += 1
    if cur:
        parts.append("".join(cur))
    return parts


def _length_prefixed_identifiers(symbol: str) -> list[tuple[str, str]]:
    identifiers: list[tuple[str, str]] = []
    i = 0
    n = len(symbol)
    while i < n:
        if not symbol[i].isdigit():
            i += 1
            continue
        j = i
        while j < n and symbol[j].isdigit():
            j += 1
        length = int(symbol[i:j])
        if length <= 0 or j + length > n:
            i = j
            continue
        end = j + length
        next_char = symbol[end] if end < n else ""
        identifiers.append((symbol[j:end], next_char))
        i = end
    return identifiers


def _decode_short_name(value: str) -> str:
    raw = value.strip()
    if not raw:
        return ""

    parts = _split_scip_top_level(raw)
    candidate = next(
        (part for part in reversed(parts) if part and part not in {".", "#", ":"}),
        raw,
    )
    decoded = unquote(candidate)
    identifiers = _length_prefixed_identifiers(decoded)
    if identifiers:
        type_marker_indexes = [
            idx
            for idx, (_name, next_char) in enumerate(identifiers)
            if next_char in "CPOVAE"
        ]
        if type_marker_indexes:
            boundary = type_marker_indexes[-1]
            if boundary + 1 < len(identifiers):
                return identifiers[boundary + 1][0]
            return identifiers[boundary][0]
        return identifiers[0][0]

    if "." in decoded:
        return decoded.rsplit(".", 1)[-1]
    if "/" in decoded:
        return decoded.rsplit("/", 1)[-1]
    return decoded.rstrip("#().:")


def canonical_symbol_short_name(
    qualified_name: str | None,
    *,
    short_name: str | None = None,
    name: str | None = None,
    symbol: str | None = None,
) -> str:
    for candidate in (short_name, name, symbol, qualified_name):
        normalized = _decode_short_name(candidate or "")
        if normalized:
            return normalized
    return ""


def canonical_symbol_short_name_candidates(
    qualified_name: str | None,
    *,
    short_name: str | None = None,
    name: str | None = None,
    symbol: str | None = None,
) -> list[str]:
    normalized = canonical_symbol_short_name(
        qualified_name,
        short_name=short_name,
        name=name,
        symbol=symbol,
    )
    if not normalized:
        return []
    candidates = [normalized]
    if "(" in normalized:
        candidates.append(normalized.split("(", 1)[0])
    return list(dict.fromkeys(candidate for candidate in candidates if candidate))
