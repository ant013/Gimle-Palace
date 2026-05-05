"""Pydantic v2 models for the dead_symbol_binary_surface extractor."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from palace_mcp.extractors.foundation.models import SCHEMA_VERSION_CURRENT


class DeadSymbolLanguage(str, Enum):
    """Language supported by dead symbol evidence in v1."""

    SWIFT = "swift"
    KOTLIN = "kotlin"
    JAVA = "java"
    UNKNOWN = "unknown"


class DeadSymbolKind(str, Enum):
    """Normalized declaration kinds emitted by dead symbol tools."""

    CLASS = "class"
    STRUCT = "struct"
    ENUM = "enum"
    PROTOCOL = "protocol"
    FUNCTION = "function"
    PROPERTY = "property"
    INITIALIZER = "initializer"
    TYPEALIAS = "typealias"
    UNKNOWN = "unknown"


class DeadSymbolEvidenceSource(str, Enum):
    """Origin of the dead symbol signal."""

    PERIPHERY = "periphery"
    REAPER = "reaper"
    CODEQL = "codeql"
    SYNTHETIC_FIXTURE = "synthetic_fixture"


class DeadSymbolEvidenceMode(str, Enum):
    """Evidence mode for a candidate."""

    STATIC = "static"
    RUNTIME = "runtime"
    HYBRID = "hybrid"


class Confidence(str, Enum):
    """Confidence level for candidate reviewability."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class CandidateState(str, Enum):
    """Dead symbol state emitted after correlation."""

    UNUSED_CANDIDATE = "unused_candidate"
    RETAINED_PUBLIC_API = "retained_public_api"
    RUNTIME_UNSEEN = "runtime_unseen"
    STATIC_UNREFERENCED = "static_unreferenced"
    SKIPPED = "skipped"


class SkipReason(str, Enum):
    """Reason a candidate should not be treated as deletable."""

    PUBLIC_API_RETAINED = "public_api_retained"
    CROSS_MODULE_CONTRACT_CONSUMED = "cross_module_contract_consumed"
    GENERATED_CODE = "generated_code"
    DYNAMIC_ENTRY_POINT = "dynamic_entry_point"
    AMBIGUOUS_SYMBOL_MATCH = "ambiguous_symbol_match"
    MISSING_SYMBOL_KEY = "missing_symbol_key"


class SurfaceKind(str, Enum):
    """Binary/public visibility surface for a symbol."""

    PUBLIC_API = "public_api"
    BINARY_VISIBLE = "binary_visible"
    DYNAMIC_ENTRY_POINT = "dynamic_entry_point"
    FRAMEWORK_RETAINED = "framework_retained"


class BinarySurfaceSource(str, Enum):
    """Source that proved a symbol belongs to the binary surface."""

    PUBLIC_API_SURFACE = "public_api_surface"
    PERIPHERY_RETAIN_PUBLIC = "periphery_retain_public"
    MANUAL_FIXTURE = "manual_fixture"
    CODEQL = "codeql"
    REAPER = "reaper"


class DeadSymbolCandidate(BaseModel):
    """A reviewable dead symbol candidate with explicit evidence quality."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    group_id: str
    project: str
    module_name: str
    language: DeadSymbolLanguage
    commit_sha: str
    symbol_key: str = ""
    display_name: str
    kind: DeadSymbolKind
    source_file: str | None = None
    source_line: int | None = Field(default=None, ge=1)
    evidence_source: DeadSymbolEvidenceSource
    evidence_mode: DeadSymbolEvidenceMode
    confidence: Confidence
    candidate_state: CandidateState
    skip_reason: SkipReason | None = None
    schema_version: int = Field(default=SCHEMA_VERSION_CURRENT, ge=1)

    @model_validator(mode="after")
    def _validate_symbol_key_or_file_line_fallback(self) -> "DeadSymbolCandidate":
        if self.symbol_key:
            return self
        if self.source_file and self.source_line is not None:
            return self
        raise ValueError(
            "symbol_key must be non-empty unless source_file and source_line are present"
        )

    @model_validator(mode="after")
    def _validate_skip_reason_contract(self) -> "DeadSymbolCandidate":
        if (
            self.candidate_state is CandidateState.UNUSED_CANDIDATE
            and self.skip_reason is not None
        ):
            raise ValueError("unused_candidate must not include skip_reason")
        if self.candidate_state is CandidateState.SKIPPED and self.skip_reason is None:
            raise ValueError("skipped candidates must include skip_reason")
        return self


class BinarySurfaceRecord(BaseModel):
    """Binary/public retention record attached to a candidate or API symbol."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    group_id: str
    project: str
    module_name: str
    language: DeadSymbolLanguage
    commit_sha: str
    symbol_key: str
    surface_kind: SurfaceKind
    retention_reason: str
    source: BinarySurfaceSource
    schema_version: int = Field(default=SCHEMA_VERSION_CURRENT, ge=1)
