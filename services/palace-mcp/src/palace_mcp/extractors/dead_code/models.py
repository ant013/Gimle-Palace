"""Pydantic models for dead_code extractor (G0d)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class FindingKind(str, Enum):
    DEAD_SYMBOL = "dead_symbol"
    DEAD_EXTENSION_CHAIN = "dead_extension_chain"
    DEAD_SCC_CLUSTER = "dead_scc_cluster"
    DEAD_MODULE = "dead_module"


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class MemberEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    qualified_name: str
    kind: str
    file_path: str | None = None


_AUTO_ID_SENTINEL = "_auto"


def _derive_finding_id(
    project: str, kind: FindingKind, members: list[MemberEntry]
) -> str:
    """Deterministic ID from (project, kind, sorted member qnames).

    Stable across re-runs → MERGE in Neo4j updates existing node instead of
    creating a duplicate, eliminating append-only count inflation observed
    by CXCR on G0d v1 (GIM-785 review).
    """
    sorted_qnames = sorted(m.qualified_name for m in members)
    content = f"{project}|{kind.value}|{','.join(sorted_qnames)}"
    return f"fd_{hashlib.sha256(content.encode()).hexdigest()[:16]}"


class DeadFinding(BaseModel):
    model_config = ConfigDict(frozen=True)

    finding_id: str = _AUTO_ID_SENTINEL
    kind: FindingKind
    severity: Severity
    project: str
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    members: list[MemberEntry]
    size: int
    reachable_from_public_surface: bool = False
    reachable_from_dynamic_dispatch: bool = False
    git_last_external_ref: str | None = None
    safe_to_delete_score: float = Field(default=0.5, ge=0.0, le=1.0)
    evidence_query: str = ""
    # dead_module only
    module_coverage_ratio: float | None = None
    # dead_extension_chain only
    target_dead_type: str | None = None
    protocol_conformance_checks: list[dict[str, Any]] | None = None

    @model_validator(mode="after")
    def _populate_deterministic_finding_id(self) -> "DeadFinding":
        if self.finding_id == _AUTO_ID_SENTINEL:
            object.__setattr__(
                self,
                "finding_id",
                _derive_finding_id(self.project, self.kind, self.members),
            )
        return self


@dataclass(frozen=True)
class SymbolNode:
    """In-memory representation of a symbol node from the SCIP graph."""

    qualified_name: str
    kind: str  # class|struct|enum|protocol|function|property|extension|actor
    file_path: str | None = None
    module_name: str | None = None
    # Access visibility
    is_public: bool = False
    is_open: bool = False
    # Dynamic dispatch markers (Step 1b)
    is_objc: bool = False
    is_dynamic: bool = False
    is_objc_members: bool = False
    is_ns_managed: bool = False
    is_property_wrapper: bool = False
    is_codable: bool = False
    is_iboutlet: bool = False
    is_ibaction: bool = False
    is_swift_app_storage: bool = False  # @AppStorage / @SceneStorage
    is_env_key: bool = False  # EnvironmentKey / PreferenceKey conformance
    is_main_entry: bool = False  # @main, ApplicationDelegate, etc.
    # Mirror usage (affects safe_to_delete_score)
    referenced_via_mirror: bool = False
    # Protocol conformance (for extension chain)
    extends_protocol: str | None = None  # protocol name if this is an extension


@dataclass(frozen=True)
class GraphEdge:
    """Directed edge in the SCIP symbol graph."""

    source: str  # qualified_name
    target: str  # qualified_name
    kind: str  # CALLS|REFERENCES|EXTENDS|CONFORMS_TO|EXTENSION_OF


@dataclass
class SymbolGraph:
    """Full in-memory graph for the dead-code algorithm."""

    symbols: dict[str, SymbolNode] = field(default_factory=dict)
    edges: list[GraphEdge] = field(default_factory=list)
    # Derived: adjacency list (source → set of targets)
    _adj: dict[str, set[str]] = field(default_factory=dict, init=False, repr=False)
    # Extensions of a type (type_qn → list of extension qns)
    _extensions: dict[str, list[str]] = field(
        default_factory=dict, init=False, repr=False
    )
    # Symbols that use a protocol via existential (protocol_qn → True)
    _existential_protocols: set[str] = field(
        default_factory=set, init=False, repr=False
    )

    def build_indexes(self) -> None:
        """Build derived lookup structures from edges."""
        for edge in self.edges:
            self._adj.setdefault(edge.source, set()).add(edge.target)
            if edge.kind == "EXTENSION_OF":
                self._extensions.setdefault(edge.target, []).append(edge.source)
            if edge.kind == "EXISTENTIAL_USE":
                self._existential_protocols.add(edge.target)

    def adj(self, qn: str) -> set[str]:
        return self._adj.get(qn, set())

    def extensions_of(self, type_qn: str) -> list[str]:
        return self._extensions.get(type_qn, [])

    def used_via_existential(self, protocol_qn: str) -> bool:
        return protocol_qn in self._existential_protocols
