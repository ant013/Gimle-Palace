"""Pydantic models for the hot_path_profiler extractor."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class FrozenModel(BaseModel):
    """Immutable model with strict field handling."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class HotPathSample(FrozenModel):
    """One aggregated function sample within a profiling trace."""

    trace_id: str
    source_format: Literal["instruments", "perfetto", "simpleperf"]
    symbol_name: str
    cpu_samples: int = Field(ge=0)
    wall_ms: int = Field(ge=0)
    total_samples_in_trace: int = Field(gt=0)
    total_wall_ms_in_trace: int = Field(ge=0)
    qualified_name: str | None = None
    thread_name: str | None = None

    @property
    def cpu_share(self) -> float:
        return self.cpu_samples / self.total_samples_in_trace

    @property
    def wall_share(self) -> float:
        if self.total_wall_ms_in_trace <= 0:
            return 0.0
        return self.wall_ms / self.total_wall_ms_in_trace


class HotPathSummary(FrozenModel):
    """Per-trace aggregate summary used by the audit contract."""

    trace_id: str
    source_format: Literal["instruments", "perfetto", "simpleperf"]
    total_cpu_samples: int = Field(ge=0)
    total_wall_ms: int = Field(ge=0)
    hot_function_count: int = Field(ge=0)
    threshold_cpu_share: float = Field(gt=0.0, le=1.0, default=0.05)


class HotPathAuditFinding(FrozenModel):
    """Rendered audit row for hot-path findings."""

    trace_id: str
    qualified_name: str
    symbol_name: str
    cpu_samples: int
    wall_ms: int
    cpu_share: float
    wall_share: float
    source_format: Literal["instruments", "perfetto", "simpleperf"]


class HotPathAuditList(FrozenModel):
    """Top-level audit payload shape for hot-path findings."""

    findings: list[HotPathAuditFinding]
