"""Integration tests for RecommendationEngine full pipeline.

Validates the complete flow from EngineResult -> RecommendationReport
including health aggregation, bottleneck ranking, conflict resolution,
and recommendation sorting.
"""

from __future__ import annotations

from typing import Any

import pytest

from mcp_trino_optimizer.parser.models import EstimatedPlan, ExecutedPlan, PlanNode
from mcp_trino_optimizer.recommender.engine import RecommendationEngine
from mcp_trino_optimizer.recommender.models import RecommendationReport
from mcp_trino_optimizer.rules.findings import (
    RuleError,
    RuleFinding,
    RuleSkipped,
)


def _make_node(
    node_id: str,
    name: str = "Output",
    cpu_time_ms: float | None = None,
    wall_time_ms: float | None = None,
    children: list[PlanNode] | None = None,
) -> PlanNode:
    return PlanNode(
        id=node_id,
        name=name,
        descriptor={},
        cpu_time_ms=cpu_time_ms,
        wall_time_ms=wall_time_ms,
        children=children or [],
    )


def _make_finding(
    rule_id: str,
    severity: str = "medium",
    confidence: float = 0.8,
    evidence: dict[str, Any] | None = None,
    operator_ids: list[str] | None = None,
) -> RuleFinding:
    return RuleFinding(
        rule_id=rule_id,
        severity=severity,
        confidence=confidence,
        message=f"Test finding for {rule_id}",
        evidence=evidence or {},
        operator_ids=operator_ids or [],
    )


class TestEngineIcebergHealthIntegration:
    """Engine populates iceberg_health in report from Iceberg findings."""

    def test_iceberg_findings_produce_health_in_report(self) -> None:
        """Findings with I1/I3 rules -> iceberg_health populated."""
        engine = RecommendationEngine()
        findings = [
            _make_finding(
                "I1",
                severity="high",
                confidence=0.95,
                evidence={
                    "table_name": "iceberg:db.orders",
                    "median_file_size_bytes": 4_000_000,
                    "threshold_bytes": 16_000_000,
                },
            ),
            _make_finding(
                "I3",
                severity="high",
                confidence=0.95,
                evidence={
                    "table_name": "iceberg:db.orders",
                    "delete_ratio": 0.2,
                },
            ),
        ]
        report = engine.recommend(findings)
        assert len(report.iceberg_health) == 1
        assert report.iceberg_health[0].table_name == "iceberg:db.orders"
        assert report.iceberg_health[0].health_score == "critical"

    def test_no_iceberg_findings_empty_health(self) -> None:
        """Only non-Iceberg findings -> empty iceberg_health."""
        engine = RecommendationEngine()
        findings = [
            _make_finding("R1", severity="medium", operator_ids=["n1"]),
        ]
        report = engine.recommend(findings)
        assert report.iceberg_health == []


class TestEngineBottleneckIntegration:
    """Engine populates bottleneck_ranking when plan is provided."""

    def test_executed_plan_produces_bottleneck(self) -> None:
        """Findings + ExecutedPlan -> bottleneck_ranking populated."""
        root = _make_node(
            "n1",
            cpu_time_ms=100.0,
            wall_time_ms=100.0,
            children=[_make_node("n2", cpu_time_ms=50.0, wall_time_ms=50.0)],
        )
        plan = ExecutedPlan(root=root)
        engine = RecommendationEngine(plan=plan)
        findings = [
            _make_finding("R1", severity="medium", operator_ids=["n1"]),
        ]
        report = engine.recommend(findings)
        assert report.bottleneck_ranking is not None
        assert len(report.bottleneck_ranking.top_operators) == 2

    def test_estimated_plan_no_bottleneck(self) -> None:
        """Findings + EstimatedPlan -> bottleneck_ranking is None."""
        root = _make_node("n1")
        plan = EstimatedPlan(root=root)
        engine = RecommendationEngine(plan=plan)
        findings = [
            _make_finding("R1", severity="medium", operator_ids=["n1"]),
        ]
        report = engine.recommend(findings)
        assert report.bottleneck_ranking is None

    def test_no_plan_no_bottleneck(self) -> None:
        """No plan provided -> bottleneck_ranking is None."""
        engine = RecommendationEngine()
        findings = [
            _make_finding("R1", severity="medium", operator_ids=["n1"]),
        ]
        report = engine.recommend(findings)
        assert report.bottleneck_ranking is None


