"""Pydantic v2 schemas for palace-memory MCP tools.

Types here are the wire contract between MCP clients and the palace-mcp
service. Keep them stable — changes are breaking.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from palace_mcp.memory.filters import EntityType

__all__ = [
    "EntityType",
    "LookupRequest",
    "LookupResponseItem",
    "LookupResponse",
    "ProjectInfo",
    "HealthResponse",
]


class LookupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_type: EntityType
    project: str | list[str] | None = None
    filters: dict[str, Any] = Field(default_factory=dict)
    limit: int = Field(default=20, ge=1, le=100)
    order_by: Literal["created_at", "name"] = "created_at"


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


class ProjectInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: str
    name: str
    tags: list[str]
    language: str | None = None
    framework: str | None = None
    repo_url: str | None = None
    source_created_at: str
    source_updated_at: str
    entity_counts: dict[str, int] = Field(default_factory=dict)
    last_ingest_started_at: str | None = None
    last_ingest_finished_at: str | None = None


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    neo4j_reachable: bool
    entity_counts: dict[str, int]
    last_ingest_started_at: str | None = None
    last_ingest_finished_at: str | None = None
    last_ingest_duration_ms: int | None = None
    last_ingest_errors: list[str] = Field(default_factory=list)
    projects: list[str] = Field(default_factory=list)
    default_project: str | None = None
    entity_counts_per_project: dict[str, dict[str, int]] = Field(default_factory=dict)
    git_repos_available: list[str] = Field(default_factory=list)
    git_repos_unregistered: list[str] = Field(default_factory=list)
    code_graph_reachable: bool = False
