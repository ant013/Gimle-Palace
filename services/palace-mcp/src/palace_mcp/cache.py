"""In-memory TTL cache + asyncio.Semaphore for palace-mcp hydration/query ops.

GIM-1181 PHASE3-F4.2.

Cache:
  - keyed by caller-computed string (use cache_key() helper)
  - LRU eviction when maxsize is exceeded
  - TTL expiry on reads
  - NOT thread-safe at the dict level: callers must be on the same event loop
    (palace-mcp is single-process uvicorn, so this holds)

Semaphore:
  - module-level asyncio.Semaphore, set via init_semaphore()
  - guards expensive blocking operations (IndexStoreDB reads, embedding calls)
  - lazy fallback to default limit when init_semaphore() has not been called

Telemetry:
  - cache.hit / cache.miss / semaphore.queued / semaphore.released events
    emitted via Python logger, which writes JSON lines via the F4.0 audit sink

Invalidation:
  - invalidate_by_body_hash() is a stub for F5a body-hash integration
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import OrderedDict
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_SEM_LIMIT = 4


class HydrationCache:
    """LRU-TTL in-memory cache for hydration results.

    Args:
        maxsize: Maximum number of entries. Oldest entry is evicted when exceeded.
        ttl_s: Seconds before an entry expires on read. 0 = never expire.
    """

    def __init__(self, maxsize: int, ttl_s: float) -> None:
        self._maxsize = maxsize
        self._ttl_s = ttl_s
        self._store: OrderedDict[str, tuple[Any, float]] = OrderedDict()

    def get(self, key: str) -> tuple[Any, bool]:
        """Return (value, hit). value is None on miss."""
        entry = self._store.get(key)
        if entry is None:
            return None, False
        value, expires_at = entry
        if self._ttl_s > 0 and time.monotonic() > expires_at:
            del self._store[key]
            return None, False
        self._store.move_to_end(key)
        return value, True

    def put(self, key: str, value: Any) -> None:
        """Store value under key. Evicts oldest entry when maxsize is exceeded."""
        expires_at = time.monotonic() + self._ttl_s if self._ttl_s > 0 else float("inf")
        if key in self._store:
            self._store.move_to_end(key)
        self._store[key] = (value, expires_at)
        if len(self._store) > self._maxsize:
            self._store.popitem(last=False)

    def invalidate(self, key: str) -> bool:
        """Remove a single entry. Returns True if the key existed."""
        return self._store.pop(key, None) is not None

    def invalidate_all(self) -> int:
        """Clear all entries. Returns count cleared."""
        n = len(self._store)
        self._store.clear()
        return n

    @property
    def size(self) -> int:
        return len(self._store)


# ---------------------------------------------------------------------------
# Module-level singletons — set from lifespan via init_cache / init_semaphore.
# ---------------------------------------------------------------------------

_cache: HydrationCache | None = None
_semaphore: asyncio.Semaphore | None = None
_sem_limit: int = _DEFAULT_SEM_LIMIT


def init_cache(maxsize: int, ttl_s: float) -> None:
    """Create the module-level HydrationCache. Called from FastAPI lifespan."""
    global _cache  # noqa: PLW0603
    _cache = HydrationCache(maxsize=maxsize, ttl_s=ttl_s)
    logger.info("palace.cache.init maxsize=%d ttl_s=%.1f", maxsize, ttl_s)


def init_semaphore(limit: int) -> None:
    """Create the module-level asyncio.Semaphore. Called from FastAPI lifespan."""
    global _semaphore, _sem_limit  # noqa: PLW0603
    _sem_limit = limit
    _semaphore = asyncio.Semaphore(limit)
    logger.info("palace.semaphore.init limit=%d", limit)


def get_cache() -> HydrationCache | None:
    return _cache


def _get_semaphore() -> asyncio.Semaphore:
    """Return the module-level semaphore, lazily creating one if needed."""
    global _semaphore  # noqa: PLW0603
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(_sem_limit)
    return _semaphore


@asynccontextmanager
async def hydration_semaphore(tool_name: str) -> AsyncGenerator[None, None]:
    """Acquire the hydration semaphore, logging queue/release events."""
    sem = _get_semaphore()
    logger.info("palace.semaphore.queued tool=%s", tool_name)
    async with sem:
        logger.info("palace.semaphore.acquired tool=%s", tool_name)
        yield
    logger.info("palace.semaphore.released tool=%s", tool_name)


def cache_key(**kwargs: Any) -> str:
    """Produce a stable, sorted cache key from keyword arguments."""
    return "|".join(f"{k}={kwargs[k]!r}" for k in sorted(kwargs))


def invalidate_by_body_hash(body_hash: str) -> None:
    """Invalidate all cache entries when a body_hash change is detected.

    Stub for F5a integration — F5a will call this when symbol body_hash changes.
    Currently clears the entire cache (conservative); F5a may narrow to
    per-symbol keys once the mapping from body_hash → cache key is established.
    """
    cache = _cache
    if cache is None:
        return
    n = cache.invalidate_all()
    logger.info(
        "palace.cache.invalidated_by_body_hash body_hash=%s entries_cleared=%d",
        body_hash,
        n,
    )
