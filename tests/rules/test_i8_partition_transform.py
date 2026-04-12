"""I8 PartitionTransform rule tests.

Three fixture classes:
  1. Synthetic-minimum: plan node with sub-day constraint boundary — fires
  2. Realistic: loads actual iceberg_partition_filter fixture
  3. Negative-control: aligned boundary / no constraint — does NOT fire

I8 uses evidence_requirement=ICEBERG_METADATA so the engine emits RuleSkipped
when catalog_source=None. However the rule itself fires on plan data alone;
the ICEBERG_METADATA requirement is a soft coupling for offline-mode skipping.
"""

from __future__ import annotations

from mcp_trino_optimizer.parser.models import EstimatedPlan, PlanNode
from mcp_trino_optimizer.rules.evidence import EvidenceBundle
from mcp_trino_optimizer.rules.i8_partition_transform import I8PartitionTransform

# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_scan_node(
    node_id: str = "1",
    table_descriptor: str = "iceberg:analytics.events",
    details: list[str] | None = None,
) -> PlanNode:
    return PlanNode(
        id=node_id,
        name="TableScan",
        descriptor={"table": table_descriptor},
        details=details or [],
    )


def _make_plan(scan: PlanNode) -> EstimatedPlan:
    return EstimatedPlan(root=scan)


def _bundle(plan: EstimatedPlan) -> EvidenceBundle:
    return EvidenceBundle(plan=plan)


# ── Synthetic-minimum: fires on sub-day constraint boundary ───────────────────


def test_fires_on_sub_day_lower_bound() -> None:
    """Constraint range with 10:30 lower bound (not midnight). I8 fires."""
    detail_line = "ts := ... :: [[2025-01-15 10:30:00 UTC, 2025-01-16 00:00:00 UTC)]"
    scan = _make_scan_node(
        table_descriptor="iceberg:analytics.events constraint on [ts]",
        details=[detail_line],
    )
    plan = _make_plan(scan)
    bundle = _bundle(plan)

    rule = I8PartitionTransform()
    findings = rule.check(plan, bundle)

    assert len(findings) >= 1
    f = findings[0]
    assert f.rule_id == "I8"
    assert f.severity == "medium"
    assert f.confidence == 0.6
    assert "constraint_column" in f.evidence
    assert f.evidence["is_day_aligned"] is False


def test_fires_on_sub_hour_lower_bound() -> None:
    """Constraint range with :45:00 lower bound (not on the hour). I8 fires."""
    detail_line = "ts := ... :: [[2025-03-10 14:45:00 UTC, 2025-03-10 15:00:00 UTC)]"
    scan = _make_scan_node(
        table_descriptor="iceberg:analytics.events constraint on [ts]",
        details=[detail_line],
    )
    plan = _make_plan(scan)
    bundle = _bundle(plan)

    rule = I8PartitionTransform()
    findings = rule.check(plan, bundle)

    assert len(findings) >= 1
    assert findings[0].evidence["is_hour_aligned"] is False


def test_fires_with_fractional_seconds() -> None:
    """Constraint with fractional seconds in lower bound. I8 fires."""
    detail_line = "event_time := ... :: [[2025-06-01 08:30:15.500000 UTC, 2025-06-02 00:00:00.000000 UTC)]"
    scan = _make_scan_node(
        table_descriptor="iceberg:analytics.events constraint on [event_time]",
        details=[detail_line],
    )
    plan = _make_plan(scan)
    bundle = _bundle(plan)

    rule = I8PartitionTransform()
    findings = rule.check(plan, bundle)

    assert len(findings) >= 1
    assert findings[0].rule_id == "I8"


# ── Negative-control: does NOT fire ──────────────────────────────────────────


def test_negative_day_aligned_boundary() -> None:
    """Lower bound is exactly midnight UTC (day-aligned). I8 returns []."""
    detail_line = "ts := ... :: [[2025-01-15 00:00:00.000000 UTC, 2025-01-16 00:00:00.000000 UTC)]"
    scan = _make_scan_node(
        table_descriptor="iceberg:analytics.events constraint on [ts]",
        details=[detail_line],
    )
    plan = _make_plan(scan)
    bundle = _bundle(plan)

    rule = I8PartitionTransform()
    findings = rule.check(plan, bundle)

    assert findings == []


def test_negative_no_constraint_in_descriptor() -> None:
    """Scan has no 'constraint on [' in descriptor. I8 returns [] (no pruning at all)."""
    scan = _make_scan_node(
        table_descriptor="iceberg:analytics.events",
        details=["ts := ... :: [[2025-01-15 10:30:00 UTC, 2025-01-16 00:00:00 UTC)]"],
    )
    plan = _make_plan(scan)
    bundle = _bundle(plan)

    rule = I8PartitionTransform()
    findings = rule.check(plan, bundle)

    assert findings == []


