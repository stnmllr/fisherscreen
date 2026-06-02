import time
from typing import Callable, Optional

DEFAULT_EDGAR_MAX_REQUESTS_PER_SECOND: float = 8.0  # SEC fair-access limit is 10 req/s; 8 is the conservative target


class RateLimiter:
    """Drift-free minimum-interval rate limiter. acquire() blocks just long
    enough to keep the aggregate call rate at or below max_requests_per_second.
    monotonic/sleep are injectable for deterministic testing."""

    def __init__(
        self,
        max_requests_per_second: float,
        *,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if max_requests_per_second <= 0:
            raise ValueError(
                f"max_requests_per_second must be > 0, got {max_requests_per_second}"
            )
        self._interval: float = 1.0 / max_requests_per_second
        self._monotonic = monotonic
        self._sleep = sleep
        self._next_allowed: Optional[float] = None

    def acquire(self) -> None:
        now = self._monotonic()
        if self._next_allowed is not None and now < self._next_allowed:
            self._sleep(self._next_allowed - now)
            now = self._next_allowed
        self._next_allowed = now + self._interval
