"""Service configuration via Pydantic BaseSettings.

Pattern #6: config merge with defaults — `cfg = {**DEFAULT_CONFIG, **raw_config}`.
Expressed here as BaseSettings fields with explicit defaults.
Optional keys never raise KeyError; required secrets are typed SecretStr
so they are masked in repr() and structured log output.

Call `.get_secret_value()` only at driver/client construction sites.
"""

import json
from pathlib import Path
from typing import Annotated, Literal, cast

from pydantic import Field, SecretStr
from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode


class Settings(BaseSettings):
    """Runtime settings for the palace-mcp FastAPI service."""

    neo4j_uri: str = "bolt://neo4j:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: SecretStr
    openai_api_key: SecretStr
    palace_default_group_id: str = "project/gimle"
    codebase_memory_mcp_binary: str = ""
    palace_ops_host: str = "host.docker.internal"
    palace_ops_ssh_key: str = "/home/appuser/.ssh/palace_ops_id_ed25519"
    palace_ops_ssh_user: str = "anton"
    paperclip_api_url: str = "http://host.docker.internal:3100"
    paperclip_api_key: str = ""
    palace_git_workspace: str = "/repos/gimle"
    palace_cm_default_project: str = "repos-gimle"

    # -----------------------------------------------------------------------
    # Extractor foundation — memory-bounded occurrence store (GIM-101a, T9)
    # -----------------------------------------------------------------------

    palace_max_occurrences_total: int = Field(
        default=50_000_000,
        description="Hard cap on total SymbolOccurrenceShadow nodes across all projects.",
    )
    palace_max_occurrences_per_project: int = Field(
        default=10_000_000,
        description="Per-project cap; circuit breaker fires above this threshold.",
    )
    palace_importance_threshold_use: float = Field(
        default=0.05,
        ge=0.0,
        le=1.0,
        description="Minimum importance score for 'use' occurrences to be retained.",
    )
    palace_max_occurrences_per_symbol: int = Field(
        default=5_000,
        description="Max occurrences stored per symbol_id (de-duplication cap).",
    )
    palace_recency_decay_days: float = Field(
        default=30.0,
        gt=0.0,
        description="Half-life (days) for the recency component of importance score.",
    )

    # Tantivy
    palace_tantivy_index_path: str = Field(
        default="/var/lib/palace/tantivy",
        description="Host path (or container path) for Tantivy index data.",
    )
    palace_tantivy_heap_mb: int = Field(
        default=100,
        gt=0,
        description="Write-merge buffer size in MB (not runtime mmap budget).",
    )

    # SCIP integration (101a decides pathing; 101b does the actual parse)
    palace_scip_index_paths: Annotated[dict[str, str], NoDecode] = Field(
        default_factory=dict,
        description=(
            "JSON-encoded dict mapping project slug → .scip file path. "
            'Example env: PALACE_SCIP_INDEX_PATHS=\'{"gimle":"/repos/gimle/.scip/index.scip"}\''
        ),
    )

    @field_validator("palace_scip_index_paths", mode="before")
    @classmethod
    def parse_scip_index_paths(cls, value: object) -> dict[str, str] | object:
        if value is None:
            return {}
        if isinstance(value, str):
            if value.strip() == "":
                return {}
            return cast(object, json.loads(value))
        return value

    # -----------------------------------------------------------------------
    # Git history extractor (GIM-186)
    # -----------------------------------------------------------------------

    github_token: str | None = Field(
        default=None,
        description="GitHub PAT for GraphQL PR/comment ingest (Phase 2). Optional.",
    )
    git_history_bot_patterns_json: str | None = Field(
        default=None,
        description="JSON string of extra bot email/name regex patterns.",
    )
    git_history_max_commits_per_run: int = Field(
        default=50_000,
        description="Hard cap on commits processed per Phase 1 run.",
    )
    git_history_tantivy_index_path: Path = Field(
        default=Path("/var/lib/palace/tantivy/git_history"),
        description="Path for the dedicated git_history Tantivy index.",
    )

    # -----------------------------------------------------------------------
    # Hotspot extractor (GIM-195, Roadmap #44)
    # -----------------------------------------------------------------------

    # -----------------------------------------------------------------------
    # Cross-repo version skew extractor (GIM-218, Roadmap #39)
    # -----------------------------------------------------------------------

    palace_version_skew_top_n_max: int = Field(
        default=500,
        ge=1,
        le=10_000,
        description="Upper bound for find_version_skew top_n arg",
    )
    palace_version_skew_query_timeout_s: int = Field(
        default=30,
        ge=1,
        le=600,
        description="Bolt session timeout for cross-repo skew aggregation Cypher (seconds)",
    )

    palace_hotspot_churn_window_days: int = Field(
        default=90,
        ge=1,
        description="Window (days) for :Commit churn aggregation per :File",
    )
    palace_hotspot_lizard_batch_size: int = Field(
        default=50,
        ge=1,
        le=500,
        description="Files per lizard subprocess invocation",
    )
    palace_hotspot_lizard_timeout_s: int = Field(
        default=30,
        ge=1,
        description="Per-batch lizard subprocess timeout (seconds)",
    )
    palace_hotspot_lizard_timeout_behavior: Literal["drop_batch", "fail_run"] = Field(
        default="drop_batch",
        description="On lizard batch timeout: skip batch (drop_batch) or error whole run (fail_run)",
    )
