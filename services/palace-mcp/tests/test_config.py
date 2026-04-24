"""Tests for Pattern #6: Config merge with defaults.

All config reads use BaseSettings with explicit default values.
No KeyError if optional env vars are absent.
"""

import os
from unittest.mock import patch

from pydantic import SecretStr

_BASE_ENV = {"NEO4J_PASSWORD": "test-pw", "OPENAI_API_KEY": "sk-test"}


class TestSettings:
    def test_neo4j_uri_default(self) -> None:
        """NEO4J_URI absent → bolt://neo4j:7687 default, no KeyError."""
        with patch.dict(os.environ, _BASE_ENV, clear=True):
            from palace_mcp.config import Settings

            s = Settings()
        assert s.neo4j_uri == "bolt://neo4j:7687"

    def test_neo4j_uri_from_env(self) -> None:
        """NEO4J_URI present → picked up from env."""
        env = {**_BASE_ENV, "NEO4J_URI": "bolt://myhost:7688"}
        with patch.dict(os.environ, env, clear=True):
            from palace_mcp.config import Settings

            s = Settings()
        assert s.neo4j_uri == "bolt://myhost:7688"

    def test_password_is_secret_str(self) -> None:
        """neo4j_password is SecretStr — repr masks the value."""
        env = {**_BASE_ENV, "NEO4J_PASSWORD": "hunter2"}
        with patch.dict(os.environ, env, clear=True):
            from palace_mcp.config import Settings

            s = Settings()
        assert isinstance(s.neo4j_password, SecretStr)
        assert "hunter2" not in repr(s)
        assert s.neo4j_password.get_secret_value() == "hunter2"

    def test_openai_api_key_is_secret_str(self) -> None:
        """openai_api_key is SecretStr — repr masks the value."""
        env = {**_BASE_ENV, "OPENAI_API_KEY": "sk-my-secret"}
        with patch.dict(os.environ, env, clear=True):
            from palace_mcp.config import Settings

            s = Settings()
        assert isinstance(s.openai_api_key, SecretStr)
        assert "sk-my-secret" not in repr(s)
        assert s.openai_api_key.get_secret_value() == "sk-my-secret"


class TestGroupId:
    def test_palace_default_group_id_defaults_to_project_gimle(self) -> None:
        with patch.dict(os.environ, _BASE_ENV, clear=True):
            from palace_mcp.config import Settings

            s = Settings()
        assert s.palace_default_group_id == "project/gimle"

    def test_palace_default_group_id_overridable_via_env(
        self, monkeypatch: object
    ) -> None:
        import importlib

        import palace_mcp.config as cfg_mod

        monkeypatch.setenv("PALACE_DEFAULT_GROUP_ID", "project/other")
        monkeypatch.setenv("NEO4J_PASSWORD", "x")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-x")
        importlib.reload(cfg_mod)
        s = cfg_mod.Settings()
        assert s.palace_default_group_id == "project/other"


class TestCodebaseMemoryUrl:
    def test_codebase_memory_mcp_url_defaults_empty(self) -> None:
        """codebase_memory_mcp_url defaults to empty string when env var unset."""
        with patch.dict(os.environ, _BASE_ENV, clear=True):
            from palace_mcp.config import Settings

            s = Settings()
        assert s.codebase_memory_mcp_url == ""

    def test_codebase_memory_mcp_url_from_env(self) -> None:
        """codebase_memory_mcp_url reads from CODEBASE_MEMORY_MCP_URL env var."""
        env = {**_BASE_ENV, "CODEBASE_MEMORY_MCP_URL": "http://cm:8765/mcp"}
        with patch.dict(os.environ, env, clear=True):
            from palace_mcp.config import Settings

            s = Settings()
        assert s.codebase_memory_mcp_url == "http://cm:8765/mcp"
