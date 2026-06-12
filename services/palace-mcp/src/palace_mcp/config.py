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
    openai_api_key: SecretStr | None = Field(
        default=None,
        description=(
            "Optional legacy OpenAI API key for Graphiti's explicit openai "
            "embedder path. The default qodo and noop memory paths do not "
            "require it."
        ),
    )
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
        description="Base path for per-project dedicated git_history Tantivy indices.",
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

    palace_crypto_semgrep_timeout_s: int = Field(
        default=120,
        ge=1,
        le=7200,
        description="Per-run semgrep subprocess timeout for crypto_domain_model (seconds)",
    )
    palace_error_handling_semgrep_timeout_s: int = Field(
        default=120,
        ge=1,
        le=7200,
        description="Per-run semgrep subprocess timeout for error_handling_policy (seconds)",
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

    # -----------------------------------------------------------------------
    # Code ownership extractor (GIM-216, Roadmap #32)
    # -----------------------------------------------------------------------

    ownership_blame_weight: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        alias="PALACE_OWNERSHIP_BLAME_WEIGHT",
        description="Alpha in weight = α × blame_share + (1-α) × recency_churn_share",
    )
    ownership_max_files_per_run: int = Field(
        default=50_000,
        ge=1,
        alias="PALACE_OWNERSHIP_MAX_FILES_PER_RUN",
        description="Hard cap on DIRTY set per code_ownership run",
    )
    ownership_write_batch_size: int = Field(
        default=2_000,
        ge=100,
        le=10_000,
        alias="PALACE_OWNERSHIP_WRITE_BATCH_SIZE",
        description="Files per Phase-4 atomic-replace tx in code_ownership writer",
    )
    mailmap_max_bytes: int = Field(
        default=1_048_576,
        ge=1024,
        alias="PALACE_MAILMAP_MAX_BYTES",
        description="Upper bound for .mailmap file size; oversized → identity passthrough",
    )

    # -----------------------------------------------------------------------
    # S0: Anchor symbols (GIM-1097)
    # -----------------------------------------------------------------------

    palace_anchor_symbols: Annotated[dict[str, list[str]], NoDecode] = Field(
        default_factory=dict,
        description=(
            "JSON-encoded dict mapping group_id → list of anchor qualified names. "
            'Example: PALACE_ANCHOR_SYMBOLS=\'{"project/uw-ios-app":["WalletKit.BalanceData"]}\''
        ),
    )

    @field_validator("palace_anchor_symbols", mode="before")
    @classmethod
    def parse_anchor_symbols(cls, value: object) -> dict[str, list[str]] | object:
        if value is None:
            return {}
        if isinstance(value, str):
            if value.strip() == "":
                return {}
            return cast(object, json.loads(value))
        return value

    # -----------------------------------------------------------------------
    # F1B: IndexStoreDB direct-read (GIM-1167 spike, GIM-1168 production)
    # -----------------------------------------------------------------------

    palace_indexstore_paths: Annotated[dict[str, str], NoDecode] = Field(
        default_factory=dict,
        description=(
            "JSON-encoded dict mapping project slug → IndexStoreDB DataStore path. "
            "Used by palace.code.call_hierarchy for per-project caller queries. "
            'Example: PALACE_INDEXSTORE_PATHS=\'{"uw-ios-app":"/path/to/DataStore"}\''
        ),
    )

    @field_validator("palace_indexstore_paths", mode="before")
    @classmethod
    def parse_indexstore_paths(cls, value: object) -> dict[str, str] | object:
        if value is None:
            return {}
        if isinstance(value, str):
            if value.strip() == "":
                return {}
            return cast(object, json.loads(value))
        return value

    palace_sourcekit_index_store_path: str | None = Field(
        default=None,
        description=(
            "Single-project fallback IndexStoreDB DataStore path for "
            "palace.code.call_hierarchy when no per-project entry exists in "
            "palace_indexstore_paths. "
            "Example: ~/Library/Developer/Xcode/DerivedData/<App>/Index.noindex/DataStore"
        ),
    )

    palace_call_hierarchy_timeout_s: float = Field(
        default=30.0,
        description=(
            "Per-call timeout in seconds for palace.code.call_hierarchy IndexStoreDB reads. "
            "Prevents runaway queries on corrupt or unusually large indexes. "
            "Returns error_code=timeout when exceeded. Default: 30."
        ),
    )

    # -----------------------------------------------------------------------
    # F4.0: Telemetry + JSONL audit sink (GIM-1097)
    # -----------------------------------------------------------------------

    palace_audit_sink_path: str | None = Field(
        default=None,
        description=(
            "Filesystem path for the JSONL audit sink file. Each MCP tool call appends "
            "one JSON line: {timestamp, tool_name, request_args, response_summary, "
            "latency_ms, error}. Disabled when None."
        ),
    )
    palace_telemetry_enabled: bool = Field(
        default=True,
        description="Master switch for MCP tool call telemetry. Set False to suppress audit lines.",
    )

    # -----------------------------------------------------------------------
    # F4.1: Qodo pre-warm (GIM-1100)
    # -----------------------------------------------------------------------

    palace_qodo_prewarm: bool = Field(
        default=True,
        description=(
            "Pre-warm Qodo embedding model on startup to eliminate ~9s cold-start latency. "
            "Set PALACE_QODO_PREWARM=0 to skip on memory-constrained hosts."
        ),
    )
    palace_memory_embedder: Literal["qodo", "openai", "noop"] = Field(
        default="qodo",
        description=(
            "Embedder used for Graphiti memory writes. "
            "Use qodo for the local model, openai for the legacy API path, or noop "
            "to disable semantic memory embeddings in dev."
        ),
    )

    # -----------------------------------------------------------------------
    # F4.2: Hydration cache + asyncio.Semaphore (GIM-1181)
    # -----------------------------------------------------------------------

    palace_cache_ttl_s: float = Field(
        default=300.0,
        gt=0.0,
        description=(
            "TTL in seconds for hydration cache entries (e.g. call_hierarchy results). "
            "Entries expire on read after this duration. Default: 300 (5 min)."
        ),
    )
    palace_cache_max_size: int = Field(
        default=1000,
        ge=1,
        description=(
            "Maximum number of entries in the hydration LRU cache. "
            "Oldest entry is evicted when the limit is exceeded."
        ),
    )
    palace_hydration_sem_limit: int = Field(
        default=4,
        ge=1,
        description=(
            "Max concurrent expensive hydration operations (IndexStoreDB reads, "
            "embedding calls). Requests above this limit queue and wait. Default: 4."
        ),
    )
    palace_periodic_reingest_ignore_globs: Annotated[list[str], NoDecode] = Field(
        default_factory=list,
        description=(
            "JSON or comma-separated glob patterns excluded from periodic "
            "re-ingest stale-file checks."
        ),
    )

    @field_validator("palace_periodic_reingest_ignore_globs", mode="before")
    @classmethod
    def parse_periodic_reingest_ignore_globs(cls, value: object) -> list[str] | object:
        if value is None:
            return []
        if isinstance(value, str):
            if value.strip() == "":
                return []
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                return [part.strip() for part in value.split(",") if part.strip()]
            return cast(object, parsed)
        return value
