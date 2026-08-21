"""Pydantic v2 schemas for palace-memory MCP tools.

Types here are the wire contract between MCP clients and the palace-mcp
service. Keep them stable — changes are breaking.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from palace_mcp.memory.filters import EntityType

__all__ = [
    "EntityType",
    "LookupRequest",
    "LookupResponseItem",
    "LookupResponse",
    "ProjectInfo",
    "BridgeHealthInfo",
    "HealthResponse",
]


class LookupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_type: EntityType
    project: str | list[str] | None = None
    filters: dict[str, Any] = Field(default_factory=dict)
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=20, ge=1, le=100)
    # Free-form "<column> [asc|desc]"; parsed + whitelisted in lookup._safe_order_by.
    order_by: str = "created_at"
    # Embedding vectors are stripped from response properties by default
    # (internal ranking artifact, ~32K chars/node); opt in only if truly needed.
    include_embeddings: bool = False


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
    total: int = 0
    returned: int = 0
    offset: int = 0
    has_more: bool = False
    next_offset: int | None = None
    truncated: bool = False
    truncated_reason: str | None = None


class ProjectInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: str
    cm_project_name: str | None = None
    name: str
    tags: list[str]
    language: str | None = None
    framework: str | None = None
    repo_url: str | None = None
    # GIM-182: parent mount for shared-prefix repo layouts
    parent_mount: str | None = None
    relative_path: str | None = None
    # Absolute on-disk repo path persisted on the :Project node (native layout).
    repo_path: str | None = None
    # GIM-283-1: language profile for audit extractor scoping
    language_profile: str | None = None
    expected_profile: bool = False
    source_created_at: str | None = None
    source_updated_at: str | None = None
    entity_counts: dict[str, int] = Field(default_factory=dict)
    code_index_stats: dict[str, int] = Field(default_factory=dict)
    last_ingest_started_at: str | None = None
    last_ingest_finished_at: str | None = None
    indexed_commit: str | None = None
    commits_behind_head: int | None = None
    # F2/F4 (Sprint-1 reliability): honest freshness/identity metadata.
    indexed_commit_source: str | None = None
    indexed_commit_status: str | None = None
    dominant_symbol_commit: str | None = None
    stale: bool | None = None
    freshness_state: str = "unknown"
    freshness_reason: str | None = None
    commits_behind_local_tree: int | None = None
    tree_head: str | None = None
    origin_checked: bool = False
    commits_behind_origin: int | None = None
    identity_check: str = "unchecked"
    # Last project_analyze provenance, separate from source freshness above.
    last_analysis_delta_id: str | None = None
    last_analysis_delta_symbol_count: int | None = None
    embedding_coverage_status: str | None = None
    stale_extractors: list[str] = Field(default_factory=list)


class BridgeHealthInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    last_run_at: str | None = None
    last_run_duration_ms: int | None = None
    nodes_written_by_type: dict[str, int] = Field(default_factory=dict)
    edges_written_by_type: dict[str, int] = Field(default_factory=dict)
    cm_index_freshness_sec: float | None = None
    staleness_warning: bool = False


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
    bridge: BridgeHealthInfo | None = None
