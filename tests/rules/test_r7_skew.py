"""R7 CpuSkew rule tests.

Three fixture classes:
1. Synthetic-minimum: ExecutedPlan with operators having skewed cpu_time_ms.
2. Negative-control: uniform cpu times, too few nodes, EstimatedPlan.
3. Skipped on EstimatedPlan: rule is safe but engine filters by PLAN_WITH_METRICS.
"""

from __future__ import annotations

import pytest

from mcp_trino_optimizer.parser.models import EstimatedPlan, ExecutedPlan, PlanNode
from mcp_trino_optimizer.rules.evidence import EvidenceBundle
from mcp_trino_optimizer.rules.r7_cpu_skew import R7CpuSkew
from mcp_trino_optimizer.rules.thresholds import RuleThresholds


def _make_executed_plan(*cpu_times: float | None) -> ExecutedPlan:
    """Build an ExecutedPlan where each node gets one cpu_time_ms value.

    Creates a chain from tail to root: root -> child1 -> ... -> last leaf.
    Build from the last node backwards so each parent correctly wraps its child.
    """
    # Start with the last (leaf) node
    n = len(cpu_times)
    current: PlanNode = PlanNode(id=str(n - 1), name="TableScan", cpu_time_ms=cpu_times[n - 1])
    # Wrap backwards toward the root
    for i in range(n - 2, -1, -1):
        current = PlanNode(
            id=str(i),
            name="TableScan",
            cpu_time_ms=cpu_times[i],
            children=[current],
        )
    return ExecutedPlan(root=current)


# ---------------------------------------------------------------------------
# Synthetic-minimum tests
# ---------------------------------------------------------------------------


class TestR7SyntheticMinimum:
    """R7 fires when max/median CPU ratio exceeds skew_ratio threshold."""

    def test_at_threshold_fires(self) -> None:
        """5 nodes with cpu_times [100,100,100,100,500]: max=500, median=100, ratio=5.0.

        At the threshold (>=5.0 with default 5.0) — fires.
        """
        plan = _make_executed_plan(100.0, 100.0, 100.0, 100.0, 500.0)
        bundle = EvidenceBundle(plan=plan)

        findings = R7CpuSkew().check(plan, bundle)

        assert len(findings) == 1
        f = findings[0]
        assert f.rule_id == "R7"
        assert f.severity == "high"
        assert f.confidence == pytest.approx(0.8)
        assert f.evidence["max_cpu_ms"] == pytest.approx(500.0)
        assert f.evidence["median_cpu_ms"] == pytest.approx(100.0)
        assert f.evidence["skew_ratio"] == pytest.approx(5.0)
        assert f.evidence["threshold"] == pytest.approx(5.0)
        assert f.evidence["node_count"] == 5

    def test_above_threshold_fires(self) -> None:
        """Ratio 5.1 (510/100) > 5.0 threshold — fires."""
        plan = _make_executed_plan(100.0, 100.0, 100.0, 100.0, 510.0)
        bundle = EvidenceBundle(plan=plan)

        findings = R7CpuSkew().check(plan, bundle)

        assert len(findings) == 1
        assert findings[0].evidence["skew_ratio"] == pytest.approx(510.0 / 100.0)

    def test_below_threshold_does_not_fire(self) -> None:
        """Ratio 4.9 (490/100) < 5.0 threshold — does not fire."""
        plan = _make_executed_plan(100.0, 100.0, 100.0, 100.0, 490.0)
        bundle = EvidenceBundle(plan=plan)

        findings = R7CpuSkew().check(plan, bundle)

        assert findings == []

    def test_custom_threshold_respected(self) -> None:
        """Custom skew_ratio=10.0 means ratio=5.0 does not fire."""
        thresholds = RuleThresholds(skew_ratio=10.0)
        plan = _make_executed_plan(100.0, 100.0, 100.0, 100.0, 500.0)
        bundle = EvidenceBundle(plan=plan)

        findings = R7CpuSkew(thresholds=thresholds).check(plan, bundle)

        assert findings == []

    def test_operator_id_is_max_node(self) -> None:
        """operator_ids contains the id of the node with max cpu_time_ms."""
        # Node id "4" has cpu_time_ms=500 (the highest)
        plan = _make_executed_plan(100.0, 100.0, 100.0, 100.0, 500.0)
        bundle = EvidenceBundle(plan=plan)

        findings = R7CpuSkew().check(plan, bundle)

        assert len(findings) == 1
        # The max node is the last in the chain — id "4"
        assert "4" in findings[0].operator_ids


# ---------------------------------------------------------------------------
# Negative-control tests
# ---------------------------------------------------------------------------


class TestR7NegativeControl:
    """R7 should NOT fire in these scenarios."""

    def test_uniform_cpu_does_not_fire(self) -> None:
        """All operators have cpu_time_ms=100 — ratio is 1.0, no skew."""
        plan = _make_executed_plan(100.0, 100.0, 100.0, 100.0, 100.0)
        bundle = EvidenceBundle(plan=plan)

        findings = R7CpuSkew().check(plan, bundle)

        assert findings == []

    def test_fewer_than_3_nodes_returns_empty(self) -> None:
        """Only 2 nodes with cpu_time_ms — insufficient data, returns []."""
        plan = _make_executed_plan(100.0, 500.0)
        bundle = EvidenceBundle(plan=plan)

        findings = R7CpuSkew().check(plan, bundle)

        assert findings == []

    def test_median_zero_does_not_crash(self) -> None:
        """All nodes have cpu_time_ms=0.0 — median=0.0, no division by zero."""
        plan = _make_executed_plan(0.0, 0.0, 0.0, 0.0, 0.0)
        bundle = EvidenceBundle(plan=plan)

        findings = R7CpuSkew().check(plan, bundle)

        assert findings == []

    def test_none_cpu_times_skipped(self) -> None:
        """Nodes with cpu_time_ms=None are excluded; if < 3 remain, returns []."""
        plan = _make_executed_plan(None, None, 100.0, 500.0, None)
        bundle = EvidenceBundle(plan=plan)

        # Only 2 nodes have non-None cpu_time_ms — insufficient
        findings = R7CpuSkew().check(plan, bundle)

        assert findings == []

    def test_estimated_plan_returns_empty(self) -> None:
        """R7 is safe on EstimatedPlan — returns [] (engine skips via PLAN_WITH_METRICS)."""
        # Build an EstimatedPlan (no cpu_time_ms values)
        node = PlanNode(id="0", name="TableScan")
        plan = EstimatedPlan(root=node)
        bundle = EvidenceBundle(plan=plan)

        findings = R7CpuSkew().check(plan, bundle)

        assert findings == []
