"""Pydantic v2 schemas for the extractor foundation (GIM-101a, T1).

All domain objects that cross storage boundaries (Tantivy ↔ Neo4j shadow ↔ MCP
API) are defined here. mypy --strict must pass; use @model_validator for
cross-field invariants (Python-pro Finding F-I).
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, model_validator


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

SCHEMA_VERSION_CURRENT: int = 1


class Language(str, Enum):
    """Source language for a symbol occurrence."""

    C = "c"
    CPP = "cpp"
    PYTHON = "python"
    TYPESCRIPT = "typescript"
    JAVASCRIPT = "javascript"
    JAVA = "java"
    KOTLIN = "kotlin"
    SWIFT = "swift"
    RUST = "rust"
    SOLIDITY = "solidity"
    FUNC = "func"
    TOLK = "tolk"
    ANCHOR = "anchor"
    UNKNOWN = "unknown"


class SymbolKind(str, Enum):
    """Role of a symbol at a particular occurrence site.

    EVENT and MODIFIER added for Solidity (Architect F23 / round-2 finding).
    KIND_WEIGHT table in importance.py must stay in sync.
    """

    DEF = "def"
    DECL = "decl"
    IMPL = "impl"
    USE = "use"
    ASSIGN = "assign"
    EVENT = "event"  # Solidity event definition
    MODIFIER = "modifier"  # Solidity modifier definition


class Ecosystem(str, Enum):
    """Package ecosystem for ExternalDependency purl resolution."""

    PYPI = "pypi"
    NPM = "npm"
    CARGO = "cargo"
    MAVEN = "maven"
    GRADLE = "gradle"
    COCOAPODS = "cocoapods"
    ETHEREUM = "ethereum"
    TON = "ton"
    UNKNOWN = "unknown"


class SourceType(str, Enum):
    """Origin of the SCIP index file."""

    SCIP = "scip"
    SYNTHETIC = "synthetic"  # test harness / synthesized occurrences


class PublicApiArtifactKind(str, Enum):
    """Artifact source used to build a public API snapshot."""

    KOTLIN_BCV_API = "kotlin_bcv_api"
    SWIFTINTERFACE = "swiftinterface"
    SWIFT_API_DIGESTER = "swift_api_digester"
    SKIE_OVERLAY = "skie_overlay"


class PublicApiSymbolKind(str, Enum):
    """Normalized kind for a symbol in the exported API surface."""

    CLASS = "class"
    STRUCT = "struct"
    ENUM = "enum"
    PROTOCOL = "protocol"
    INTERFACE = "interface"
    FUNCTION = "function"
    METHOD = "method"
    PROPERTY = "property"
    INITIALIZER = "initializer"
    TYPEALIAS = "typealias"
    EXTENSION = "extension"
    UNKNOWN = "unknown"


class PublicApiVisibility(str, Enum):
    """Visibility captured from an API artifact."""

    PUBLIC = "public"
    OPEN = "open"
    PROTECTED = "protected"
    PUBLISHED_API_INTERNAL = "published_api_internal"
    PACKAGE = "package"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Core occurrence model
# ---------------------------------------------------------------------------


class SymbolOccurrence(BaseModel):
    """One occurrence of a symbol in source code.

    Stored in Tantivy (primary) keyed by doc_key for uniqueness. Shadow in
    Neo4j via SymbolOccurrenceShadow.

    symbol_id constraint: signed i64 range (Python-pro Finding F-A fix for
    blake2b unsigned u64 → Tantivy i64 overflow).
    """

    model_config = {"frozen": True}

    doc_key: str = Field(
        ...,
        description="Primary key: '{symbol_id}:{file_path}:{line}:{col_start}'",
    )
    symbol_id: int = Field(..., ge=-(2**63), le=2**63 - 1)
    symbol_qualified_name: str
    kind: SymbolKind
    language: Language
    file_path: str
    line: int = Field(..., ge=0)
    col_start: int = Field(..., ge=0)
    col_end: int = Field(..., ge=0)
    importance: float = Field(..., ge=0.0, le=1.0)
    commit_sha: str
    ingest_run_id: str
    schema_version: int = Field(default=SCHEMA_VERSION_CURRENT, ge=1)
    synthesized_by: str | None = None  # extractor name if artificially emitted

    @model_validator(mode="after")
    def col_end_gte_col_start(self) -> "SymbolOccurrence":
        if self.col_end < self.col_start:
            raise ValueError(
                f"col_end ({self.col_end}) must be >= col_start ({self.col_start})"
            )
        return self

    @model_validator(mode="after")
    def doc_key_matches_fields(self) -> "SymbolOccurrence":
        expected = f"{self.symbol_id}:{self.file_path}:{self.line}:{self.col_start}"
        if self.doc_key != expected:
            raise ValueError(
                f"doc_key '{self.doc_key}' does not match expected '{expected}'"
            )
        return self


# ---------------------------------------------------------------------------
# External dependency
# ---------------------------------------------------------------------------

UNRESOLVED_VERSION_SENTINEL: str = "unresolved"


class ExternalDependency(BaseModel):
    """An external package dependency referenced from ingest."""

    model_config = {"frozen": True}

    purl: str = Field(..., description="Package URL per ECMA-427")
    ecosystem: Ecosystem
    resolved_version: str = Field(
        ...,
        description=(
            f"Pinned version string, or '{UNRESOLVED_VERSION_SENTINEL}' "
            "when resolution failed (never optional — sentinel required)."
        ),
    )
    group_id: str

    @model_validator(mode="after")
    def resolved_version_not_empty(self) -> "ExternalDependency":
        if not self.resolved_version:
            raise ValueError(
                "resolved_version must be a non-empty string "
                f"(use '{UNRESOLVED_VERSION_SENTINEL}' if resolution failed)"
            )
        return self


# ---------------------------------------------------------------------------
# Neo4j shadow + eviction
# ---------------------------------------------------------------------------


class SymbolOccurrenceShadow(BaseModel):
    """Lightweight Neo4j shadow node for eviction policy decisions.

    Authoritative for eviction ordering; Tantivy is rebuildable.
    """

    model_config = {"frozen": True}

    symbol_id: int = Field(..., ge=-(2**63), le=2**63 - 1)
    symbol_qualified_name: str
    importance: float = Field(..., ge=0.0, le=1.0)
    kind: SymbolKind
    tier_weight: float = Field(..., ge=0.0, le=1.0)
    last_seen_at: datetime
    group_id: str
    schema_version: int = Field(default=SCHEMA_VERSION_CURRENT, ge=1)


class EvictionRecord(BaseModel):
    """Written per-round when eviction removes symbols from both stores.

    Backed by a UNIQUE constraint on (symbol_qualified_name, project) so
    concurrent eviction passes are race-safe via MERGE semantics.
    """

    model_config = {"frozen": True}

    symbol_qualified_name: str
    project: str
    eviction_round: Literal["round_1", "round_2", "round_3"]
    evicted_at: datetime
    run_id: str


# ---------------------------------------------------------------------------
# Checkpoint
# ---------------------------------------------------------------------------


class IngestCheckpoint(BaseModel):
    """Source of truth for phase completion in both stores.

    Both Tantivy commit AND Neo4j shadow write must be acknowledged before
    this checkpoint is written (Architect F5 / Silent-failure F4 fix).
    """

    model_config = {"frozen": True}

    run_id: str
    project: str
    phase: Literal["phase1_defs", "phase2_user_uses", "phase3_vendor_uses"]
    expected_doc_count: int = Field(
        ...,
        ge=0,
        description=(
            "Number of Tantivy docs committed for this run+phase. "
            "Reconciliation on restart: count(docs) == expected_doc_count."
        ),
    )
    completed_at: datetime


class PublicApiSurface(BaseModel):
    """Committed snapshot of one module-level public API artifact."""

    model_config = {"frozen": True}

    id: str
    group_id: str
    project: str
    module_name: str
    language: Language
    commit_sha: str
    artifact_path: str
    artifact_kind: PublicApiArtifactKind
    tool_name: str
    tool_version: str
    generated_at: datetime | None = None
    schema_version: int = Field(default=SCHEMA_VERSION_CURRENT, ge=1)


class PublicApiSymbol(BaseModel):
    """One exported symbol captured from a public API artifact."""

    model_config = {"frozen": True}

    id: str
    group_id: str
    project: str
    module_name: str
    language: Language
    commit_sha: str
    fqn: str
    display_name: str
    kind: PublicApiSymbolKind
    visibility: PublicApiVisibility
    signature: str
    signature_hash: str
    source_artifact_path: str
    source_line: int | None = Field(default=None, ge=1)
    is_generated: bool = False
    is_bridge_exported: bool = False
    bridge_source: str | None = None
    symbol_qualified_name: str | None = None
    schema_version: int = Field(default=SCHEMA_VERSION_CURRENT, ge=1)


class TantivyOccurrenceMatch(BaseModel):
    """Committed occurrence evidence reconstructed from Tantivy stored fields."""

    model_config = {"frozen": True}

    doc_key: str
    symbol_id: int = Field(..., ge=-(2**63), le=2**63 - 1)
    file_path: str
    line: int = Field(..., ge=0)
    col_start: int = Field(..., ge=0)
    # TantivyBridge v1 can reconstruct col_start from doc_key, but col_end is not
    # stored in current segments and therefore remains optional until a future
    # reviewed schema slice adds persisted column-end retrieval.
    col_end: int | None = Field(default=None, ge=0)
    commit_sha: str


class ModuleContractConsumption(BaseModel):
    """Edge payload from ModuleContractSnapshot to PublicApiSymbol."""

    model_config = {"frozen": True}

    public_symbol_id: str
    group_id: str
    commit_sha: str
    match_key: Literal["symbol_qualified_name"] = "symbol_qualified_name"
    match_symbol_id: int = Field(..., ge=-(2**63), le=2**63 - 1)
    use_count: int = Field(..., ge=0)
    file_count: int = Field(..., ge=0)
    first_seen_path: str
    evidence_paths_sample: list[str] = Field(default_factory=list)
    schema_version: int = Field(default=SCHEMA_VERSION_CURRENT, ge=1)


class ModuleContractAffectedSymbol(BaseModel):
    """Delta edge payload referencing an existing PublicApiSymbol."""

    model_config = {"frozen": True}

    public_symbol_id: str
    change_kind: Literal["added", "removed", "signature_changed"]
    affected_use_count: int = Field(..., ge=0)
    schema_version: int = Field(default=SCHEMA_VERSION_CURRENT, ge=1)


class ModuleContractSnapshot(BaseModel):
    """One producer/consumer module pair at one commit."""

    model_config = {"frozen": True}

    id: str
    group_id: str
    project: str
    consumer_module_name: str
    producer_module_name: str
    language: Language
    commit_sha: str
    include_package: bool = False
    producer_surface_id: str
    symbol_count: int = Field(..., ge=0)
    use_count: int = Field(..., ge=0)
    file_count: int = Field(..., ge=0)
    skipped_symbol_count: int = Field(..., ge=0)
    consumer_evidence_source: Literal["tantivy_symbol_occurrence"] = (
        "tantivy_symbol_occurrence"
    )
    schema_version: int = Field(default=SCHEMA_VERSION_CURRENT, ge=1)


class ModuleContractDelta(BaseModel):
    """Minimal explicit old/new contract comparison record."""

    model_config = {"frozen": True}

    id: str
    group_id: str
    project: str
    consumer_module_name: str
    producer_module_name: str
    language: Language
    from_commit_sha: str
    to_commit_sha: str
    removed_consumed_symbol_count: int = Field(..., ge=0)
    signature_changed_consumed_symbol_count: int = Field(..., ge=0)
    added_consumed_symbol_count: int = Field(..., ge=0)
    affected_use_count: int = Field(..., ge=0)
    classification_scope: Literal["minimal_symbol_delta"] = "minimal_symbol_delta"
    schema_version: int = Field(default=SCHEMA_VERSION_CURRENT, ge=1)
