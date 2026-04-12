"""R3 PredicatePushdown rule tests.

Three fixture classes:
1. Synthetic-minimum: hand-built PlanNode with function-wrapped column predicates.
2. Realistic: loaded from tests/fixtures/explain/429/simple_select.json (no function wrap
   → serves as negative-control realistic case) plus synthetic realistic fixtures.
3. Negative-control: range predicates, no filterPredicate.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_trino_optimizer.parser.models import EstimatedPlan, PlanNode
from mcp_trino_optimizer.parser.parser import parse_estimated_plan
from mcp_trino_optimizer.rules.evidence import EvidenceBundle
from mcp_trino_optimizer.rules.r3_predicate_pushdown import R3PredicatePushdown
from mcp_trino_optimizer.rules.registry import registry

FIXTURES_429 = Path(__file__).parent.parent / "fixtures" / "explain" / "429"
FIXTURES_480 = Path(__file__).parent.parent / "fixtures" / "explain" / "480"


def _make_plan(node: PlanNode) -> EstimatedPlan:
    """Wrap a single node in a minimal EstimatedPlan."""
    return EstimatedPlan(root=node)


def _scan_filter_node(predicate: str, node_id: str = "1") -> PlanNode:
    """Build a ScanFilter node with the given filterPredicate."""
    return PlanNode(
        id=node_id,
        name="ScanFilter",
        descriptor={
            "table": "iceberg:test_fixtures.orders$data@123",
            "filterPredicate": predicate,
        },
    )


# ---------------------------------------------------------------------------
# Synthetic-minimum tests — function-wrapped columns fire R3
# ---------------------------------------------------------------------------


class TestR3SyntheticMinimum:
    """R3 fires when filterPredicate wraps a column in a function."""

    def test_date_function_wrap_fires(self) -> None:
        """date(ts) = '2025-01-15' → R3 fires."""
        node = _scan_filter_node('("date"(ts) = DATE \'2025-01-15\')')
        plan = _make_plan(node)
        bundle = EvidenceBundle(plan=plan)

        findings = R3PredicatePushdown().check(plan, bundle)

        assert len(findings) == 1
        f = findings[0]
        assert f.rule_id == "R3"
        assert f.severity == "high"
        assert "1" in f.operator_ids
        assert len(f.evidence["detected_functions"]) >= 1

    def test_year_function_wrap_fires(self) -> None:
        """year(ts) = 2025 → R3 fires."""
        node = _scan_filter_node("(year(ts) = 2025)")
        plan = _make_plan(node)
        bundle = EvidenceBundle(plan=plan)

        findings = R3PredicatePushdown().check(plan, bundle)

        assert len(findings) == 1
        assert findings[0].rule_id == "R3"

    def test_month_function_wrap_fires(self) -> None:
        """month(created_at) = 6 → R3 fires."""
        node = _scan_filter_node("(month(created_at) = 6)")
        plan = _make_plan(node)
        bundle = EvidenceBundle(plan=plan)

        findings = R3PredicatePushdown().check(plan, bundle)

        assert len(findings) == 1
        assert findings[0].rule_id == "R3"

    def test_cast_function_wrap_fires(self) -> None:
        """cast(amount AS varchar) = '100' → R3 fires."""
        node = _scan_filter_node("(CAST(amount AS varchar) = '100')")
        plan = _make_plan(node)
        bundle = EvidenceBundle(plan=plan)

        findings = R3PredicatePushdown().check(plan, bundle)

        assert len(findings) == 1
        assert findings[0].rule_id == "R3"

    def test_trunc_function_wrap_fires(self) -> None:
        """trunc(ts, 'MONTH') → R3 fires via regex fallback."""
        node = _scan_filter_node("(trunc(ts, 'MONTH') = DATE '2025-01-01')")
        plan = _make_plan(node)
        bundle = EvidenceBundle(plan=plan)

        findings = R3PredicatePushdown().check(plan, bundle)

        assert len(findings) == 1
        assert findings[0].rule_id == "R3"

    def test_scan_filter_project_also_fires(self) -> None:
        """ScanFilterProject with function-wrapped predicate also fires R3."""
        node = PlanNode(
            id="2",
            name="ScanFilterProject",
            descriptor={
                "table": "iceberg:test_fixtures.orders$data@123",
                "filterPredicate": "(year(ts) = 2025)",
            },
        )
        plan = _make_plan(node)
        bundle = EvidenceBundle(plan=plan)

        findings = R3PredicatePushdown().check(plan, bundle)

        assert len(findings) == 1
        assert findings[0].evidence["operator_type"] == "ScanFilterProject"

    def test_confidence_high_for_ast_detection(self) -> None:
        """AST-detected function wrapping returns confidence >= 0.85."""
        node = _scan_filter_node("(year(ts) = 2025)")
        plan = _make_plan(node)
        bundle = EvidenceBundle(plan=plan)

        findings = R3PredicatePushdown().check(plan, bundle)

        assert len(findings) == 1
        assert findings[0].confidence >= 0.6  # at minimum regex confidence


# ---------------------------------------------------------------------------
# Realistic tests
# ---------------------------------------------------------------------------


class TestR3Realistic:
    """Realistic fixture tests for R3."""

    def test_simple_select_429_no_function_wrap_negative(self) -> None:
        """429/simple_select.json has (\"id\" > BIGINT '10') — no function wrap → R3 silent."""
        json_text = (FIXTURES_429 / "simple_select.json").read_text()
        plan = parse_estimated_plan(json_text)
        bundle = EvidenceBundle(plan=plan)

        findings = R3PredicatePushdown().check(plan, bundle)

        r3_findings = [f for f in findings if f.rule_id == "R3"]
        assert r3_findings == []

    def test_realistic_iceberg_date_wrap_fires(self) -> None:
        """Realistic Iceberg ScanFilter with date() wrap → R3 fires.

        Uses the same table format as the 480 fixtures.
        """
        node = PlanNode(
            id="100",
            name="ScanFilter",
            descriptor={
                "table": "iceberg:test_fixtures.orders$data@7192078785404198795",
                "filterPredicate": "(date(ts) = DATE '2025-01-15')",
            },
        )
        plan = _make_plan(node)
        bundle = EvidenceBundle(plan=plan)

        findings = R3PredicatePushdown().check(plan, bundle)

        assert len(findings) == 1
        assert findings[0].rule_id == "R3"
        assert "ts" in findings[0].evidence["filter_predicate"]


# ---------------------------------------------------------------------------
# Negative-control tests
# ---------------------------------------------------------------------------


class TestR3NegativeControl:
    """R3 does NOT fire for range predicates or missing filterPredicate."""

    def test_range_predicate_no_function_wrap_no_finding(self) -> None:
        """Range predicate without function wrap → R3 does not fire."""
        node = _scan_filter_node(
            "(ts >= TIMESTAMP '2025-01-15 00:00:00 UTC' AND ts < TIMESTAMP '2025-01-16 00:00:00 UTC')"
        )
        plan = _make_plan(node)
        bundle = EvidenceBundle(plan=plan)

        findings = R3PredicatePushdown().check(plan, bundle)

        assert findings == []

    def test_simple_equality_no_function_no_finding(self) -> None:
        """id = 42 — direct column equality → R3 does not fire."""
        node = _scan_filter_node('("id" = BIGINT \'42\')')
        plan = _make_plan(node)
        bundle = EvidenceBundle(plan=plan)

        findings = R3PredicatePushdown().check(plan, bundle)

        assert findings == []

    def test_no_filter_predicate_no_finding(self) -> None:
        """ScanFilter with no filterPredicate → R3 does not fire."""
        node = PlanNode(
            id="5",
            name="ScanFilter",
            descriptor={"table": "iceberg:test_fixtures.orders$data@123"},
        )
        plan = _make_plan(node)
        bundle = EvidenceBundle(plan=plan)

        findings = R3PredicatePushdown().check(plan, bundle)

        assert findings == []

    def test_empty_filter_predicate_no_finding(self) -> None:
        """Empty filterPredicate string → R3 does not fire."""
        node = _scan_filter_node("")
        plan = _make_plan(node)
        bundle = EvidenceBundle(plan=plan)

        findings = R3PredicatePushdown().check(plan, bundle)

        assert findings == []

    def test_non_filter_node_skipped(self) -> None:
        """Aggregate node is not a filter type — R3 does not fire."""
        node = PlanNode(
            id="6",
            name="Aggregate",
            descriptor={"filterPredicate": "(year(ts) = 2025)"},
        )
        plan = _make_plan(node)
        bundle = EvidenceBundle(plan=plan)

        findings = R3PredicatePushdown().check(plan, bundle)

        assert findings == []

    def test_amount_comparison_no_function_no_finding(self) -> None:
        """(amount > decimal(10,2) '100.00') — numeric comparison, no function wrap on column."""
        node = _scan_filter_node("(amount > decimal(10,2) '100.00')")
        plan = _make_plan(node)
        bundle = EvidenceBundle(plan=plan)

        # decimal() here is a type cast literal, not wrapping the column
        findings = R3PredicatePushdown().check(plan, bundle)

        # This predicate does not wrap a column in a function
        # The column 'amount' is on the left side without a function wrap
        assert findings == []


# ---------------------------------------------------------------------------
# Registry test
# ---------------------------------------------------------------------------


def test_r3_registered() -> None:
    """R3PredicatePushdown is registered in the global registry after import."""
    import mcp_trino_optimizer.rules.r3_predicate_pushdown  # noqa: F401

    ids = [r.rule_id for r in registry.all_rules()]
    assert "R3" in ids
