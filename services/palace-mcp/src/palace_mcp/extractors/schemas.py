"""Pydantic response models for palace.ingest.* MCP tools.

Used internally by runner to validate + serialize responses. MCP tool
signatures return dict[str, Any] (matching palace-mcp convention from
GIM-34/52/53/54/57); these models are the internal contract.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


_CFG = ConfigDict(extra="forbid")


class ExtractorRunResponse(BaseModel):
    """Successful extractor run response."""

    model_config = _CFG

    ok: Literal[True] = True
    run_id: str
    extractor: str
    project: str
    started_at: str
    finished_at: str
    duration_ms: int
    nodes_written: int
    edges_written: int
    success: Literal[True] = True


class ExtractorErrorResponse(BaseModel):
    """Failed extractor run / validation error response."""

    model_config = _CFG

    ok: Literal[False] = False
    error_code: str
    message: str
    extractor: str | None = None
    project: str | None = None
    run_id: str | None = None


class ExtractorDescriptor(BaseModel):
    """One entry in palace.ingest.list_extractors response."""

    model_config = _CFG

    name: str
    description: str


class ExtractorListResponse(BaseModel):
    """palace.ingest.list_extractors response."""

    model_config = _CFG

    ok: Literal[True] = True
    extractors: list[ExtractorDescriptor]
