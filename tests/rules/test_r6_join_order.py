"""R6 JoinOrderInversion rule tests.

Three fixture classes:
1. Synthetic-minimum: InnerJoin with large probe/build row-count ratio.
2. Realistic: join.json fixture (probe > build by realistic margin).
3. Negative-control: balanced ratio, stats present, no join nodes.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_trino_optimizer.parser.models import CostEstimate, EstimatedPlan, PlanNode
from mcp_trino_optimizer.parser.parser import parse_estimated_plan
from mcp_trino_optimizer.rules.evidence import EvidenceBundle
from mcp_trino_optimizer.rules.r6_join_order import R6JoinOrderInversion

FIXTURES_480 = Path(__file__).parent.parent / "fixtures" / "explain" / "480"


def _make_plan(node: PlanNode) -> EstimatedPlan:
    return EstimatedPlan(root=node)


def _make_join_node(
    *,
    probe_rows: float | None,
    build_rows: float | None,
    join_name: str = "InnerJoin",
    join_id: str = "1",
    probe_id: str = "2",
    build_id: str = "3",
) -> PlanNode:
    """Build an InnerJoin with the given probe/build row estimates."""
    probe_estimates: list[CostEstimate] = []
    if probe_rows is not None:
        probe_estimates = [CostEstimate(outputRowCount=probe_rows)]

    build_estimates: list[CostEstimate] = []
    if build_rows is not None:
        build_estimates = [CostEstimate(outputRowCount=build_rows)]

    probe = PlanNode(id=probe_id, name="ScanFilter", estimates=probe_estimates)
    build = PlanNode(id=build_id, name="TableScan", estimates=build_estimates)
    return PlanNode(
        id=join_id,
        name=join_name,
        descriptor={"distribution": "PARTITIONED"},
        children=[probe, build],
    )


# ---------------------------------------------------------------------------
# Synthetic-minimum tests
# ---------------------------------------------------------------------------


class TestR6SyntheticMinimum:
    """R6 fires when probe is much larger than build (>100x ratio) with no stats."""

    def test_large_probe_no_stats_fires(self) -> None:
        """Probe 1M rows, build 1K rows (1000x ratio), no table_stats -> R6 fires."""
        join = _make_join_node(probe_rows=1_000_000.0, build_rows=1_000.0)
        plan = _make_plan(join)
        bundle = EvidenceBundle(plan=plan, table_stats=None)

        findings = R6JoinOrderInversion().check(plan, bundle)

        assert len(findings) == 1
        f = findings[0]
        assert f.rule_id == "R6"
        assert f.severity == "medium"
        assert f.confidence == pytest.approx(0.6)
        assert "1" in f.operator_ids
        assert f.evidence["probe_estimated_rows"] == pytest.approx(1_000_000.0)
        assert f.evidence["build_estimated_rows"] == pytest.approx(1_000.0)
        assert f.evidence["probe_to_build_ratio"] == pytest.approx(1000.0)
        assert f.evidence["stats_available"] is False

    def test_exactly_100x_ratio_does_not_fire(self) -> None:
        """Exactly 100x probe-to-build ratio does NOT fire (threshold is > 100)."""
        join = _make_join_node(probe_rows=100_000.0, build_rows=1_000.0)
        plan = _make_plan(join)
        bundle = EvidenceBundle(plan=plan, table_stats=None)

        findings = R6JoinOrderInversion().check(plan, bundle)
        assert findings == []

    def test_just_over_100x_fires(self) -> None:
        """100_001 / 1_000 > 100x -> fires."""
        join = _make_join_node(probe_rows=100_001.0, build_rows=1_000.0)
        plan = _make_plan(join)
        bundle = EvidenceBundle(plan=plan, table_stats=None)

        findings = R6JoinOrderInversion().check(plan, bundle)
        assert len(findings) == 1

    def test_semi_join_also_detected(self) -> None:
        """SemiJoin with large probe/build ratio fires R6."""
        join = _make_join_node(
            probe_rows=1_000_000.0,
            build_rows=1_000.0,
            join_name="SemiJoin",
        )
        plan = _make_plan(join)
        bundle = EvidenceBundle(plan=plan, table_stats=None)

        findings = R6JoinOrderInversion().check(plan, bundle)
        assert len(findings) == 1
        assert findings[0].rule_id == "R6"


# ---------------------------------------------------------------------------
# Negative-control tests
# ---------------------------------------------------------------------------


class TestR6NegativeControl:
    """R6 should NOT fire in these scenarios."""

    def test_balanced_ratio_does_not_fire(self) -> None:
        """Probe 1M rows, build 500K rows (2x ratio) — well below threshold."""
        join = _make_join_node(probe_rows=1_000_000.0, build_rows=500_000.0)
        plan = _make_plan(join)
        bundle = EvidenceBundle(plan=plan, table_stats=None)

        findings = R6JoinOrderInversion().check(plan, bundle)

        assert findings == []

    def test_stats_present_suppresses_r6(self) -> None:
        """Even with large probe/build ratio, table_stats with row_count suppresses R6.

        CBO may have a valid reason for this order if stats are available.
        """
        join = _make_join_node(probe_rows=1_000_000.0, build_rows=1_000.0)
        plan = _make_plan(join)
        bundle = EvidenceBundle(
            plan=plan,
            table_stats={"row_count": 1_000_000, "columns": {}},
        )

        findings = R6JoinOrderInversion().check(plan, bundle)

        assert findings == []

    def test_missing_probe_estimate_skips(self) -> None:
        """If probe estimate is missing (None), R6 cannot determine ratio -> returns []."""
        join = _make_join_node(probe_rows=None, build_rows=1_000.0)
        plan = _make_plan(join)
        bundle = EvidenceBundle(plan=plan, table_stats=None)

        findings = R6JoinOrderInversion().check(plan, bundle)

        assert findings == []

    def test_missing_build_estimate_skips(self) -> None:
        """If build estimate is missing (None), R6 cannot determine ratio -> returns []."""
        join = _make_join_node(probe_rows=1_000_000.0, build_rows=None)
        plan = _make_plan(join)
        bundle = EvidenceBundle(plan=plan, table_stats=None)

        findings = R6JoinOrderInversion().check(plan, bundle)

        assert findings == []

    def test_no_join_nodes_returns_empty(self) -> None:
        """Plan with only a scan node — R6 returns []."""
        scan = PlanNode(
            id="0",
            name="TableScan",
            estimates=[CostEstimate(outputRowCount=1_000_000.0)],
        )
        plan = _make_plan(scan)
        bundle = EvidenceBundle(plan=plan, table_stats=None)

        findings = R6JoinOrderInversion().check(plan, bundle)

        assert findings == []

    def test_single_child_join_does_not_crash(self) -> None:
        """Malformed join with only one child must not raise (T-04-13 guard)."""
        join = PlanNode(
            id="1",
            name="InnerJoin",
            descriptor={"distribution": "PARTITIONED"},
            children=[
                PlanNode(
                    id="2",
                    name="TableScan",
                    estimates=[CostEstimate(outputRowCount=1_000_000.0)],
                )
            ],
        )
        plan = _make_plan(join)
        bundle = EvidenceBundle(plan=plan, table_stats=None)

        findings = R6JoinOrderInversion().check(plan, bundle)
        assert findings == []


# ---------------------------------------------------------------------------
# Realistic fixture tests
# ---------------------------------------------------------------------------


class TestR6Realistic:
    """R6 against the join.json fixture."""

    def test_fixture_join_balanced_estimates(self) -> None:
        """join.json probe has 20 rows, build (via LocalExchange) has ~16 rows.

        Ratio is ~1.25x, well below the 100x threshold — R6 should NOT fire.
        """
        json_text = (FIXTURES_480 / "join.json").read_text()
        plan = parse_estimated_plan(json_text)

        bundle = EvidenceBundle(plan=plan, table_stats=None)
        findings = R6JoinOrderInversion().check(plan, bundle)

        # Both sides are tiny (20 and 16 rows) — ratio is ~1.25x, no inversion
        assert findings == []
