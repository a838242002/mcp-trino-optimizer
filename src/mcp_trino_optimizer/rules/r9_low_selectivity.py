"""R9 LowSelectivity — fires when a scan reads far more data than it outputs.

A scan with low selectivity (output_bytes / input_bytes < threshold) is reading
large amounts of data but filtering most of it away. This is a strong signal of:
  - Missing partition pruning (should be R2, but this catches byte-level evidence)
  - Full file scans when predicate pushdown would help
  - Missing or misconfigured Iceberg partition transforms

This rule reads actual runtime bytes (input_bytes, output_bytes on PlanNode),
which are only populated for ExecutedPlan. EstimatedPlan nodes have these as None
so the rule silently skips them. The rule declares PLAN_ONLY evidence (no external
fetches needed) but effectively only fires on ExecutedPlan data.

Detection logic:
  - Find all TableScan, ScanFilter, ScanFilterProject nodes via plan.walk().
  - For each, check node.input_bytes and node.output_bytes (actual runtime metrics).
  - Skip if either is None (no runtime data — EstimatedPlan case).
  - Skip if input_bytes == 0 (avoid division by zero).
  - Compute ratio = output_bytes / input_bytes.
  - Fire if ratio < thresholds.scan_selectivity_threshold.

Evidence: PLAN_ONLY — no external fetches; reads actual bytes from plan node fields.
"""

from __future__ import annotations

from typing import ClassVar

from mcp_trino_optimizer.parser.models import BasePlan
from mcp_trino_optimizer.rules.base import Rule
from mcp_trino_optimizer.rules.evidence import EvidenceBundle, EvidenceRequirement
from mcp_trino_optimizer.rules.findings import RuleFinding
from mcp_trino_optimizer.rules.registry import registry
from mcp_trino_optimizer.rules.thresholds import RuleThresholds

_SCAN_TYPES = frozenset({"TableScan", "ScanFilter", "ScanFilterProject"})


class R9LowSelectivity(Rule):
    """R9: Scan node reads significantly more data than it outputs.

    When output bytes are less than scan_selectivity_threshold (default 10%) of
    input bytes, the scan is filtering most of what it reads. This wastes I/O and
    CPU — investigate partition pruning, predicate pushdown, and file layout.
    """

    rule_id: ClassVar[str] = "R9"
    evidence_requirement: ClassVar[EvidenceRequirement] = EvidenceRequirement.PLAN_ONLY

    def __init__(self, thresholds: RuleThresholds | None = None) -> None:
        self._thresholds = thresholds or RuleThresholds()

    def check(self, plan: BasePlan, evidence: EvidenceBundle) -> list[RuleFinding]:  # noqa: ARG002
        """Detect scan nodes with low byte-level selectivity."""
        findings: list[RuleFinding] = []

        for node in plan.walk():
            if node.operator_type not in _SCAN_TYPES:
                continue

            input_bytes = node.input_bytes
            output_bytes = node.output_bytes

            # Skip if actual byte metrics are absent (EstimatedPlan case)
            if input_bytes is None or output_bytes is None:
                continue
            # Avoid division by zero
            if input_bytes == 0:
                continue

            ratio = output_bytes / input_bytes

            if ratio >= self._thresholds.scan_selectivity_threshold:
                continue

            table = node.descriptor.get("table", "")
            findings.append(
                RuleFinding(
                    rule_id="R9",
                    severity="medium",
                    confidence=0.9,
                    message=(
                        f"Scan '{node.operator_type}' (id={node.id}) has low selectivity: "
                        f"{ratio:.1%} of bytes read were output "
                        f"(threshold: {self._thresholds.scan_selectivity_threshold:.0%}). "
                        "Consider partition pruning, predicate pushdown, or file compaction."
                    ),
                    evidence={
                        "input_bytes": input_bytes,
                        "output_bytes": output_bytes,
                        "selectivity_ratio": ratio,
                        "threshold": self._thresholds.scan_selectivity_threshold,
                        "table": table,
                    },
                    operator_ids=[node.id],
                )
            )

        return findings


registry.register(R9LowSelectivity)
