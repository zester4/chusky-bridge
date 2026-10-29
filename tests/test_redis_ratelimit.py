from chusky_bridge.ratelimit import RedisRateLimiter


class FakeRedis:
    def __init__(self):
        self.counts = {}
        self.expiries = {}

    def incr(self, key):
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    def expire(self, key, seconds):
        self.expiries[key] = seconds


def test_fixed_window_limit_is_enforced_across_instances():
    shared = FakeRedis()
    replica_a = RedisRateLimiter(shared, per_minute=2)
    replica_b = RedisRateLimiter(shared, per_minute=2)
    assert replica_a.allow("tenant:tool", now=600.0)
    assert replica_b.allow("tenant:tool", now=601.0)
    assert not replica_a.allow("tenant:tool", now=602.0)


def test_new_window_resets_count():
    shared = FakeRedis()
    limiter = RedisRateLimiter(shared, per_minute=1)
    assert limiter.allow("k", now=0.0)
    assert not limiter.allow("k", now=30.0)
    assert limiter.allow("k", now=61.0)


def test_key_expiry_is_set_on_first_hit():
    shared = FakeRedis()
    RedisRateLimiter(shared, per_minute=5).allow("k", now=0.0)
    assert list(shared.expiries.values()) == [120]
