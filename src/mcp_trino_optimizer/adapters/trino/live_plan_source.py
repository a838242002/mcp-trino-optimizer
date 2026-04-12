"""LivePlanSource — implements PlanSource via live TrinoClient (TRN-08).

Thin wrapper that delegates EXPLAIN calls to ``TrinoClient``.
The SqlClassifier gate lives inside ``TrinoClient`` — this class
does not duplicate it.

On ``TimeoutResult``, raises ``TrinoTimeoutError`` rather than silently
returning empty/partial data, since a partial EXPLAIN plan is not useful.

Phase 3: TrinoClient now returns EstimatedPlan/ExecutedPlan directly via the
Phase 3 parser. This class is a pass-through wrapper that raises on timeout.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp_trino_optimizer.adapters.trino.errors import TrinoTimeoutError
from mcp_trino_optimizer.adapters.trino.handle import TimeoutResult
from mcp_trino_optimizer.parser.models import EstimatedPlan, ExecutedPlan

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

    async def fetch_plan(self, sql: str) -> EstimatedPlan:
        """Run ``EXPLAIN (FORMAT JSON) <sql>`` and return the typed plan."""
        result = await self._client.fetch_plan(sql)
        if isinstance(result, TimeoutResult):
            raise TrinoTimeoutError(
                f"EXPLAIN timed out after {result.elapsed_ms}ms",
                query_id=result.query_id,
            )
        return result

    async def fetch_analyze_plan(self, sql: str) -> ExecutedPlan:
        """Run ``EXPLAIN ANALYZE <sql>`` and return the typed executed plan."""
        result = await self._client.fetch_analyze_plan(sql)
        if isinstance(result, TimeoutResult):
            raise TrinoTimeoutError(
                f"EXPLAIN ANALYZE timed out after {result.elapsed_ms}ms",
                query_id=result.query_id,
            )
        return result

    async def fetch_distributed_plan(self, sql: str) -> EstimatedPlan:
        """Run ``EXPLAIN (TYPE DISTRIBUTED) <sql>`` and return the typed plan."""
        result = await self._client.fetch_distributed_plan(sql)
        if isinstance(result, TimeoutResult):
            raise TrinoTimeoutError(
                f"EXPLAIN DISTRIBUTED timed out after {result.elapsed_ms}ms",
                query_id=result.query_id,
            )
        return result
