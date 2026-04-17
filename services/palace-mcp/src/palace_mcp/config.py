"""Service configuration via Pydantic BaseSettings.

All credentials are typed as SecretStr so they are masked in repr()
and structured log output (e.g. `Settings(neo4j_password=SecretStr('**********'))`).
Call `.get_secret_value()` only at the driver/client construction site.
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
