from __future__ import annotations


from dataclasses import dataclass

import pytest

from palace_mcp.embeddings.backend import EmbeddingBackend, EmbeddingBackendDispatcher


@dataclass
class _FakeEmbeddingBackend:
    marker: float

    def embed_text(self, text: str) -> list[float]:
        return [self.marker, float(len(text))]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [[self.marker, float(len(text))] for text in texts]


class TestEmbeddingBackend:
    def test_protocol_is_runtime_checkable(self) -> None:
        backend = _FakeEmbeddingBackend(marker=1.0)
        assert isinstance(backend, EmbeddingBackend)


class TestEmbeddingBackendDispatcher:
    def test_dispatcher_uses_selected_backend_for_embed_text(self) -> None:
        qodo = _FakeEmbeddingBackend(marker=2.0)
        openai = _FakeEmbeddingBackend(marker=3.0)
        dispatcher = EmbeddingBackendDispatcher(
            backends={"qodo": qodo, "openai": openai},
            default_backend="qodo",
        )

        assert dispatcher.embed_text("alpha", backend_name="openai") == [3.0, 5.0]
        assert dispatcher.embed_text("abc", backend_name="qodo") == [2.0, 3.0]

    def test_dispatcher_defaults_to_configured_backend(self) -> None:
        qodo = _FakeEmbeddingBackend(marker=2.0)
        openai = _FakeEmbeddingBackend(marker=3.0)
        dispatcher = EmbeddingBackendDispatcher(
            backends={"qodo": qodo, "openai": openai},
            default_backend="openai",
        )

        assert dispatcher.embed_batch(["a", "bb"]) == [[3.0, 1.0], [3.0, 2.0]]

    def test_dispatcher_rejects_unknown_backend(self) -> None:
        dispatcher = EmbeddingBackendDispatcher(
            backends={"qodo": _FakeEmbeddingBackend(marker=2.0)},
            default_backend="qodo",
        )

        with pytest.raises(ValueError, match="Unknown embedding backend"):
            dispatcher.embed_text("nope", backend_name="openai")
