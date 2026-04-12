"""R2 PartitionPruning — fires when an Iceberg scan has a filter predicate but
the Trino planner did not apply partition pruning (no "constraint on [" in
the table descriptor).

Without partition pruning Trino reads all Iceberg partitions regardless of the
predicate, causing full table scans on partitioned tables. This is the most
common single cause of unexpectedly slow queries on partitioned Iceberg tables.

Detection logic:
  - Iterate scan nodes (TableScan, ScanFilter, ScanFilterProject).
  - Skip nodes with no filterPredicate in descriptor (no predicate = no opportunity).
  - Skip nodes whose descriptor["table"] already contains "constraint on [" (pruning
    was applied).
  - Only fire for Iceberg tables (descriptor["table"] contains "iceberg:").
  - Return one RuleFinding per affected scan node.

Evidence: TABLE_STATS (for potential row-count secondary signal; PLAN_ONLY suffices
for detection but TABLE_STATS is declared to allow future ratio calculation).
"""

from __future__ import annotations

import re

from mcp_trino_optimizer.parser.models import BasePlan, PlanNode
from mcp_trino_optimizer.rules.base import Rule
from mcp_trino_optimizer.rules.evidence import EvidenceBundle, EvidenceRequirement
from mcp_trino_optimizer.rules.findings import RuleFinding
from mcp_trino_optimizer.rules.registry import registry

_SCAN_TYPES = frozenset({"TableScan", "ScanFilter", "ScanFilterProject"})

# T-04-03: cap table_str length before regex to prevent ReDoS
_TABLE_STR_MAX_LEN = 1000

# Pattern for "constraint on [" in table descriptor
_CONSTRAINT_PREFIX = "constraint on ["


def _has_partition_constraint(node: PlanNode) -> bool:
    """Return True if the node's table descriptor indicates partition pruning was applied."""
    table_str = node.descriptor.get("table", "")[:_TABLE_STR_MAX_LEN]
    return _CONSTRAINT_PREFIX in table_str


def _is_iceberg_table(node: PlanNode) -> bool:
    """Return True if the table descriptor indicates an Iceberg table."""
    table_str = node.descriptor.get("table", "")[:_TABLE_STR_MAX_LEN]
    return "iceberg:" in table_str


def _get_version_note(plan: BasePlan) -> str | None:
    """Return a version-specific note if partition pruning was limited in this version."""
    version = plan.source_trino_version
    if version is None:
        return None
    # Parse major version number
    match = re.match(r"(\d+)", version)
    if match:
        major = int(match.group(1))
        if major < 440:
            return "partial_alignment_pruning_unavailable"
    return None


class R2PartitionPruning(Rule):
    """R2: Iceberg scan has a filter predicate but partition pruning was not applied.

    Fires when a scan node has a non-empty filterPredicate but the Trino plan
    shows no "constraint on [" in the table descriptor, meaning all partitions
    were scanned regardless of the predicate.
    """

    rule_id = "R2"
    evidence_requirement = EvidenceRequirement.TABLE_STATS

    def check(self, plan: BasePlan, evidence: EvidenceBundle) -> list[RuleFinding]:  # noqa: ARG002
        """Detect Iceberg scans with filters but no partition constraint applied."""
        findings: list[RuleFinding] = []

        version_note = _get_version_note(plan)

        for node in plan.walk():
            if node.operator_type not in _SCAN_TYPES:
                continue

            # No filterPredicate → no pushdown opportunity missed
            filter_predicate = node.descriptor.get("filterPredicate", "")
            if not filter_predicate:
                continue

            # Only fire for Iceberg tables
            if not _is_iceberg_table(node):
                continue

            # Partition pruning was already applied → no finding
            if _has_partition_constraint(node):
                continue

            table_str = node.descriptor.get("table", "")

            evidence_dict: dict[str, object] = {
                "filter_predicate": filter_predicate,
                "table": table_str,
                "has_partition_constraint": False,
            }
            if version_note:
                evidence_dict["version_note"] = version_note

            findings.append(
                RuleFinding(
                    rule_id="R2",
                    severity="high",
                    confidence=0.8,
                    message=(
                        f"Scan node '{node.operator_type}' (id={node.id}) has a filter "
                        f"predicate but no Iceberg partition constraint was applied. "
                        "The query may be scanning all partitions."
                    ),
                    evidence=evidence_dict,
                    operator_ids=[node.id],
                )
            )

        return findings


registry.register(R2PartitionPruning)
