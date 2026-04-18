"""Pydantic v2 schemas for palace-memory MCP tools.

Types here are the wire contract between MCP clients and the palace-mcp
service. Keep them stable — changes are breaking.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

EntityType = Literal["Issue", "Comment", "Agent"]


class LookupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_type: EntityType
    filters: dict[str, Any] = Field(default_factory=dict)
    limit: int = Field(default=20, ge=1, le=100)
    order_by: Literal["source_updated_at", "source_created_at"] = "source_updated_at"


class LookupResponseItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    type: EntityType
    properties: dict[str, Any]
    related: dict[str, dict[str, Any] | list[dict[str, Any]] | None] = Field(
        default_factory=dict
    )


class LookupResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[LookupResponseItem]
    total_matched: int
    query_ms: int
    warnings: list[str] = Field(default_factory=list)


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    neo4j_reachable: bool
    embedder_reachable: bool = False
    entity_counts: dict[str, int]
    last_ingest_started_at: str | None = None
    last_ingest_finished_at: str | None = None
    last_ingest_duration_ms: int | None = None
    last_ingest_errors: list[str] = Field(default_factory=list)
