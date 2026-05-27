"""Self-hosted Qodo embedding backend."""

from __future__ import annotations

import importlib
import os
from typing import Any, Protocol, cast

from palace_mcp.embeddings.cache_preflight import preflight_or_fail

QODO_EMBED_MODEL_NAME = "Qodo/Qodo-Embed-1-1.5B"


def _local_files_only_from_env() -> bool:
    return os.environ.get("PALACE_EMBEDDING_LOCAL_ONLY", "").lower() in (
        "1",
        "true",
        "yes",
    )


class _SentenceEncoder(Protocol):
    def encode(
        self,
        sentences: list[str],
        *,
        convert_to_numpy: bool,
        normalize_embeddings: bool,
        show_progress_bar: bool,
    ) -> Any: ...


def _load_sentence_transformer(
    model_name: str,
    *,
    trust_remote_code: bool,
    local_files_only: bool,
) -> _SentenceEncoder:
    try:
        module = importlib.import_module("sentence_transformers")
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "sentence-transformers is required to use QodoEmbeddingBackend"
        ) from exc

    sentence_transformer = getattr(module, "SentenceTransformer")
    try:
        return cast(
            _SentenceEncoder,
            sentence_transformer(
                model_name,
                trust_remote_code=trust_remote_code,
                local_files_only=local_files_only,
            ),
        )
    except OSError as exc:
        if local_files_only:
            raise RuntimeError(
                f"Model '{model_name}' not found in local cache "
                f"(PALACE_EMBEDDING_LOCAL_ONLY=true). "
                f"Download: huggingface-cli download {model_name} "
                f"(cache: ~/.cache/huggingface/hub/). "
                f"Or set PALACE_EMBEDDING_LOCAL_ONLY=false to allow network access."
            ) from exc
        raise RuntimeError(
            f"Failed to load sentence transformer '{model_name}': {exc}"
        ) from exc


class QodoEmbeddingBackend:
    def __init__(
        self,
        *,
        encoder: _SentenceEncoder | None = None,
        model_name: str = QODO_EMBED_MODEL_NAME,
        normalize_embeddings: bool = True,
        trust_remote_code: bool = True,
        local_files_only: bool | None = None,
    ) -> None:
        if local_files_only is None:
            local_files_only = _local_files_only_from_env()
        if encoder is None:
            preflight_or_fail(model_name, local_only=local_files_only)
        self._encoder = encoder or _load_sentence_transformer(
            model_name,
            trust_remote_code=trust_remote_code,
            local_files_only=local_files_only,
        )
        self._normalize_embeddings = normalize_embeddings

    def embed_text(self, text: str) -> list[float]:
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        embeddings = self._encoder.encode(
            texts,
            convert_to_numpy=True,
            normalize_embeddings=self._normalize_embeddings,
            show_progress_bar=False,
        )
        return [list(map(float, row)) for row in embeddings.tolist()]
