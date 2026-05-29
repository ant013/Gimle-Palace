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

    _ensure_qwen2_rope_theta_compat()
    _ensure_dynamic_cache_legacy_compat()
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


def _ensure_dynamic_cache_legacy_compat() -> None:
    """Restore DynamicCache APIs removed in transformers 5.x.

    Patches the class with these removed methods:
    - from_legacy_cache: classmethod, removed in 5.x
    - to_legacy_cache: instance method, removed in 5.x (layers use .keys/.values)
    - get_usable_length: renamed to get_seq_length in 5.x
    - get_max_length: removed in 5.x (DynamicCache is unbounded)
    - seen_tokens property: removed in 5.x
    """
    try:
        module = importlib.import_module("transformers")
    except ModuleNotFoundError:
        return

    dynamic_cache = getattr(module, "DynamicCache", None)
    if dynamic_cache is None:
        return

    if not hasattr(dynamic_cache, "from_legacy_cache"):

        @classmethod  # type: ignore[misc]
        def from_legacy_cache(cls: Any, past_key_values: Any = None) -> Any:
            cache = cls()
            if past_key_values is not None:
                for layer_idx, (key_states, value_states) in enumerate(past_key_values):
                    cache.update(key_states, value_states, layer_idx)
            return cache

        setattr(dynamic_cache, "from_legacy_cache", from_legacy_cache)

    if not hasattr(dynamic_cache, "to_legacy_cache"):

        def to_legacy_cache(self: Any) -> tuple[Any, ...]:
            return tuple((layer.keys, layer.values) for layer in self.layers)

        setattr(dynamic_cache, "to_legacy_cache", to_legacy_cache)

    if not hasattr(dynamic_cache, "get_usable_length"):

        def get_usable_length(self: Any, new_seq_length: int, layer_idx: int = 0) -> int:
            return self.get_seq_length(layer_idx)

        setattr(dynamic_cache, "get_usable_length", get_usable_length)

    if not hasattr(dynamic_cache, "get_max_length"):

        def get_max_length(self: Any) -> int | None:
            return None

        setattr(dynamic_cache, "get_max_length", get_max_length)

    if not hasattr(dynamic_cache, "seen_tokens"):
        setattr(
            dynamic_cache,
            "seen_tokens",
            property(lambda self: self.get_seq_length()),
        )


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
