"""Tests for operator bottleneck ranking (REC-07).

Verifies that rank_bottlenecks correctly walks ExecutedPlan nodes,
computes CPU percentages, associates findings, renders narratives,
and handles edge cases (EstimatedPlan, all-None CPU).
"""

from __future__ import annotations

import pytest

from mcp_trino_optimizer.parser.models import EstimatedPlan, ExecutedPlan, PlanNode
from mcp_trino_optimizer.recommender.bottleneck import (
    rank_bottlenecks,
)
from mcp_trino_optimizer.recommender.models import BottleneckRanking
from mcp_trino_optimizer.rules.findings import RuleFinding


def _make_node(
    node_id: str,
    name: str = "HashJoin",
    cpu_time_ms: float | None = None,
    wall_time_ms: float | None = None,
    input_rows: int | None = None,
    output_rows: int | None = None,
    peak_memory_bytes: int | None = None,
    children: list[PlanNode] | None = None,
) -> PlanNode:
    """Build a PlanNode with metrics."""
    return PlanNode(
        id=node_id,
        name=name,
        descriptor={},
        cpu_time_ms=cpu_time_ms,
        wall_time_ms=wall_time_ms,
        input_rows=input_rows,
        output_rows=output_rows,
        peak_memory_bytes=peak_memory_bytes,
        children=children or [],
    )


def _make_finding(
    rule_id: str,
    operator_ids: list[str],
    severity: str = "medium",
) -> RuleFinding:
    return RuleFinding(
        rule_id=rule_id,
        severity=severity,
        confidence=0.8,
        message=f"Test {rule_id}",
        evidence={},
        operator_ids=operator_ids,
    )


class TestRankBottlenecks:
    """Tests for rank_bottlenecks function."""

    def test_three_nodes_sorted_by_cpu(self) -> None:
        """3 nodes with cpu=100, 50, 10 -> sorted descending, pct correct."""
        root = _make_node(
            "n1",
            name="Output",
            cpu_time_ms=100.0,
            wall_time_ms=120.0,
            children=[
                _make_node("n2", name="HashJoin", cpu_time_ms=50.0, wall_time_ms=60.0),
                _make_node("n3", name="TableScan", cpu_time_ms=10.0, wall_time_ms=15.0),
            ],
        )
        plan = ExecutedPlan(root=root)
        result = rank_bottlenecks(plan, [], top_n=3)

        assert result is not None
        assert isinstance(result, BottleneckRanking)
        assert len(result.top_operators) == 3
        assert result.total_cpu_time_ms == pytest.approx(160.0)

        # Sorted by CPU descending
        assert result.top_operators[0].operator_id == "n1"
        assert result.top_operators[0].cpu_pct == pytest.approx(100.0 / 160.0 * 100)
        assert result.top_operators[1].operator_id == "n2"
        assert result.top_operators[1].cpu_pct == pytest.approx(50.0 / 160.0 * 100)
        assert result.top_operators[2].operator_id == "n3"
        assert result.top_operators[2].cpu_pct == pytest.approx(10.0 / 160.0 * 100)

    def test_top_n_limits_results(self) -> None:
        """top_n=2 returns only top 2 operators."""
        root = _make_node(
            "n1",
            cpu_time_ms=100.0,
            wall_time_ms=100.0,
            children=[
                _make_node("n2", cpu_time_ms=50.0, wall_time_ms=50.0),
                _make_node("n3", cpu_time_ms=10.0, wall_time_ms=10.0),
            ],
        )
        plan = ExecutedPlan(root=root)
        result = rank_bottlenecks(plan, [], top_n=2)

        assert result is not None
        assert len(result.top_operators) == 2
        assert result.top_n == 2
        assert result.top_operators[0].cpu_time_ms == pytest.approx(100.0)
        assert result.top_operators[1].cpu_time_ms == pytest.approx(50.0)

    def test_related_findings_associated_by_operator_id(self) -> None:
        """Findings with matching operator_ids are associated."""
        root = _make_node(
            "n1",
            cpu_time_ms=100.0,
            wall_time_ms=100.0,
            children=[
                _make_node("n2", name="TableScan", cpu_time_ms=50.0, wall_time_ms=50.0),
            ],
        )
        plan = ExecutedPlan(root=root)
        findings = [
            _make_finding("R1", ["n1"]),
            _make_finding("R2", ["n2"]),
            _make_finding("R5", ["n1", "n2"]),
        ]
        result = rank_bottlenecks(plan, findings, top_n=5)

        assert result is not None
        # n1 should have R1, R5
        n1_entry = result.top_operators[0]
        assert n1_entry.operator_id == "n1"
        assert set(n1_entry.related_findings) == {"R1", "R5"}

        # n2 should have R2, R5
        n2_entry = result.top_operators[1]
        assert n2_entry.operator_id == "n2"
        assert set(n2_entry.related_findings) == {"R2", "R5"}

    def test_estimated_plan_returns_none(self) -> None:
        """EstimatedPlan -> returns None (no runtime metrics)."""
        root = _make_node("n1", cpu_time_ms=None)
        plan = EstimatedPlan(root=root)
        result = rank_bottlenecks(plan, [])
        assert result is None

    def test_executed_plan_all_none_cpu_returns_none(self) -> None:
        """ExecutedPlan with all cpu_time_ms=None -> returns None."""
        root = _make_node(
            "n1",
            cpu_time_ms=None,
            children=[_make_node("n2", cpu_time_ms=None)],
        )
        plan = ExecutedPlan(root=root)
        result = rank_bottlenecks(plan, [])
        assert result is None

    def test_narrative_contains_operator_type_and_pct(self) -> None:
        """Bottleneck narrative contains operator_type and cpu_pct."""
        root = _make_node("n1", name="HashJoin", cpu_time_ms=100.0, wall_time_ms=100.0)
        plan = ExecutedPlan(root=root)
        result = rank_bottlenecks(plan, [], top_n=5)

        assert result is not None
        narrative = result.top_operators[0].narrative
        assert "HashJoin" in narrative
        assert "100.0%" in narrative

    def test_plan_type_is_executed(self) -> None:
        """BottleneckRanking.plan_type is always 'executed'."""
        root = _make_node("n1", cpu_time_ms=50.0, wall_time_ms=50.0)
        plan = ExecutedPlan(root=root)
        result = rank_bottlenecks(plan, [])
        assert result is not None
        assert result.plan_type == "executed"
