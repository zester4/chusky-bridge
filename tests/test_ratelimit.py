from chusky_bridge.ratelimit import RateLimiter


def test_bucket_allows_burst_then_denies():
    limiter = RateLimiter(per_minute=3)
    assert [limiter.allow("k", now=0.0) for _ in range(4)] == [True, True, True, False]


def test_bucket_refills_over_time():
    limiter = RateLimiter(per_minute=3)
    for _ in range(3):
        limiter.allow("k", now=0.0)
    assert not limiter.allow("k", now=0.0)
    assert limiter.allow("k", now=60.0)


def test_keys_are_isolated():
    limiter = RateLimiter(per_minute=1)
    assert limiter.allow("a", now=0.0)
    assert limiter.allow("b", now=0.0)
