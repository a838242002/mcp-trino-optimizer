"""D11 CostVsActual rule tests.

Three fixture classes:
1. Synthetic-minimum: ExecutedPlan scan nodes with large CBO vs actual row divergence.
2. Negative-control: within threshold, NaN estimate, no estimates, EstimatedPlan.
3. Directional: both over-estimate and under-estimate directions.
"""

from __future__ import annotations

import math

import pytest

from mcp_trino_optimizer.parser.models import CostEstimate, EstimatedPlan, ExecutedPlan, PlanNode
from mcp_trino_optimizer.rules.evidence import EvidenceBundle
from mcp_trino_optimizer.rules.d11_cost_vs_actual import D11CostVsActual
from mcp_trino_optimizer.rules.thresholds import RuleThresholds


def _make_executed_scan(
    *,
    estimated_rows: float | None,
    actual_rows: int | None,
    node_id: str = "0",
    name: str = "TableScan",
) -> ExecutedPlan:
    """Build a minimal ExecutedPlan with a single scan node."""
    estimates: list[CostEstimate] = []
    if estimated_rows is not None:
        estimates = [CostEstimate(outputRowCount=estimated_rows)]
    node = PlanNode(
        id=node_id,
        name=name,
        estimates=estimates,
        output_rows=actual_rows,
    )
    return ExecutedPlan(root=node)


# ---------------------------------------------------------------------------
# Synthetic-minimum tests
# ---------------------------------------------------------------------------


class TestD11SyntheticMinimum:
    """D11 fires when |estimated - actual| / actual > stats_divergence_factor (5x)."""

    def test_under_estimate_fires(self) -> None:
        """CBO estimated 1000 rows, actual 10000 rows -> ratio 10x > 5x threshold."""
        plan = _make_executed_scan(estimated_rows=1000.0, actual_rows=10_000)
        bundle = EvidenceBundle(plan=plan)

        findings = D11CostVsActual().check(plan, bundle)

        assert len(findings) == 1
        f = findings[0]
        assert f.rule_id == "D11"
        assert f.severity == "high"
        assert f.confidence == pytest.approx(0.95)
        assert f.evidence["estimated_rows"] == pytest.approx(1000.0)
        assert f.evidence["actual_rows"] == 10_000
        assert f.evidence["divergence_factor"] == pytest.approx(10.0)
        assert f.evidence["threshold"] == pytest.approx(5.0)
        assert "0" in f.operator_ids

    def test_over_estimate_fires(self) -> None:
        """CBO estimated 10000 rows, actual 100 rows -> inverse ratio 100x > 5x."""
        plan = _make_executed_scan(estimated_rows=10_000.0, actual_rows=100)
        bundle = EvidenceBundle(plan=plan)

        findings = D11CostVsActual().check(plan, bundle)

        assert len(findings) == 1
        f = findings[0]
        assert f.rule_id == "D11"
        # divergence = 10000/100 = 100x (estimated >> actual)
        assert f.evidence["divergence_factor"] == pytest.approx(100.0)

    def test_scan_filter_detected(self) -> None:
        """ScanFilter with divergence also fires D11."""
        plan = _make_executed_scan(
            estimated_rows=1000.0,
            actual_rows=10_000,
            name="ScanFilter",
        )
        bundle = EvidenceBundle(plan=plan)

        findings = D11CostVsActual().check(plan, bundle)

        assert len(findings) == 1
        assert findings[0].rule_id == "D11"

    def test_scan_filter_project_detected(self) -> None:
        """ScanFilterProject with divergence also fires D11."""
        plan = _make_executed_scan(
            estimated_rows=1000.0,
            actual_rows=10_000,
            name="ScanFilterProject",
        )
        bundle = EvidenceBundle(plan=plan)

        findings = D11CostVsActual().check(plan, bundle)

        assert len(findings) == 1

    def test_custom_threshold_respected(self) -> None:
        """stats_divergence_factor=20.0 means 10x ratio does not fire."""
        thresholds = RuleThresholds(stats_divergence_factor=20.0)
        plan = _make_executed_scan(estimated_rows=1000.0, actual_rows=10_000)
        bundle = EvidenceBundle(plan=plan)

        findings = D11CostVsActual(thresholds=thresholds).check(plan, bundle)

        assert findings == []


# ---------------------------------------------------------------------------
# Negative-control tests
# ---------------------------------------------------------------------------


class TestD11NegativeControl:
    """D11 should NOT fire in these scenarios."""

    def test_within_threshold_does_not_fire(self) -> None:
        """estimated=1000, actual=1200 -> ratio=1.2 < 5.0 threshold."""
        plan = _make_executed_scan(estimated_rows=1000.0, actual_rows=1200)
        bundle = EvidenceBundle(plan=plan)

        findings = D11CostVsActual().check(plan, bundle)

        assert findings == []

    def test_nan_estimate_skips(self) -> None:
        """NaN outputRowCount -> safe_float returns None -> D11 skips."""
        plan = _make_executed_scan(
            estimated_rows=float("nan"),
            actual_rows=10_000,
        )
        bundle = EvidenceBundle(plan=plan)

        findings = D11CostVsActual().check(plan, bundle)

        assert findings == []

    def test_none_estimate_skips(self) -> None:
        """No estimates list -> D11 skips."""
        plan = _make_executed_scan(estimated_rows=None, actual_rows=10_000)
        bundle = EvidenceBundle(plan=plan)

        findings = D11CostVsActual().check(plan, bundle)

        assert findings == []

    def test_none_actual_rows_skips(self) -> None:
        """output_rows=None (no runtime metric) -> D11 skips."""
        plan = _make_executed_scan(estimated_rows=1000.0, actual_rows=None)
        bundle = EvidenceBundle(plan=plan)

        findings = D11CostVsActual().check(plan, bundle)

        assert findings == []

    def test_zero_actual_rows_skips(self) -> None:
        """actual_rows=0 -> division by zero guard -> D11 skips."""
        plan = _make_executed_scan(estimated_rows=1000.0, actual_rows=0)
        bundle = EvidenceBundle(plan=plan)

        findings = D11CostVsActual().check(plan, bundle)

        assert findings == []

    def test_non_scan_node_ignored(self) -> None:
        """InnerJoin node is not a scan type — D11 ignores it."""
        node = PlanNode(
            id="0",
            name="InnerJoin",
            estimates=[CostEstimate(outputRowCount=1000.0)],
            output_rows=10_000,
        )
        plan = ExecutedPlan(root=node)
        bundle = EvidenceBundle(plan=plan)

        findings = D11CostVsActual().check(plan, bundle)

        assert findings == []

    def test_estimated_plan_returns_empty(self) -> None:
        """D11 is safe on EstimatedPlan — no output_rows, returns []."""
        node = PlanNode(
            id="0",
            name="TableScan",
            estimates=[CostEstimate(outputRowCount=1000.0)],
            # output_rows is None on EstimatedPlan
        )
        plan = EstimatedPlan(root=node)
        bundle = EvidenceBundle(plan=plan)

        findings = D11CostVsActual().check(plan, bundle)

        assert findings == []
