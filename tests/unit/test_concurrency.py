import time

import pytest

from ah_research.concurrency import process_map, thread_map


def _slow_square(x: int) -> int:
    time.sleep(0.05)
    return x * x


def _bad(x: int) -> int:
    if x == 3:
        raise ValueError("nope")
    return x


def test_thread_map_returns_ordered_results():
    results = thread_map(_slow_square, [1, 2, 3, 4, 5], max_workers=4)
    assert results == [1, 4, 9, 16, 25]


@pytest.mark.slow
def test_thread_map_is_faster_than_serial():
    inputs = list(range(10))
    t0 = time.perf_counter()
    _ = [_slow_square(x) for x in inputs]
    serial = time.perf_counter() - t0

    t0 = time.perf_counter()
    _ = thread_map(_slow_square, inputs, max_workers=8)
    concurrent = time.perf_counter() - t0

    assert concurrent < serial / 3, f"serial={serial:.3f}s concurrent={concurrent:.3f}s"


def test_process_map_handles_pickleable_fn():
    results = process_map(_slow_square, [1, 2, 3], max_workers=2)
    assert results == [1, 4, 9]


def test_thread_map_propagates_exceptions():
    with pytest.raises(ValueError, match="nope"):
        thread_map(_bad, [1, 2, 3, 4], max_workers=2)
