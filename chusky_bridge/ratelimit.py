import threading
import time
from typing import Any

from chusky_bridge.config import settings


class RateLimiter:
    """Token bucket per key. Process-local. Use the Redis backend for multiple replicas."""

    MAX_KEYS = 50_000

    def __init__(self, per_minute: int):
        self.capacity = float(per_minute)
        self.refill_per_second = per_minute / 60.0
        self._buckets: dict[str, tuple[float, float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        with self._lock:
            if len(self._buckets) > self.MAX_KEYS:
                self._buckets.clear()
            tokens, last = self._buckets.get(key, (self.capacity, now))
            tokens = min(self.capacity, tokens + (now - last) * self.refill_per_second)
            if tokens < 1:
                self._buckets[key] = (tokens, now)
                return False
            self._buckets[key] = (tokens - 1, now)
            return True


class RedisRateLimiter:
    """Fixed one-minute window counter shared across replicas via INCR and EXPIRE."""

    def __init__(self, client: Any, per_minute: int, prefix: str = "chusky:rl:"):
        self.client = client
        self.per_minute = per_minute
        self.prefix = prefix

    def allow(self, key: str, now: float | None = None) -> bool:
        window = int((time.time() if now is None else now) // 60)
        redis_key = f"{self.prefix}{key}:{window}"
        count = int(self.client.incr(redis_key))
        if count == 1:
            self.client.expire(redis_key, 120)
        return count <= self.per_minute


def build_rate_limiter() -> RateLimiter | RedisRateLimiter:
    if settings.rate_limit_backend == "redis":
        import redis

        client = redis.Redis.from_url(settings.redis_url, socket_timeout=2)
        return RedisRateLimiter(client, settings.rate_limit_per_minute)
    return RateLimiter(settings.rate_limit_per_minute)


rate_limiter = build_rate_limiter()
