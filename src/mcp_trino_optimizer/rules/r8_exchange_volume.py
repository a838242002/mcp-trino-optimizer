"""R8 ExchangeVolume — fires when total exchange bytes exceed total scan bytes.

Exchange nodes shuffle data between workers. When the total bytes shuffled exceeds
the total bytes read from storage, the query is spending more network/memory on
redistribution than on I/O — a strong signal of a missing partition pruning,
unnecessary cross-join broadcast, or poor distribution key choice.

Detection logic:
  - Walk the entire plan tree.
  - exchange_bytes: sum of output_size_in_bytes from Exchange, LocalExchange,
    RemoteSource nodes (via safe_float; skip None).
  - scan_bytes: sum of output_size_in_bytes from TableScan, ScanFilter,
    ScanFilterProject nodes (via safe_float; skip None).
  - Fire if exchange_bytes > scan_bytes AND both > 0.

Evidence: PLAN_ONLY — uses CBO estimates from the plan JSON.
"""

from __future__ import annotations

from typing import ClassVar

from mcp_trino_optimizer.parser.models import BasePlan, PlanNode
from mcp_trino_optimizer.rules.base import Rule
from mcp_trino_optimizer.rules.evidence import EvidenceBundle, EvidenceRequirement, safe_float
from mcp_trino_optimizer.rules.findings import RuleFinding
from mcp_trino_optimizer.rules.registry import registry

_EXCHANGE_TYPES = frozenset({"Exchange", "LocalExchange", "RemoteSource"})
_SCAN_TYPES = frozenset({"TableScan", "ScanFilter", "ScanFilterProject"})


def _node_output_bytes(node: PlanNode) -> float | None:
    """Return safe_float of the node's first estimate output_size_in_bytes."""
    if not node.estimates:
        return None
    return safe_float(node.estimates[0].output_size_in_bytes)


class R8ExchangeVolume(Rule):
    """R8: Total exchange volume exceeds total scan volume.

    When more bytes are shuffled between workers than were read from storage,
    the query has a distribution problem. Common causes: missing partition pruning,
    wrong distribution key, or implicit cross-join broadcast.
    """

    rule_id: ClassVar[str] = "R8"
    evidence_requirement: ClassVar[EvidenceRequirement] = EvidenceRequirement.PLAN_ONLY

    def check(self, plan: BasePlan, evidence: EvidenceBundle) -> list[RuleFinding]:
        """Detect plans where exchange volume exceeds scan volume."""
        exchange_bytes = 0.0
        scan_bytes = 0.0
        exchange_node_ids: list[str] = []

        for node in plan.walk():
            if node.operator_type in _EXCHANGE_TYPES:
                val = _node_output_bytes(node)
                if val is not None:
                    exchange_bytes += val
                    exchange_node_ids.append(node.id)
            elif node.operator_type in _SCAN_TYPES:
                val = _node_output_bytes(node)
                if val is not None:
                    scan_bytes += val

        # Require both non-zero to compute a meaningful ratio
        if exchange_bytes <= 0 or scan_bytes <= 0:
            return []
        if exchange_bytes <= scan_bytes:
            return []

        ratio = exchange_bytes / scan_bytes
        return [
            RuleFinding(
                rule_id="R8",
                severity="medium",
                confidence=0.75,
                message=(
                    f"Total exchange volume ({exchange_bytes / (1024 * 1024):.1f} MB) "
                    f"exceeds total scan volume ({scan_bytes / (1024 * 1024):.1f} MB) "
                    f"by {ratio:.1f}x. This indicates excessive data redistribution. "
                    "Check distribution keys, partition pruning, and join strategies."
                ),
                evidence={
                    "total_exchange_bytes": exchange_bytes,
                    "total_scan_bytes": scan_bytes,
                    "ratio": ratio,
                },
                operator_ids=exchange_node_ids,
            )
        ]


registry.register(R8ExchangeVolume)
