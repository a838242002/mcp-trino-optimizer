"""Recommendation engine — models, scoring, impact, conflicts, templates, session properties.

Converts RuleFinding objects from the rule engine into prioritized
Recommendation objects with deterministic scoring, conflict resolution,
narrative templates, and session property grounding.
"""

from mcp_trino_optimizer.recommender.conflicts import (
    CONFLICT_PAIRS,
    ScoredFinding,
    resolve_conflicts,
)
from mcp_trino_optimizer.recommender.engine import RecommendationEngine
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
from mcp_trino_optimizer.recommender.session_properties import (
    RULE_SESSION_PROPERTIES,
    SESSION_PROPERTIES,
    SessionProperty,
    build_set_session_statements,
)
from mcp_trino_optimizer.recommender.templates import (
    TEMPLATES,
    render_recommendation,
)

__all__ = [
    "CONFLICT_PAIRS",
    "DEFAULT_IMPACT",
    "RULE_SESSION_PROPERTIES",
    "SESSION_PROPERTIES",
    "SEVERITY_WEIGHTS",
    "TEMPLATES",
    "BottleneckEntry",
    "BottleneckRanking",
    "ConsideredButRejected",
    "HealthScore",
    "IcebergTableHealth",
    "PriorityTier",
    "Recommendation",
    "RecommendationEngine",
    "RecommendationReport",
    "RiskLevel",
    "ScoredFinding",
    "SessionProperty",
    "assign_tier",
    "build_set_session_statements",
    "compute_priority",
    "get_impact",
    "register_impact",
    "render_recommendation",
    "resolve_conflicts",
]
