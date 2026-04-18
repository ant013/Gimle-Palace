"""Service configuration via Pydantic BaseSettings.

Pattern #6: config merge with defaults — `cfg = {**DEFAULT_CONFIG, **raw_config}`.
Expressed here as BaseSettings fields with explicit defaults.
Optional keys never raise KeyError; required secrets are typed SecretStr
so they are masked in repr() and structured log output.

Call `.get_secret_value()` only at driver/client construction sites.
"""

from pydantic import SecretStr
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Runtime settings for the palace-mcp FastAPI service."""

    neo4j_uri: str = "bolt://neo4j:7687"
    neo4j_password: SecretStr


class IngestSettings(BaseSettings):
    """Runtime settings for the palace-mcp ingest CLI."""

    neo4j_uri: str = "bolt://neo4j:7687"
    neo4j_password: SecretStr

    paperclip_api_url: str
    paperclip_ingest_api_key: SecretStr
    paperclip_company_id: str
