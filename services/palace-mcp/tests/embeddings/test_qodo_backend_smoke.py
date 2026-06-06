from __future__ import annotations

import os
import platform
import time

import pytest

from palace_mcp.embeddings.qodo import QODO_EMBED_MODEL_NAME, QodoEmbeddingBackend


def _smoke_batch() -> list[str]:
    return [
        " ".join(f"query_token_{index}" for index in range(100)),
        " ".join(f"document_token_{index}" for index in range(100)),
    ]


@pytest.mark.slow
def test_qodo_backend_latency_smoke() -> None:
    if os.environ.get("PALACE_RUN_QODO_SMOKE") != "1":
        pytest.skip("set PALACE_RUN_QODO_SMOKE=1 to run the local Qodo smoke")
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        pytest.skip("Qodo latency target is only measured on M-series Macs")

    pytest.importorskip(
        "sentence_transformers",
        reason="sentence-transformers is required for the local Qodo smoke",
    )

    model_name = os.environ.get("PALACE_QODO_MODEL_NAME", QODO_EMBED_MODEL_NAME)
    local_files_only = os.environ.get("PALACE_QODO_LOCAL_FILES_ONLY", "1") != "0"

    try:
        backend = QodoEmbeddingBackend(
            model_name=model_name,
            local_files_only=local_files_only,
        )
    except Exception as exc:
        pytest.skip(f"Qodo model is not available for local smoke: {exc}")

    start = time.perf_counter()
    embeddings = backend.embed_batch(_smoke_batch())
    elapsed_ms = (time.perf_counter() - start) * 1000

    assert len(embeddings) == 2
    assert all(embedding for embedding in embeddings)
    assert elapsed_ms <= 500.0, f"Qodo smoke exceeded 500ms target: {elapsed_ms:.1f}ms"
