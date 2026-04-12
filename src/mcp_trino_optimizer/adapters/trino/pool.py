"""TrinoThreadPool — bounded asyncio.to_thread pool with semaphore backpressure.

D-04: Every Trino HTTP call is executed in a dedicated ThreadPoolExecutor
(default 4 workers, config-overridable via max_concurrent_queries).

A matching asyncio.Semaphore(max_workers) provides **backpressure**: if all
slots are occupied, TrinoPoolBusyError is raised immediately rather than
queueing the request indefinitely. This prevents memory growth under load
(T-02-08 denial-of-service mitigation).
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any, TypeVar

from mcp_trino_optimizer.adapters.trino.errors import TrinoPoolBusyError

__all__ = ["TrinoThreadPool"]

T = TypeVar("T")

# How long to attempt acquiring the semaphore before giving up.
# 0.1 s is intentionally short — callers should retry or surface an error.
_ACQUIRE_TIMEOUT: float = 0.1


class TrinoThreadPool:
    """Bounded thread pool for synchronous Trino cursor operations.

    Attributes:
        max_workers: Maximum number of concurrent Trino queries. Must match
            ``Settings.max_concurrent_queries`` (default 4).

    Raises:
        TrinoPoolBusyError: Immediately when all worker slots are occupied.
    """

    def __init__(self, max_workers: int = 4) -> None:
        self._max_workers = max_workers
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="trino-",
        )
        self._semaphore = asyncio.Semaphore(max_workers)

    async def run(self, fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        """Run *fn* in the thread pool; raise TrinoPoolBusyError if full.

        Args:
            fn: Synchronous callable to run in the executor.
            *args: Positional arguments forwarded to *fn*.
            **kwargs: Keyword arguments forwarded to *fn*.

        Returns:
            The return value of *fn*.

        Raises:
            TrinoPoolBusyError: If all worker slots are currently occupied.
        """
        # Try to acquire the semaphore within the short timeout.
        # asyncio.shield() prevents wait_for from cancelling the acquire()
        # coroutine on timeout, avoiding the bpo-45584 semaphore counter leak
        # that occurs on Python 3.11+ when the acquire() task completes between
        # the TimeoutError being raised and wait_for's cleanup running.
        try:
            await asyncio.wait_for(
                asyncio.shield(self._semaphore.acquire()),
                timeout=_ACQUIRE_TIMEOUT,
            )
        except TimeoutError as err:
            raise TrinoPoolBusyError(
                f"All {self._max_workers} Trino query slots are occupied. "
                "Try again later or increase max_concurrent_queries."
            ) from err

        loop = asyncio.get_running_loop()
        try:
            if kwargs:
                import functools

                result: T = await loop.run_in_executor(
                    self._executor,
                    functools.partial(fn, *args, **kwargs),
                )
            else:
                result = await loop.run_in_executor(self._executor, fn, *args)
            return result
        finally:
            self._semaphore.release()

    def shutdown(self, wait: bool = True) -> None:
        """Shut down the underlying ThreadPoolExecutor."""
        self._executor.shutdown(wait=wait)
