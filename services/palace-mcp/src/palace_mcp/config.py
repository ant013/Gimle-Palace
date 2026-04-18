"""Service configuration via Pydantic BaseSettings.

Pattern #6: config merge with defaults — `cfg = {**DEFAULT_CONFIG, **raw_config}`.
Expressed here as BaseSettings fields with explicit defaults.
Optional keys never raise KeyError; required secrets are typed SecretStr
so they are masked in repr() and structured log output.

Call `.get_secret_value()` only at driver/client construction sites.
"""

from pydantic import SecretStr
from pydantic_settings import BaseSettings


class _EmbedderMixin(BaseSettings):
    """Shared embedder + LLM settings for graphiti-core clients."""

    # Embedder config — graphiti-core OpenAIEmbedder via OpenAI-compat endpoint
    embedding_base_url: str = "http://ollama:11434/v1"
    embedding_api_key: SecretStr = SecretStr("placeholder")
    embedding_model: str = "nomic-embed-text"
    embedding_dim: int = 768

    # LLM client — required by graphiti-core constructor; not invoked in N+1a
    # (add_triplet bypasses LLM extraction). Falls back to embedding settings.
    llm_base_url: str | None = None
    llm_api_key: SecretStr | None = None
    llm_model: str = "llama3:8b"

    @property
    def effective_llm_base_url(self) -> str:
        return self.llm_base_url or self.embedding_base_url

    @property
    def effective_llm_api_key(self) -> SecretStr:
        return self.llm_api_key or self.embedding_api_key


class Settings(_EmbedderMixin):
    """Runtime settings for the palace-mcp FastAPI service."""

    neo4j_uri: str = "bolt://neo4j:7687"
    neo4j_password: SecretStr


class IngestSettings(_EmbedderMixin):
    """Runtime settings for the palace-mcp ingest CLI."""

    neo4j_uri: str = "bolt://neo4j:7687"
    neo4j_password: SecretStr

    paperclip_api_url: str
    paperclip_ingest_api_key: SecretStr
    paperclip_company_id: str
