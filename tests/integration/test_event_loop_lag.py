"""Integration tests for event-loop lag during concurrent Trino queries (D-05, TRN-02, TRN-15).

Verifies that the event loop is never blocked > 100ms while TrinoClient
executes concurrent Trino queries in the bounded thread pool.

Requires docker-compose stack to be running. Run with:
    uv run pytest -m integration tests/integration/test_event_loop_lag.py
"""

from __future__ import annotations

import asyncio
import time

import pytest

from mcp_trino_optimizer.adapters.trino.client import TrinoClient
from mcp_trino_optimizer.ports.plan_source import ExplainPlan


@pytest.mark.integration
class TestEventLoopLag:
    """Event-loop responsiveness during concurrent Trino queries."""

    async def test_event_loop_not_blocked(self, trino_client: TrinoClient) -> None:
        """Launch 4 concurrent fetch_plan calls; assert no event-loop tick gap > 100ms.

        Uses asyncio.get_event_loop().call_later to schedule a recurring ticker
        every 50ms. After all queries complete, checks that no two consecutive
        ticks were separated by more than 100ms — which would indicate the event
        loop was blocked by a synchronous Trino call in the main thread.
        """
        loop = asyncio.get_event_loop()
        tick_timestamps: list[float] = []
        ticker_running = True

        def record_tick() -> None:
            tick_timestamps.append(time.monotonic())
            if ticker_running:
                loop.call_later(0.05, record_tick)  # schedule next tick in 50ms

        # Start the ticker
        loop.call_later(0.05, record_tick)

        # Launch 4 concurrent EXPLAIN queries
        tasks = [
            trino_client.fetch_plan("SELECT 1"),
            trino_client.fetch_plan("SELECT 2"),
            trino_client.fetch_plan("SELECT 3"),
            trino_client.fetch_plan("SELECT 4"),
        ]
        results = await asyncio.gather(*tasks)

        # Stop the ticker
        ticker_running = False

        # Give the last tick one more cycle to fire
        await asyncio.sleep(0.06)

        # Verify all queries returned valid plans
        for result in results:
            assert isinstance(result, ExplainPlan), (
                f"Expected ExplainPlan, got {type(result)}"
            )

        # Verify event-loop was never blocked > 100ms
        if len(tick_timestamps) < 2:
            pytest.skip("Not enough ticks recorded — query completed too quickly to measure lag")

        max_gap_ms = max(
            (tick_timestamps[i + 1] - tick_timestamps[i]) * 1000
            for i in range(len(tick_timestamps) - 1)
        )
        assert max_gap_ms <= 100, (
            f"Event loop was blocked for {max_gap_ms:.1f}ms — "
            "Trino calls must run in the thread pool, not the event loop. "
            "Check TrinoThreadPool.run() uses anyio.to_thread or asyncio.to_thread."
        )
