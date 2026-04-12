"""PlanSource port — the hexagonal boundary for Trino EXPLAIN plan retrieval.

This module is a pure Protocol definition. It MUST NOT import anything from
``mcp_trino_optimizer.adapters``. Both live and offline adapters satisfy this
Protocol, keeping rule/recommender/rewrite engines mode-agnostic.

Phase 3: ExplainPlan placeholder removed. PlanSource now returns typed
EstimatedPlan and ExecutedPlan domain objects from the parser subpackage.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

# Re-export EstimatedPlan and ExecutedPlan for consumers who import from ports.
# ports/plan_source.py may import from parser (not from adapters — that direction
# is forbidden). The parser subpackage has no dependency on ports or adapters.
from mcp_trino_optimizer.parser.models import EstimatedPlan, ExecutedPlan


@runtime_checkable
class PlanSource(Protocol):
    """Port contract for retrieving Trino EXPLAIN plans.

    Implementations:
    - ``adapters.trino.live_plan_source.LivePlanSource`` — issues EXPLAIN
      against a live Trino cluster.
    - ``adapters.offline.json_plan_source.OfflinePlanSource`` — parses
      raw text from tool input (no cluster required).

    All methods are ``async`` because the live adapter is async under the hood
    (sync trino-python-client bridged via ``anyio.to_thread``).
    """

    async def fetch_plan(self, sql: str) -> EstimatedPlan:
        """Run ``EXPLAIN (FORMAT JSON) <sql>`` and return the typed plan.

        For offline mode, ``sql`` is the raw JSON text of the plan.
        """
        ...

    async def fetch_analyze_plan(self, sql: str) -> ExecutedPlan:
        """Run ``EXPLAIN ANALYZE <sql>`` and return the typed executed plan.

        Returns an ``ExecutedPlan`` with per-operator runtime metrics extracted
        from the EXPLAIN ANALYZE text output.

        For offline mode, ``sql`` is the raw EXPLAIN ANALYZE text.

        Note: EXPLAIN ANALYZE does NOT support FORMAT JSON (Trino grammar
        limitation). Text parsing is the only supported path.
        """
        ...

    async def fetch_distributed_plan(self, sql: str) -> EstimatedPlan:
        """Run ``EXPLAIN (TYPE DISTRIBUTED, FORMAT JSON) <sql>`` and return the plan.

        Returns an ``EstimatedPlan`` with stage/fragment distribution information.
        Distributed plans are JSON format, parsed as EstimatedPlan.

        For offline mode, ``sql`` is the raw JSON text of a distributed plan.
        """
        ...
