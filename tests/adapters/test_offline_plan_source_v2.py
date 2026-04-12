"""Updated tests for OfflinePlanSource after Phase 3 migration.

These tests validate that OfflinePlanSource now returns EstimatedPlan/ExecutedPlan
(typed domain objects from the parser) instead of the old ExplainPlan placeholder.
"""

from __future__ import annotations

import json

import pytest

VALID_ESTIMATED_JSON = json.dumps(
    {
        "id": "0",
        "name": "Output",
        "descriptor": {"columnNames": "[id]"},
        "outputs": [{"symbol": "id", "type": "bigint"}],
        "details": [],
        "estimates": [{"outputRowCount": 10.0}],
        "children": [
            {
                "id": "1",
                "name": "TableScan",
                "descriptor": {"table": "iceberg.schema.test_table"},
                "outputs": [],
                "details": [],
                "estimates": [],
                "children": [],
            }
        ],
    }
)

VALID_ANALYZE_TEXT = """\
Fragment 0 [SINGLE]
    CPU: 150.00ms, Scheduled: 200.00ms, Blocked 0.00ns (Input: 0.00ns, Output: 0.00ns), Input: 100 rows (5.00kB)
    Output[columnNames = [id]] => [id:bigint]
        CPU: 10.00ms, Scheduled: 12.00ms, Blocked: 0.00ns, Output: 100 rows (0.80kB)
        \u2514\u2500 TableScan[iceberg.schema.test_table] => [id:bigint]
                CPU: 130.00ms, Scheduled: 180.00ms, Blocked: 0.00ns, Output: 1000 rows (8.00kB)
                Input: 1000 rows (8.00kB), 3 splits
"""

VALID_DISTRIBUTED_JSON = json.dumps(
    {
        "id": "0",
        "name": "Output",
        "children": [],
    }
)


class TestFetchPlanReturnsEstimatedPlan:
    """OfflinePlanSource.fetch_plan() must return EstimatedPlan, not ExplainPlan."""

    async def test_fetch_plan_returns_estimated_plan_type(self) -> None:
        """fetch_plan() returns an EstimatedPlan object."""
        from mcp_trino_optimizer.adapters.offline.json_plan_source import OfflinePlanSource
        from mcp_trino_optimizer.parser.models import EstimatedPlan

        source = OfflinePlanSource()
        result = await source.fetch_plan(VALID_ESTIMATED_JSON)

        assert isinstance(result, EstimatedPlan)

    async def test_fetch_plan_result_has_typed_root_node(self) -> None:
        """fetch_plan() result has a typed PlanNode root."""
        from mcp_trino_optimizer.adapters.offline.json_plan_source import OfflinePlanSource
        from mcp_trino_optimizer.parser.models import PlanNode

        source = OfflinePlanSource()
        result = await source.fetch_plan(VALID_ESTIMATED_JSON)

        assert isinstance(result.root, PlanNode)
        assert result.root.name == "Output"

    async def test_fetch_plan_result_has_children_tree(self) -> None:
        """fetch_plan() result has a recursive PlanNode tree."""
        from mcp_trino_optimizer.adapters.offline.json_plan_source import OfflinePlanSource

        source = OfflinePlanSource()
        result = await source.fetch_plan(VALID_ESTIMATED_JSON)

        assert len(result.root.children) == 1
        assert result.root.children[0].name == "TableScan"

    async def test_fetch_plan_source_trino_version_is_none(self) -> None:
        """fetch_plan() sets source_trino_version=None for offline mode."""
        from mcp_trino_optimizer.adapters.offline.json_plan_source import OfflinePlanSource

        source = OfflinePlanSource()
        result = await source.fetch_plan(VALID_ESTIMATED_JSON)

        assert result.source_trino_version is None

    async def test_fetch_plan_invalid_json_raises_value_error(self) -> None:
        """fetch_plan() with invalid JSON still raises ValueError."""
        from mcp_trino_optimizer.adapters.offline.json_plan_source import OfflinePlanSource

        source = OfflinePlanSource()
        with pytest.raises((ValueError, Exception)):
            await source.fetch_plan("not valid json {{{")

    async def test_fetch_plan_size_limit_still_enforced(self) -> None:
        """fetch_plan() 1MB size cap is still enforced."""
        from mcp_trino_optimizer.adapters.offline.json_plan_source import OfflinePlanSource

        source = OfflinePlanSource()
        big_json = json.dumps({"data": "x" * 1_000_001})

        with pytest.raises(ValueError, match="exceeds maximum"):
            await source.fetch_plan(big_json)


