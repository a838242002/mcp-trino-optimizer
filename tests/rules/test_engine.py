"""Engine prefetch-once + skip + run-loop tests."""

from typing import Any, ClassVar
from unittest.mock import AsyncMock

import pytest

from mcp_trino_optimizer.parser.models import EstimatedPlan, ExecutedPlan, PlanNode
from mcp_trino_optimizer.rules.base import Rule
from mcp_trino_optimizer.rules.engine import RuleEngine
from mcp_trino_optimizer.rules.evidence import EvidenceBundle, EvidenceRequirement
from mcp_trino_optimizer.rules.findings import RuleFinding, RuleSkipped
from mcp_trino_optimizer.rules.registry import RuleRegistry


def _make_plan(plan_type: str = "estimated") -> EstimatedPlan | ExecutedPlan:
    root = PlanNode(id="root", name="Output", children=[])
    if plan_type == "executed":
        return ExecutedPlan(root=root)
    return EstimatedPlan(root=root)


class _PlanOnlyRule(Rule):
    rule_id: ClassVar[str] = "TEST_PLAN_ONLY"
    evidence_requirement: ClassVar[EvidenceRequirement] = EvidenceRequirement.PLAN_ONLY

    def check(self, plan: Any, evidence: EvidenceBundle) -> list[RuleFinding]:
        return [
            RuleFinding(
                rule_id=self.rule_id,
                severity="low",
                confidence=1.0,
                message="plan_only fired",
                evidence={},
                operator_ids=[],
            )
        ]


class _StatsRule(Rule):
    rule_id: ClassVar[str] = "TEST_STATS"
    evidence_requirement: ClassVar[EvidenceRequirement] = EvidenceRequirement.TABLE_STATS

    def check(self, plan: Any, evidence: EvidenceBundle) -> list[RuleFinding]:
        return []


class _IcebergRule(Rule):
    rule_id: ClassVar[str] = "TEST_ICEBERG"
    evidence_requirement: ClassVar[EvidenceRequirement] = EvidenceRequirement.ICEBERG_METADATA

    def check(self, plan: Any, evidence: EvidenceBundle) -> list[RuleFinding]:
        return []


class _MetricsRule(Rule):
    rule_id: ClassVar[str] = "TEST_METRICS"
    evidence_requirement: ClassVar[EvidenceRequirement] = EvidenceRequirement.PLAN_WITH_METRICS

    def check(self, plan: Any, evidence: EvidenceBundle) -> list[RuleFinding]:
        return []


@pytest.mark.asyncio
async def test_plan_only_rule_runs_with_no_sources() -> None:
    """A PLAN_ONLY rule runs even when stats_source and catalog_source are None."""
    reg = RuleRegistry()
    reg.register(_PlanOnlyRule)
    engine = RuleEngine(stats_source=None, catalog_source=None, registry=reg)

    results = await engine.run(_make_plan())
    assert len(results) == 1
    assert isinstance(results[0], RuleFinding)
    assert results[0].rule_id == "TEST_PLAN_ONLY"


@pytest.mark.asyncio
async def test_stats_rule_skipped_when_no_stats_source() -> None:
    """TABLE_STATS rule emits RuleSkipped when stats_source is None."""
    reg = RuleRegistry()
    reg.register(_StatsRule)
    engine = RuleEngine(stats_source=None, catalog_source=None, registry=reg)

    results = await engine.run(_make_plan())
    assert len(results) == 1
    assert isinstance(results[0], RuleSkipped)
    assert results[0].rule_id == "TEST_STATS"
    assert results[0].reason == "offline_mode_no_stats_source"


@pytest.mark.asyncio
async def test_iceberg_rule_skipped_when_no_catalog_source() -> None:
    """ICEBERG_METADATA rule emits RuleSkipped when catalog_source is None."""
    reg = RuleRegistry()
    reg.register(_IcebergRule)
    engine = RuleEngine(stats_source=None, catalog_source=None, registry=reg)

    results = await engine.run(_make_plan())
    assert len(results) == 1
    assert isinstance(results[0], RuleSkipped)
    assert results[0].reason == "offline_mode_no_catalog_source"


@pytest.mark.asyncio
async def test_metrics_rule_skipped_for_estimated_plan() -> None:
    """PLAN_WITH_METRICS rule emits RuleSkipped when plan is EstimatedPlan."""
    reg = RuleRegistry()
    reg.register(_MetricsRule)
    engine = RuleEngine(stats_source=None, catalog_source=None, registry=reg)

    results = await engine.run(_make_plan("estimated"))
    assert len(results) == 1
    assert isinstance(results[0], RuleSkipped)
    assert results[0].reason == "requires_executed_plan_estimated_provided"


@pytest.mark.asyncio
async def test_metrics_rule_runs_for_executed_plan() -> None:
    """PLAN_WITH_METRICS rule is not skipped when plan is ExecutedPlan."""
    reg = RuleRegistry()
    reg.register(_MetricsRule)
    engine = RuleEngine(stats_source=None, catalog_source=None, registry=reg)

    results = await engine.run(_make_plan("executed"))
    # _MetricsRule.check() returns [] so results should be empty (no skip, no finding)
    assert len(results) == 0


@pytest.mark.asyncio
async def test_stats_prefetch_called_once_for_two_stats_rules() -> None:
    """fetch_table_stats is called exactly once even when two TABLE_STATS rules are registered."""

    class _StatsRule2(Rule):
        rule_id: ClassVar[str] = "TEST_STATS2"
        evidence_requirement: ClassVar[EvidenceRequirement] = EvidenceRequirement.TABLE_STATS

        def check(self, plan: Any, evidence: EvidenceBundle) -> list[RuleFinding]:
            return []

    mock_stats = AsyncMock()
    mock_stats.fetch_table_stats = AsyncMock(return_value={})

    # Build a plan with a TableScan node that has a resolvable table descriptor
    scan_node = PlanNode(
        id="scan1",
        name="TableScan",
        descriptor={"table": "iceberg:analytics.orders"},
        children=[],
    )
    root = PlanNode(id="root", name="Output", children=[scan_node])
    plan = EstimatedPlan(root=root)

    reg = RuleRegistry()
    reg.register(_StatsRule)
    reg.register(_StatsRule2)
    engine = RuleEngine(stats_source=mock_stats, catalog_source=None, registry=reg)

    await engine.run(plan)
    # Despite two TABLE_STATS rules, prefetch runs only once
    mock_stats.fetch_table_stats.assert_called_once()
