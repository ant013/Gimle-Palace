"""Strict Pydantic models for reactive_dependency_tracer."""

from __future__ import annotations

from enum import Enum
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from palace_mcp.extractors.foundation.models import Language, SCHEMA_VERSION_CURRENT

REACTIVE_TRACER_SOURCE: Final[Literal["extractor.reactive_dependency_tracer"]] = (
    "extractor.reactive_dependency_tracer"
)
MAX_REDACTED_MESSAGE_LEN = 512


class Range(BaseModel):
    """1-based inclusive source range."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    start_line: int = Field(..., ge=1)
    start_col: int = Field(..., ge=1)
    end_line: int = Field(..., ge=1)
    end_col: int = Field(..., ge=1)

    @model_validator(mode="after")
    def _validate_order(self) -> "Range":
        if self.end_line < self.start_line:
            raise ValueError("end_line must be >= start_line")
        if self.end_line == self.start_line and self.end_col < self.start_col:
            raise ValueError("end_col must be >= start_col when lines match")
        return self


class ReactiveResolutionStatus(str, Enum):
    SYNTAX_EXACT = "syntax_exact"
    SYNTAX_HEURISTIC = "syntax_heuristic"
    SYMBOL_CORRELATED = "symbol_correlated"
    MACRO_UNEXPANDED = "macro_unexpanded"
    TYPE_UNRESOLVED = "type_unresolved"


class ReactiveComponentKind(str, Enum):
    SWIFTUI_VIEW = "swiftui_view"
    OBSERVABLE_TYPE = "observable_type"
    VIEW_MODEL = "view_model"
    FUNCTION = "function"
    CLOSURE = "closure"
    COMBINE_PIPELINE = "combine_pipeline"
    UIKIT_CONTROLLER = "uikit_controller"
    COMPOSABLE = "composable"
    UNKNOWN = "unknown"


class ReactiveStateKind(str, Enum):
    STATE = "state"
    BINDING = "binding"
    OBSERVABLE = "observable"
    OBSERVABLE_OBJECT = "observable_object"
    PUBLISHED = "published"
    ENVIRONMENT = "environment"
    ENVIRONMENT_OBJECT = "environment_object"
    PUBLISHER = "publisher"
    SUBJECT = "subject"
    ASYNC_SEQUENCE = "async_sequence"
    CALLBACK = "callback"
    DELEGATE = "delegate"
    NOTIFICATION = "notification"
    COMPOSE_STATE = "compose_state"
    FLOW = "flow"
    UNKNOWN = "unknown"


class MacroExpansionStatus(str, Enum):
    NOT_APPLICABLE = "not_applicable"
    NOT_EXPANDED = "not_expanded"
    EXPANDED = "expanded"
    UNKNOWN = "unknown"


class ReactiveEffectKind(str, Enum):
    RENDER = "render"
    SINK = "sink"
    ASSIGN = "assign"
    TASK = "task"
    ON_CHANGE = "on_change"
    ON_RECEIVE = "on_receive"
    CALLBACK = "callback"
    DELEGATE_CALL = "delegate_call"
    NAVIGATION = "navigation"
    PRESENTATION = "presentation"
    NETWORK_CALL_CANDIDATE = "network_call_candidate"
    STORAGE_WRITE_CANDIDATE = "storage_write_candidate"
    UNKNOWN = "unknown"


class ReactiveConfidence(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ReactiveEdgeKind(str, Enum):
    DECLARES_STATE = "declares_state"
    READS_STATE = "reads_state"
    WRITES_STATE = "writes_state"
    BINDS_TO = "binds_to"
    TRIGGERS_EFFECT = "triggers_effect"
    HAS_LIFECYCLE_EFFECT = "has_lifecycle_effect"
    CALLS_REACTIVE_COMPONENT = "calls_reactive_component"


class TriggerExpressionKind(str, Enum):
    ON_CHANGE_OF = "on_change_of"
    ON_RECEIVE_PUBLISHER = "on_receive_publisher"
    TASK_ID = "task_id"
    BINDING_WRITE = "binding_write"
    STATE_WRITE = "state_write"
    PUBLISHER_SINK = "publisher_sink"
    LIFECYCLE = "lifecycle"
    UNKNOWN = "unknown"


class DiagnosticSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class ReactiveDiagnosticCode(str, Enum):
    SWIFT_HELPER_UNAVAILABLE = "swift_helper_unavailable"
    SWIFT_HELPER_VERSION_UNSUPPORTED = "swift_helper_version_unsupported"
    SWIFT_PARSE_FAILED = "swift_parse_failed"
    SWIFT_FILE_TOO_LARGE = "swift_file_too_large"
    SWIFT_GENERATED_OR_VENDOR_SKIPPED = "swift_generated_or_vendor_skipped"
    KOTLIN_TOOLING_UNAVAILABLE = "kotlin_tooling_unavailable"
    DETEKT_TYPE_RESOLUTION_UNAVAILABLE = "detekt_type_resolution_unavailable"
    COMPOSE_STABILITY_REPORT_UNAVAILABLE = "compose_stability_report_unavailable"
    SYMBOL_CORRELATION_UNAVAILABLE = "symbol_correlation_unavailable"
    MAX_EDGES_PER_FILE_EXCEEDED = "max_edges_per_file_exceeded"
    INVALID_HELPER_REF = "invalid_helper_ref"
    HELPER_JSON_TOO_LARGE = "helper_json_too_large"
    PATH_EMPTY = "path_empty"
    PATH_PARENT_TRAVERSAL = "path_parent_traversal"
    PATH_ABSOLUTE_OUTSIDE_REPO = "path_absolute_outside_repo"
    PATH_SYMLINK_ESCAPE = "path_symlink_escape"
    PATH_WINDOWS_SEPARATOR = "path_windows_separator"
    RAW_SOURCE_SNIPPET_REJECTED = "raw_source_snippet_rejected"
    PARTIAL_BATCH_VALIDATION_FAILED = "partial_batch_validation_failed"
    MACRO_UNEXPANDED = "macro_unexpanded"


class ReactiveComponent(BaseModel):
    """Reactive container such as a SwiftUI view or callback scope."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    group_id: str
    project: str
    commit_sha: str
    language: Language
    module_name: str
    file_path: str
    qualified_name: str
    display_name: str
    component_kind: ReactiveComponentKind
    start_line: int = Field(..., ge=1)
    end_line: int = Field(..., ge=1)
    range: Range
    resolution_status: ReactiveResolutionStatus
    schema_version: int = Field(default=SCHEMA_VERSION_CURRENT, ge=1)
    source: Literal["extractor.reactive_dependency_tracer"] = REACTIVE_TRACER_SOURCE


