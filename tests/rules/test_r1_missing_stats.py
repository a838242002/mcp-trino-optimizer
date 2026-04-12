"""R1 MissingStats rule tests.

Three fixture classes:
1. Synthetic-minimum: hand-built PlanNode with NaN/None estimates.
2. Realistic: loaded from tests/fixtures/explain/480/full_scan.json with injected stats.
3. Negative-control: node with valid estimates and table_stats.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_trino_optimizer.parser.models import CostEstimate, EstimatedPlan, PlanNode
from mcp_trino_optimizer.parser.parser import parse_estimated_plan
from mcp_trino_optimizer.rules.evidence import EvidenceBundle
from mcp_trino_optimizer.rules.r1_missing_stats import R1MissingStats
from mcp_trino_optimizer.rules.registry import registry

FIXTURES_480 = Path(__file__).parent.parent / "fixtures" / "explain" / "480"


def _make_plan(node: PlanNode) -> EstimatedPlan:
    """Wrap a single node in a minimal EstimatedPlan."""
    return EstimatedPlan(root=node)


def _make_scan_node(
    *,
    output_row_count: float | None = None,
    name: str = "TableScan",
    node_id: str = "0",
) -> PlanNode:
    """Build a scan PlanNode with the given estimate."""
    estimates = [] if output_row_count is None else [CostEstimate(outputRowCount=output_row_count)]
    return PlanNode(id=node_id, name=name, estimates=estimates)


# ---------------------------------------------------------------------------
# Synthetic-minimum tests
# ---------------------------------------------------------------------------


class TestR1SyntheticMinimum:
    """R1 fires on NaN estimate + missing table_stats."""

    def test_nan_estimate_fires(self) -> None:
        """TableScan with NaN outputRowCount and no table_stats triggers R1."""
        node = _make_scan_node(output_row_count=float("nan"))
        plan = _make_plan(node)
        bundle = EvidenceBundle(plan=plan, table_stats=None)

        findings = R1MissingStats().check(plan, bundle)

        assert len(findings) == 1
        f = findings[0]
        assert f.rule_id == "R1"
        assert f.severity == "critical"
        assert f.confidence == pytest.approx(0.9)
        assert "0" in f.operator_ids
        assert f.evidence["estimated_row_count"] is None  # NaN converted to None by safe_float
        assert f.evidence["table_stats_row_count"] is None

    def test_none_table_stats_row_count_fires_critical(self) -> None:
        """table_stats present but row_count=None triggers R1 with confidence=0.9."""
        node = _make_scan_node(output_row_count=None)
        plan = _make_plan(node)
        bundle = EvidenceBundle(plan=plan, table_stats={"row_count": None, "columns": {}})

        findings = R1MissingStats().check(plan, bundle)

        assert len(findings) == 1
        f = findings[0]
        assert f.rule_id == "R1"
        assert f.severity == "critical"
        assert f.confidence == pytest.approx(0.9)
        assert f.evidence["table_stats_row_count"] is None

    def test_no_estimates_list_fires(self) -> None:
        """Node with empty estimates list and no table_stats triggers R1."""
        node = PlanNode(id="1", name="ScanFilter", estimates=[])
        plan = _make_plan(node)
        bundle = EvidenceBundle(plan=plan, table_stats=None)

        findings = R1MissingStats().check(plan, bundle)

        assert len(findings) == 1
        assert findings[0].rule_id == "R1"

    def test_nan_estimate_with_valid_stats_fires_lower_confidence(self) -> None:
        """NaN estimate but valid row_count in table_stats → lower confidence."""
        node = _make_scan_node(output_row_count=float("nan"))
        plan = _make_plan(node)
        # table_stats has a valid row_count but estimate is NaN
        bundle = EvidenceBundle(plan=plan, table_stats={"row_count": 50000.0})

        # Still fires because estimate is NaN (stats missing from CBO perspective)
        findings = R1MissingStats().check(plan, bundle)

        assert len(findings) == 1
        f = findings[0]
        assert f.rule_id == "R1"
        # Confidence is 0.7 because table_stats row_count is present (only estimate is bad)
        assert f.confidence == pytest.approx(0.7)

    def test_scan_filter_project_fires(self) -> None:
        """ScanFilterProject operator type also triggers R1."""
        node = PlanNode(id="2", name="ScanFilterProject", estimates=[])
        plan = _make_plan(node)
        bundle = EvidenceBundle(plan=plan, table_stats=None)

        findings = R1MissingStats().check(plan, bundle)

        assert len(findings) == 1
        assert findings[0].evidence["operator_type"] == "ScanFilterProject"


# ---------------------------------------------------------------------------
# Realistic fixture tests
# ---------------------------------------------------------------------------


class TestR1Realistic:
    """R1 fires when injecting null table_stats into a real fixture."""

    def test_full_scan_fixture_with_null_stats(self) -> None:
        """Load full_scan.json (valid estimates) and inject table_stats=None → R1 fires."""
        json_text = (FIXTURES_480 / "full_scan.json").read_text()
        plan = parse_estimated_plan(json_text)

        bundle = EvidenceBundle(plan=plan, table_stats={"row_count": None})

        rule = R1MissingStats()
        findings = rule.check(plan, bundle)

        # full_scan.json has one TableScan node
        assert len(findings) >= 1
        rule_ids = {f.rule_id for f in findings}
        assert "R1" in rule_ids
        # All findings should be critical
        for f in findings:
            assert f.severity == "critical"

    def test_full_scan_fixture_with_no_stats_source(self) -> None:
        """Load full_scan.json and pass table_stats=None → R1 fires."""
        json_text = (FIXTURES_480 / "full_scan.json").read_text()
        plan = parse_estimated_plan(json_text)

        bundle = EvidenceBundle(plan=plan, table_stats=None)

        findings = R1MissingStats().check(plan, bundle)

        # At least one scan node should fire
        assert len(findings) >= 1


# ---------------------------------------------------------------------------
# Negative-control tests
# ---------------------------------------------------------------------------


class TestR1NegativeControl:
    """R1 does NOT fire when both estimate and table_stats are valid."""

    def test_valid_estimate_and_stats_no_finding(self) -> None:
        """Valid outputRowCount and valid table_stats → R1 returns []."""
        node = _make_scan_node(output_row_count=50000.0)
        plan = _make_plan(node)
        bundle = EvidenceBundle(
            plan=plan,
            table_stats={"row_count": 50000.0, "columns": {"id": {"min": 1, "max": 50000}}},
        )

        findings = R1MissingStats().check(plan, bundle)

        assert findings == []

    def test_non_scan_node_skipped(self) -> None:
        """Aggregate node is not a scan type — R1 does not fire."""
        node = PlanNode(id="10", name="Aggregate", estimates=[])
        plan = _make_plan(node)
        bundle = EvidenceBundle(plan=plan, table_stats=None)

        findings = R1MissingStats().check(plan, bundle)

        assert findings == []

    def test_full_scan_fixture_with_valid_stats_no_finding(self) -> None:
        """full_scan.json with valid table_stats row_count → no R1 findings."""
        json_text = (FIXTURES_480 / "full_scan.json").read_text()
        plan = parse_estimated_plan(json_text)

        # Full scan has outputRowCount=20.0 in estimates; table_stats also valid
        bundle = EvidenceBundle(plan=plan, table_stats={"row_count": 20.0})

        findings = R1MissingStats().check(plan, bundle)

        assert findings == []


# ---------------------------------------------------------------------------
# Registry test
# ---------------------------------------------------------------------------


def test_r1_registered() -> None:
    """R1MissingStats is registered in the global registry after import."""
    import mcp_trino_optimizer.rules.r1_missing_stats  # noqa: F401

    ids = [r.rule_id for r in registry.all_rules()]
    assert "R1" in ids
