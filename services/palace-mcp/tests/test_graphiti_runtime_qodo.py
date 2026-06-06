from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from palace_mcp.config import Settings
from palace_mcp.embeddings import EmbeddingBackendDispatcher
from palace_mcp.graphiti_runtime import QodoGraphitiEmbedder, _NoopEmbedder


class _FakeBackend:
    def __init__(self, *, dim: int = 2) -> None:
        self.dim = dim
        self.texts: list[str] = []
        self.batches: list[list[str]] = []

    def embed_text(self, text: str) -> list[float]:
        self.texts.append(text)
        return [0.5] * self.dim

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        self.batches.append(list(texts))
        return [[0.25] * self.dim for _ in texts]


def test_qodo_graphiti_embedder_create_delegates_to_backend() -> None:
    backend = _FakeBackend()
    embedder = QodoGraphitiEmbedder(backend)

    result = asyncio.run(embedder.create(["alpha"]))

    assert result == [0.5, 0.5]
    assert backend.texts == ["alpha"]


def test_qodo_graphiti_embedder_create_batch_delegates_to_backend() -> None:
    backend = _FakeBackend()
    embedder = QodoGraphitiEmbedder(backend)

    result = asyncio.run(embedder.create_batch(["alpha", "beta"]))

    assert result == [[0.25, 0.25], [0.25, 0.25]]
    assert backend.batches == [["alpha", "beta"]]


def test_settings_memory_embedder_defaults_to_qodo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    settings = Settings(neo4j_password="pw")  # type: ignore[arg-type]
    assert settings.palace_memory_embedder == "qodo"
    assert settings.openai_api_key is None


def test_settings_memory_embedder_can_select_noop() -> None:
    settings = Settings(  # type: ignore[arg-type]
        neo4j_password="pw",
        palace_memory_embedder="noop",
    )
    assert settings.palace_memory_embedder == "noop"


def test_build_graphiti_defaults_to_qodo_embedder() -> None:
    from palace_mcp.graphiti_runtime import build_graphiti

    backend = _FakeBackend(dim=1024)
    dispatcher = EmbeddingBackendDispatcher({"qodo": backend}, default_backend="qodo")
    settings = Settings(  # type: ignore[arg-type]
        neo4j_uri="bolt://test:7687",
        neo4j_password="pw",
    )
    graphiti = MagicMock()

    with (
        patch("palace_mcp.graphiti_runtime.Graphiti", return_value=graphiti) as patched,
        patch("palace_mcp.graphiti_runtime.OpenAIClient"),
        patch(
            "palace_mcp.graphiti_runtime.get_embedding_dispatcher",
            return_value=dispatcher,
        ),
    ):
        result = build_graphiti(settings)

    embedder = patched.call_args.kwargs["embedder"]
    assert isinstance(embedder, QodoGraphitiEmbedder)
    assert asyncio.run(embedder.create(["decision title"])) == [0.5] * 1024
    assert result is graphiti


def test_build_graphiti_can_select_openai_embedder() -> None:
    from palace_mcp.graphiti_runtime import build_graphiti

    settings = Settings(  # type: ignore[arg-type]
        neo4j_uri="bolt://test:7687",
        neo4j_password="pw",
        openai_api_key="sk-test",
        palace_memory_embedder="openai",
    )
    graphiti = MagicMock()
    openai_embedder = MagicMock()

    with (
        patch("palace_mcp.graphiti_runtime.Graphiti", return_value=graphiti) as patched,
        patch("palace_mcp.graphiti_runtime.OpenAIClient"),
        patch(
            "palace_mcp.graphiti_runtime.OpenAIEmbedder",
            return_value=openai_embedder,
        ) as patched_openai,
    ):
        build_graphiti(settings)

    assert patched_openai.called
    assert patched.call_args.kwargs["embedder"] is openai_embedder


def test_build_graphiti_openai_selector_requires_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from palace_mcp.graphiti_runtime import build_graphiti

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    settings = Settings(  # type: ignore[arg-type]
        neo4j_uri="bolt://test:7687",
        neo4j_password="pw",
        palace_memory_embedder="openai",
    )

    with pytest.raises(
        ValueError,
        match="OPENAI_API_KEY is required when PALACE_MEMORY_EMBEDDER=openai",
    ):
        build_graphiti(settings)


def test_build_graphiti_can_select_noop_embedder() -> None:
    from palace_mcp.graphiti_runtime import build_graphiti

    settings = Settings(  # type: ignore[arg-type]
        neo4j_uri="bolt://test:7687",
        neo4j_password="pw",
        palace_memory_embedder="noop",
    )

    with (
        patch(
            "palace_mcp.graphiti_runtime.Graphiti", return_value=MagicMock()
        ) as patched,
        patch("palace_mcp.graphiti_runtime.OpenAIClient"),
    ):
        build_graphiti(settings)

    embedder = patched.call_args.kwargs["embedder"]
    assert isinstance(embedder, _NoopEmbedder)
    assert asyncio.run(embedder.create(["alpha"])) == [0.0] * 1024
