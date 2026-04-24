"""Tests for Pattern #6: Config merge with defaults.

All config reads use BaseSettings with explicit default values.
No KeyError if optional env vars are absent.
"""

import os
from unittest.mock import patch

from pydantic import SecretStr


class TestSettings:
    def test_neo4j_uri_default(self) -> None:
        """NEO4J_URI absent → bolt://neo4j:7687 default, no KeyError."""
        env = {"NEO4J_PASSWORD": "test-pw"}
        with patch.dict(os.environ, env, clear=True):
            from palace_mcp.config import Settings

            s = Settings()
        assert s.neo4j_uri == "bolt://neo4j:7687"

    def test_neo4j_uri_from_env(self) -> None:
        """NEO4J_URI present → picked up from env."""
        env = {"NEO4J_URI": "bolt://myhost:7688", "NEO4J_PASSWORD": "pw"}
        with patch.dict(os.environ, env, clear=True):
            from palace_mcp.config import Settings

            s = Settings()
        assert s.neo4j_uri == "bolt://myhost:7688"

    def test_password_is_secret_str(self) -> None:
        """neo4j_password is SecretStr — repr masks the value."""
        env = {"NEO4J_PASSWORD": "hunter2"}
        with patch.dict(os.environ, env, clear=True):
            from palace_mcp.config import Settings

            s = Settings()
        assert isinstance(s.neo4j_password, SecretStr)
        assert "hunter2" not in repr(s)
        assert s.neo4j_password.get_secret_value() == "hunter2"


class TestIngestSettings:
    def test_all_required_fields_read(self) -> None:
        """IngestSettings reads all required fields from env."""
        env = {
            "NEO4J_PASSWORD": "pw",
            "PAPERCLIP_API_URL": "http://localhost:3000",
            "PAPERCLIP_INGEST_API_KEY": "key123",
            "PAPERCLIP_COMPANY_ID": "comp-1",
        }
        with patch.dict(os.environ, env, clear=True):
            from palace_mcp.config import IngestSettings

            s = IngestSettings()
        assert s.neo4j_uri == "bolt://neo4j:7687"  # default
        assert s.paperclip_api_url == "http://localhost:3000"
        assert s.paperclip_ingest_api_key.get_secret_value() == "key123"
        assert s.paperclip_company_id == "comp-1"

    def test_ingest_api_key_is_secret_str(self) -> None:
        """PAPERCLIP_INGEST_API_KEY is SecretStr — masked in repr."""
        env = {
            "NEO4J_PASSWORD": "pw",
            "PAPERCLIP_API_URL": "http://localhost:3000",
            "PAPERCLIP_INGEST_API_KEY": "supersecret",
            "PAPERCLIP_COMPANY_ID": "comp-1",
        }
        with patch.dict(os.environ, env, clear=True):
            from palace_mcp.config import IngestSettings

            s = IngestSettings()
        assert isinstance(s.paperclip_ingest_api_key, SecretStr)
        assert "supersecret" not in repr(s)


class TestGroupId:
    def test_palace_default_group_id_defaults_to_project_gimle(self) -> None:
        env = {"NEO4J_PASSWORD": "x"}
        with patch.dict(os.environ, env, clear=True):
            from palace_mcp.config import Settings

            s = Settings()
        assert s.palace_default_group_id == "project/gimle"

    def test_ingest_palace_default_group_id_defaults_to_project_gimle(self) -> None:
        env = {
            "NEO4J_PASSWORD": "x",
            "PAPERCLIP_API_URL": "http://test",
            "PAPERCLIP_INGEST_API_KEY": "k",
            "PAPERCLIP_COMPANY_ID": "test-co",
        }
        with patch.dict(os.environ, env, clear=True):
            from palace_mcp.config import IngestSettings

            s = IngestSettings()
        assert s.palace_default_group_id == "project/gimle"

    def test_palace_default_group_id_overridable_via_env(
        self, monkeypatch: object
    ) -> None:
        import importlib

        import palace_mcp.config as cfg_mod

        monkeypatch.setenv("PALACE_DEFAULT_GROUP_ID", "project/other")
        monkeypatch.setenv("NEO4J_PASSWORD", "x")
        importlib.reload(cfg_mod)
        s = cfg_mod.Settings()
        assert s.palace_default_group_id == "project/other"


class TestCodebaseMemoryUrl:
    def test_codebase_memory_mcp_url_defaults_empty(self) -> None:
        """codebase_memory_mcp_url defaults to empty string when env var unset."""
        with patch.dict(os.environ, {"NEO4J_PASSWORD": "test"}, clear=True):
            from palace_mcp.config import Settings

            s = Settings()
        assert s.codebase_memory_mcp_url == ""

    def test_codebase_memory_mcp_url_from_env(self) -> None:
        """codebase_memory_mcp_url reads from CODEBASE_MEMORY_MCP_URL env var."""
        with patch.dict(
            os.environ,
            {"NEO4J_PASSWORD": "test", "CODEBASE_MEMORY_MCP_URL": "http://cm:8765/mcp"},
            clear=True,
        ):
            from palace_mcp.config import Settings

            s = Settings()
        assert s.codebase_memory_mcp_url == "http://cm:8765/mcp"
