"""PlanSource port — the hexagonal boundary for Trino EXPLAIN plan retrieval.

This module is a pure Protocol definition. It MUST NOT import anything from
``mcp_trino_optimizer.adapters``. Both live and offline adapters satisfy this
Protocol, keeping rule/recommender/rewrite engines mode-agnostic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, runtime_checkable


@dataclass
class ExplainPlan:
    """Minimum-viable domain type for a Trino EXPLAIN plan.

    Phase 3 will replace this with a typed stage/operator hierarchy derived
    from the full EXPLAIN (FORMAT JSON) schema. For now, we carry the raw
    parsed dict and enough metadata to route the plan to the right rules.

    Attributes:
        plan_json: The raw parsed JSON dict from EXPLAIN (FORMAT JSON).
        plan_type: One of "estimated" (EXPLAIN), "executed" (EXPLAIN ANALYZE),
            or "distributed" (EXPLAIN (TYPE DISTRIBUTED)).
        source_trino_version: Trino version string from the live adapter, or
            ``None`` for offline mode where no cluster is involved.
        raw_text: The original JSON text for round-trip fidelity. Populated
            by adapters that receive raw text input; empty for live adapters
            that receive the JSON from the Trino HTTP response.
    """

    plan_json: dict[str, Any]
    plan_type: Literal["estimated", "executed", "distributed"]
    source_trino_version: str | None = None
    raw_text: str = field(default="")


@runtime_checkable
class PlanSource(Protocol):
    """Port contract for retrieving Trino EXPLAIN plans.

    Implementations:
    - ``adapters.trino.live_plan_source.LivePlanSource`` — issues EXPLAIN
      against a live Trino cluster.
    - ``adapters.offline.json_plan_source.OfflinePlanSource`` — parses
      raw JSON text from tool input (no cluster required).

    All methods are ``async`` because the live adapter is async under the hood
    (sync trino-python-client bridged via ``anyio.to_thread``).
    """

    async def fetch_plan(self, sql: str) -> ExplainPlan:
        """Run ``EXPLAIN (FORMAT JSON) <sql>`` and return the plan.

        For offline mode, ``sql`` is the raw JSON text of the plan.
        """
        ...

    async def fetch_analyze_plan(self, sql: str) -> ExplainPlan:
        """Run ``EXPLAIN ANALYZE (FORMAT JSON) <sql>`` and return the plan.

        Returns an ``ExplainPlan`` with ``plan_type="executed"`` carrying
        per-operator runtime metrics.

        For offline mode, ``sql`` is the raw JSON text of an EXPLAIN ANALYZE
        plan.
        """
        ...

    async def fetch_distributed_plan(self, sql: str) -> ExplainPlan:
        """Run ``EXPLAIN (TYPE DISTRIBUTED, FORMAT JSON) <sql>`` and return the plan.

        Returns an ``ExplainPlan`` with ``plan_type="distributed"`` carrying
        stage/fragment distribution information.

        For offline mode, ``sql`` is the raw JSON text of a distributed plan.
        """
        ...
