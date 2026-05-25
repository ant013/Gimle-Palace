"""Self-hosted Qodo embedding backend."""

from __future__ import annotations

import importlib
import os
import sys
from collections.abc import Iterable
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
    _install_qodo_transformers_compat()
    try:
        module = importlib.import_module("sentence_transformers")
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "sentence-transformers is required to use QodoEmbeddingBackend"
        ) from exc

    sentence_transformer = getattr(module, "SentenceTransformer")
    return cast(
        _SentenceEncoder,
        sentence_transformer(
            model_name,
            trust_remote_code=trust_remote_code,
            local_files_only=local_files_only,
        ),
    )


def _install_qodo_transformers_compat() -> None:
    """Patch narrow Transformers drift that Qodo remote code still expects."""

    try:
        qwen2_config_module = importlib.import_module(
            "transformers.models.qwen2.configuration_qwen2"
        )
    except ModuleNotFoundError:
        qwen2_config_module = None

    if qwen2_config_module is not None:
        qwen2_config = getattr(qwen2_config_module, "Qwen2Config", None)
        if qwen2_config is not None and not hasattr(qwen2_config, "rope_theta"):

            def _rope_theta(self: object) -> float:
                rope_parameters = getattr(self, "rope_parameters", None)
                if isinstance(rope_parameters, dict):
                    value = rope_parameters.get("rope_theta")
                    if value is not None:
                        return float(value)
                return 1_000_000.0

            setattr(qwen2_config, "rope_theta", property(_rope_theta))

    try:
        cache_utils = importlib.import_module("transformers.cache_utils")
    except ModuleNotFoundError:
        return

    dynamic_cache = getattr(cache_utils, "DynamicCache", None)
    if dynamic_cache is None:
        return

    if not hasattr(dynamic_cache, "from_legacy_cache"):

        @classmethod
        def _from_legacy_cache(
            cls: type[Any],
            past_key_values: Iterable[tuple[Any, Any]] | None = None,
        ) -> Any:
            cache = cls()
            if past_key_values is None:
                return cache
            for layer_idx, (key_states, value_states) in enumerate(past_key_values):
                cache.update(key_states, value_states, layer_idx)
            return cache

        setattr(dynamic_cache, "from_legacy_cache", _from_legacy_cache)

    if not hasattr(dynamic_cache, "get_usable_length"):

        def _get_usable_length(self: object, _: int, layer_idx: int = 0) -> int:
            get_seq_length = getattr(self, "get_seq_length")
            return int(get_seq_length(layer_idx))

        setattr(dynamic_cache, "get_usable_length", _get_usable_length)

    if not hasattr(dynamic_cache, "to_legacy_cache"):

        def _to_legacy_cache(self: object) -> tuple[tuple[Any, Any], ...]:
            layers = getattr(self, "layers", None)
            if layers is not None:
                legacy_layers: list[tuple[Any, Any]] = []
                for layer in layers:
                    keys = getattr(layer, "keys", None)
                    values = getattr(layer, "values", None)
                    if keys is not None and values is not None:
                        legacy_layers.append((keys, values))
                return tuple(legacy_layers)

            key_cache = getattr(self, "key_cache", [])
            value_cache = getattr(self, "value_cache", [])
            return tuple(zip(key_cache, value_cache, strict=False))

        setattr(dynamic_cache, "to_legacy_cache", _to_legacy_cache)

    try:
        tokenization_qwen2 = importlib.import_module(
            "transformers.models.qwen2.tokenization_qwen2"
        )
    except ModuleNotFoundError:
        return

    sys.modules.setdefault(
        "transformers.models.qwen2.tokenization_qwen2_fast",
        tokenization_qwen2,
    )


def _env_bool(name: str, *, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


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
        resolved_local_files_only = (
            _env_bool("PALACE_QODO_LOCAL_FILES_ONLY")
            if local_files_only is None
            else local_files_only
        )
        self._encoder = encoder or _load_sentence_transformer(
            model_name,
            trust_remote_code=trust_remote_code,
            local_files_only=resolved_local_files_only,
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
