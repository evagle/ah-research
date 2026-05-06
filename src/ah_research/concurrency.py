"""Concurrency helpers.

Use thread_map for I/O-bound work (network, disk). Use process_map for CPU-bound
work (backtests, factor studies). asyncio is intentionally not used — Baostock
and AKshare are blocking libraries.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor


def thread_map[T, R](
    fn: Callable[[T], R],
    items: Iterable[T],
    *,
    max_workers: int = 8,
) -> list[R]:
    """Apply fn to each item via a thread pool. Results preserve input order.
    Exceptions propagate from the first failing item."""
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        return list(ex.map(fn, items))


def process_map[T, R](
    fn: Callable[[T], R],
    items: Iterable[T],
    *,
    max_workers: int | None = None,
) -> list[R]:
    """Apply fn to each item via a process pool. fn must be picklable
    (top-level function, no closures). Results preserve input order."""
    with ProcessPoolExecutor(max_workers=max_workers) as ex:
        return list(ex.map(fn, items))
