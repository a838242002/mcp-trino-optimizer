"""R7 CpuSkew rule tests.

Four fixture classes:
1. Synthetic-minimum: ExecutedPlan with operators having skewed cpu_time_ms.
2. Negative-control: uniform cpu times, too few nodes, EstimatedPlan.
3. Skipped on EstimatedPlan: rule is safe but engine filters by PLAN_WITH_METRICS.
4. Realistic-from-compose: parse the real join_analyze.txt fixture and inject skew.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_trino_optimizer.parser.models import EstimatedPlan, ExecutedPlan, PlanNode
from mcp_trino_optimizer.parser.parser import parse_executed_plan
from mcp_trino_optimizer.rules.evidence import EvidenceBundle
from mcp_trino_optimizer.rules.r7_cpu_skew import R7CpuSkew
from mcp_trino_optimizer.rules.thresholds import RuleThresholds

_FIXTURES = Path(__file__).parent.parent / "fixtures" / "explain" / "480"


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


# ---------------------------------------------------------------------------
# Realistic-from-compose tests
# ---------------------------------------------------------------------------


class TestR7RealisticFromCompose:
    """R7 on a real ExecutedPlan parsed from the join_analyze.txt compose fixture.

    The join_analyze.txt fixture was captured from a live Trino 480 + Iceberg
    compose stack. It has real per-node cpu_time_ms values but they are too
    close in ratio to trigger R7. We load the real plan and copy it while
    injecting a skewed cpu_time_ms onto one node to simulate a hotkey scenario.
    This validates that:
      1. parse_executed_plan produces an ExecutedPlan with cpu_time_ms populated.
      2. R7 correctly fires when the max/median ratio crosses the threshold.
      3. R7 correctly stays silent on the unmodified realistic plan.
    """

    @staticmethod
    def _load_compose_plan() -> ExecutedPlan:
        """Parse the join_analyze.txt fixture captured from the compose stack."""
        txt = (_FIXTURES / "join_analyze.txt").read_text()
        return parse_executed_plan(txt)

    def test_compose_fixture_parses_to_executed_plan(self) -> None:
        """join_analyze.txt parses to ExecutedPlan with cpu_time_ms on nodes."""
        plan = self._load_compose_plan()
        assert isinstance(plan, ExecutedPlan)
        nodes_with_cpu = [n for n in plan.walk() if n.cpu_time_ms is not None]
        assert len(nodes_with_cpu) >= 3, "fixture should have >= 3 nodes with cpu_time_ms"

    def test_unmodified_compose_plan_does_not_fire(self) -> None:
        """Unmodified fixture has balanced cpu times — R7 should not fire."""
        plan = self._load_compose_plan()
        bundle = EvidenceBundle(plan=plan)
        findings = R7CpuSkew().check(plan, bundle)
        assert findings == [], (
            "Unmodified compose fixture should not trigger R7 "
            "(cpu times are within normal variance)"
        )

    def test_compose_plan_with_injected_skew_fires(self) -> None:
        """Re-build the compose plan with one node's cpu_time_ms set to 500x the median.

        This simulates a hotkey scenario where one worker handles all the heavy rows.
        We take real parsed nodes and replace one cpu_time_ms to create detectable skew.
        """
        plan = self._load_compose_plan()
        # Gather nodes that have cpu_time_ms (real runtime data from compose)
        cpu_nodes = [n for n in plan.walk() if n.cpu_time_ms is not None and n.cpu_time_ms > 0]
        assert len(cpu_nodes) >= 3, "need >= 3 nodes with non-zero cpu to build skew scenario"

        # Build a new ExecutedPlan with a skewed node injected.
        # Use the real plan structure but override the max-cpu node with a large value.
        # The median of the realistic nodes is ~a few ms; inject 10000ms to force ratio > 5x.
        skewed_nodes = []
        for i, n in enumerate(cpu_nodes):
            new_cpu = 10_000.0 if i == 0 else n.cpu_time_ms
            skewed_nodes.append(
                PlanNode(
                    id=n.id,
                    name=n.name,
                    cpu_time_ms=new_cpu,
                )
            )

        # Build a flat ExecutedPlan from the skewed node list (chain structure)
        leaf = skewed_nodes[-1]
        for node in reversed(skewed_nodes[:-1]):
            leaf = PlanNode(
                id=node.id,
                name=node.name,
                cpu_time_ms=node.cpu_time_ms,
                children=[leaf],
            )
        skewed_plan = ExecutedPlan(root=leaf)
        bundle = EvidenceBundle(plan=skewed_plan)

        findings = R7CpuSkew().check(skewed_plan, bundle)

        assert len(findings) == 1
        f = findings[0]
        assert f.rule_id == "R7"
        assert f.evidence["max_cpu_ms"] == pytest.approx(10_000.0)
        assert f.evidence["skew_ratio"] > 5.0
