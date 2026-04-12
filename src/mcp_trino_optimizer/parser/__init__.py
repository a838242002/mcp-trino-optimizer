"""Public API for the mcp-trino-optimizer plan parser.

Two entry points:
- parse_estimated_plan: EXPLAIN (FORMAT JSON) -> EstimatedPlan
- parse_executed_plan: EXPLAIN ANALYZE text -> ExecutedPlan

Domain types re-exported for consumer convenience.
"""

from mcp_trino_optimizer.parser.models import (
    BasePlan,
    CostEstimate,
    EstimatedPlan,
    ExecutedPlan,
    OutputSymbol,
    ParseError,
    PlanNode,
    SchemaDriftWarning,
)
from mcp_trino_optimizer.parser.parser import parse_estimated_plan, parse_executed_plan

__all__ = [
    "BasePlan",
    "CostEstimate",
    "EstimatedPlan",
    "ExecutedPlan",
    "OutputSymbol",
    "ParseError",
    "PlanNode",
    "SchemaDriftWarning",
    "parse_estimated_plan",
    "parse_executed_plan",
]
