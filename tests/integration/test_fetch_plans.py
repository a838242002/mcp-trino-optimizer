"""Integration tests for EXPLAIN plan fetching (D-24 item 1, TRN-01, TRN-09).

Requires docker-compose stack to be running. Run with:
    uv run pytest -m integration tests/integration/test_fetch_plans.py
"""

from __future__ import annotations

import pytest

from mcp_trino_optimizer.adapters.trino.client import TrinoClient
from mcp_trino_optimizer.ports.plan_source import ExplainPlan


@pytest.mark.integration
class TestFetchPlans:
    """EXPLAIN plan fetching via TrinoClient against real Trino 480."""

    async def test_fetch_plan_select_one(self, trino_client: TrinoClient) -> None:
        """EXPLAIN (FORMAT JSON) SELECT 1 returns an estimated ExplainPlan."""
        result = await trino_client.fetch_plan("SELECT 1")
        assert isinstance(result, ExplainPlan), f"Expected ExplainPlan, got {type(result)}"
        assert result.plan_type == "estimated"
        assert result.plan_json is not None

    async def test_fetch_analyze_plan_select_one(self, trino_client: TrinoClient) -> None:
        """EXPLAIN ANALYZE (FORMAT JSON) SELECT 1 returns an executed ExplainPlan."""
        result = await trino_client.fetch_analyze_plan("SELECT 1")
        assert isinstance(result, ExplainPlan), f"Expected ExplainPlan, got {type(result)}"
        assert result.plan_type == "executed"
        assert result.plan_json is not None

    async def test_fetch_distributed_plan(self, trino_client: TrinoClient) -> None:
        """EXPLAIN (TYPE DISTRIBUTED) SELECT 1 returns a distributed ExplainPlan."""
        result = await trino_client.fetch_distributed_plan("SELECT 1")
        assert isinstance(result, ExplainPlan), f"Expected ExplainPlan, got {type(result)}"
        assert result.plan_type == "distributed"

    async def test_fetch_plan_iceberg_table(
        self, trino_client: TrinoClient, seeded_stack: tuple[str, int]
    ) -> None:
        """EXPLAIN plan for a real Iceberg table query returns a populated ExplainPlan."""
        result = await trino_client.fetch_plan(
            "SELECT * FROM iceberg.test_schema.test_table"
        )
        assert isinstance(result, ExplainPlan), f"Expected ExplainPlan, got {type(result)}"
        assert result.plan_type == "estimated"
        # The plan JSON should have content for a real table scan
        assert result.plan_json is not None
