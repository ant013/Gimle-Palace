"""Unit tests for palace_mcp.graphiti_client.build_graphiti."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from pydantic import SecretStr

from palace_mcp.config import Settings
from palace_mcp.graphiti_client import build_graphiti


def _make_settings(**overrides: object) -> Settings:
    defaults = {
        "neo4j_password": "test-password",
        "embedding_base_url": "http://ollama:11434/v1",
        "embedding_api_key": "placeholder",
        "embedding_model": "nomic-embed-text",
        "embedding_dim": 768,
        "llm_model": "llama3:8b",
    }
    defaults.update(overrides)
    return Settings(**defaults)  # type: ignore[arg-type]


def test_build_graphiti_returns_graphiti_instance() -> None:
    """build_graphiti returns a Graphiti instance."""
    from graphiti_core import Graphiti

    settings = _make_settings()
    with patch("palace_mcp.graphiti_client.Graphiti") as mock_cls:
        mock_graphiti = MagicMock(spec=Graphiti)
        mock_cls.return_value = mock_graphiti
        result = build_graphiti(settings)
    assert result is mock_graphiti


def test_build_graphiti_uses_neo4j_uri() -> None:
    """build_graphiti passes neo4j_uri to Graphiti constructor."""
    settings = _make_settings()
    with patch("palace_mcp.graphiti_client.Graphiti") as mock_cls:
        mock_cls.return_value = MagicMock()
        build_graphiti(settings)
    call_args = mock_cls.call_args
    assert call_args.args[0] == "bolt://neo4j:7687"


def test_build_graphiti_uses_neo4j_password() -> None:
    """build_graphiti passes neo4j_password (secret) to Graphiti."""
    settings = _make_settings(neo4j_password="secret-pw")
    with patch("palace_mcp.graphiti_client.Graphiti") as mock_cls:
        mock_cls.return_value = MagicMock()
        build_graphiti(settings)
    call_args = mock_cls.call_args
    # Third positional arg is the password
    assert call_args.args[2] == "secret-pw"


def test_build_graphiti_llm_fallback_to_embedding_url() -> None:
    """When llm_base_url is None, effective_llm_base_url falls back to embedding_base_url."""
    settings = _make_settings(llm_base_url=None)
    assert settings.effective_llm_base_url == settings.embedding_base_url


def test_build_graphiti_llm_override() -> None:
    """When llm_base_url is set, effective_llm_base_url uses it."""
    settings = _make_settings(llm_base_url="http://custom-llm:8080/v1")
    assert settings.effective_llm_base_url == "http://custom-llm:8080/v1"


def test_build_graphiti_embedding_dim_passed() -> None:
    """build_graphiti passes embedding_dim to OpenAIEmbedderConfig."""
    settings = _make_settings(embedding_dim=1536)
    with (
        patch("palace_mcp.graphiti_client.Graphiti") as mock_g,
        patch("palace_mcp.graphiti_client.OpenAIEmbedder") as mock_embedder,
        patch("palace_mcp.graphiti_client.OpenAIEmbedderConfig") as mock_cfg,
    ):
        mock_g.return_value = MagicMock()
        mock_embedder.return_value = MagicMock()
        mock_cfg.return_value = MagicMock()
        build_graphiti(settings)
    _, kwargs = mock_cfg.call_args
    assert kwargs.get("embedding_dim") == 1536
