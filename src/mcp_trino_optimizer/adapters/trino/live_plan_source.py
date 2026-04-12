"""LivePlanSource — implements PlanSource via live TrinoClient (TRN-08).

Thin wrapper that delegates EXPLAIN calls to ``TrinoClient``.
The SqlClassifier gate lives inside ``TrinoClient`` — this class
does not duplicate it.

On ``TimeoutResult``, raises ``TrinoTimeoutError`` rather than silently
returning empty/partial data, since a partial EXPLAIN plan is not useful.

Phase 3: Updated to return EstimatedPlan/ExecutedPlan (typed domain objects)
by bridging the TrinoClient's ExplainPlan output through the parser. The
TrinoClient internals still use ExplainPlan internally from Phase 2 — this
class converts to the new typed domain before returning.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import orjson

from mcp_trino_optimizer.adapters.trino.errors import TrinoTimeoutError
from mcp_trino_optimizer.adapters.trino.handle import TimeoutResult
from mcp_trino_optimizer.parser import parse_estimated_plan, parse_executed_plan
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
        """Run ``EXPLAIN (FORMAT JSON) <sql>`` and return the typed plan.

        Args:
            sql: The user SQL to explain.

        Returns:
            ``EstimatedPlan`` with a typed PlanNode tree.

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
        # Bridge Phase 2 ExplainPlan to Phase 3 typed EstimatedPlan
        json_text = result.raw_text or orjson.dumps(result.plan_json).decode()
        return parse_estimated_plan(json_text, trino_version=result.source_trino_version)

    async def fetch_analyze_plan(self, sql: str) -> ExecutedPlan:
        """Run ``EXPLAIN ANALYZE <sql>`` and return the typed executed plan.

        Args:
            sql: The user SQL to analyze.

        Returns:
            ``ExecutedPlan`` with per-operator runtime metrics.

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
        # Bridge Phase 2 ExplainPlan to Phase 3 typed ExecutedPlan.
        # EXPLAIN ANALYZE returns text only (not JSON), so we use raw_text.
        analyze_text = result.raw_text or ""
        return parse_executed_plan(analyze_text, trino_version=result.source_trino_version)

    async def fetch_distributed_plan(self, sql: str) -> EstimatedPlan:
        """Run ``EXPLAIN (TYPE DISTRIBUTED, FORMAT JSON) <sql>`` and return the plan.

        Args:
            sql: The user SQL to explain distributedly.

        Returns:
            ``EstimatedPlan`` with stage/fragment distribution information.

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
        # Bridge Phase 2 ExplainPlan to Phase 3 typed EstimatedPlan
        json_text = result.raw_text or orjson.dumps(result.plan_json).decode()
        return parse_estimated_plan(json_text, trino_version=result.source_trino_version)
