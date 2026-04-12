"""R6 JoinOrderInversion — fires when probe side is much larger than build side.

In a hash join, the smaller table should be the build side (hashed into memory).
When the probe side has far more estimated rows than the build side, the join order
may be inverted — either due to missing statistics or a CBO bug. Without stats,
we cannot be certain the inversion is wrong, so confidence is moderate (0.6).

Detection logic:
  - Find all InnerJoin and SemiJoin nodes.
  - Guard: if len(children) < 2, skip (T-04-13).
  - probe_rows = safe_float(children[0].estimates[0].output_row_count)
  - build_rows = safe_float(children[1].estimates[0].output_row_count)
  - Skip if either is None (no estimate available).
  - If probe_rows / build_rows > _JOIN_ORDER_RATIO_THRESHOLD (100.0):
    - AND evidence.table_stats is None or table_stats.get("row_count") is None:
      fire R6.
  - The 100x threshold is a detection heuristic, not user-tunable.
    Citation: Trino join-reordering doc; 100x is the empirical boundary where
    probe-as-larger is almost always a mistake (not a deliberate outer-join ordering).

Evidence: TABLE_STATS — stats presence suppresses the finding.
"""

from __future__ import annotations

from typing import ClassVar

from mcp_trino_optimizer.parser.models import BasePlan
from mcp_trino_optimizer.rules.base import Rule
from mcp_trino_optimizer.rules.evidence import EvidenceBundle, EvidenceRequirement, safe_float
from mcp_trino_optimizer.rules.findings import RuleFinding
from mcp_trino_optimizer.rules.registry import registry

_JOIN_TYPES = frozenset({"InnerJoin", "SemiJoin"})

# 100x is the detection heuristic threshold for probe-to-build row ratio.
# Citation: Trino join reordering semantics — when probe is >100x the build,
# the join order is almost certainly inverted (not deliberate).
_JOIN_ORDER_RATIO_THRESHOLD = 100.0


class R6JoinOrderInversion(Rule):
    """R6: Join order may be inverted (large probe, small build, no stats to confirm).

    Fires when the probe side has more than 100x the estimated rows of the build side
    and table statistics are absent. When stats are present, CBO may have a valid
    reason for the order (e.g., anti-join semantics, semi-join selectivity).
    """

    rule_id: ClassVar[str] = "R6"
    evidence_requirement: ClassVar[EvidenceRequirement] = EvidenceRequirement.TABLE_STATS

    def check(self, plan: BasePlan, evidence: EvidenceBundle) -> list[RuleFinding]:
        """Detect potentially inverted join orders."""
        findings: list[RuleFinding] = []

        # Check if stats are available — suppress R6 when stats present
        stats_available = evidence.table_stats is not None and evidence.table_stats.get("row_count") is not None

        for node in plan.walk():
            if node.operator_type not in _JOIN_TYPES:
                continue
            # T-04-13: guard against malformed single-child joins
            if len(node.children) < 2:
                continue

            # Extract probe and build row estimates
            probe_node = node.children[0]
            build_node = node.children[1]

            probe_rows: float | None = None
            if probe_node.estimates:
                probe_rows = safe_float(probe_node.estimates[0].output_row_count)

            build_rows: float | None = None
            if build_node.estimates:
                build_rows = safe_float(build_node.estimates[0].output_row_count)

            # Skip if either estimate is missing or NaN
            if probe_rows is None or build_rows is None:
                continue
            # Avoid division by zero
            if build_rows == 0.0:
                continue

            ratio = probe_rows / build_rows

            # Only fire if ratio exceeds threshold AND no stats to validate
            if ratio <= _JOIN_ORDER_RATIO_THRESHOLD:
                continue
            if stats_available:
                continue

            findings.append(
                RuleFinding(
                    rule_id="R6",
                    severity="medium",
                    confidence=0.6,
                    message=(
                        f"Join (id={node.id}) probe side has {probe_rows:.0f} estimated rows "
                        f"vs build side {build_rows:.0f} rows ({ratio:.0f}x ratio). "
                        "Without table statistics, join order inversion cannot be ruled out. "
                        "Run ANALYZE on the involved tables."
                    ),
                    evidence={
                        "probe_estimated_rows": probe_rows,
                        "build_estimated_rows": build_rows,
                        "probe_to_build_ratio": ratio,
                        "stats_available": stats_available,
                    },
                    operator_ids=[node.id],
                )
            )

        return findings


registry.register(R6JoinOrderInversion)
