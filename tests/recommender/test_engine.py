"""Tests for RecommendationEngine (D-01 through D-09)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from mcp_trino_optimizer.recommender.engine import RecommendationEngine
from mcp_trino_optimizer.recommender.models import RecommendationReport
from mcp_trino_optimizer.rules.findings import (
    RuleError,
    RuleFinding,
    RuleSkipped,
)


def _make_finding(
    rule_id: str = "R1",
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
        operator_ids=operator_ids or ["node-1"],
    )


@dataclass(frozen=True)
class _FakeCapabilityMatrix:
    trino_version_major: int


class TestRecommendationEngineSingleFinding:
    """RecommendationEngine.recommend with a single finding."""

    def test_single_r1_finding(self) -> None:
        engine = RecommendationEngine()
        report = engine.recommend([_make_finding("R1")])
        assert isinstance(report, RecommendationReport)
        assert len(report.recommendations) == 1
        rec = report.recommendations[0]
        assert rec.rule_id == "R1"
        assert rec.priority_score > 0
        assert rec.reasoning
        assert rec.expected_impact
        assert rec.validation_steps

    def test_empty_findings_returns_empty_report(self) -> None:
        engine = RecommendationEngine()
        report = engine.recommend([])
        assert len(report.recommendations) == 0
        assert len(report.considered_but_rejected) == 0


class TestRecommendationEngineConflicts:
    """Conflict resolution wired into the pipeline."""

    def test_r1_d11_conflict_d11_wins(self) -> None:
        """R1 + D11 on same operator => D11 wins, R1 rejected."""
        findings = [
            _make_finding("R1", severity="medium", confidence=0.8, operator_ids=["op-1"]),
            _make_finding("D11", severity="high", confidence=0.95, operator_ids=["op-1"]),
        ]
        engine = RecommendationEngine()
        report = engine.recommend(findings)
        rec_ids = [r.rule_id for r in report.recommendations]
        rejected_ids = [r.rule_id for r in report.considered_but_rejected]
        assert "D11" in rec_ids
        assert "R1" in rejected_ids
        assert "R1" not in rec_ids


class TestRecommendationEngineSorting:
    """Recommendations sorted by priority_score descending."""

    def test_sorted_descending(self) -> None:
        findings = [
            _make_finding("R1", severity="low", confidence=0.5, operator_ids=["op-a"]),
            _make_finding("R5", severity="high", confidence=0.9, operator_ids=["op-b"]),
        ]
        engine = RecommendationEngine()
        report = engine.recommend(findings)
        scores = [r.priority_score for r in report.recommendations]
        assert scores == sorted(scores, reverse=True)


class TestRecommendationEngineSessionProperties:
    """Session property wiring."""

    def test_r5_has_set_session(self) -> None:
        """R5 finding with live cap matrix => SET SESSION statements."""
        cap = _FakeCapabilityMatrix(trino_version_major=480)
        engine = RecommendationEngine(capability_matrix=cap)
        report = engine.recommend([_make_finding("R5", severity="high", confidence=0.9, operator_ids=["op-1"])])
        rec = report.recommendations[0]
        assert rec.session_property_statements is not None
        assert any("SET SESSION" in s for s in rec.session_property_statements)

    def test_r1_has_no_session_properties(self) -> None:
        """R1 has no session properties => None."""
        cap = _FakeCapabilityMatrix(trino_version_major=480)
        engine = RecommendationEngine(capability_matrix=cap)
        report = engine.recommend([_make_finding("R1", operator_ids=["op-1"])])
        rec = report.recommendations[0]
        assert rec.session_property_statements is None

    def test_offline_mode_advisory(self) -> None:
        """capability_matrix=None => advisory-only session statements."""
        engine = RecommendationEngine(capability_matrix=None)
        report = engine.recommend([_make_finding("R5", severity="high", confidence=0.9, operator_ids=["op-1"])])
        rec = report.recommendations[0]
        assert rec.session_property_statements is not None
        for s in rec.session_property_statements:
            assert s.startswith("-- Advisory:")


class TestRecommendationEngineFiltering:
    """Engine filters out RuleError and RuleSkipped."""

    def test_filters_errors_and_skips(self) -> None:
        results = [
            _make_finding("R1", operator_ids=["op-1"]),
            RuleError(rule_id="R2", error_type="ValueError", message="boom"),
            RuleSkipped(rule_id="R3", reason="no_stats"),
            _make_finding("R5", severity="high", confidence=0.9, operator_ids=["op-2"]),
        ]
        engine = RecommendationEngine()
        report = engine.recommend(results)  # type: ignore[arg-type]
        rec_ids = [r.rule_id for r in report.recommendations]
        assert "R1" in rec_ids
        assert "R5" in rec_ids
        assert "R2" not in rec_ids
        assert "R3" not in rec_ids
        assert len(report.recommendations) == 2
