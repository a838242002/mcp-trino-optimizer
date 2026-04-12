"""R7 CpuSkew — fires when max/median CPU time ratio among operators exceeds threshold.

CPU skew indicates that some workers are doing much more work than others, typically
caused by data skew (hotkey problem), uneven partition distribution, or a single
operator handling disproportionate data volume. This rule requires ExecutedPlan
(EXPLAIN ANALYZE) because it reads actual cpu_time_ms per operator.

Detection logic:
  - Collect cpu_time_ms from all nodes via plan.walk() where cpu_time_ms is not None.
  - If fewer than 3 nodes have cpu_time_ms data, return [] (insufficient data).
  - Compute max_cpu and median (stdlib statistics.median — no numpy).
  - If median == 0.0, return [] (avoid division by zero).
  - If max_cpu / median > thresholds.skew_ratio, fire.

Evidence: PLAN_WITH_METRICS — requires ExecutedPlan runtime metrics.
"""

from __future__ import annotations

import statistics
from typing import ClassVar

from mcp_trino_optimizer.parser.models import BasePlan
from mcp_trino_optimizer.rules.base import Rule
from mcp_trino_optimizer.rules.evidence import EvidenceBundle, EvidenceRequirement
from mcp_trino_optimizer.rules.findings import RuleFinding
from mcp_trino_optimizer.rules.registry import registry
from mcp_trino_optimizer.rules.thresholds import RuleThresholds

_MIN_NODES_FOR_SKEW = 3
"""Minimum number of nodes with cpu_time_ms to compute a meaningful skew ratio."""


class R7CpuSkew(Rule):
    """R7: Operator CPU time skew detected (max/median ratio exceeds threshold).

    When one operator handles disproportionate CPU time relative to the median,
    the query has a skew problem. Common causes: data hotkeys, uneven partition
    distribution, or a single large partition being processed by one worker.
    """

    rule_id: ClassVar[str] = "R7"
    evidence_requirement: ClassVar[EvidenceRequirement] = EvidenceRequirement.PLAN_WITH_METRICS

    def __init__(self, thresholds: RuleThresholds | None = None) -> None:
        self._thresholds = thresholds or RuleThresholds()

    def check(self, plan: BasePlan, evidence: EvidenceBundle) -> list[RuleFinding]:
        """Detect CPU skew across operators."""
        # Collect all non-None cpu_time_ms values along with their node ids
        cpu_values: list[float] = []
        node_ids: list[str] = []

        for node in plan.walk():
            if node.cpu_time_ms is not None:
                cpu_values.append(node.cpu_time_ms)
                node_ids.append(node.id)

        # Insufficient data — need at least 3 nodes for a meaningful comparison
        if len(cpu_values) < _MIN_NODES_FOR_SKEW:
            return []

        max_cpu = max(cpu_values)
        median_cpu = statistics.median(cpu_values)

        # Avoid division by zero — all operators idle
        if median_cpu == 0.0:
            return []

        ratio = max_cpu / median_cpu

        if ratio < self._thresholds.skew_ratio:
            return []

        # Find the id of the node with max cpu_time_ms
        max_idx = cpu_values.index(max_cpu)
        max_node_id = node_ids[max_idx]

        return [
            RuleFinding(
                rule_id="R7",
                severity="high",
                confidence=0.8,
                message=(
                    f"CPU time skew detected: max {max_cpu:.1f}ms vs median "
                    f"{median_cpu:.1f}ms ({ratio:.1f}x ratio > "
                    f"{self._thresholds.skew_ratio}x threshold). "
                    "Check for data skew or hotkeys in the input partitioning."
                ),
                evidence={
                    "max_cpu_ms": max_cpu,
                    "median_cpu_ms": median_cpu,
                    "skew_ratio": ratio,
                    "threshold": self._thresholds.skew_ratio,
                    "node_count": len(cpu_values),
                },
                operator_ids=[max_node_id],
            )
        ]


registry.register(R7CpuSkew)
