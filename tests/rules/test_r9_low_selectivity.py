"""R9 LowSelectivity rule tests.

Three fixture classes:
1. Synthetic-minimum: scan nodes with actual input_bytes/output_bytes (ExecutedPlan fields).
2. Realistic: full_scan.json loaded as EstimatedPlan — no actual bytes, R9 skips silently.
3. Negative-control: high selectivity, None bytes, no scan nodes.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_trino_optimizer.parser.models import CostEstimate, EstimatedPlan, ExecutedPlan, PlanNode
from mcp_trino_optimizer.parser.parser import parse_estimated_plan
from mcp_trino_optimizer.rules.evidence import EvidenceBundle
from mcp_trino_optimizer.rules.r9_low_selectivity import R9LowSelectivity
from mcp_trino_optimizer.rules.thresholds import RuleThresholds

FIXTURES_480 = Path(__file__).parent.parent / "fixtures" / "explain" / "480"

_1MB = 1_000_000
_50KB = 50_000


def _make_scan_executed(
    *,
    input_bytes: int | None,
    output_bytes: int | None,
    name: str = "TableScan",
    node_id: str = "0",
    table: str = "iceberg:test.orders",
) -> ExecutedPlan:
    """Build a minimal ExecutedPlan with a single scan node having actual byte metrics."""
    node = PlanNode(
        id=node_id,
        name=name,
        descriptor={"table": table},
        input_bytes=input_bytes,
        output_bytes=output_bytes,
    )
    return ExecutedPlan(root=node)


# ---------------------------------------------------------------------------
# Synthetic-minimum tests
# ---------------------------------------------------------------------------


class TestR9SyntheticMinimum:
    """R9 fires when output_bytes/input_bytes < scan_selectivity_threshold (0.10)."""

    def test_low_selectivity_fires(self) -> None:
        """output=50KB, input=1MB -> selectivity=0.05 < 0.10 threshold -> R9 fires."""
        plan = _make_scan_executed(input_bytes=_1MB, output_bytes=_50KB)
        bundle = EvidenceBundle(plan=plan)

        findings = R9LowSelectivity().check(plan, bundle)

        assert len(findings) == 1
        f = findings[0]
        assert f.rule_id == "R9"
        assert f.severity == "medium"
        assert f.confidence == pytest.approx(0.9)
        assert f.evidence["input_bytes"] == _1MB
        assert f.evidence["output_bytes"] == _50KB
        assert f.evidence["selectivity_ratio"] == pytest.approx(0.05)
        assert f.evidence["threshold"] == pytest.approx(0.10)
        assert "0" in f.operator_ids

    def test_scan_filter_also_detected(self) -> None:
        """ScanFilter node with low selectivity also fires R9."""
        node = PlanNode(
            id="1",
            name="ScanFilter",
            descriptor={"table": "iceberg:test.orders"},
            input_bytes=_1MB,
            output_bytes=_50KB,
        )
        plan = ExecutedPlan(root=node)
        bundle = EvidenceBundle(plan=plan)

        findings = R9LowSelectivity().check(plan, bundle)

        assert len(findings) == 1
        assert findings[0].rule_id == "R9"

    def test_scan_filter_project_also_detected(self) -> None:
        """ScanFilterProject node with low selectivity fires R9."""
        node = PlanNode(
            id="2",
            name="ScanFilterProject",
            descriptor={"table": "iceberg:test.orders"},
            input_bytes=_1MB,
            output_bytes=_50KB,
        )
        plan = ExecutedPlan(root=node)
        bundle = EvidenceBundle(plan=plan)

        findings = R9LowSelectivity().check(plan, bundle)

        assert len(findings) == 1

    def test_custom_threshold_respected(self) -> None:
        """Custom threshold=0.03 means selectivity=0.05 does NOT fire."""
        thresholds = RuleThresholds(scan_selectivity_threshold=0.03)
        plan = _make_scan_executed(input_bytes=_1MB, output_bytes=_50KB)
        bundle = EvidenceBundle(plan=plan)

        findings = R9LowSelectivity(thresholds=thresholds).check(plan, bundle)

        assert findings == []


# ---------------------------------------------------------------------------
# Negative-control tests
# ---------------------------------------------------------------------------


class TestR9NegativeControl:
    """R9 should NOT fire in these scenarios."""

    def test_high_selectivity_does_not_fire(self) -> None:
        """output=200KB, input=1MB -> selectivity=0.20 > 0.10 threshold -> no fire."""
        plan = _make_scan_executed(input_bytes=_1MB, output_bytes=200_000)
        bundle = EvidenceBundle(plan=plan)

        findings = R9LowSelectivity().check(plan, bundle)

        assert findings == []

    def test_none_input_bytes_skips(self) -> None:
        """input_bytes=None (no metrics) — R9 skips silently."""
        plan = _make_scan_executed(input_bytes=None, output_bytes=_50KB)
        bundle = EvidenceBundle(plan=plan)

        findings = R9LowSelectivity().check(plan, bundle)

        assert findings == []

    def test_none_output_bytes_skips(self) -> None:
        """output_bytes=None (no metrics) — R9 skips silently."""
        plan = _make_scan_executed(input_bytes=_1MB, output_bytes=None)
        bundle = EvidenceBundle(plan=plan)

        findings = R9LowSelectivity().check(plan, bundle)

        assert findings == []

    def test_zero_input_bytes_skips(self) -> None:
        """input_bytes=0 — avoid division by zero, return []."""
        plan = _make_scan_executed(input_bytes=0, output_bytes=0)
        bundle = EvidenceBundle(plan=plan)

        findings = R9LowSelectivity().check(plan, bundle)

        assert findings == []

    def test_non_scan_nodes_ignored(self) -> None:
        """InnerJoin node — R9 only checks scan types."""
        node = PlanNode(
            id="0",
            name="InnerJoin",
            input_bytes=_1MB,
            output_bytes=_50KB,
        )
        plan = ExecutedPlan(root=node)
        bundle = EvidenceBundle(plan=plan)

        findings = R9LowSelectivity().check(plan, bundle)

        assert findings == []


# ---------------------------------------------------------------------------
# Realistic fixture tests
# ---------------------------------------------------------------------------


class TestR9Realistic:
    """R9 against real fixtures."""

    def test_estimated_plan_no_actual_bytes_skips(self) -> None:
        """full_scan.json is an EstimatedPlan — no input_bytes/output_bytes populated.

        R9 uses PLAN_ONLY evidence but reads actual bytes fields which are only
        present on ExecutedPlan nodes. EstimatedPlan nodes have None -> skips silently.
        """
        json_text = (FIXTURES_480 / "full_scan.json").read_text()
        plan = parse_estimated_plan(json_text)

        bundle = EvidenceBundle(plan=plan)
        findings = R9LowSelectivity().check(plan, bundle)

        # EstimatedPlan has no actual bytes — R9 silently skips all nodes
        assert findings == []