class ReactiveState(BaseModel):
    """Reactive state-bearing declaration."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    group_id: str
    project: str
    commit_sha: str
    language: Language
    module_name: str
    file_path: str
    owner_qualified_name: str
    state_name: str
    declared_type: str | None = None
    state_kind: ReactiveStateKind
    wrapper_or_api: str | None = None
    macro_expansion_status: MacroExpansionStatus
    resolution_status: ReactiveResolutionStatus
    confidence: ReactiveConfidence
    schema_version: int = Field(default=SCHEMA_VERSION_CURRENT, ge=1)
    source: Literal["extractor.reactive_dependency_tracer"] = REACTIVE_TRACER_SOURCE


class ReactiveEffect(BaseModel):
    """Reactive effect or sink triggered by state or lifecycle."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    group_id: str = ""
    project: str = ""
    commit_sha: str = ""
    language: Language = Language.UNKNOWN
    component_id: str
    effect_kind: ReactiveEffectKind
    callee_name: str | None = None
    file_path: str
    start_line: int = Field(..., ge=1)
    end_line: int = Field(..., ge=1)
    range: Range
    trigger_expression_kind: TriggerExpressionKind | None = None
    resolution_status: ReactiveResolutionStatus
    confidence: ReactiveConfidence
    source: Literal["extractor.reactive_dependency_tracer"] = REACTIVE_TRACER_SOURCE
    schema_version: int = Field(default=SCHEMA_VERSION_CURRENT, ge=1)


class ReactiveDiagnostic(BaseModel):
    """Persisted skip/warning/error evidence for the extractor."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    group_id: str
    project: str
    commit_sha: str
    run_id: str
    language: Language
    file_path: str | None = None
    ref: str | None = None
    diagnostic_code: ReactiveDiagnosticCode
    severity: DiagnosticSeverity
    message_redacted: str | None = Field(
        default=None, max_length=MAX_REDACTED_MESSAGE_LEN
    )
    range: Range | None = None
    source: Literal["extractor.reactive_dependency_tracer"] = REACTIVE_TRACER_SOURCE
    schema_version: int = Field(default=SCHEMA_VERSION_CURRENT, ge=1)


class ReactiveEdge(BaseModel):
    """Normalized relationship record before Neo4j write."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    owner_component_id: str
    edge_kind: ReactiveEdgeKind
    source_id: str
    target_id: str
    file_path: str
    line: int = Field(..., ge=1)
    confidence: ReactiveConfidence
    access_path: str | None = None
    binding_kind: str | None = None
    trigger_expression_kind: TriggerExpressionKind | None = None
    resolution_status: ReactiveResolutionStatus

    @model_validator(mode="after")
    def _validate_trigger_contract(self) -> "ReactiveEdge":
        if (
            self.edge_kind is ReactiveEdgeKind.TRIGGERS_EFFECT
            and self.trigger_expression_kind is None
        ):
            raise ValueError(
                "trigger_expression_kind is required for triggers_effect edges"
            )
        return self
