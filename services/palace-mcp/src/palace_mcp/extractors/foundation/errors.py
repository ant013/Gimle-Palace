"""Extractor error codes and error envelope (GIM-101a — Silent-failure F2 fix)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal


class ExtractorErrorCode(str, Enum):
    """Exhaustive error code surface for all foundation extractor failures."""

    # Config
    INVALID_PROJECT = "invalid_project"
    SCIP_PATH_REQUIRED = "scip_path_required"  # 101b only
    PERIPHERY_FIXTURES_MISSING = "periphery_fixtures_missing"
    PUBLIC_API_ARTIFACTS_REQUIRED = "public_api_artifacts_required"
    PUBLIC_API_PARSE_FAILED = "public_api_parse_failed"

    # Schema
    SCHEMA_DRIFT_DETECTED = "schema_drift_detected"
    SCHEMA_BOOTSTRAP_FAILED = "schema_bootstrap_failed"

    # Counter
    COUNTER_STATE_CORRUPT = "counter_state_corrupt"

    # Tantivy
    TANTIVY_OPEN_FAILED = "tantivy_open_failed"
    TANTIVY_COMMIT_FAILED = "tantivy_commit_failed"
    TANTIVY_DISK_FULL = "tantivy_disk_full"
    TANTIVY_LOCK_HELD = "tantivy_lock_held"
    TANTIVY_DELETE_FAILED = "tantivy_delete_failed"

    # Neo4j
    NEO4J_SHADOW_WRITE_FAILED = "neo4j_shadow_write_failed"
    CHECKPOINT_WRITE_FAILED = "checkpoint_write_failed"
    EVICTION_ROUND_1_FAILED = "eviction_round_1_failed"
    EVICTION_ROUND_2_FAILED = "eviction_round_2_failed"
    EVICTION_ROUND_3_FAILED = "eviction_round_3_failed"

    # Budget
    BUDGET_EXCEEDED = "budget_exceeded"
    BUDGET_EXCEEDED_RESUME_BLOCKED = "budget_exceeded_resume_blocked"

    # Checkpoint
    CHECKPOINT_DOC_COUNT_MISMATCH = "checkpoint_doc_count_mismatch"

    # Cross-repo version skew (GIM-218, Roadmap #39)
    BUNDLE_HAS_NO_MEMBERS = "bundle_has_no_members"
    BUNDLE_INVALID = "bundle_invalid"
    BUNDLE_NOT_REGISTERED = "bundle_not_registered"
    DEPENDENCY_SURFACE_NOT_INDEXED = "dependency_surface_not_indexed"
    EXTRACTOR_RUNTIME_ERROR = "extractor_runtime_error"
    INVALID_ECOSYSTEM_FILTER = "invalid_ecosystem_filter"
    INVALID_SEVERITY_FILTER = "invalid_severity_filter"
    MISSING_TARGET = "missing_target"
    MUTUALLY_EXCLUSIVE_ARGS = "mutually_exclusive_args"
    SLUG_INVALID = "slug_invalid"
    TOP_N_OUT_OF_RANGE = "top_n_out_of_range"

    # Code ownership extractor (GIM-216)
    GIT_HISTORY_NOT_INDEXED = "git_history_not_indexed"
    OWNERSHIP_DIFF_FAILED = "ownership_diff_failed"
    OWNERSHIP_MAX_FILES_EXCEEDED = "ownership_max_files_exceeded"
    REPO_HEAD_INVALID = "repo_head_invalid"


ActionType = Literal[
    "retry",
    "rebuild_tantivy",
    "manual_cleanup",
    "raise_budget",
    "restore_backup",
]


@dataclass
class ExtractorError(Exception):
    """Structured error raised from extractor failure paths.

    Subclasses Exception so it can be raised and caught normally.
    Always includes a machine-readable error_code and a human message.
    The action field tells the operator what to do to recover.
    """

    error_code: ExtractorErrorCode
    message: str
    recoverable: bool
    action: ActionType
    phase: str | None = None
    partial_writes: int | None = None
    context: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        super().__init__(self.message)
