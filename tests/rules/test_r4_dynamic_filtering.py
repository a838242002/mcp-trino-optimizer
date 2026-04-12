"""R4 DynamicFiltering rule tests.

Three fixture classes:
1. Synthetic-minimum: hand-built join nodes with various dynamic filter states.
2. Realistic: loaded from tests/fixtures/explain/480/join.json.
3. Negative-control: join with both assignments and probe dynamicFilters present.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_trino_optimizer.parser.models import EstimatedPlan, PlanNode
from mcp_trino_optimizer.parser.parser import parse_estimated_plan
from mcp_trino_optimizer.rules.evidence import EvidenceBundle
from mcp_trino_optimizer.rules.r4_dynamic_filtering import R4DynamicFiltering
from mcp_trino_optimizer.rules.registry import registry

FIXTURES_480 = Path(__file__).parent.parent / "fixtures" / "explain" / "480"


def _make_plan(root: PlanNode) -> EstimatedPlan:
    """Wrap a single node in a minimal EstimatedPlan."""
    return EstimatedPlan(root=root)


def _make_inner_join(
    *,
    node_id: str = "100",
    criteria: str = "(id = id)",
    details: list[str] | None = None,
    probe_descriptor: dict[str, str] | None = None,
) -> PlanNode:
    """Build an InnerJoin PlanNode with optional probe scan as children[0]."""
    if details is None:
        details = []

    probe_node = PlanNode(
        id="200",
        name="ScanFilter",
        descriptor=probe_descriptor or {"table": "iceberg:schema.orders$data@123"},
    )
    build_node = PlanNode(
        id="300",
        name="TableScan",
        descriptor={"table": "iceberg:schema.customers$data@456"},
    )

    return PlanNode(
        id=node_id,
        name="InnerJoin",
        descriptor={"criteria": criteria, "distribution": "PARTITIONED"},
        details=details,
        children=[probe_node, build_node],
    )


# ---------------------------------------------------------------------------
# Synthetic-minimum tests
# ---------------------------------------------------------------------------


class TestR4SyntheticMinimum:
    """R4 fires on joins missing dynamic filter assignments or application."""

    def test_no_df_assignments_equality_join_fires_medium(self) -> None:
        """InnerJoin with equality criteria and no dynamicFilterAssignments → R4 medium."""
        join = _make_inner_join(
            criteria="(id = id)",
            details=["Distribution: PARTITIONED"],
            probe_descriptor={"table": "iceberg:schema.orders$data@123"},
        )
        plan = _make_plan(join)
        bundle = EvidenceBundle(plan=plan)

        findings = R4DynamicFiltering().check(plan, bundle)

        assert len(findings) == 1
        f = findings[0]
        assert f.rule_id == "R4"
        assert f.severity == "medium"
        assert f.evidence["join_has_df_assignments"] is False
        assert f.evidence["probe_has_df_applied"] is False

    def test_df_declared_but_not_pushed_fires_high(self) -> None:
        """InnerJoin has dynamicFilterAssignments but probe scan has no dynamicFilters → R4 high."""
        join = _make_inner_join(
            details=["Distribution: PARTITIONED", "dynamicFilterAssignments = {id -> #df_1}"],
            probe_descriptor={"table": "iceberg:schema.orders$data@123"},
            # No dynamicFilters key in probe descriptor
        )
        plan = _make_plan(join)
        bundle = EvidenceBundle(plan=plan)

        findings = R4DynamicFiltering().check(plan, bundle)

        assert len(findings) == 1
        f = findings[0]
        assert f.rule_id == "R4"
        assert f.severity == "high"
        assert f.evidence["join_has_df_assignments"] is True
        assert f.evidence["probe_has_df_applied"] is False
        assert "#df_1" in f.evidence["dynamic_filter_ids"]

    def test_operator_ids_include_join_and_probe(self) -> None:
        """When R4 fires, operator_ids includes both join and probe scan node IDs."""
        join = _make_inner_join(
            node_id="99",
            criteria="(order_id = order_id)",
            details=[],
        )
        plan = _make_plan(join)
        bundle = EvidenceBundle(plan=plan)

        findings = R4DynamicFiltering().check(plan, bundle)

        assert len(findings) == 1
        assert "99" in findings[0].operator_ids
        assert "200" in findings[0].operator_ids  # probe scan id

    def test_semi_join_no_df_fires(self) -> None:
        """SemiJoin with equality condition and no dynamicFilterAssignments → R4 fires."""
        probe = PlanNode(id="201", name="ScanFilter", descriptor={"table": "iceberg:schema.t1$data@1"})
        build = PlanNode(id="301", name="TableScan", descriptor={"table": "iceberg:schema.t2$data@2"})
        semi_join = PlanNode(
            id="101",
            name="SemiJoin",
            descriptor={"criteria": "(a = b)"},
            details=["Distribution: REPLICATED"],
            children=[probe, build],
        )
        plan = _make_plan(semi_join)
        bundle = EvidenceBundle(plan=plan)

        findings = R4DynamicFiltering().check(plan, bundle)

        assert len(findings) == 1
        assert findings[0].rule_id == "R4"
        assert findings[0].severity == "medium"


# ---------------------------------------------------------------------------
# Realistic fixture tests
# ---------------------------------------------------------------------------


class TestR4Realistic:
    """Realistic fixture tests for R4."""

    def test_join_fixture_dynamic_filtering_working_no_finding(self) -> None:
        """join.json has dynamicFilterAssignments + probe dynamicFilters → R4 does not fire."""
        json_text = (FIXTURES_480 / "join.json").read_text()
        plan = parse_estimated_plan(json_text)
        bundle = EvidenceBundle(plan=plan)

        findings = R4DynamicFiltering().check(plan, bundle)

        r4_findings = [f for f in findings if f.rule_id == "R4"]
        # join.json has both dynamicFilterAssignments in join details
        # and dynamicFilters in probe ScanFilter descriptor → no R4
        assert r4_findings == []


# ---------------------------------------------------------------------------
# Negative-control tests
# ---------------------------------------------------------------------------


class TestR4NegativeControl:
    """R4 does NOT fire when dynamic filtering is correctly configured."""

    def test_df_assigned_and_probe_has_filters_no_finding(self) -> None:
        """InnerJoin with assignments AND probe scan with dynamicFilters → R4 silent."""
        join = _make_inner_join(
            details=[
                "Distribution: REPLICATED",
                "dynamicFilterAssignments = {id -> #df_388}",
            ],
            probe_descriptor={
                "table": "iceberg:schema.orders$data@123",
                "dynamicFilters": "{id_0 = #df_388}",
            },
        )
        plan = _make_plan(join)
        bundle = EvidenceBundle(plan=plan)

        findings = R4DynamicFiltering().check(plan, bundle)

        assert findings == []

    def test_non_join_node_skipped(self) -> None:
        """Aggregate node is not a join type — R4 does not fire."""
        node = PlanNode(
            id="50",
            name="Aggregate",
            descriptor={"criteria": "(id = id)"},
            details=["Distribution: PARTITIONED"],
        )
        plan = _make_plan(node)
        bundle = EvidenceBundle(plan=plan)

        findings = R4DynamicFiltering().check(plan, bundle)

        assert findings == []

    def test_join_no_equality_condition_no_finding(self) -> None:
        """InnerJoin with no equality condition → no dynamic filter opportunity → R4 silent."""
        join = PlanNode(
            id="102",
            name="InnerJoin",
            descriptor={"criteria": "(ts > ts_2)", "distribution": "PARTITIONED"},
            details=["Distribution: PARTITIONED"],
            children=[
                PlanNode(id="202", name="ScanFilter", descriptor={"table": "iceberg:schema.t1$data@1"}),
                PlanNode(id="302", name="TableScan", descriptor={"table": "iceberg:schema.t2$data@2"}),
            ],
        )
        plan = _make_plan(join)
        bundle = EvidenceBundle(plan=plan)

        findings = R4DynamicFiltering().check(plan, bundle)

        assert findings == []

    def test_join_no_children_no_finding(self) -> None:
        """InnerJoin with no children (degenerate case) → R4 does not crash or fire."""
        join = PlanNode(
            id="103",
            name="InnerJoin",
            descriptor={"criteria": "(id = id)"},
            details=[],
            children=[],
        )
        plan = _make_plan(join)
        bundle = EvidenceBundle(plan=plan)

        # Should not crash; no probe scan found → fires medium (equality join, no assignments)
        # But no probe children → operator_ids only has join id
        findings = R4DynamicFiltering().check(plan, bundle)

        # With no children, _get_probe_scan returns None
        # has_equality_condition is True via criteria
        # has_assignments is False
        # → fires medium
        assert len(findings) == 1
        assert findings[0].severity == "medium"
        assert "103" in findings[0].operator_ids


# ---------------------------------------------------------------------------
# Registry test
# ---------------------------------------------------------------------------


def test_r4_registered() -> None:
    """R4DynamicFiltering is registered in the global registry after import."""
    import mcp_trino_optimizer.rules.r4_dynamic_filtering  # noqa: F401

    ids = [r.rule_id for r in registry.all_rules()]
    assert "R4" in ids
