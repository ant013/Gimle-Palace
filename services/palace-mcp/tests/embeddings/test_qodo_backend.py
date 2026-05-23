from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import pytest

from palace_mcp.embeddings import EmbeddingBackend, EmbeddingBackendDispatcher
from palace_mcp.embeddings.qodo import QODO_EMBED_MODEL_NAME, QodoEmbeddingBackend


class _FakeArray:
    def __init__(self, rows: list[list[float]]) -> None:
        self._rows = rows

    def tolist(self) -> list[list[float]]:
        return self._rows


@dataclass
class _FakeEncoder:
    rows_by_text: dict[str, list[float]]
    calls: list[dict[str, Any]] = field(default_factory=list)

    def encode(
        self,
        sentences: list[str],
        *,
        convert_to_numpy: bool,
        normalize_embeddings: bool,
        show_progress_bar: bool,
    ) -> _FakeArray:
        self.calls.append(
            {
                "sentences": list(sentences),
                "convert_to_numpy": convert_to_numpy,
                "normalize_embeddings": normalize_embeddings,
                "show_progress_bar": show_progress_bar,
            }
        )
        return _FakeArray([self.rows_by_text[text] for text in sentences])


class TestQodoEmbeddingBackend:
    def test_backend_satisfies_protocol(self) -> None:
        backend = QodoEmbeddingBackend(encoder=_FakeEncoder({"alpha": [1.0, 2.0]}))

        assert isinstance(backend, EmbeddingBackend)

    def test_embed_text_returns_single_embedding(self) -> None:
        encoder = _FakeEncoder({"alpha": [1, 2.5]})
        backend = QodoEmbeddingBackend(encoder=encoder, normalize_embeddings=False)

        assert backend.embed_text("alpha") == [1.0, 2.5]
        assert encoder.calls == [
            {
                "sentences": ["alpha"],
                "convert_to_numpy": True,
                "normalize_embeddings": False,
                "show_progress_bar": False,
            }
        ]

    def test_embed_batch_preserves_input_order(self) -> None:
        encoder = _FakeEncoder(
            {
                "second": [2.0, 20.0],
                "first": [1.0, 10.0],
            }
        )
        backend = QodoEmbeddingBackend(encoder=encoder)

        assert backend.embed_batch(["second", "first"]) == [
            [2.0, 20.0],
            [1.0, 10.0],
        ]

    def test_embed_batch_returns_empty_list_for_empty_input(self) -> None:
        backend = QodoEmbeddingBackend(encoder=_FakeEncoder({}))

        assert backend.embed_batch([]) == []

    def test_loader_uses_sentence_transformer_with_qodo_defaults(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict[str, Any] = {}
        original_import_module = importlib.import_module

        class _FakeSentenceTransformer:
            def __init__(
                self,
                model_name: str,
                *,
                trust_remote_code: bool,
                local_files_only: bool,
            ) -> None:
                captured["model_name"] = model_name
                captured["trust_remote_code"] = trust_remote_code
                captured["local_files_only"] = local_files_only

            def encode(
                self,
                sentences: list[str],
                *,
                convert_to_numpy: bool,
                normalize_embeddings: bool,
                show_progress_bar: bool,
            ) -> _FakeArray:
                captured["sentences"] = list(sentences)
                captured["convert_to_numpy"] = convert_to_numpy
                captured["normalize_embeddings"] = normalize_embeddings
                captured["show_progress_bar"] = show_progress_bar
                return _FakeArray([[7.0, 8.0] for _ in sentences])

        def _fake_import_module(name: str) -> object:
            if name == "sentence_transformers":
                return SimpleNamespace(SentenceTransformer=_FakeSentenceTransformer)
            return original_import_module(name)

        monkeypatch.setattr(importlib, "import_module", _fake_import_module)

        backend = QodoEmbeddingBackend(local_files_only=True)

        assert backend.embed_text("alpha") == [7.0, 8.0]
        assert captured == {
            "model_name": QODO_EMBED_MODEL_NAME,
            "trust_remote_code": True,
            "local_files_only": True,
            "sentences": ["alpha"],
            "convert_to_numpy": True,
            "normalize_embeddings": True,
            "show_progress_bar": False,
        }

    def test_loader_raises_helpful_error_when_dependency_is_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        original_import_module = importlib.import_module

        def _fake_import_module(name: str) -> object:
            if name == "sentence_transformers":
                raise ModuleNotFoundError(name)
            return original_import_module(name)

        monkeypatch.setattr(importlib, "import_module", _fake_import_module)

        with pytest.raises(RuntimeError, match="sentence-transformers"):
            QodoEmbeddingBackend()


class TestQodoEmbeddingBackendDispatcher:
    def test_dispatcher_uses_qodo_backend_through_shared_abstraction(self) -> None:
        backend = QodoEmbeddingBackend(
            encoder=_FakeEncoder(
                {
                    "alpha": [5.0, 1.0],
                    "beta": [5.0, 2.0],
                }
            )
        )
        dispatcher = EmbeddingBackendDispatcher(
            backends={"qodo": backend},
            default_backend="qodo",
        )

        assert dispatcher.embed_batch(["alpha", "beta"]) == [
            [5.0, 1.0],
            [5.0, 2.0],
        ]
