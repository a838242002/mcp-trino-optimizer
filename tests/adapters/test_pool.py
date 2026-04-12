"""Unit tests for TrinoThreadPool, QueryIdCell, and TimeoutResult (D-04, D-06, D-10)."""

from __future__ import annotations

import asyncio
import contextlib
import threading
import time

import pytest

from mcp_trino_optimizer.adapters.trino.errors import TrinoPoolBusyError
from mcp_trino_optimizer.adapters.trino.handle import QueryIdCell, TimeoutResult
from mcp_trino_optimizer.adapters.trino.pool import TrinoThreadPool

# ---------------------------------------------------------------------------
# TrinoThreadPool tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pool_run_executes_callable() -> None:
    """TrinoThreadPool.run() executes the callable in a thread and returns the result."""
    pool = TrinoThreadPool(max_workers=2)
    try:
        result = await pool.run(lambda: 42)
        assert result == 42
    finally:
        pool.shutdown(wait=False)


@pytest.mark.asyncio
async def test_pool_run_passes_args() -> None:
    """TrinoThreadPool.run() forwards *args correctly."""
    pool = TrinoThreadPool(max_workers=2)
    try:
        result = await pool.run(lambda a, b: a + b, 3, 4)
        assert result == 7
    finally:
        pool.shutdown(wait=False)


@pytest.mark.asyncio
async def test_pool_run_passes_kwargs() -> None:
    """TrinoThreadPool.run() forwards **kwargs correctly."""

    def add(a: int, b: int = 0) -> int:
        return a + b

    pool = TrinoThreadPool(max_workers=2)
    try:
        result = await pool.run(add, 10, b=5)
        assert result == 15
    finally:
        pool.shutdown(wait=False)


@pytest.mark.asyncio
async def test_pool_rejects_when_full() -> None:
    """TrinoThreadPool raises TrinoPoolBusyError when all slots are busy."""
    pool = TrinoThreadPool(max_workers=1)

    # Hold the single slot via an event inside the thread
    slot_held = threading.Event()
    release_slot = threading.Event()

    def hold_slot() -> None:
        slot_held.set()
        release_slot.wait(timeout=5.0)

    try:
        # Start a task that holds the slot
        task = asyncio.create_task(pool.run(hold_slot))
        # Wait until the slot is actually occupied
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: slot_held.wait(timeout=2.0))

        # Now try to acquire another slot — should be rejected
        with pytest.raises(TrinoPoolBusyError):
            await pool.run(lambda: None)
    finally:
        release_slot.set()
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task
        pool.shutdown(wait=False)


@pytest.mark.asyncio
async def test_pool_max_workers_1_sequential() -> None:
    """TrinoThreadPool with max_workers=1 allows sequential execution."""
    pool = TrinoThreadPool(max_workers=1)
    results: list[int] = []
    try:
        for i in range(3):
            val = await pool.run(
                lambda x=i: x,
            )
            results.append(val)
        assert results == [0, 1, 2]
    finally:
        pool.shutdown(wait=False)


# ---------------------------------------------------------------------------
# QueryIdCell tests
# ---------------------------------------------------------------------------


def test_query_id_cell_set_once_stores_value() -> None:
    """QueryIdCell.set_once sets the value and makes it readable."""
    cell = QueryIdCell()
    assert cell.value is None
    cell.set_once("q-123")
    assert cell.value == "q-123"


def test_query_id_cell_set_once_is_idempotent() -> None:
    """Second call to set_once is a no-op — first value wins."""
    cell = QueryIdCell()
    cell.set_once("first")
    cell.set_once("second")
    assert cell.value == "first"


def test_query_id_cell_wait_for_returns_value_after_set() -> None:
    """wait_for returns the value after set_once is called from another thread."""
    cell = QueryIdCell()

    def setter() -> None:
        time.sleep(0.05)
        cell.set_once("async-id")

    t = threading.Thread(target=setter)
    t.start()
    value = cell.wait_for(timeout=2.0)
    t.join()
    assert value == "async-id"


def test_query_id_cell_wait_for_timeout_returns_none() -> None:
    """wait_for returns None if the event is never set within timeout."""
    cell = QueryIdCell()
    value = cell.wait_for(timeout=0.01)
    assert value is None


# ---------------------------------------------------------------------------
# TimeoutResult tests
# ---------------------------------------------------------------------------


def test_timeout_result_defaults() -> None:
    """TimeoutResult has correct field defaults."""
    tr: TimeoutResult[list[int]] = TimeoutResult(partial=[])
    assert tr.timed_out is True
    assert tr.elapsed_ms == 0
    assert tr.query_id == ""
    assert tr.reason == "wall_clock_deadline"
    assert tr.partial == []


def test_timeout_result_custom_values() -> None:
    """TimeoutResult stores custom partial data and metadata."""
    tr: TimeoutResult[dict[str, int]] = TimeoutResult(
        partial={"rows": 5},
        timed_out=True,
        elapsed_ms=30000,
        query_id="q-abc",
    )
    assert tr.partial == {"rows": 5}
    assert tr.elapsed_ms == 30000
    assert tr.query_id == "q-abc"
