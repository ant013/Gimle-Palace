"""Extractor protocol — BaseExtractor ABC + ExtractorRunContext + errors.

Contract for all palace-mcp extractors (spec §3.5). Extractors implement
run(graphiti, ctx) and write domain nodes/edges via graphiti_runtime helpers.
The runner orchestrator handles :IngestRun lifecycle via its own driver handle.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from graphiti_core import Graphiti

if TYPE_CHECKING:
    from palace_mcp.audit.contracts import AuditContract


class ExtractorOutcome(StrEnum):
    """Successful extractor outcomes exposed to higher-level orchestration."""

    OK = "ok"
    SKIPPED = "skipped"
    NOT_APPLICABLE = "not_applicable"
    MISSING_INPUT = "missing_input"


class ExtractorExecutionMode(StrEnum):
    """How an extractor executed within a project_analyze run."""

    FULL = "full"
    INCREMENTAL = "incremental"
    SKIPPED = "skipped"


class ExtractorIncrementalCapability(StrEnum):
    """Declared behavior when a project analysis is incremental."""

    DELTA = "delta"
    GLOBAL_STALE = "global_stale"
    FULL_ONLY = "full_only"


@dataclass(frozen=True)
class AnalysisDelta:
    """Immutable run-owned source/symbol scope passed to incremental extractors."""

    delta_id: str
    base_commit: str | None
    target_commit: str | None
    changed_paths: tuple[str, ...] = ()
    removed_paths: tuple[str, ...] = ()
    changed_symbol_ids: tuple[str, ...] = ()
    removed_symbol_paths: tuple[str, ...] = ()
    reason: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "delta_id": self.delta_id,
            "base_commit": self.base_commit,
            "target_commit": self.target_commit,
            "changed_paths": list(self.changed_paths),
            "removed_paths": list(self.removed_paths),
            "changed_symbol_ids": list(self.changed_symbol_ids),
            "removed_symbol_paths": list(self.removed_symbol_paths),
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "AnalysisDelta":
        def _paths(key: str) -> tuple[str, ...]:
            raw = value.get(key)
            return tuple(str(item) for item in raw) if isinstance(raw, list) else ()

        return cls(
            delta_id=str(value["delta_id"]),
            base_commit=(
                str(value["base_commit"]) if value.get("base_commit") else None
            ),
            target_commit=(
                str(value["target_commit"]) if value.get("target_commit") else None
            ),
            changed_paths=_paths("changed_paths"),
            removed_paths=_paths("removed_paths"),
            changed_symbol_ids=_paths("changed_symbol_ids"),
            removed_symbol_paths=_paths("removed_symbol_paths"),
            reason=str(value["reason"]) if value.get("reason") else None,
        )


class BaseExtractor(ABC):
    """Contract for an extractor. Subclass + implement run()."""

    # Required class attributes
    name: ClassVar[str]
    description: ClassVar[str]

    # Schema declaration — aggregated by ensure_extractors_schema
    constraints: ClassVar[list[str]] = []
    indexes: ClassVar[list[str]] = []
    timeout_s: ClassVar[float | None] = None
    incremental_capability: ClassVar[ExtractorIncrementalCapability] = (
        ExtractorIncrementalCapability.GLOBAL_STALE
    )

    @abstractmethod
    async def run(
        self, *, graphiti: Graphiti, ctx: ExtractorRunContext
    ) -> ExtractorStats:
        """Run the extractor. Write nodes/edges via graphiti_runtime helpers.

        Returns ExtractorStats with counts (for :IngestRun finalize).
        Raise ExtractorError subclass or any Exception on failure —
        runner catches + finalizes :IngestRun as errored.
        """
        raise NotImplementedError

    def audit_contract(self) -> "AuditContract | None":
        """Return audit contract for this extractor, or None to opt out.

        Default: None. Override in extractors that participate in palace.audit.run.
        The returned AuditContract tells the fetcher which Cypher query to run
        and which Jinja2 template to render results with.
        """
        return None


@dataclass(frozen=True)
class ExtractorRunContext:
    """Per-run context passed by runner into extractor.run()."""

    project_slug: str
    group_id: str
    repo_path: Path
    run_id: str
    duration_ms: int
    logger: logging.Logger
    scip_path: Path | None = None
    companion_run_id: str | None = None
    execution_mode: ExtractorExecutionMode = ExtractorExecutionMode.FULL
    analysis_delta: AnalysisDelta | None = None
    # When True, bypass content-freshness short-circuits (e.g. symbol_index_swift's
    # body_hash skip) so a writer/schema change can be rolled out over unchanged
    # source without hand-clearing :File.body_hash.
    force: bool = False


@dataclass(frozen=True)
class ExtractorStats:
    """What run() returns. Merged into :IngestRun for observability."""

    nodes_written: int = 0
    edges_written: int = 0
    outcome: ExtractorOutcome = ExtractorOutcome.OK
    message: str | None = None
    next_action: str | None = None
    mode: ExtractorExecutionMode | None = None


class ExtractorError(Exception):
    """Base class for extractor-originating errors the runner should surface."""

    error_code: ClassVar[str] = "extractor_error"


class ExtractorConfigError(ExtractorError):
    """Extractor misconfigured (missing tool, bad params). Non-retryable."""

    error_code: ClassVar[str] = "extractor_config_error"


class ExtractorRuntimeError(ExtractorError):
    """Extractor ran but data was invalid / partial. Retryable."""

    error_code: ClassVar[str] = "extractor_runtime_error"
