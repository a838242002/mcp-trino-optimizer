"""RecommendationEngine -- orchestrates the full recommendation pipeline.

Pipeline: findings -> scoring -> conflict resolution -> templates
-> session properties -> sorted RecommendationReport.

This is the main entry point for the suggest_optimizations tool (Phase 8).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from mcp_trino_optimizer.recommender.conflicts import ScoredFinding, resolve_conflicts
from mcp_trino_optimizer.recommender.impact import get_impact
from mcp_trino_optimizer.recommender.models import (
    Recommendation,
    RecommendationReport,
)
from mcp_trino_optimizer.recommender.scoring import assign_tier, compute_priority
from mcp_trino_optimizer.recommender.session_properties import build_set_session_statements
from mcp_trino_optimizer.recommender.templates import render_recommendation
from mcp_trino_optimizer.rules.findings import RuleFinding

if TYPE_CHECKING:
    from mcp_trino_optimizer.settings import Settings


class RecommendationEngine:
    """Orchestrates scoring, conflict resolution, templates, and session properties.

    Args:
        capability_matrix: Live Trino capabilities, or None for offline mode.
        settings: Application settings for tier thresholds. Defaults used if None.
    """

    def __init__(
        self,
        capability_matrix: Any | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._capability_matrix = capability_matrix
        self._settings = settings

    def _get_thresholds(self) -> tuple[float, float, float]:
        """Get tier thresholds from settings or defaults."""
        if self._settings is not None:
            return (
                self._settings.recommender_tier_p1,
                self._settings.recommender_tier_p2,
                self._settings.recommender_tier_p3,
            )
        return (2.4, 1.2, 0.5)

    def recommend(
        self,
        engine_results: list[Any],
    ) -> RecommendationReport:
        """Run the full recommendation pipeline.

        Args:
            engine_results: List of EngineResult objects (RuleFinding,
                RuleError, RuleSkipped). Only RuleFinding objects are
                processed; errors and skips are filtered out (T-05-06).

        Returns:
            A RecommendationReport with sorted recommendations and
            conflict resolution audit trail.
        """
        # Step a: Filter to only RuleFinding objects
        findings: list[RuleFinding] = [
            r for r in engine_results if isinstance(r, RuleFinding)
        ]

        if not findings:
            return RecommendationReport(recommendations=[], considered_but_rejected=[])

        thresholds = self._get_thresholds()

        # Steps b-e: Score each finding
        scored: list[ScoredFinding] = []
        for finding in findings:
            impact = get_impact(finding.rule_id, finding.evidence)
            priority_score = compute_priority(finding.severity, impact, finding.confidence)
            scored.append(ScoredFinding(finding=finding, priority_score=priority_score))

        # Step f: Resolve conflicts
        winners, rejected = resolve_conflicts(scored)

        # Steps g-i: Build Recommendation objects
        recommendations: list[Recommendation] = []
        for sf in winners:
            finding = sf.finding
            priority_score = sf.priority_score
            tier = assign_tier(priority_score, thresholds)

            # Render narrative
            narrative = render_recommendation(finding.rule_id, finding.evidence)

            # Build session property statements
            session_stmts = build_set_session_statements(
                finding.rule_id, self._capability_matrix
            )

            recommendations.append(
                Recommendation(
                    rule_id=finding.rule_id,
                    severity=finding.severity,
                    confidence=finding.confidence,
                    priority_score=priority_score,
                    priority_tier=tier,
                    operator_ids=finding.operator_ids,
                    reasoning=narrative["reasoning"],
                    expected_impact=narrative["expected_impact"],
                    risk_level=narrative["risk_level"],  # type: ignore[arg-type]
                    validation_steps=narrative["validation_steps"],
                    session_property_statements=session_stmts if session_stmts else None,
                    evidence_summary=finding.evidence,
                )
            )

        # Step j: Sort by priority_score descending
        recommendations.sort(key=lambda r: r.priority_score, reverse=True)

        # Step k: Build report
        return RecommendationReport(
            recommendations=recommendations,
            considered_but_rejected=rejected,
        )


__all__ = ["RecommendationEngine"]
