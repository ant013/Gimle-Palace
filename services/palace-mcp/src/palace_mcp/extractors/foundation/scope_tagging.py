from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from neo4j import AsyncManagedTransaction

ALLOWED_LABELS = frozenset(
    {
        "A11yMissing",
        "ArchRule",
        "ArchViolation",
        "Author",
        "CatchSite",
        "Commit",
        "Convention",
        "ConventionViolation",
        "CryptoFinding",
        "DiPattern",
        "ErrorFinding",
        "ExternalDependency",
        "File",
        "Function",
        "HardcodedString",
        "Layer",
        "LocaleResource",
        "Module",
        "OwnershipFileState",
        "PR",
        "PRComment",
        "TestDouble",
        "UntestableSite",
    }
)


def _create_query(label: str) -> str:
    return f"CREATE (n:{label}) SET n += $props"


class ScopeTaggedWriter:
    def __init__(
        self,
        *,
        default_group_id: str | None = None,
        remove_legacy_path: bool = False,
    ) -> None:
        self._default_group_id = default_group_id
        self._remove_legacy_path = remove_legacy_path

    def normalize_props(
        self,
        props: Mapping[str, Any],
        *,
        group_id: str | None = None,
    ) -> dict[str, Any]:
        effective_group_id = group_id or self._default_group_id
        if not effective_group_id:
            raise ValueError("group_id is required")

        normalized = dict(props)
        normalized["group_id"] = effective_group_id

        path = normalized.get("path")
        file_path = normalized.get("file_path")
        if file_path is None and path is not None:
            normalized["file_path"] = path
        elif path is None and file_path is not None and not self._remove_legacy_path:
            normalized["path"] = file_path

        if self._remove_legacy_path:
            normalized.pop("path", None)

        return normalized

    async def write_node(
        self,
        tx: AsyncManagedTransaction,
        label: str,
        props: Mapping[str, Any],
        *,
        group_id: str | None = None,
    ) -> None:
        if label not in ALLOWED_LABELS:
            raise ValueError(f"label {label!r} is not allowed")
        await tx.run(
            _create_query(label),
            props=self.normalize_props(props, group_id=group_id),
        )
