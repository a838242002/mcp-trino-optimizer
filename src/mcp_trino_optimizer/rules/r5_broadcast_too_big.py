"""R5 BroadcastTooBig — fires when a REPLICATED join build side is too large.

REPLICATED (broadcast) joins copy the build side to every worker. When the build
side exceeds the join.max-broadcast-table-size (default 100 MB), Trino will spill
or OOM. The CBO should catch this, but with stale or missing statistics it may
choose REPLICATED when PARTITIONED would be safer.

Detection logic:
  - Find all InnerJoin and SemiJoin nodes with descriptor["distribution"] == "REPLICATED".
  - For each, look at children[1] (build side). Guard: if len(children) < 2, skip.
  - Check the build child's estimates[0].output_size_in_bytes (via safe_float).
  - Fire if build_bytes > thresholds.broadcast_max_bytes.

Evidence: PLAN_ONLY — CBO estimates are in the plan JSON.
"""

from __future__ import annotations

from typing import ClassVar

from mcp_trino_optimizer.parser.models import BasePlan, PlanNode
from mcp_trino_optimizer.rules.base import Rule
from mcp_trino_optimizer.rules.evidence import EvidenceBundle, EvidenceRequirement, safe_float
from mcp_trino_optimizer.rules.findings import RuleFinding
from mcp_trino_optimizer.rules.registry import registry
from mcp_trino_optimizer.rules.thresholds import RuleThresholds

_JOIN_TYPES = frozenset({"InnerJoin", "SemiJoin"})


def _get_build_bytes(build_node: PlanNode) -> float | None:
    """Extract outputSizeInBytes from the build side node's first estimate."""
    if not build_node.estimates:
        return None
    return safe_float(build_node.estimates[0].output_size_in_bytes)


class R5BroadcastTooBig(Rule):
    """R5: REPLICATED join build side exceeds broadcast size threshold.

    Fires when the CBO estimate for the build side of a REPLICATED join exceeds
    thresholds.broadcast_max_bytes (default 100 MB). This indicates the join is
    at risk of OOM or excessive memory pressure on all workers.
    """

    rule_id: ClassVar[str] = "R5"
    evidence_requirement: ClassVar[EvidenceRequirement] = EvidenceRequirement.PLAN_ONLY

    def __init__(self, thresholds: RuleThresholds | None = None) -> None:
        self._thresholds = thresholds or RuleThresholds()

    def check(self, plan: BasePlan, evidence: EvidenceBundle) -> list[RuleFinding]:  # noqa: ARG002
        """Detect REPLICATED joins with oversized build sides."""
        findings: list[RuleFinding] = []

        for node in plan.walk():
            if node.operator_type not in _JOIN_TYPES:
                continue
            if node.descriptor.get("distribution") != "REPLICATED":
                continue
            # T-04-13: guard against malformed joins with fewer than 2 children
            if len(node.children) < 2:
                continue

            build_node = node.children[1]
            build_bytes = _get_build_bytes(build_node)

            if build_bytes is None:
                continue
            if build_bytes <= self._thresholds.broadcast_max_bytes:
                continue

            findings.append(
                RuleFinding(
                    rule_id="R5",
                    severity="high",
                    confidence=0.85,
                    message=(
                        f"REPLICATED join (id={node.id}) build side estimated at "
                        f"{build_bytes / (1024 * 1024):.1f} MB exceeds "
                        f"broadcast threshold of "
                        f"{self._thresholds.broadcast_max_bytes / (1024 * 1024):.0f} MB. "
                        "Consider switching to PARTITIONED distribution or reducing the build side."
                    ),
                    evidence={
                        "distribution": "REPLICATED",
                        "build_side_estimated_bytes": build_bytes,
                        "threshold_bytes": self._thresholds.broadcast_max_bytes,
                    },
                    operator_ids=[node.id],
                )
            )

        return findings


registry.register(R5BroadcastTooBig)
