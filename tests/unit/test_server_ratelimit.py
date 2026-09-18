"""The generate rate limiter: token buckets per client, and how a client is keyed."""

import pytest
from starlette.requests import Request

from server.ratelimit import (
    GENERATE_CAPACITY,
    GENERATE_REFILL_SECONDS,
    RateLimiter,
    client_address,
    client_key,
)


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock():
    return Clock()


def test_the_generate_limits_are_sane():
    assert GENERATE_CAPACITY >= 1
    assert GENERATE_REFILL_SECONDS > 0


def test_a_full_bucket_allows_its_capacity_then_refuses(clock):
    limiter = RateLimiter(3, 60, clock)
    assert [limiter.allow("a") for _ in range(4)] == [True, True, True, False]


def test_one_token_comes_back_per_refill_period(clock):
    limiter = RateLimiter(2, 60, clock)
    assert limiter.allow("a") and limiter.allow("a")
    clock.now += 59
    assert not limiter.allow("a")
    clock.now += 1
    assert limiter.allow("a")
    assert not limiter.allow("a")


def test_a_refusal_takes_nothing(clock):
    limiter = RateLimiter(1, 60, clock)
    assert limiter.allow("a")
    clock.now += 30
    assert not limiter.allow("a")
    clock.now += 30
    assert limiter.allow("a")


def test_a_bucket_never_holds_more_than_its_capacity(clock):
    limiter = RateLimiter(2, 60, clock)
    limiter.allow("a")
    clock.now += 60 * 100
    assert [limiter.allow("a") for _ in range(3)] == [True, True, False]


def test_keys_have_their_own_buckets(clock):
    limiter = RateLimiter(1, 60, clock)
    assert limiter.allow("a")
    assert not limiter.allow("a")
    assert limiter.allow("b")


def test_refilled_buckets_are_forgotten(clock):
    limiter = RateLimiter(2, 60, clock)
    limiter.allow("a")
    limiter.allow("b")
    assert len(limiter) == 2
    clock.now += 2 * 60
    limiter.allow("c")
    assert len(limiter) == 1


@pytest.mark.parametrize("capacity, refill", [(0, 60), (1, 0), (1, -5)])
def test_a_limiter_needs_capacity_and_a_refill_time(capacity, refill):
    with pytest.raises(ValueError):
        RateLimiter(capacity, refill)


def request(headers=(), client=("203.0.113.9", 5000)) -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/generate",
            "headers": [
                (name.lower().encode(), value.encode()) for name, value in headers
            ],
            "client": client,
        }
    )


def test_the_address_is_the_last_forwarded_address():
    assert (
        client_address(request([("X-Forwarded-For", "198.51.100.1, 192.0.2.7")]))
        == "192.0.2.7"
    )
    assert client_address(request([("X-Forwarded-For", "192.0.2.7")])) == "192.0.2.7"


def test_without_the_header_the_address_is_the_peer():
    assert client_address(request()) == "203.0.113.9"
    assert client_address(request([("X-Forwarded-For", " , ")])) == "203.0.113.9"
    assert client_address(request(client=None)) == "unknown"


def test_a_signed_out_client_is_keyed_by_address_and_a_signed_in_one_by_user():
    assert client_key(request()) == "ip:203.0.113.9"
    assert client_key(request(), user_id=None) == "ip:203.0.113.9"
    assert client_key(request(), user_id=42) == "user:42"
    assert (
        client_key(request([("X-Forwarded-For", "192.0.2.7")]), user_id=42) == "user:42"
    )
