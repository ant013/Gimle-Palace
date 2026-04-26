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