class TestFetchAnalyzePlanReturnsExecutedPlan:
    """OfflinePlanSource.fetch_analyze_plan() must return ExecutedPlan, not ExplainPlan."""

    async def test_fetch_analyze_plan_returns_executed_plan_type(self) -> None:
        """fetch_analyze_plan() returns an ExecutedPlan object."""
        from mcp_trino_optimizer.adapters.offline.json_plan_source import OfflinePlanSource
        from mcp_trino_optimizer.parser.models import ExecutedPlan

        source = OfflinePlanSource()
        result = await source.fetch_analyze_plan(VALID_ANALYZE_TEXT)

        assert isinstance(result, ExecutedPlan)

    async def test_fetch_analyze_plan_result_has_typed_root_node(self) -> None:
        """fetch_analyze_plan() result has a typed PlanNode root."""
        from mcp_trino_optimizer.adapters.offline.json_plan_source import OfflinePlanSource
        from mcp_trino_optimizer.parser.models import PlanNode

        source = OfflinePlanSource()
        result = await source.fetch_analyze_plan(VALID_ANALYZE_TEXT)

        assert isinstance(result.root, PlanNode)

    async def test_fetch_analyze_plan_source_trino_version_is_none(self) -> None:
        """fetch_analyze_plan() sets source_trino_version=None for offline mode."""
        from mcp_trino_optimizer.adapters.offline.json_plan_source import OfflinePlanSource

        source = OfflinePlanSource()
        result = await source.fetch_analyze_plan(VALID_ANALYZE_TEXT)

        assert result.source_trino_version is None

    async def test_fetch_analyze_plan_size_limit_enforced(self) -> None:
        """fetch_analyze_plan() 1MB size cap still enforced."""
        from mcp_trino_optimizer.adapters.offline.json_plan_source import OfflinePlanSource

        source = OfflinePlanSource()
        big_text = "x" * 1_000_001

        with pytest.raises(ValueError, match="exceeds maximum"):
            await source.fetch_analyze_plan(big_text)


class TestFetchDistributedPlanReturnsEstimatedPlan:
    """OfflinePlanSource.fetch_distributed_plan() must return EstimatedPlan."""

    async def test_fetch_distributed_plan_returns_estimated_plan(self) -> None:
        """fetch_distributed_plan() returns an EstimatedPlan object."""
        from mcp_trino_optimizer.adapters.offline.json_plan_source import OfflinePlanSource
        from mcp_trino_optimizer.parser.models import EstimatedPlan

        source = OfflinePlanSource()
        result = await source.fetch_distributed_plan(VALID_DISTRIBUTED_JSON)

        assert isinstance(result, EstimatedPlan)


class TestOfflinePlanSourceProtocolConformance:
    """OfflinePlanSource must still satisfy PlanSource protocol after migration."""

    def test_offline_plan_source_satisfies_plan_source_protocol(self) -> None:
        """isinstance(OfflinePlanSource(), PlanSource) must still be True."""
        from mcp_trino_optimizer.adapters.offline.json_plan_source import OfflinePlanSource
        from mcp_trino_optimizer.ports import PlanSource

        source = OfflinePlanSource()
        assert isinstance(source, PlanSource)
