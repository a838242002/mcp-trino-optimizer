"""R2 PartitionPruning rule tests.

Three fixture classes:
1. Synthetic-minimum: hand-built PlanNode with filterPredicate but no constraint.
2. Realistic: loaded from tests/fixtures/explain/480/ fixtures.
3. Negative-control: node with constraint applied, or no filterPredicate.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_trino_optimizer.parser.models import CostEstimate, EstimatedPlan, PlanNode
from mcp_trino_optimizer.parser.parser import parse_estimated_plan
from mcp_trino_optimizer.rules.evidence import EvidenceBundle
from mcp_trino_optimizer.rules.r2_partition_pruning import R2PartitionPruning
from mcp_trino_optimizer.rules.registry import registry

FIXTURES_480 = Path(__file__).parent.parent / "fixtures" / "explain" / "480"


def _make_plan(node: PlanNode) -> EstimatedPlan:
    """Wrap a single node in a minimal EstimatedPlan."""
    return EstimatedPlan(root=node)


def _make_scan_node(
    *,
    table: str = "iceberg:schema.orders$data@123",
    filter_predicate: str = "(ts > DATE '2025-01-01')",
    name: str = "ScanFilter",
    node_id: str = "1",
) -> PlanNode:
    """Build a scan node with the given descriptor."""
    descriptor: dict[str, str] = {"table": table}
    if filter_predicate:
        descriptor["filterPredicate"] = filter_predicate
    return PlanNode(
        id=node_id,
        name=name,
        descriptor=descriptor,
        estimates=[CostEstimate(outputRowCount=100.0)],
    )


# ---------------------------------------------------------------------------
# Synthetic-minimum tests
# ---------------------------------------------------------------------------


class TestR2SyntheticMinimum:
    """R2 fires when Iceberg scan has filter but no partition constraint."""

    def test_filter_without_constraint_fires(self) -> None:
        """ScanFilter with filterPredicate but no 'constraint on [' → R2 fires."""
        node = _make_scan_node(
            table="iceberg:schema.orders$data@123",
            filter_predicate="(ts > DATE '2025-01-01')",
        )
        plan = _make_plan(node)
        bundle = EvidenceBundle(plan=plan)

        findings = R2PartitionPruning().check(plan, bundle)

        assert len(findings) == 1
        f = findings[0]
        assert f.rule_id == "R2"
        assert f.severity == "high"
        assert f.confidence == pytest.approx(0.8)
        assert "1" in f.operator_ids
        assert f.evidence["has_partition_constraint"] is False
        assert "(ts > DATE '2025-01-01')" in f.evidence["filter_predicate"]

    def test_table_scan_with_filter_fires(self) -> None:
        """TableScan with filterPredicate also triggers R2."""
        node = PlanNode(
            id="5",
            name="TableScan",
            descriptor={
                "table": "iceberg:catalog.db.events$data@999",
                "filterPredicate": "(event_date = DATE '2025-06-01')",
            },
        )
        plan = _make_plan(node)
        bundle = EvidenceBundle(plan=plan)

        findings = R2PartitionPruning().check(plan, bundle)

        assert len(findings) == 1
        assert findings[0].rule_id == "R2"

    def test_scan_filter_project_with_filter_fires(self) -> None:
        """ScanFilterProject with filterPredicate and no constraint fires."""
        node = PlanNode(
            id="6",
            name="ScanFilterProject",
            descriptor={
                "table": "iceberg:schema.sales$data@456",
                "filterPredicate": "(year(created_at) = 2025)",
            },
        )
        plan = _make_plan(node)
        bundle = EvidenceBundle(plan=plan)

        findings = R2PartitionPruning().check(plan, bundle)

        assert len(findings) == 1
        assert findings[0].rule_id == "R2"


# ---------------------------------------------------------------------------
# Realistic fixture tests
# ---------------------------------------------------------------------------


class TestR2Realistic:
    """R2 fires on real fixture scans without partition constraint."""

    def test_full_scan_no_filter_no_finding(self) -> None:
        """full_scan.json has a TableScan with no filterPredicate → R2 does not fire."""
        json_text = (FIXTURES_480 / "full_scan.json").read_text()
        plan = parse_estimated_plan(json_text)
        bundle = EvidenceBundle(plan=plan)

        findings = R2PartitionPruning().check(plan, bundle)

        # The TableScan in full_scan.json has no filterPredicate
        assert findings == []

    def test_synthetic_iceberg_scan_with_filter_fires(self) -> None:
        """Iceberg ScanFilterProject with filterPredicate and no constraint → R2 fires.

        This serves as the 'realistic' case: uses the same table format as the
        test fixtures (iceberg: prefix, Iceberg table snapshot ID format).
        """
        node = PlanNode(
            id="189",
            name="ScanFilterProject",
            descriptor={
                "table": "iceberg:test_fixtures.orders$data@7192078785404198795",
                "filterPredicate": "(amount > decimal(10,2) '100.00')",
            },
            estimates=[CostEstimate(outputRowCount=16.0)],
        )
        plan = _make_plan(node)
        bundle = EvidenceBundle(plan=plan)

        findings = R2PartitionPruning().check(plan, bundle)

        # ScanFilterProject has filterPredicate and no "constraint on [" → R2 fires
        assert len(findings) == 1
        f = findings[0]
        assert f.rule_id == "R2"
        assert "amount > decimal" in f.evidence["filter_predicate"]


# ---------------------------------------------------------------------------
# Negative-control tests
# ---------------------------------------------------------------------------


class TestR2NegativeControl:
    """R2 does NOT fire when constraint is present or no filter exists."""

    def test_constraint_applied_no_finding(self) -> None:
        """Table descriptor contains 'constraint on [' → R2 does not fire."""
        node = _make_scan_node(
            table="iceberg:schema.orders$data@123 constraint on [ts]",
            filter_predicate="(ts > DATE '2025-01-01')",
        )
        plan = _make_plan(node)
        bundle = EvidenceBundle(plan=plan)

        findings = R2PartitionPruning().check(plan, bundle)

        assert findings == []

    def test_no_filter_predicate_no_finding(self) -> None:
        """Scan with no filterPredicate → no missed pruning opportunity → R2 silent."""
        node = PlanNode(
            id="3",
            name="TableScan",
            descriptor={"table": "iceberg:schema.orders$data@123"},
        )
        plan = _make_plan(node)
        bundle = EvidenceBundle(plan=plan)

        findings = R2PartitionPruning().check(plan, bundle)

        assert findings == []

    def test_empty_filter_predicate_no_finding(self) -> None:
        """Empty string filterPredicate → treated as no predicate → R2 silent."""
        node = PlanNode(
            id="4",
            name="ScanFilter",
            descriptor={
                "table": "iceberg:schema.orders$data@123",
                "filterPredicate": "",
            },
        )
        plan = _make_plan(node)
        bundle = EvidenceBundle(plan=plan)

        findings = R2PartitionPruning().check(plan, bundle)

        assert findings == []

    def test_non_iceberg_table_no_finding(self) -> None:
        """Non-Iceberg table (e.g. hive:) with filter → R2 does not fire."""
        node = PlanNode(
            id="7",
            name="ScanFilter",
            descriptor={
                "table": "hive:schema.orders$data@123",
                "filterPredicate": "(ts > DATE '2025-01-01')",
            },
        )
        plan = _make_plan(node)
        bundle = EvidenceBundle(plan=plan)

        findings = R2PartitionPruning().check(plan, bundle)

        assert findings == []

    def test_iceberg_partition_filter_fixture_no_finding(self) -> None:
        """iceberg_partition_filter.json has 'constraint on [ts]' → R2 does not fire."""
        json_text = (FIXTURES_480 / "iceberg_partition_filter.json").read_text()
        plan = parse_estimated_plan(json_text)
        bundle = EvidenceBundle(plan=plan)

        findings = R2PartitionPruning().check(plan, bundle)

        assert findings == []


# ---------------------------------------------------------------------------
# Registry test
# ---------------------------------------------------------------------------


def test_r2_registered() -> None:
    """R2PartitionPruning is registered in the global registry after import."""
    import mcp_trino_optimizer.rules.r2_partition_pruning  # noqa: F401

    ids = [r.rule_id for r in registry.all_rules()]
    assert "R2" in ids
