"""Recommendation engine — models, scoring, and impact extraction.

Converts RuleFinding objects from the rule engine into prioritized
Recommendation objects with deterministic scoring.
"""

from mcp_trino_optimizer.recommender.impact import (
    DEFAULT_IMPACT,
    get_impact,
    register_impact,
)
from mcp_trino_optimizer.recommender.models import (
    BottleneckEntry,
    BottleneckRanking,
    ConsideredButRejected,
    HealthScore,
    IcebergTableHealth,
    PriorityTier,
    Recommendation,
    RecommendationReport,
    RiskLevel,
)
from mcp_trino_optimizer.recommender.scoring import (
    SEVERITY_WEIGHTS,
    assign_tier,
    compute_priority,
)

__all__ = [
    "DEFAULT_IMPACT",
    "SEVERITY_WEIGHTS",
    "BottleneckEntry",
    "BottleneckRanking",
    "ConsideredButRejected",
    "HealthScore",
    "IcebergTableHealth",
    "PriorityTier",
    "Recommendation",
    "RecommendationReport",
    "RiskLevel",
    "assign_tier",
    "compute_priority",
    "get_impact",
    "register_impact",
]
