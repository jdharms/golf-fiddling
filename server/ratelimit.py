"""A token bucket per client, in process memory, for `POST /generate`.

Generating is the one request a stranger can use to make the server do work and store
bytes, so each client gets a small bucket of seeds that refills over time. There is no
global ceiling: a surge of real users queues on the build semaphore instead. See
docs/randomizer_devplan.md, "Users and access".
"""

import threading
import time
from collections.abc import Callable

from starlette.requests import Request

#: seeds a client may generate back to back
GENERATE_CAPACITY = 5
#: seconds for one more seed to come back to a client's bucket
GENERATE_REFILL_SECONDS = 60.0

FORWARDED_HEADER = "x-forwarded-for"


class RateLimiter:
    def __init__(self, capacity: int, refill_seconds: float, clock: Callable[[], float] = time.monotonic):
        if capacity < 1 or refill_seconds <= 0:
            raise ValueError("a rate limiter needs a capacity of at least 1 and a positive refill time")
        self.capacity = capacity
        self.refill_seconds = refill_seconds
        self._clock = clock
        self._lock = threading.Lock()
        #: key -> (tokens, when they were counted)
        self._buckets: dict[str, tuple[float, float]] = {}
        self._last_prune = clock()

    def _tokens(self, key: str, now: float) -> float:
        tokens, counted = self._buckets.get(key, (self.capacity, now))
        return min(self.capacity, tokens + (now - counted) / self.refill_seconds)

    def allow(self, key: str) -> bool:
        """Take a token from this key's bucket. False, taking nothing, when the bucket is empty."""
        with self._lock:
            now = self._clock()
            self._prune(now)
            tokens = self._tokens(key, now)
            if tokens < 1:
                self._buckets[key] = (tokens, now)
                return False
            self._buckets[key] = (tokens - 1, now)
            return True

    def _prune(self, now: float) -> None:
        """Forget buckets that have refilled, since a full bucket is what an unknown key gets."""
        if now - self._last_prune < self.refill_seconds * self.capacity:
            return
        self._last_prune = now
        full = [key for key in self._buckets if self._tokens(key, now) >= self.capacity]
        for key in full:
            del self._buckets[key]

    def __len__(self) -> int:
        return len(self._buckets)


def client_key(request: Request) -> str:
    """The client's address, from the reverse proxy's forwarded header when there is one.

    The proxy appends the address it saw to whatever the client sent, so the last entry
    is the one a client cannot forge. Without the header, as in development, it is the
    socket's peer.
    """
    forwarded = request.headers.get(FORWARDED_HEADER)
    if forwarded:
        addresses = [part.strip() for part in forwarded.split(",") if part.strip()]
        if addresses:
            return addresses[-1]
    return request.client.host if request.client is not None else "unknown"
