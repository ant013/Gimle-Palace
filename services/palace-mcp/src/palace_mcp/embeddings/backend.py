"""Embedding backend abstraction and lightweight dispatcher."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, runtime_checkable


@runtime_checkable
class EmbeddingBackend(Protocol):
    def embed_text(self, text: str) -> list[float]: ...

    def embed_batch(self, texts: list[str]) -> list[list[float]]: ...


class EmbeddingBackendDispatcher:
    """Resolve embedding backends by name and dispatch calls."""

    def __init__(
        self,
        backends: Mapping[str, EmbeddingBackend],
        default_backend: str,
    ) -> None:
        self._backends = dict(backends)
        self._default_backend = default_backend

    def backend(self, backend_name: str | None = None) -> EmbeddingBackend:
        name = backend_name or self._default_backend
        if name not in self._backends:
            raise ValueError(f"Unknown embedding backend: {name}")
        return self._backends[name]

    def embed_text(self, text: str, *, backend_name: str | None = None) -> list[float]:
        return self.backend(backend_name).embed_text(text)

    def embed_batch(
        self,
        texts: list[str],
        *,
        backend_name: str | None = None,
    ) -> list[list[float]]:
        return self.backend(backend_name).embed_batch(texts)
