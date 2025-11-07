from dgas.data.rate_limiter import RateLimiter


def test_rate_limiter_blocks_until_slot_available() -> None:
    state = {"time": 0.0}
    sleep_calls: list[float] = []

    def now() -> float:
        return state["time"]

    def sleep(duration: float) -> None:
        sleep_calls.append(duration)
        state["time"] += duration

    limiter = RateLimiter(max_calls=2, period=1.0, now_func=now, sleep_func=sleep)

    limiter.acquire()  # allowed immediately
    limiter.acquire()  # allowed immediately (second token)

    # Third call must wait until 1 second has elapsed
    limiter.acquire()

    assert sleep_calls == [1.0]
    assert state["time"] == 1.0
