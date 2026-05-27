#!/usr/bin/env python3
"""Lightweight image smoke check for the palace-mcp container.

Verifies inside the built image:
- palace_mcp imports without error
- Key ML package versions match committed uv.lock pins
- PALACE_EMBEDDING_LOCAL_ONLY is honoured (model load raises actionable error, not silent hang)
- QodoEmbeddingBackend raises an actionable RuntimeError when model cache is absent
  in local-only mode (not an implicit network download or opaque OSError)
- Cache preflight status is printed without secrets

Usage:
    # From host after `docker compose up -d palace-mcp`:
    docker exec <container> python /app/scripts/smoke_image.py
    docker exec -e PALACE_EMBEDDING_LOCAL_ONLY=1 <container> python /app/scripts/smoke_image.py

    # Direct docker run (no NEO4J required):
    docker run --rm -e PALACE_EMBEDDING_LOCAL_ONLY=1 palace-mcp python /app/scripts/smoke_image.py

Pass/fail: exits 0 on success, 1 on any failure.
"""

from __future__ import annotations

import os
import sys
from importlib.metadata import PackageNotFoundError, version as pkg_version

# Expected versions — keep in lockstep with constraints/ml-packages.txt and uv.lock
EXPECTED_VERSIONS: dict[str, str] = {
    "torch": "2.12.0",
    "sentence-transformers": "5.5.1",
    "tokenizers": "0.21.4",
    "transformers": "4.48.0",
    "huggingface-hub": "0.36.2",
    "safetensors": "0.7.0",
    "numpy": "2.4.4",
}

_failures: list[str] = []
_total = 0


def check(name: str, passed: bool, detail: str = "") -> None:
    global _total
    _total += 1
    label = "PASS" if passed else "FAIL"
    suffix = f"  ({detail})" if detail else ""
    print(f"  [{label}] {name}{suffix}", flush=True)
    if not passed:
        _failures.append(name)


print("=== palace-mcp image smoke ===", flush=True)

# ── 1. Core import ─────────────────────────────────────────────────────────
print("[1] Core import", flush=True)
try:
    import palace_mcp  # noqa: F401

    check("import palace_mcp", True)
except ImportError as exc:
    check("import palace_mcp", False, str(exc))

# ── 2. Pinned version check ─────────────────────────────────────────────────
print("[2] Package versions vs uv.lock pins", flush=True)
for pkg, expected in EXPECTED_VERSIONS.items():
    try:
        actual = pkg_version(pkg)
        check(
            f"{pkg}=={expected}",
            actual == expected,
            f"actual={actual}" if actual != expected else "",
        )
    except PackageNotFoundError:
        check(f"{pkg} installed", False, "not found")

# ── 3. PALACE_EMBEDDING_LOCAL_ONLY behaviour ────────────────────────────────
print("[3] PALACE_EMBEDDING_LOCAL_ONLY", flush=True)
local_only_raw = os.environ.get("PALACE_EMBEDDING_LOCAL_ONLY", "")
is_local_only = local_only_raw.lower() in ("1", "true", "yes")

if is_local_only:
    try:
        from palace_mcp.embeddings.qodo import QodoEmbeddingBackend

        try:
            # Attempt to initialise with local_files_only=True.
            # If model is cached this succeeds (valid outcome).
            # If model is absent this must raise RuntimeError with an actionable message.
            QodoEmbeddingBackend(local_files_only=True)
            check("QodoEmbeddingBackend initialised (model cached)", True)
        except RuntimeError as exc:
            msg = str(exc)
            actionable = any(
                kw in msg
                for kw in (
                    "PALACE_EMBEDDING_LOCAL_ONLY",
                    "huggingface-cli",
                    "local cache",
                    "local_files_only",
                )
            )
            check(
                "QodoEmbeddingBackend local-only raises actionable RuntimeError",
                actionable,
                msg[:150],
            )
        except Exception as exc:
            check(
                "QodoEmbeddingBackend local-only raises actionable RuntimeError",
                False,
                f"unexpected {type(exc).__name__}: {exc}",
            )
    except ImportError as exc:
        check("sentence-transformers importable", False, str(exc))
else:
    check(
        "PALACE_EMBEDDING_LOCAL_ONLY not set — skipping strict local-only check",
        True,
        "re-run with PALACE_EMBEDDING_LOCAL_ONLY=1 for full check",
    )

# ── 4. Cache preflight status ───────────────────────────────────────────────
print("[4] Cache preflight status", flush=True)
try:
    from palace_mcp.embeddings.cache_preflight import (
        CacheStatus,
        check_model_cache,
    )
    from palace_mcp.embeddings.qodo import QODO_EMBED_MODEL_NAME

    result = check_model_cache(QODO_EMBED_MODEL_NAME)
    print(
        f"  [INFO] model={result.model_id} status={result.status.value} "
        f"cache_root={result.cache_root} size={result.size_bytes / (1024 * 1024):.1f}MB "
        f"owner_ok={result.owner_ok} writeable={result.writeable}",
        flush=True,
    )
    if is_local_only:
        check(
            "cache status is present (local-only mode)",
            result.status == CacheStatus.present,
            f"status={result.status.value}"
            if result.status != CacheStatus.present
            else "",
        )
    else:
        check(
            "cache preflight module importable",
            True,
            f"status={result.status.value} (not enforced when local-only=false)",
        )
except Exception as exc:
    check("cache preflight importable", False, str(exc))

# ── Result ──────────────────────────────────────────────────────────────────
print("", flush=True)
if _failures:
    print(
        f"FAILED  {len(_failures)}/{_total} check(s): {', '.join(_failures)}",
        flush=True,
    )
    sys.exit(1)
else:
    print(f"OK  {_total}/{_total} checks passed", flush=True)