def test_negative_no_details() -> None:
    """Scan has constraint in descriptor but no detail lines. I8 returns []."""
    scan = _make_scan_node(
        table_descriptor="iceberg:analytics.events constraint on [ts]",
        details=[],
    )
    plan = _make_plan(scan)
    bundle = _bundle(plan)

    rule = I8PartitionTransform()
    findings = rule.check(plan, bundle)

    assert findings == []


def test_negative_details_without_range_brackets() -> None:
    """Detail lines present but no [[...UTC, ...UTC)] range pattern. I8 returns []."""
    scan = _make_scan_node(
        table_descriptor="iceberg:analytics.events constraint on [ts]",
        details=["ts IS NOT NULL", "ts > CURRENT_DATE"],
    )
    plan = _make_plan(scan)
    bundle = _bundle(plan)

    rule = I8PartitionTransform()
    findings = rule.check(plan, bundle)

    assert findings == []


def test_negative_midnight_lower_bound_zero_seconds() -> None:
    """Lower bound 00:00:00 UTC (no fractional seconds). I8 returns []."""
    detail_line = "ts := ... :: [[2025-07-04 00:00:00 UTC, 2025-07-05 00:00:00 UTC)]"
    scan = _make_scan_node(
        table_descriptor="iceberg:analytics.orders constraint on [ts]",
        details=[detail_line],
    )
    plan = _make_plan(scan)
    bundle = _bundle(plan)

    rule = I8PartitionTransform()
    findings = rule.check(plan, bundle)

    assert findings == []


# ── Realistic: scan node with operator_ids populated ─────────────────────────


def test_operator_ids_populated() -> None:
    """Finding operator_ids must include the scan node id."""
    detail_line = "ts := ... :: [[2025-01-15 10:30:00 UTC, 2025-01-16 00:00:00 UTC)]"
    scan = _make_scan_node(
        node_id="scan-42",
        table_descriptor="iceberg:analytics.events constraint on [ts]",
        details=[detail_line],
    )
    plan = _make_plan(scan)
    bundle = _bundle(plan)

    rule = I8PartitionTransform()
    findings = rule.check(plan, bundle)

    assert len(findings) >= 1
    assert "scan-42" in findings[0].operator_ids


def test_evidence_fields_present() -> None:
    """Finding must contain all documented evidence fields."""
    detail_line = "ts := ... :: [[2025-01-15 10:30:00 UTC, 2025-01-16 00:00:00 UTC)]"
    scan = _make_scan_node(
        table_descriptor="iceberg:analytics.events constraint on [ts]",
        details=[detail_line],
    )
    plan = _make_plan(scan)
    bundle = _bundle(plan)

    rule = I8PartitionTransform()
    findings = rule.check(plan, bundle)

    assert len(findings) >= 1
    ev = findings[0].evidence
    assert "constraint_column" in ev
    assert "constraint_lower_bound" in ev
    assert "is_day_aligned" in ev
    assert "is_hour_aligned" in ev


def test_multiple_constraint_columns_each_fires() -> None:
    """Multiple detail lines with misaligned bounds — one finding per line."""
    scan = PlanNode(
        id="1",
        name="TableScan",
        descriptor={"table": "iceberg:analytics.events constraint on [ts] constraint on [created_at]"},
        details=[
            "ts := ... :: [[2025-01-15 10:30:00 UTC, 2025-01-16 00:00:00 UTC)]",
            "created_at := ... :: [[2025-01-15 14:00:00 UTC, 2025-01-16 00:00:00 UTC)]",
        ],
    )
    plan = EstimatedPlan(root=scan)
    bundle = EvidenceBundle(plan=plan)

    rule = I8PartitionTransform()
    findings = rule.check(plan, bundle)

    # Both detail lines have misaligned lower bounds
    assert len(findings) == 2


def test_detail_string_capped_for_safety() -> None:
    """Detail strings > 1000 chars are handled safely (T-04-15 regex safety)."""
    # Pad with garbage before the actual constraint pattern
    padding = "X" * 2000
    detail_line = f"{padding} :: [[2025-01-15 10:30:00 UTC, 2025-01-16 00:00:00 UTC)]"
    scan = _make_scan_node(
        table_descriptor="iceberg:analytics.events constraint on [ts]",
        details=[detail_line],
    )
    plan = _make_plan(scan)
    bundle = _bundle(plan)

    rule = I8PartitionTransform()
    # Should not hang or crash — T-04-15 caps the string before regex
    findings = rule.check(plan, bundle)

    # The pattern is beyond 1000 chars so it may or may not find it — just must not crash
    assert isinstance(findings, list)
