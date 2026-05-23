"""Embedding package."""

from palace_mcp.embeddings.backend import EmbeddingBackend, EmbeddingBackendDispatcher
from palace_mcp.embeddings.qodo import QODO_EMBED_MODEL_NAME, QodoEmbeddingBackend

__all__ = [
    "EmbeddingBackend",
    "EmbeddingBackendDispatcher",
    "QODO_EMBED_MODEL_NAME",
    "QodoEmbeddingBackend",
]
