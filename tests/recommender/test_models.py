"""Tests for recommender pydantic models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError


class TestRecommendationModel:
    """Recommendation model validates all required fields."""

    def test_valid_recommendation(self) -> None:
        from mcp_trino_optimizer.recommender.models import Recommendation

        rec = Recommendation(
            rule_id="R1",
            severity="critical",
            confidence=0.9,
            priority_score=3.6,
            priority_tier="P1",
            operator_ids=["node-1"],
            reasoning="Missing stats cause full table scans.",
            expected_impact="Reduce scan by 80%",
            risk_level="low",
            validation_steps="Run ANALYZE TABLE",
            evidence_summary={"table": "orders"},
        )
        assert rec.rule_id == "R1"
        assert rec.severity == "critical"
        assert rec.confidence == 0.9
        assert rec.priority_score == 3.6
        assert rec.priority_tier == "P1"
        assert rec.operator_ids == ["node-1"]
        assert rec.reasoning == "Missing stats cause full table scans."
        assert rec.expected_impact == "Reduce scan by 80%"
        assert rec.risk_level == "low"
        assert rec.validation_steps == "Run ANALYZE TABLE"
        assert rec.evidence_summary == {"table": "orders"}

    def test_recommendation_optional_fields(self) -> None:
        from mcp_trino_optimizer.recommender.models import Recommendation

        rec = Recommendation(
            rule_id="R5",
            severity="high",
            confidence=0.85,
            priority_score=2.55,
            priority_tier="P1",
            operator_ids=["node-2"],
            reasoning="Broadcast too big.",
            expected_impact="Switch to partitioned join.",
            risk_level="medium",
            validation_steps="Check join distribution.",
            evidence_summary={},
            session_property_statements=["SET SESSION join_distribution_type = 'PARTITIONED'"],
        )
        assert rec.session_property_statements == ["SET SESSION join_distribution_type = 'PARTITIONED'"]
        assert rec.considered_but_rejected == []

    def test_recommendation_invalid_confidence(self) -> None:
        from mcp_trino_optimizer.recommender.models import Recommendation

        with pytest.raises(ValidationError):
            Recommendation(
                rule_id="R1",
                severity="critical",
                confidence=1.5,  # out of range
                priority_score=3.6,
                priority_tier="P1",
                operator_ids=[],
                reasoning="test",
                expected_impact="test",
                risk_level="low",
                validation_steps="test",
                evidence_summary={},
            )


class TestConsideredButRejectedModel:
    """ConsideredButRejected model validates rule_id, reason, original_priority_score."""

    def test_valid(self) -> None:
        from mcp_trino_optimizer.recommender.models import ConsideredButRejected

        cbr = ConsideredButRejected(
            rule_id="R1",
            reason="Superseded by D11 with higher confidence.",
            original_priority_score=1.4,
        )
        assert cbr.rule_id == "R1"
        assert cbr.reason == "Superseded by D11 with higher confidence."
        assert cbr.original_priority_score == 1.4


class TestIcebergTableHealthModel:
    """IcebergTableHealth model validates all fields."""

    def test_valid_full(self) -> None:
        from mcp_trino_optimizer.recommender.models import IcebergTableHealth

        health = IcebergTableHealth(
            table_name="iceberg.db.orders",
            snapshot_count=150,
            small_file_ratio=0.3,
            delete_file_ratio=0.05,
            partition_spec_evolution="day(ts) -> hour(ts)",
            last_compaction_reference="2026-04-01",
            health_score="degraded",
            narrative="Table has too many snapshots.",
        )
        assert health.table_name == "iceberg.db.orders"
        assert health.snapshot_count == 150
        assert health.health_score == "degraded"

    def test_valid_minimal(self) -> None:
        from mcp_trino_optimizer.recommender.models import IcebergTableHealth

        health = IcebergTableHealth(
            table_name="iceberg.db.orders",
            health_score="healthy",
            narrative="No issues detected.",
        )
        assert health.snapshot_count is None
        assert health.small_file_ratio is None


class TestBottleneckEntryModel:
    """BottleneckEntry model validates all fields."""

    def test_valid(self) -> None:
        from mcp_trino_optimizer.recommender.models import BottleneckEntry

        entry = BottleneckEntry(
            operator_id="node-3",
            operator_type="HashJoin",
            cpu_time_ms=5000.0,
            wall_time_ms=6000.0,
            cpu_pct=45.5,
            input_rows=1_000_000,
            output_rows=500_000,
            peak_memory_bytes=256_000_000,
            related_findings=["R5", "R6"],
            narrative="HashJoin is the top CPU consumer.",
        )
        assert entry.operator_id == "node-3"
        assert entry.cpu_pct == 45.5
        assert entry.related_findings == ["R5", "R6"]


class TestBottleneckRankingModel:
    """BottleneckRanking model validates top_operators, total_cpu_time_ms, plan_type, top_n."""

    def test_valid(self) -> None:
        from mcp_trino_optimizer.recommender.models import (
            BottleneckEntry,
            BottleneckRanking,
        )

        ranking = BottleneckRanking(
            top_operators=[
                BottleneckEntry(
                    operator_id="node-3",
                    operator_type="HashJoin",
                    cpu_time_ms=5000.0,
                    wall_time_ms=6000.0,
                    cpu_pct=45.5,
                    related_findings=[],
                    narrative="Top CPU consumer.",
                ),
            ],
            total_cpu_time_ms=11000.0,
            plan_type="executed",
            top_n=5,
        )
        assert len(ranking.top_operators) == 1
        assert ranking.total_cpu_time_ms == 11000.0
        assert ranking.top_n == 5


class TestRecommendationReportModel:
    """RecommendationReport validates recommendations list and optional fields."""

    def test_valid_minimal(self) -> None:
        from mcp_trino_optimizer.recommender.models import RecommendationReport

        report = RecommendationReport(recommendations=[])
        assert report.recommendations == []
        assert report.iceberg_health == []
        assert report.bottleneck_ranking is None
        assert report.considered_but_rejected == []

    def test_valid_with_content(self) -> None:
        from mcp_trino_optimizer.recommender.models import (
            Recommendation,
            RecommendationReport,
        )

        rec = Recommendation(
            rule_id="R1",
            severity="medium",
            confidence=0.8,
            priority_score=1.6,
            priority_tier="P2",
            operator_ids=["node-1"],
            reasoning="Missing stats.",
            expected_impact="Better estimates.",
            risk_level="low",
            validation_steps="Run ANALYZE.",
            evidence_summary={},
        )
        report = RecommendationReport(recommendations=[rec])
        assert len(report.recommendations) == 1


class TestPriorityTierType:
    """PriorityTier literal type exists."""

    def test_priority_tier_values(self) -> None:
        from mcp_trino_optimizer.recommender.models import PriorityTier

        # PriorityTier is a Literal type, verify it exists
        assert PriorityTier is not None
