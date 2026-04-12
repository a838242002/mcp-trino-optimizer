"""Tests for recommender conflict resolution (D-04, D-05)."""

from __future__ import annotations

from mcp_trino_optimizer.recommender.conflicts import (
    CONFLICT_PAIRS,
    ScoredFinding,
    resolve_conflicts,
)
from mcp_trino_optimizer.rules.findings import RuleFinding


def _make_finding(
    rule_id: str,
    severity: str = "medium",
    confidence: float = 0.8,
    operator_ids: list[str] | None = None,
) -> RuleFinding:
    return RuleFinding(
        rule_id=rule_id,
        severity=severity,
        confidence=confidence,
        message=f"Test finding for {rule_id}",
        evidence={},
        operator_ids=operator_ids or ["node-1"],
    )


def _make_scored(
    rule_id: str,
    priority_score: float,
    severity: str = "medium",
    confidence: float = 0.8,
    operator_ids: list[str] | None = None,
) -> ScoredFinding:
    return ScoredFinding(
        finding=_make_finding(rule_id, severity, confidence, operator_ids),
        priority_score=priority_score,
    )


class TestConflictPairs:
    """CONFLICT_PAIRS should declare R1/D11, R2/R9, R5/R8 bidirectionally."""

    def test_r1_d11_bidirectional(self) -> None:
        assert "D11" in CONFLICT_PAIRS["R1"]
        assert "R1" in CONFLICT_PAIRS["D11"]

    def test_r2_r9_bidirectional(self) -> None:
        assert "R9" in CONFLICT_PAIRS["R2"]
        assert "R2" in CONFLICT_PAIRS["R9"]

    def test_r5_r8_bidirectional(self) -> None:
        assert "R8" in CONFLICT_PAIRS["R5"]
        assert "R5" in CONFLICT_PAIRS["R8"]


class TestResolveConflicts:
    """resolve_conflicts picks winner by confidence, severity, then rule_id."""

    def test_r1_d11_same_operator_d11_wins(self) -> None:
        """D11(conf=0.95) beats R1(conf=0.8) on the same operator."""
        scored = [
            _make_scored("R1", 1.6, severity="medium", confidence=0.8, operator_ids=["op-1"]),
            _make_scored("D11", 2.85, severity="high", confidence=0.95, operator_ids=["op-1"]),
        ]
        winners, rejected = resolve_conflicts(scored)
        winner_ids = [w.finding.rule_id for w in winners]
        rejected_ids = [r.rule_id for r in rejected]
        assert "D11" in winner_ids
        assert "R1" in rejected_ids
        assert "R1" not in winner_ids

    def test_r2_r9_same_operator_r2_wins(self) -> None:
        """R2(sev=high) beats R9(sev=medium) on the same operator."""
        scored = [
            _make_scored("R2", 2.4, severity="high", confidence=0.8, operator_ids=["op-2"]),
            _make_scored("R9", 1.6, severity="medium", confidence=0.8, operator_ids=["op-2"]),
        ]
        winners, rejected = resolve_conflicts(scored)
        winner_ids = [w.finding.rule_id for w in winners]
        rejected_ids = [r.rule_id for r in rejected]
        assert "R2" in winner_ids
        assert "R9" in rejected_ids

    def test_r5_r8_overlapping_nodes_r5_wins(self) -> None:
        """R5(sev=high) beats R8(sev=medium) on overlapping nodes."""
        scored = [
            _make_scored("R5", 2.4, severity="high", confidence=0.8, operator_ids=["op-3", "op-4"]),
            _make_scored("R8", 1.6, severity="medium", confidence=0.8, operator_ids=["op-3"]),
        ]
        winners, _rejected = resolve_conflicts(scored)
        winner_ids = [w.finding.rule_id for w in winners]
        assert "R5" in winner_ids
        assert "R8" not in winner_ids

    def test_same_confidence_severity_tiebreak_alphabetical(self) -> None:
        """When confidence and severity tie, lower rule_id wins."""
        scored = [
            _make_scored("R5", 1.6, severity="medium", confidence=0.8, operator_ids=["op-5"]),
            _make_scored("R8", 1.6, severity="medium", confidence=0.8, operator_ids=["op-5"]),
        ]
        winners, rejected = resolve_conflicts(scored)
        winner_ids = [w.finding.rule_id for w in winners]
        rejected_ids = [r.rule_id for r in rejected]
        assert "R5" in winner_ids
        assert "R8" in rejected_ids

    def test_no_conflicts_all_pass_through(self) -> None:
        """No declared conflicts => all findings survive."""
        scored = [
            _make_scored("R1", 1.6, operator_ids=["op-a"]),
            _make_scored("R3", 1.2, operator_ids=["op-b"]),
        ]
        winners, rejected = resolve_conflicts(scored)
        assert len(winners) == 2
        assert len(rejected) == 0

    def test_different_operators_no_conflict(self) -> None:
        """R1 and D11 on different operators should NOT conflict."""
        scored = [
            _make_scored("R1", 1.6, operator_ids=["op-x"]),
            _make_scored("D11", 2.85, operator_ids=["op-y"]),
        ]
        winners, rejected = resolve_conflicts(scored)
        assert len(winners) == 2
        assert len(rejected) == 0

    def test_iceberg_rules_empty_operators_same_analysis_group(self) -> None:
        """Iceberg rules with operator_ids=[] form one 'same analysis' group."""
        scored = [
            _make_scored("I1", 1.0, operator_ids=[]),
            _make_scored("I3", 1.2, operator_ids=[]),
            _make_scored("I6", 0.8, operator_ids=[]),
        ]
        # No conflicts declared between I1/I3/I6, so all should pass
        winners, rejected = resolve_conflicts(scored)
        assert len(winners) == 3
        assert len(rejected) == 0
