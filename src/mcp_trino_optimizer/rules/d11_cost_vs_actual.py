"""D11 CostVsActual — fires when CBO row estimate diverges significantly from actual.

The cost-based optimizer (CBO) uses statistics to estimate row counts. When the
actual row count (from EXPLAIN ANALYZE) diverges by more than stats_divergence_factor
(default 5x) from the estimate, the statistics are stale or missing. This root-cause
evidence directly explains why R1, R5, R6, and R8 may have triggered — bad estimates
cascade into bad join orders, broadcast decisions, and memory grants.

Detection logic:
  - Find all TableScan, ScanFilter, ScanFilterProject nodes via plan.walk().
  - For each scan node:
    * estimated = safe_float(node.estimates[0].output_row_count) if estimates present
    * actual = node.output_rows (int | None; only populated for ExecutedPlan)
    * Skip if estimated is None (NaN or missing) or actual is None or actual == 0.
    * divergence = actual / estimated  (how many times larger actual is than estimated)
    * Also check inverse: estimated / actual (over-estimate case)
    * Fire if max(divergence, 1/divergence) > threshold
      Equivalently: divergence > factor OR divergence < 1/factor
  - severity: high (stale stats are a root cause, not just a symptom)
  - confidence: 0.95 (actual vs estimated is direct measurement evidence)

Evidence: PLAN_WITH_METRICS — requires ExecutedPlan runtime metrics.

Threat T-04-11 mitigated:
  - safe_float() guards NaN estimates.
  - Division by zero guarded by `if estimated <= 0` and `if actual == 0`.
  - Both over- and under-estimate directions are checked.
"""

from __future__ import annotations

from typing import ClassVar

from mcp_trino_optimizer.parser.models import BasePlan
from mcp_trino_optimizer.rules.base import Rule
from mcp_trino_optimizer.rules.evidence import EvidenceBundle, EvidenceRequirement, safe_float
from mcp_trino_optimizer.rules.findings import RuleFinding
from mcp_trino_optimizer.rules.registry import registry
from mcp_trino_optimizer.rules.thresholds import RuleThresholds

_SCAN_TYPES = frozenset({"TableScan", "ScanFilter", "ScanFilterProject"})


class D11CostVsActual(Rule):
    """D11: CBO row estimate diverges significantly from actual row count.

    When the CBO estimate is off by more than stats_divergence_factor (default 5x)
    in either direction, statistics are stale or missing. This is the root cause
    evidence for most cost-model failures.
    """

    rule_id: ClassVar[str] = "D11"
    evidence_requirement: ClassVar[EvidenceRequirement] = EvidenceRequirement.PLAN_WITH_METRICS

    def __init__(self, thresholds: RuleThresholds | None = None) -> None:
        self._thresholds = thresholds or RuleThresholds()

    def check(self, plan: BasePlan, evidence: EvidenceBundle) -> list[RuleFinding]:
        """Detect scan nodes where CBO estimate diverges from actual rows."""
        findings: list[RuleFinding] = []
        factor = self._thresholds.stats_divergence_factor

        for node in plan.walk():
            if node.operator_type not in _SCAN_TYPES:
                continue

            # Get CBO estimate (NaN-safe)
            estimated: float | None = None
            if node.estimates:
                estimated = safe_float(node.estimates[0].output_row_count)

            # Skip if estimate is missing or NaN
            if estimated is None:
                continue
            # Avoid division by zero in the inverse check
            if estimated <= 0:
                continue

            # Get actual rows (only populated for ExecutedPlan)
            actual = node.output_rows
            if actual is None or actual == 0:
                continue

            # Compute divergence in both directions
            # actual / estimated: how many times actual exceeds estimate
            divergence = actual / estimated

            # Check both directions: under-estimate (divergence > factor)
            # and over-estimate (estimated >> actual, i.e. divergence < 1/factor)
            if divergence <= factor and divergence >= (1.0 / factor):
                continue

            # Magnitude: always >= 1.0 so evidence is human-readable
            # regardless of direction (under-estimate or over-estimate).
            magnitude = divergence if divergence >= 1.0 else (1.0 / divergence)

            findings.append(
                RuleFinding(
                    rule_id="D11",
                    severity="high",
                    confidence=0.95,
                    message=(
                        f"CBO estimate {estimated:.0f} rows diverged {magnitude:.1f}x "
                        f"from actual {actual} rows "
                        f"(threshold: {factor}x). "
                        "Run ANALYZE to refresh table statistics."
                    ),
                    evidence={
                        "estimated_rows": estimated,
                        "actual_rows": actual,
                        "divergence_factor": magnitude,
                        "threshold": factor,
                    },
                    operator_ids=[node.id],
                )
            )

        return findings


registry.register(D11CostVsActual)
