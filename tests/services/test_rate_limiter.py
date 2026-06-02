import pytest

from app.services.rate_limiter import (
    DEFAULT_EDGAR_MAX_REQUESTS_PER_SECOND,
    RateLimiter,
)


class _FakeClock:
    """Deterministic clock+sleep pair. sleep(s) advances the fake time by s and
    records the requested durations so tests can assert exact sleep amounts."""

    def __init__(self, start: float = 0.0) -> None:
        self.t = start
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.t += seconds


def _limiter(clock: _FakeClock, rate: float = 8.0) -> RateLimiter:
    return RateLimiter(rate, monotonic=clock.monotonic, sleep=clock.sleep)


def test_default_rate_constant_is_eight():
    assert DEFAULT_EDGAR_MAX_REQUESTS_PER_SECOND == 8.0


def test_first_acquire_never_sleeps():
    clock = _FakeClock()
    limiter = _limiter(clock)

    limiter.acquire()

    assert clock.sleeps == []


def test_second_immediate_acquire_sleeps_exactly_one_interval():
    clock = _FakeClock()
    limiter = _limiter(clock, rate=8.0)

    limiter.acquire()  # no sleep
    limiter.acquire()  # clock not advanced by the test → must wait one interval

    assert clock.sleeps == [pytest.approx(0.125)]


def test_acquire_after_elapsed_time_does_not_sleep():
    clock = _FakeClock()
    limiter = _limiter(clock, rate=8.0)

    limiter.acquire()
    clock.t += 1.0  # far more than the 0.125 interval has elapsed
    limiter.acquire()

    assert clock.sleeps == []


def test_configurable_rate_reflected_in_sleep_duration():
    clock = _FakeClock()
    limiter = _limiter(clock, rate=4.0)  # interval 0.25

    limiter.acquire()
    limiter.acquire()

    assert clock.sleeps == [pytest.approx(0.25)]


def test_non_positive_rate_raises_value_error():
    with pytest.raises(ValueError, match="max_requests_per_second must be > 0"):
        RateLimiter(0)
    with pytest.raises(ValueError, match="max_requests_per_second must be > 0"):
        RateLimiter(-1.0)


def test_drift_free_three_rapid_acquires_schedule_at_multiples_of_interval():
    # _next_allowed must advance by exactly one interval per acquire, independent of
    # how long the actual sleep ran — three rapid acquires schedule at 0, i, 2i.
    clock = _FakeClock()
    limiter = _limiter(clock, rate=8.0)
    interval = 0.125

    limiter.acquire()
    assert limiter._next_allowed == pytest.approx(interval)

    limiter.acquire()
    assert limiter._next_allowed == pytest.approx(2 * interval)

    limiter.acquire()
    assert limiter._next_allowed == pytest.approx(3 * interval)
