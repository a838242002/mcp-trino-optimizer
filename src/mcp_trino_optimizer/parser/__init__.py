"""Public API for the mcp-trino-optimizer plan parser.

Three entry points:
- parse_estimated_plan: EXPLAIN (FORMAT JSON) -> EstimatedPlan
- parse_executed_plan: EXPLAIN ANALYZE text -> ExecutedPlan
- parse_distributed_plan: EXPLAIN (TYPE DISTRIBUTED) text -> EstimatedPlan

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
from mcp_trino_optimizer.parser.parser import (
    parse_distributed_plan,
    parse_estimated_plan,
    parse_executed_plan,
)

__all__ = [
    "BasePlan",
    "CostEstimate",
    "EstimatedPlan",
    "ExecutedPlan",
    "OutputSymbol",
    "ParseError",
    "PlanNode",
    "SchemaDriftWarning",
    "parse_distributed_plan",
    "parse_estimated_plan",
    "parse_executed_plan",
]
