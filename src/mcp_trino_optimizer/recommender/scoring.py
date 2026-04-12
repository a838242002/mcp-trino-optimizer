"""Priority scoring for recommendations (D-01, D-03).

Implements the deterministic scoring formula:
    priority = severity_weight * impact * confidence

And configurable tier assignment (P1/P2/P3/P4).
"""

from __future__ import annotations

from mcp_trino_optimizer.recommender.models import PriorityTier

SEVERITY_WEIGHTS: dict[str, int] = {
    "critical": 4,
    "high": 3,
    "medium": 2,
    "low": 1,
}
"""Severity to numeric weight mapping. critical=4, high=3, medium=2, low=1."""


def compute_priority(severity: str, impact: float, confidence: float) -> float:
    """Compute the priority score for a finding.

    Formula: severity_weight * impact * confidence (D-01).

    Args:
        severity: One of 'critical', 'high', 'medium', 'low'.
        impact: Impact score from 0.0 to 1.0 (from impact extractor).
        confidence: Confidence score from 0.0 to 1.0 (from RuleFinding).

    Returns:
        Priority score as a float. Max = 4.0 (critical * 1.0 * 1.0).
    """
    weight = SEVERITY_WEIGHTS[severity]
    return weight * impact * confidence


def assign_tier(
    score: float,
    thresholds: tuple[float, float, float] = (2.4, 1.2, 0.5),
) -> PriorityTier:
    """Assign a priority tier based on the score and configurable thresholds.

    Args:
        score: Priority score from compute_priority().
        thresholds: (P1_threshold, P2_threshold, P3_threshold).
            P1 if score >= thresholds[0],
            P2 if score >= thresholds[1],
            P3 if score >= thresholds[2],
            P4 otherwise.

    Returns:
        One of 'P1', 'P2', 'P3', 'P4'.
    """
    if score >= thresholds[0]:
        return "P1"
    if score >= thresholds[1]:
        return "P2"
    if score >= thresholds[2]:
        return "P3"
    return "P4"


__all__ = [
    "SEVERITY_WEIGHTS",
    "assign_tier",
    "compute_priority",
]
