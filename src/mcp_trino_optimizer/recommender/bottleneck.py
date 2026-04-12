"""Operator bottleneck ranking from ExecutedPlan metrics (REC-07).

Walks ExecutedPlan nodes, computes CPU time percentages, associates
related rule findings, and produces a ranked list of top-N operators.

Returns None for EstimatedPlan (no runtime metrics available).

T-05-08: O(n) single walk; top_n bounded by settings (max 50).
T-05-09: Narrative uses only PlanNode typed fields, no user-origin strings.
"""

from __future__ import annotations

from mcp_trino_optimizer.parser.models import BasePlan, ExecutedPlan, PlanNode
from mcp_trino_optimizer.recommender.models import BottleneckEntry, BottleneckRanking
from mcp_trino_optimizer.rules.findings import RuleFinding

BOTTLENECK_NARRATIVE = (
    "Operator {operator_id} ({operator_type}) consumed {cpu_pct:.1f}% of total CPU "
    "({cpu_time_ms:.0f}ms). {detail}"
)
"""Template for bottleneck narrative. Uses only typed PlanNode fields."""


def rank_bottlenecks(
    plan: BasePlan,
    findings: list[RuleFinding],
    top_n: int = 5,
) -> BottleneckRanking | None:
    """Rank operators by CPU time contribution from an ExecutedPlan.

    Args:
        plan: The query plan. Must be ExecutedPlan for bottleneck analysis.
        findings: Rule findings to associate with operators by operator_ids.
        top_n: Maximum number of operators to include in ranking.

    Returns:
        BottleneckRanking with top-N operators, or None if:
        - plan is not ExecutedPlan (Pitfall 5)
        - No nodes have cpu_time_ms
        - Total CPU time is 0
    """
    # Only ExecutedPlan has runtime metrics
    if not isinstance(plan, ExecutedPlan):
        return None

    # Walk plan once, collect nodes with CPU metrics
    nodes_with_cpu: list[PlanNode] = []
    for node in plan.walk():
        if node.cpu_time_ms is not None:
            nodes_with_cpu.append(node)

    if not nodes_with_cpu:
        return None

    total_cpu = sum(n.cpu_time_ms for n in nodes_with_cpu if n.cpu_time_ms is not None)
    if total_cpu == 0:
        return None

    # Sort by CPU descending, take top_n
    nodes_with_cpu.sort(key=lambda n: n.cpu_time_ms or 0.0, reverse=True)
    top_nodes = nodes_with_cpu[:top_n]

    # Build operator -> related findings mapping
    entries: list[BottleneckEntry] = []
    for node in top_nodes:
        cpu_ms = node.cpu_time_ms or 0.0
        wall_ms = node.wall_time_ms or 0.0
        cpu_pct = (cpu_ms / total_cpu) * 100.0

        # Find related findings by operator_id
        related = [f.rule_id for f in findings if node.id in f.operator_ids]

        # Build narrative detail
        if related:
            detail = f"Related findings: {', '.join(sorted(related))}"
        else:
            detail = "No specific findings for this operator."

        narrative = BOTTLENECK_NARRATIVE.format(
            operator_id=node.id,
            operator_type=node.operator_type,
            cpu_pct=cpu_pct,
            cpu_time_ms=cpu_ms,
            detail=detail,
        )

        entries.append(
            BottleneckEntry(
                operator_id=node.id,
                operator_type=node.operator_type,
                cpu_time_ms=cpu_ms,
                wall_time_ms=wall_ms,
                cpu_pct=cpu_pct,
                input_rows=node.input_rows,
                output_rows=node.output_rows,
                peak_memory_bytes=node.peak_memory_bytes,
                related_findings=related,
                narrative=narrative,
            )
        )

    return BottleneckRanking(
        top_operators=entries,
        total_cpu_time_ms=total_cpu,
        plan_type="executed",
        top_n=top_n,
    )


__all__ = [
    "BOTTLENECK_NARRATIVE",
    "rank_bottlenecks",
]
