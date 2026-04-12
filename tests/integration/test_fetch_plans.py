"""Integration tests for EXPLAIN plan fetching (D-24 item 1, TRN-01, TRN-09).

Requires docker-compose stack to be running. Run with:
    uv run pytest -m integration tests/integration/test_fetch_plans.py
"""

from __future__ import annotations

import pytest

from mcp_trino_optimizer.adapters.trino.client import TrinoClient
from mcp_trino_optimizer.adapters.trino.handle import TimeoutResult
from mcp_trino_optimizer.parser.models import EstimatedPlan, ExecutedPlan


@pytest.mark.integration
class TestFetchPlans:
    """EXPLAIN plan fetching via TrinoClient against real Trino 480."""

    async def test_fetch_plan_select_one(self, trino_client: TrinoClient) -> None:
        """EXPLAIN (FORMAT JSON) SELECT 1 returns an EstimatedPlan."""
        result = await trino_client.fetch_plan("SELECT 1")
        assert isinstance(result, EstimatedPlan), f"Expected EstimatedPlan, got {type(result)}"
        assert result.plan_type == "estimated"
        assert result.root is not None

    async def test_fetch_analyze_plan_select_one(self, trino_client: TrinoClient) -> None:
        """EXPLAIN ANALYZE SELECT 1 returns an ExecutedPlan (or TimeoutResult on slow CI)."""
        result = await trino_client.fetch_analyze_plan("SELECT 1")
        assert not isinstance(result, TimeoutResult), "Unexpected timeout on SELECT 1"
        assert isinstance(result, ExecutedPlan), f"Expected ExecutedPlan, got {type(result)}"
        assert result.plan_type == "executed"
        assert result.root is not None

    async def test_fetch_distributed_plan(self, trino_client: TrinoClient) -> None:
        """EXPLAIN (TYPE DISTRIBUTED) SELECT 1 returns an EstimatedPlan."""
        result = await trino_client.fetch_distributed_plan("SELECT 1")
        assert isinstance(result, EstimatedPlan), f"Expected EstimatedPlan, got {type(result)}"
        assert result.plan_type == "estimated"

    async def test_fetch_plan_iceberg_table(self, trino_client: TrinoClient, seeded_stack: tuple[str, int]) -> None:
        """EXPLAIN plan for a real Iceberg table query returns a populated EstimatedPlan."""
        result = await trino_client.fetch_plan("SELECT * FROM iceberg.test_schema.test_table")
        assert isinstance(result, EstimatedPlan), f"Expected EstimatedPlan, got {type(result)}"
        assert result.plan_type == "estimated"
        assert result.root is not None
