"""Self-hosted Qodo embedding backend."""

from __future__ import annotations

import importlib
from typing import Any, Protocol, cast

QODO_EMBED_MODEL_NAME = "Qodo/Qodo-Embed-1-1.5B"


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

    _ensure_qwen2_rope_theta_compat()
    sentence_transformer = getattr(module, "SentenceTransformer")
    return cast(
        _SentenceEncoder,
        sentence_transformer(
            model_name,
            trust_remote_code=trust_remote_code,
            local_files_only=local_files_only,
        ),
    )


def _ensure_qwen2_rope_theta_compat() -> None:
    try:
        module = importlib.import_module("transformers")
    except ModuleNotFoundError:
        return

    qwen2_config = getattr(module, "Qwen2Config", None)
    if qwen2_config is None or hasattr(qwen2_config, "rope_theta"):
        return

    def _rope_theta(self: Any) -> Any:
        compat_rope_theta = getattr(self, "_qodo_compat_rope_theta", None)
        if compat_rope_theta is not None:
            return compat_rope_theta
        rope_parameters = getattr(self, "rope_parameters", None)
        if isinstance(rope_parameters, dict):
            return rope_parameters.get("rope_theta")
        return getattr(rope_parameters, "rope_theta", None)

    def _set_rope_theta(self: Any, value: Any) -> None:
        setattr(self, "_qodo_compat_rope_theta", value)

    setattr(qwen2_config, "rope_theta", property(_rope_theta, _set_rope_theta))


class QodoEmbeddingBackend:
    def __init__(
        self,
        *,
        encoder: _SentenceEncoder | None = None,
        model_name: str = QODO_EMBED_MODEL_NAME,
        normalize_embeddings: bool = True,
        trust_remote_code: bool = True,
        local_files_only: bool = False,
    ) -> None:
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
