"""In-memory cache for expensive computations during migration.

Prevents recomputation of dependency graphs, AST summaries, and analysis
results within a single migration session.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, TypeVar

T = TypeVar("T")


class MigrationCache:
    """Simple in-memory cache for migration artifacts.

    Thread-safe is not required for current single-threaded execution.
    Future: Replace with Redis/PostgreSQL for persistent caching.
    """

    def __init__(self):
        """Initialize empty cache."""
        self._store: dict[str, Any] = {}
        self._hit_count: dict[str, int] = {}

    def _make_key(self, prefix: str, **kwargs: Any) -> str:
        """Generate cache key from prefix and parameters.

        Args:
            prefix: Cache key prefix (e.g., 'dep_graph', 'ast_summary')
            **kwargs: Parameters to hash into the key

        Returns:
            Deterministic cache key string
        """
        # Sort kwargs for deterministic key generation
        param_str = json.dumps(kwargs, sort_keys=True)
        param_hash = hashlib.sha256(param_str.encode()).hexdigest()[:16]
        return f"{prefix}:{param_hash}"

    def get(self, prefix: str, **kwargs: Any) -> Any | None:
        """Retrieve cached value if present.

        Args:
            prefix: Cache key prefix
            **kwargs: Parameters identifying the cached item

        Returns:
            Cached value or None if not found
        """
        key = self._make_key(prefix, **kwargs)

        if key in self._store:
            self._hit_count[key] = self._hit_count.get(key, 0) + 1
            return self._store[key]

        return None

    def set(self, prefix: str, value: Any, **kwargs: Any) -> None:
        """Store value in cache.

        Args:
            prefix: Cache key prefix
            value: Value to cache (must be JSON-serializable for future persistence)
            **kwargs: Parameters identifying the cached item
        """
        key = self._make_key(prefix, **kwargs)
        self._store[key] = value

    def invalidate(self, prefix: str, **kwargs: Any) -> bool:
        """Remove item from cache.

        Args:
            prefix: Cache key prefix
            **kwargs: Parameters identifying the cached item

        Returns:
            True if item was present and removed, False otherwise
        """
        key = self._make_key(prefix, **kwargs)
        if key in self._store:
            del self._store[key]
            self._hit_count.pop(key, None)
            return True
        return False

    def clear(self, prefix: str | None = None) -> int:
        """Clear cache entries.

        Args:
            prefix: If provided, only clear entries with this prefix.
                   If None, clear entire cache.

        Returns:
            Number of entries removed
        """
        if prefix is None:
            count = len(self._store)
            self._store.clear()
            self._hit_count.clear()
            return count

        # Clear entries matching prefix
        keys_to_remove = [k for k in self._store if k.startswith(f"{prefix}:")]
        for key in keys_to_remove:
            del self._store[key]
            self._hit_count.pop(key, None)

        return len(keys_to_remove)

    def stats(self) -> dict[str, Any]:
        """Get cache statistics.

        Returns:
            Dict with cache metrics
        """
        return {
            "total_entries": len(self._store),
            "total_hits": sum(self._hit_count.values()),
            "hit_rate": (
                sum(self._hit_count.values()) / len(self._hit_count)
                if self._hit_count
                else 0.0
            ),
            "prefixes": list(set(k.split(":")[0] for k in self._store)),
        }


# Global cache instance for migration session
_global_cache = MigrationCache()


def get_cache() -> MigrationCache:
    """Get global migration cache instance."""
    return _global_cache
