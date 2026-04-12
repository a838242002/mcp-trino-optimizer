"""Tests for Iceberg table health aggregation (REC-06).

Verifies that aggregate_iceberg_health correctly groups I1/I3/I6/I8
findings by table, populates IcebergTableHealth fields, classifies
health scores, and renders templated narratives.
"""

from __future__ import annotations

import pytest

from mcp_trino_optimizer.recommender.health import (
    ICEBERG_RULES,
    aggregate_iceberg_health,
)
from mcp_trino_optimizer.rules.findings import RuleFinding


def _make_finding(
    rule_id: str,
    severity: str = "medium",
    confidence: float = 0.9,
    evidence: dict | None = None,
    operator_ids: list[str] | None = None,
) -> RuleFinding:
    """Helper to build RuleFinding with defaults."""
    return RuleFinding(
        rule_id=rule_id,
        severity=severity,
        confidence=confidence,
        message=f"Test finding for {rule_id}",
        evidence=evidence or {},
        operator_ids=operator_ids or [],
    )


class TestAggregateIcebergHealth:
    """Tests for aggregate_iceberg_health function."""

    def test_i1_high_severity_produces_critical_health(self) -> None:
        """I1 finding with severity=high for a table -> health_score=critical."""
        findings = [
            _make_finding(
                "I1",
                severity="high",
                evidence={
                    "table_name": "iceberg:db.orders",
                    "median_file_size_bytes": 4_000_000,
                    "threshold_bytes": 16_000_000,
                },
            ),
        ]
        result = aggregate_iceberg_health(findings)
        assert len(result) == 1
        health = result[0]
        assert health.table_name == "iceberg:db.orders"
        assert health.health_score == "critical"
        assert health.small_file_ratio is not None
        assert health.small_file_ratio == pytest.approx(4_000_000 / 16_000_000)

    def test_i6_medium_severity_produces_degraded_health(self) -> None:
        """I6 finding with severity=medium -> health_score=degraded."""
        findings = [
            _make_finding(
                "I6",
                severity="medium",
                evidence={
                    "table_name": "iceberg:db.events",
                    "snapshot_count": 120,
                    "threshold_count": 50,
                },
            ),
        ]
        result = aggregate_iceberg_health(findings)
        assert len(result) == 1
        health = result[0]
        assert health.health_score == "degraded"
        assert health.snapshot_count == 120

    def test_combined_i1_i3_i6_same_table(self) -> None:
        """I1 + I3 + I6 findings for same table -> single health with all fields."""
        findings = [
            _make_finding(
                "I1",
                severity="high",
                evidence={
                    "table_name": "iceberg:db.orders",
                    "median_file_size_bytes": 4_000_000,
                    "threshold_bytes": 16_000_000,
                },
            ),
            _make_finding(
                "I3",
                severity="high",
                evidence={
                    "table_name": "iceberg:db.orders",
                    "delete_ratio": 0.15,
                },
            ),
            _make_finding(
                "I6",
                severity="medium",
                evidence={
                    "table_name": "iceberg:db.orders",
                    "snapshot_count": 80,
                },
            ),
        ]
        result = aggregate_iceberg_health(findings)
        assert len(result) == 1
        health = result[0]
        assert health.table_name == "iceberg:db.orders"
        assert health.health_score == "critical"  # I1 high -> critical
        assert health.small_file_ratio is not None
        assert health.delete_file_ratio == pytest.approx(0.15)
        assert health.snapshot_count == 80

    def test_different_tables_produce_separate_health_objects(self) -> None:
        """I1 for table A and I3 for table B -> two separate health objects."""
        findings = [
            _make_finding(
                "I1",
                severity="high",
                evidence={
                    "table_name": "iceberg:db.orders",
                    "median_file_size_bytes": 4_000_000,
                    "threshold_bytes": 16_000_000,
                },
            ),
            _make_finding(
                "I3",
                severity="high",
                evidence={
                    "table_name": "iceberg:db.events",
                    "delete_ratio": 0.25,
                },
            ),
        ]
        result = aggregate_iceberg_health(findings)
        assert len(result) == 2
        table_names = {h.table_name for h in result}
        assert table_names == {"iceberg:db.orders", "iceberg:db.events"}

    def test_no_iceberg_findings_returns_empty(self) -> None:
        """Non-Iceberg findings (R1, R5, etc.) -> empty list."""
        findings = [
            _make_finding("R1", severity="high", evidence={"filter_predicate": "x > 1"}),
            _make_finding("R5", severity="medium", evidence={}),
        ]
        result = aggregate_iceberg_health(findings)
        assert result == []

    def test_i8_produces_partition_evolution_and_degraded(self) -> None:
        """I8 finding -> partition_spec_evolution populated, health_score=degraded."""
        findings = [
            _make_finding(
                "I8",
                severity="medium",
                confidence=0.6,
                evidence={
                    "table_name": "iceberg:db.events",
                    "constraint_column": "ts",
                    "is_day_aligned": False,
                    "is_hour_aligned": True,
                },
            ),
        ]
        result = aggregate_iceberg_health(findings)
        assert len(result) == 1
        health = result[0]
        assert health.health_score == "degraded"
        assert health.partition_spec_evolution is not None
        assert "ts" in health.partition_spec_evolution

    def test_narrative_contains_table_name(self) -> None:
        """Health narrative is templated and contains table_name."""
        findings = [
            _make_finding(
                "I1",
                severity="high",
                evidence={
                    "table_name": "iceberg:db.orders",
                    "median_file_size_bytes": 4_000_000,
                    "threshold_bytes": 16_000_000,
                },
            ),
        ]
        result = aggregate_iceberg_health(findings)
        assert len(result) == 1
        assert "iceberg:db.orders" in result[0].narrative
        # Narrative must not contain {message} from RuleFinding
        assert "{message}" not in result[0].narrative

    def test_health_score_classification(self) -> None:
        """health_score: I1/I3 high->critical, I6/I8->degraded."""
        # I3 severity=high -> critical
        critical_findings = [
            _make_finding(
                "I3",
                severity="high",
                evidence={
                    "table_name": "iceberg:db.t1",
                    "delete_ratio": 0.3,
                },
            ),
        ]
        result_critical = aggregate_iceberg_health(critical_findings)
        assert result_critical[0].health_score == "critical"

        # I6 severity=medium -> degraded (not critical)
        degraded_findings = [
            _make_finding(
                "I6",
                severity="medium",
                evidence={
                    "table_name": "iceberg:db.t2",
                    "snapshot_count": 100,
                },
            ),
        ]
        result_degraded = aggregate_iceberg_health(degraded_findings)
        assert result_degraded[0].health_score == "degraded"

        # I1 severity=medium -> degraded (not critical, since not high)
        degraded_i1 = [
            _make_finding(
                "I1",
                severity="medium",
                evidence={
                    "table_name": "iceberg:db.t3",
                    "iceberg_split_count": 5000,
                    "threshold": 1000,
                },
            ),
        ]
        result_d2 = aggregate_iceberg_health(degraded_i1)
        assert result_d2[0].health_score == "degraded"

    def test_findings_without_table_name_use_fallback(self) -> None:
        """Findings with no table_name in evidence use 'unknown_table'."""
        findings = [
            _make_finding(
                "I1",
                severity="high",
                evidence={
                    "iceberg_split_count": 15000,
                    "threshold": 10000,
                },
            ),
        ]
        result = aggregate_iceberg_health(findings)
        assert len(result) == 1
        assert result[0].table_name == "unknown_table"

    def test_last_compaction_reference_for_i1(self) -> None:
        """I1/I3 findings -> compaction reference is optimize."""
        findings = [
            _make_finding(
                "I1",
                severity="high",
                evidence={
                    "table_name": "iceberg:db.orders",
                    "median_file_size_bytes": 4_000_000,
                    "threshold_bytes": 16_000_000,
                },
            ),
        ]
        result = aggregate_iceberg_health(findings)
        assert result[0].last_compaction_reference is not None
        assert "optimize" in result[0].last_compaction_reference.lower()

    def test_last_compaction_reference_for_i6(self) -> None:
        """I6 findings -> compaction reference is expire_snapshots."""
        findings = [
            _make_finding(
                "I6",
                severity="medium",
                evidence={
                    "table_name": "iceberg:db.events",
                    "snapshot_count": 100,
                },
            ),
        ]
        result = aggregate_iceberg_health(findings)
        assert result[0].last_compaction_reference is not None
        assert "expire_snapshots" in result[0].last_compaction_reference.lower()


class TestIcebergRulesConstant:
    """Tests for ICEBERG_RULES constant."""

    def test_contains_expected_rules(self) -> None:
        assert {"I1", "I3", "I6", "I8"} == ICEBERG_RULES
