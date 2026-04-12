"""LivePlanSource — implements PlanSource via live TrinoClient (TRN-08).

Thin wrapper that delegates EXPLAIN calls to ``TrinoClient``.
The SqlClassifier gate lives inside ``TrinoClient`` — this class
does not duplicate it.

On ``TimeoutResult``, raises ``TrinoTimeoutError`` rather than silently
returning empty/partial data, since a partial EXPLAIN plan is not useful.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp_trino_optimizer.adapters.trino.errors import TrinoTimeoutError
from mcp_trino_optimizer.adapters.trino.handle import TimeoutResult
from mcp_trino_optimizer.ports.plan_source import ExplainPlan

if TYPE_CHECKING:
    from mcp_trino_optimizer.adapters.trino.client import TrinoClient

__all__ = ["LivePlanSource"]


class LivePlanSource:
    """PlanSource via a live TrinoClient. Thin delegation wrapper.

    Args:
        client: Configured ``TrinoClient`` instance.
    """

    def __init__(self, client: TrinoClient) -> None:
        self._client = client

    async def fetch_plan(self, sql: str) -> ExplainPlan:
        """Run ``EXPLAIN (FORMAT JSON) <sql>`` and return the plan.

        Args:
            sql: The user SQL to explain.

        Returns:
            ``ExplainPlan`` with ``plan_type="estimated"``.

        Raises:
            TrinoTimeoutError: If the EXPLAIN query times out.
            TrinoClassifierRejected: If ``sql`` is not a read-only SELECT.
        """
        result = await self._client.fetch_plan(sql)
        if isinstance(result, TimeoutResult):
            raise TrinoTimeoutError(
                f"EXPLAIN timed out after {result.elapsed_ms}ms",
                query_id=result.query_id,
            )
        return result

    async def fetch_analyze_plan(self, sql: str) -> ExplainPlan:
        """Run ``EXPLAIN ANALYZE (FORMAT JSON) <sql>`` and return the plan.

        Args:
            sql: The user SQL to analyze.

        Returns:
            ``ExplainPlan`` with ``plan_type="executed"``.

        Raises:
            TrinoTimeoutError: If the EXPLAIN ANALYZE query times out.
            TrinoClassifierRejected: If ``sql`` is not a read-only SELECT.
        """
        result = await self._client.fetch_analyze_plan(sql)
        if isinstance(result, TimeoutResult):
            raise TrinoTimeoutError(
                f"EXPLAIN ANALYZE timed out after {result.elapsed_ms}ms",
                query_id=result.query_id,
            )
        return result

    async def fetch_distributed_plan(self, sql: str) -> ExplainPlan:
        """Run ``EXPLAIN (TYPE DISTRIBUTED, FORMAT JSON) <sql>`` and return the plan.

        Args:
            sql: The user SQL to explain distributedly.

        Returns:
            ``ExplainPlan`` with ``plan_type="distributed"``.

        Raises:
            TrinoTimeoutError: If the EXPLAIN DISTRIBUTED query times out.
            TrinoClassifierRejected: If ``sql`` is not a read-only SELECT.
        """
        result = await self._client.fetch_distributed_plan(sql)
        if isinstance(result, TimeoutResult):
            raise TrinoTimeoutError(
                f"EXPLAIN DISTRIBUTED timed out after {result.elapsed_ms}ms",
                query_id=result.query_id,
            )
        return result
