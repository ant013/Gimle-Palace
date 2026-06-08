"""Embedding package."""

from __future__ import annotations

from collections.abc import Callable

from palace_mcp.embeddings.backend import EmbeddingBackend, EmbeddingBackendDispatcher
from palace_mcp.embeddings.qodo import (
    QODO_EMBED_MODEL_NAME,
    QodoEmbeddingBackend,
    warmup,
)

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


def prewarm_dispatcher() -> None:
    """Pre-warm Qodo model and wire the warmed backend into the dispatcher cache.

    Calling this at startup eliminates the ~9s cold-load penalty on the first
    semantic_search request. Runs synchronously — call via asyncio.to_thread in
    an async context.
    """
    global _dispatcher_cache  # noqa: PLW0603
    backend = warmup()
    _dispatcher_cache = EmbeddingBackendDispatcher(
        backends={"qodo": backend},
        default_backend="qodo",
    )


__all__ = [
    "EmbeddingBackend",
    "EmbeddingBackendDispatcher",
    "QODO_EMBED_MODEL_NAME",
    "QodoEmbeddingBackend",
    "get_embedding_dispatcher",
    "prewarm_dispatcher",
    "set_embedding_dispatcher_factory",
    "warmup",
]
