"""Tiny in-memory cache for short-lived live and web answers."""

import time


class TTLCache:
    """Store string values until their configured lifetime expires."""

    def __init__(self, seconds: int, max_entries: int = 100):
        self.seconds = max(0, seconds)
        self.max_entries = max(1, max_entries)
        self._values: dict[str, tuple[float, str]] = {}

    def get(self, key: str) -> str | None:
        """Return a fresh cached value, or None when it is missing or expired."""
        entry = self._values.get(key)
        if not entry:
            return None
        expires_at, value = entry
        if time.monotonic() >= expires_at:
            self._values.pop(key, None)
            return None
        return value

    def set(self, key: str, value: str) -> None:
        """Cache a value unless caching is disabled with a zero lifetime."""
        if self.seconds:
            if key not in self._values and len(self._values) >= self.max_entries:
                self._values.pop(next(iter(self._values)))
            self._values[key] = (time.monotonic() + self.seconds, value)
