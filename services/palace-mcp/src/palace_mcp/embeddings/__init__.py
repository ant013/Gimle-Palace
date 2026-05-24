"""Embedding package."""

from __future__ import annotations

from collections.abc import Callable

from palace_mcp.embeddings.backend import EmbeddingBackend, EmbeddingBackendDispatcher
from palace_mcp.embeddings.qodo import QODO_EMBED_MODEL_NAME, QodoEmbeddingBackend

_dispatcher_cache: EmbeddingBackendDispatcher | None = None
_dispatcher_factory: Callable[[], EmbeddingBackendDispatcher] | None = None


def _build_default_dispatcher() -> EmbeddingBackendDispatcher:
    return EmbeddingBackendDispatcher(
        backends={"qodo": QodoEmbeddingBackend()},
        default_backend="qodo",
    )


def get_embedding_dispatcher() -> EmbeddingBackendDispatcher:
    global _dispatcher_cache  # noqa: PLW0603
    if _dispatcher_cache is None:
        factory = _dispatcher_factory or _build_default_dispatcher
        _dispatcher_cache = factory()
    return _dispatcher_cache


def set_embedding_dispatcher_factory(
    factory: Callable[[], EmbeddingBackendDispatcher] | None,
) -> None:
    global _dispatcher_cache, _dispatcher_factory  # noqa: PLW0603
    _dispatcher_factory = factory
    _dispatcher_cache = None

__all__ = [
    "EmbeddingBackend",
    "EmbeddingBackendDispatcher",
    "QODO_EMBED_MODEL_NAME",
    "QodoEmbeddingBackend",
    "get_embedding_dispatcher",
    "set_embedding_dispatcher_factory",
]
