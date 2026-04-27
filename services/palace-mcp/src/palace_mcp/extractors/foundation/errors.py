"""Extractor error codes and error envelope (GIM-101a — Silent-failure F2 fix)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal


class ExtractorErrorCode(str, Enum):
    """Exhaustive error code surface for all foundation extractor failures.

    16 codes covering config, schema, counter, tantivy, neo4j, and budget
    failure modes. Using str-Enum so codes serialize naturally to JSON.
    """

    # Config
    INVALID_PROJECT = "invalid_project"
    SCIP_PATH_REQUIRED = "scip_path_required"  # 101b only

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