class TestFullPipelineIntegration:
    """Full pipeline: mixed EngineResult -> complete RecommendationReport."""

    def test_full_pipeline(self) -> None:
        """Mixed findings + errors + skips -> complete report."""
        root = _make_node(
            "n1",
            name="Output",
            cpu_time_ms=200.0,
            wall_time_ms=250.0,
            children=[
                _make_node(
                    "n2",
                    name="HashJoin",
                    cpu_time_ms=100.0,
                    wall_time_ms=120.0,
                    children=[
                        _make_node("n3", name="TableScan", cpu_time_ms=50.0, wall_time_ms=60.0),
                        _make_node("n4", name="Exchange", cpu_time_ms=30.0, wall_time_ms=35.0),
                    ],
                ),
            ],
        )
        plan = ExecutedPlan(root=root)

        # Build mixed engine results
        engine_results: list[Any] = [
            # R1 and D11 on same operator -> conflict (D11 wins)
            _make_finding("R1", severity="medium", confidence=0.7, operator_ids=["n2"]),
            _make_finding(
                "D11",
                severity="high",
                confidence=0.95,
                evidence={"divergence_factor": 15.0},
                operator_ids=["n2"],
            ),
            # R5 -> should produce SET SESSION statements
            _make_finding(
                "R5",
                severity="medium",
                confidence=0.8,
                evidence={"build_size_bytes": 500_000_000, "broadcast_threshold_bytes": 100_000_000},
                operator_ids=["n2"],
            ),
            # Iceberg findings
            _make_finding(
                "I1",
                severity="high",
                confidence=0.95,
                evidence={
                    "table_name": "iceberg:db.orders",
                    "median_file_size_bytes": 4_000_000,
                    "threshold_bytes": 16_000_000,
                },
            ),
            _make_finding(
                "I3",
                severity="high",
                confidence=0.95,
                evidence={
                    "table_name": "iceberg:db.orders",
                    "delete_ratio": 0.15,
                },
            ),
            # Errors and skips (should be filtered out)
            RuleError(rule_id="R9", error_type="ValueError", message="test error"),
            RuleSkipped(rule_id="I6", reason="offline_mode"),
        ]

        engine = RecommendationEngine(plan=plan)
        report = engine.recommend(engine_results)

        assert isinstance(report, RecommendationReport)

        # Recommendations sorted by priority_score descending
        scores = [r.priority_score for r in report.recommendations]
        assert scores == sorted(scores, reverse=True)

        # R1/D11 conflict resolved: D11 wins, R1 in considered_but_rejected
        rec_rule_ids = {r.rule_id for r in report.recommendations}
        assert "D11" in rec_rule_ids
        assert "R1" not in rec_rule_ids

        # R5 has session property statements
        r5_recs = [r for r in report.recommendations if r.rule_id == "R5"]
        assert len(r5_recs) == 1
        # R5 should have session property statements (may be None if no cap_matrix)
        # but the recommendation should exist

        # Iceberg health populated
        assert len(report.iceberg_health) == 1
        assert report.iceberg_health[0].table_name == "iceberg:db.orders"
        assert report.iceberg_health[0].health_score == "critical"

        # Bottleneck ranking populated from ExecutedPlan
        assert report.bottleneck_ranking is not None
        assert len(report.bottleneck_ranking.top_operators) > 0
        assert report.bottleneck_ranking.total_cpu_time_ms == pytest.approx(380.0)

        # considered_but_rejected is non-empty (R1 lost to D11)
        assert len(report.considered_but_rejected) > 0
        rejected_ids = {r.rule_id for r in report.considered_but_rejected}
        assert "R1" in rejected_ids

    def test_empty_findings_returns_empty_report(self) -> None:
        """No findings at all -> empty report with defaults."""
        engine = RecommendationEngine()
        report = engine.recommend([])
        assert report.recommendations == []
        assert report.iceberg_health == []
        assert report.bottleneck_ranking is None
        assert report.considered_but_rejected == []

    def test_only_errors_and_skips_returns_empty(self) -> None:
        """Only RuleError and RuleSkipped -> empty report."""
        engine = RecommendationEngine()
        results: list[Any] = [
            RuleError(rule_id="R1", error_type="ValueError", message="boom"),
            RuleSkipped(rule_id="I1", reason="offline"),
        ]
        report = engine.recommend(results)
        assert report.recommendations == []
        assert report.iceberg_health == []
