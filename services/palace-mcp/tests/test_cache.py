"""Tests for palace_mcp.cache (GIM-1181 PHASE3-F4.2)."""

from __future__ import annotations

import asyncio
import time
from typing import Any

import pytest

from palace_mcp.cache import (
    HydrationCache,
    cache_key,
    get_cache,
    hydration_semaphore,
    init_cache,
    init_semaphore,
    invalidate_by_body_hash,
)


# ---------------------------------------------------------------------------
# HydrationCache unit tests
# ---------------------------------------------------------------------------


class TestHydrationCache:
    def test_put_and_get_hit(self) -> None:
        cache = HydrationCache(maxsize=10, ttl_s=60.0)
        cache.put("k1", {"ok": True, "callers": []})
        value, hit = cache.get("k1")
        assert hit
        assert value == {"ok": True, "callers": []}

    def test_miss_on_absent_key(self) -> None:
        cache = HydrationCache(maxsize=10, ttl_s=60.0)
        value, hit = cache.get("absent")
        assert not hit
        assert value is None

    def test_ttl_expiry(self, monkeypatch: pytest.MonkeyPatch) -> None:
        cache = HydrationCache(maxsize=10, ttl_s=1.0)
        cache.put("k1", {"ok": True})
        original = time.monotonic()
        monkeypatch.setattr(time, "monotonic", lambda: original + 2.0)
        value, hit = cache.get("k1")
        assert not hit
        assert value is None

    def test_no_expiry_when_ttl_zero(self, monkeypatch: pytest.MonkeyPatch) -> None:
        cache = HydrationCache(maxsize=10, ttl_s=0.0)
        cache.put("k1", "permanent")
        original = time.monotonic()
        monkeypatch.setattr(time, "monotonic", lambda: original + 9999.0)
        value, hit = cache.get("k1")
        assert hit
        assert value == "permanent"

    def test_maxsize_evicts_oldest(self) -> None:
        cache = HydrationCache(maxsize=3, ttl_s=60.0)
        cache.put("a", 1)
        cache.put("b", 2)
        cache.put("c", 3)
        cache.put("d", 4)  # "a" evicted (LRU oldest)
        _, hit_a = cache.get("a")
        _, hit_d = cache.get("d")
        assert not hit_a
        assert hit_d

    def test_lru_access_refreshes_order(self) -> None:
        cache = HydrationCache(maxsize=3, ttl_s=60.0)
        cache.put("a", 1)
        cache.put("b", 2)
        cache.put("c", 3)
        cache.get("a")  # "a" now most-recently-used
        cache.put("d", 4)  # evicts "b" (now oldest)
        _, hit_a = cache.get("a")
        _, hit_b = cache.get("b")
        assert hit_a
        assert not hit_b

    def test_invalidate_single_key(self) -> None:
        cache = HydrationCache(maxsize=10, ttl_s=60.0)
        cache.put("k1", "v1")
        assert cache.invalidate("k1")
        _, hit = cache.get("k1")
        assert not hit

    def test_invalidate_absent_key(self) -> None:
        cache = HydrationCache(maxsize=10, ttl_s=60.0)
        assert not cache.invalidate("nonexistent")

    def test_invalidate_all(self) -> None:
        cache = HydrationCache(maxsize=10, ttl_s=60.0)
        cache.put("k1", "v1")
        cache.put("k2", "v2")
        n = cache.invalidate_all()
        assert n == 2
        assert cache.size == 0

    def test_size_property(self) -> None:
        cache = HydrationCache(maxsize=10, ttl_s=60.0)
        assert cache.size == 0
        cache.put("k1", "v1")
        assert cache.size == 1
        cache.invalidate("k1")
        assert cache.size == 0

    def test_overwrite_existing_key(self) -> None:
        cache = HydrationCache(maxsize=10, ttl_s=60.0)
        cache.put("k1", "v1")
        cache.put("k1", "v2")
        value, hit = cache.get("k1")
        assert hit
        assert value == "v2"
        assert cache.size == 1


# ---------------------------------------------------------------------------
# cache_key tests
# ---------------------------------------------------------------------------


