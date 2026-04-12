"""R1 MissingStats — fires when a scan node has no reliable row count estimate.

Missing statistics is the root cause of most join-order and cost-model failures in
Trino. When the CBO cannot estimate row counts it falls back to default assumptions
that often produce wildly wrong join orders, broadcast join choices, and memory grants.

Detection logic:
  - Iterate all nodes via plan.walk().
  - For nodes with operator_type in (TableScan, ScanFilter, ScanFilterProject):
    * estimates[0].output_row_count is None or NaN (use safe_float), OR
    * evidence.table_stats is None, OR
    * evidence.table_stats.get("row_count") is None
  - Fire one RuleFinding per affected scan node.

Evidence: TABLE_STATS — requires a SHOW STATS response to cross-check.
"""

from __future__ import annotations

import math

from mcp_trino_optimizer.parser.models import BasePlan, PlanNode
from mcp_trino_optimizer.rules.base import Rule
from mcp_trino_optimizer.rules.evidence import EvidenceBundle, EvidenceRequirement, safe_float
from mcp_trino_optimizer.rules.findings import RuleFinding
from mcp_trino_optimizer.rules.registry import registry

_SCAN_TYPES = frozenset({"TableScan", "ScanFilter", "ScanFilterProject"})


def _is_stats_missing(node: PlanNode, table_stats_row_count: float | None) -> bool:
    """Return True if either the CBO estimate or table stats indicate missing stats."""
    # Check CBO estimate
    estimate_missing = True
    if node.estimates:
        val = safe_float(node.estimates[0].output_row_count)
        if val is not None:
            estimate_missing = False

    # Check table_stats row_count
    stats_missing = table_stats_row_count is None

    # Fire if either signal is missing
    return estimate_missing or stats_missing


class R1MissingStats(Rule):
    """R1: Scan node has no reliable row count estimate.

    Fires when the CBO estimate is NaN/None or the SHOW STATS row_count is absent.
    Missing stats causes poor join ordering, broadcast-join misclassification, and
    excessive memory grants.
    """

    rule_id = "R1"
    evidence_requirement = EvidenceRequirement.TABLE_STATS

    def check(self, plan: BasePlan, evidence: EvidenceBundle) -> list[RuleFinding]:  # noqa: ARG002
        """Detect scan nodes missing reliable row count statistics."""
        findings: list[RuleFinding] = []

        # Extract table_stats row_count once (applies to all scan nodes in this plan)
        table_stats_row_count: float | None = None
        if evidence.table_stats is not None:
            raw_rc = evidence.table_stats.get("row_count")
            if raw_rc is not None:
                f = safe_float(raw_rc)
                table_stats_row_count = f  # None if NaN
        # If evidence.table_stats is None → table_stats_row_count stays None

        for node in plan.walk():
            if node.operator_type not in _SCAN_TYPES:
                continue

            # Determine per-estimate NaN status
            estimated_row_count: float | None = None
            if node.estimates:
                estimated_row_count = safe_float(node.estimates[0].output_row_count)

            stats_row_count = table_stats_row_count

            if not _is_stats_missing(node, table_stats_row_count):
                continue

            # Determine confidence
            # High confidence (0.9) when SHOW STATS confirms no row_count
            # Lower confidence (0.7) when only the CBO estimate is NaN
            if evidence.table_stats is None or evidence.table_stats.get("row_count") is None:
                confidence = 0.9
            else:
                confidence = 0.7

            findings.append(
                RuleFinding(
                    rule_id="R1",
                    severity="critical",
                    confidence=confidence,
                    message=(
                        f"Scan node '{node.operator_type}' (id={node.id}) has no reliable "
                        "row count estimate. Missing table statistics cause poor join ordering "
                        "and memory grant decisions."
                    ),
                    evidence={
                        "estimated_row_count": estimated_row_count,
                        "table_stats_row_count": stats_row_count,
                        "operator_type": node.operator_type,
                    },
                    operator_ids=[node.id],
                )
            )

        return findings


registry.register(R1MissingStats)
