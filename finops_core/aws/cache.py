"""Small thread-safe TTL cache. Cost Explorer is billed per request, so we memoize
identical queries within a short window."""
from __future__ import annotations

import threading
import time
from typing import Callable


class TTLCache:
    def __init__(self, ttl_seconds: int = 3600):
        self.ttl = ttl_seconds
        self._data: dict = {}
        self._lock = threading.Lock()

    def get_or_compute(self, key, compute: Callable):
        now = time.monotonic()
        with self._lock:
            hit = self._data.get(key)
            if hit and now - hit[0] < self.ttl:
                return hit[1]
        value = compute()
        with self._lock:
            self._data[key] = (now, value)
        return value

    def clear(self) -> None:
        with self._lock:
            self._data.clear()
