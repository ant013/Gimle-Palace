from __future__ import annotations

from typing import Generic, Optional, TypeVar

K = TypeVar("K")
V = TypeVar("V")


class Cache(Generic[K, V]):
    def __init__(self) -> None:
        self._store: dict[K, V] = {}

    def put(self, key: K, value: V) -> None:
        self._store[key] = value

    def get(self, key: K) -> Optional[V]:
        return self._store.get(key)