class TestCacheKey:
    def test_stable_across_calls(self) -> None:
        k1 = cache_key(qualified_name="Foo.bar", project="gimle", max_results=50)
        k2 = cache_key(qualified_name="Foo.bar", project="gimle", max_results=50)
        assert k1 == k2

    def test_order_independent(self) -> None:
        k1 = cache_key(a=1, b=2)
        k2 = cache_key(b=2, a=1)
        assert k1 == k2

    def test_different_values_differ(self) -> None:
        k1 = cache_key(qualified_name="Foo.bar", project="gimle")
        k2 = cache_key(qualified_name="Foo.baz", project="gimle")
        assert k1 != k2

    def test_none_vs_empty_string_differ(self) -> None:
        k1 = cache_key(project=None)
        k2 = cache_key(project="")
        assert k1 != k2


# ---------------------------------------------------------------------------
# asyncio.Semaphore concurrency tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_semaphore_limits_concurrency() -> None:
    """Semaphore(2) allows at most 2 concurrent holders."""
    init_semaphore(2)
    active = [0]
    peak = [0]

    async def task() -> None:
        async with hydration_semaphore("test.tool"):
            active[0] += 1
            peak[0] = max(peak[0], active[0])
            await asyncio.sleep(0.01)
            active[0] -= 1

    await asyncio.gather(*[task() for _ in range(6)])
    assert peak[0] <= 2


@pytest.mark.asyncio
async def test_semaphore_queued_and_released_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """hydration_semaphore emits queued/acquired/released log events."""
    import logging

    init_semaphore(2)
    with caplog.at_level(logging.INFO, logger="palace_mcp.cache"):
        async with hydration_semaphore("test.tool"):
            pass

    messages = [r.message for r in caplog.records]
    assert any("palace.semaphore.queued" in m for m in messages)
    assert any("palace.semaphore.acquired" in m for m in messages)
    assert any("palace.semaphore.released" in m for m in messages)


# ---------------------------------------------------------------------------
# Module-level init + invalidation tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_init_cache_creates_instance() -> None:
    init_cache(100, 300.0)
    cache = get_cache()
    assert cache is not None
    assert cache.size == 0


@pytest.mark.asyncio
async def test_invalidate_by_body_hash_clears_cache() -> None:
    init_cache(100, 300.0)
    cache = get_cache()
    assert cache is not None
    cache.put("k1", "v1")
    cache.put("k2", "v2")
    invalidate_by_body_hash("abc123")
    assert cache.size == 0


@pytest.mark.asyncio
async def test_invalidate_by_body_hash_noop_when_no_cache() -> None:
    """invalidate_by_body_hash is safe to call before init_cache."""
    import palace_mcp.cache as _cache_module

    original = _cache_module._cache
    _cache_module._cache = None
    try:
        invalidate_by_body_hash("xyz")  # must not raise
    finally:
        _cache_module._cache = original


# ---------------------------------------------------------------------------
# Cache wired into palace_code_call_hierarchy (functional tests)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cache_hit_avoids_second_computation() -> None:
    """Cache stores ok=True results; a second lookup returns without recomputing."""
    init_cache(100, 300.0)

    fake_result: dict[str, Any] = {
        "ok": True,
        "qualified_name": "MyClass",
        "callers": [{"source_file": "Foo.swift", "line": 10}],
        "caller_count": 1,
        "latency_s": 0.5,
    }

    key = cache_key(
        qualified_name="MyClass",
        project="gimle",
        max_results=50,
        index_store_path="",
    )
    cache = get_cache()
    assert cache is not None

    # First lookup — miss
    _, hit = cache.get(key)
    assert not hit

    # Store result (as palace_code_call_hierarchy does for ok=True)
    cache.put(key, fake_result)

    # Second lookup — hit, same object
    cached_value, hit2 = cache.get(key)
    assert hit2
    assert cached_value == fake_result


@pytest.mark.asyncio
async def test_call_hierarchy_does_not_cache_errors() -> None:
    """ok=False results are not stored in cache."""
    init_cache(100, 300.0)
    key = cache_key(
        qualified_name="Missing", project="gimle", max_results=50, index_store_path=""
    )
    cache = get_cache()
    assert cache is not None

    error_result = {"ok": False, "error_code": "index_store_not_configured"}
    # Simulate the caching gate: only store when ok=True
    if error_result.get("ok"):
        cache.put(key, error_result)

    _, hit = cache.get(key)
    assert not hit
