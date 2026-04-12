"""R4 DynamicFiltering — fires when an InnerJoin or SemiJoin lacks dynamic filter pushdown.

Dynamic filtering is Trino's runtime optimization where values from the build side of a
hash join are pushed to the probe side as a bloom filter during execution. When missing,
the probe side scans all rows before the join filter is applied, causing large unnecessary
reads on the probe table.

Detection logic:
  - Find all InnerJoin and SemiJoin nodes via plan.walk().
  - Case 1 (no assignments declared):
    * If the join details list has no "dynamicFilterAssignments" string AND
    * the join has an equality condition (look for "=" in descriptor or detail lines):
    * → R4 fires with severity="medium" (missing opportunity)
  - Case 2 (assignments declared but not pushed to probe):
    * If "dynamicFilterAssignments" IS in details AND
    * the probe-side scan (children[0]) does NOT have "dynamicFilters" in descriptor:
    * → R4 fires with severity="high" (declared but not pushed — worse case)
  - Negative: join has assignments AND probe scan has dynamicFilters → R4 silent.

Helpers:
  - _extract_df_ids(details): regex r"#df_\\w+" to extract dynamic filter IDs
  - _get_probe_scan(join_node): DFS into children[0] to find first scan-type node

Evidence: PLAN_ONLY.
"""

from __future__ import annotations

import re

from mcp_trino_optimizer.parser.models import BasePlan, PlanNode
from mcp_trino_optimizer.rules.base import Rule
from mcp_trino_optimizer.rules.evidence import EvidenceBundle, EvidenceRequirement
from mcp_trino_optimizer.rules.findings import RuleFinding
from mcp_trino_optimizer.rules.registry import registry

_JOIN_TYPES = frozenset({"InnerJoin", "SemiJoin"})
_SCAN_TYPES = frozenset({"TableScan", "ScanFilter", "ScanFilterProject"})

_DF_ID_REGEX = re.compile(r"#df_\w+")
_DF_ASSIGNMENTS_KEY = "dynamicFilterAssignments"
_EQUALITY_PATTERN = re.compile(r"\b\w+\s*=\s*\w+")


def _extract_df_ids(details: list[str]) -> list[str]:
    """Extract dynamic filter IDs (e.g. '#df_388') from a node's details list."""
    ids: list[str] = []
    for line in details:
        ids.extend(_DF_ID_REGEX.findall(line))
    return ids


def _get_probe_scan(join_node: PlanNode) -> PlanNode | None:
    """DFS into the probe side (children[0]) to find the first scan-type node."""
    if not join_node.children:
        return None

    stack = [join_node.children[0]]
    while stack:
        node = stack.pop()
        if node.operator_type in _SCAN_TYPES:
            return node
        stack.extend(reversed(node.children))
    return None


def _has_df_assignments(node: PlanNode) -> bool:
    """Return True if the join node's details contain a dynamicFilterAssignments entry."""
    return any(_DF_ASSIGNMENTS_KEY in line for line in node.details)


def _has_equality_condition(node: PlanNode) -> bool:
    """Return True if the join has an equality condition in descriptor or details."""
    # Check descriptor criteria field
    criteria = node.descriptor.get("criteria", "")
    if "=" in criteria:
        return True
    # Check details strings
    for line in node.details:
        if _EQUALITY_PATTERN.search(line):
            return True
    return False


class R4DynamicFiltering(Rule):
    """R4: InnerJoin or SemiJoin is missing dynamic filter pushdown.

    Fires when a join has an equality condition but the dynamic filter was either
    not declared (severity=medium) or declared but not pushed to the probe scan
    (severity=high).
    """

    rule_id = "R4"
    evidence_requirement = EvidenceRequirement.PLAN_ONLY

    def check(self, plan: BasePlan, evidence: EvidenceBundle) -> list[RuleFinding]:  # noqa: ARG002
        """Detect join nodes missing dynamic filter pushdown."""
        findings: list[RuleFinding] = []

        for node in plan.walk():
            if node.operator_type not in _JOIN_TYPES:
                continue

            has_assignments = _has_df_assignments(node)
            probe_scan = _get_probe_scan(node)

            # Determine if probe scan has dynamic filters applied
            probe_has_df = False
            if probe_scan is not None:
                probe_has_df = bool(probe_scan.descriptor.get("dynamicFilters", ""))

            if has_assignments and probe_has_df:
                # Dynamic filtering is working correctly — no finding
                continue

            df_ids = _extract_df_ids(node.details)

            if has_assignments and not probe_has_df:
                # Case 2: declared but not pushed — more severe
                severity = "high"
                message = (
                    f"Join node (id={node.id}) has dynamicFilterAssignments declared "
                    "but the probe-side scan has no dynamicFilters applied. "
                    "Dynamic filter was not pushed to the probe side."
                )
            elif not has_assignments and _has_equality_condition(node):
                # Case 1: equality join with no dynamic filter at all
                severity = "medium"
                message = (
                    f"Join node (id={node.id}) has an equality join condition but no "
                    "dynamicFilterAssignments. Dynamic filtering opportunity was missed."
                )
            else:
                # Non-equality join or no condition found — skip
                continue

            operator_ids = [node.id]
            if probe_scan is not None:
                operator_ids.append(probe_scan.id)

            findings.append(
                RuleFinding(
                    rule_id="R4",
                    severity=severity,  # type: ignore[arg-type]
                    confidence=0.7,
                    message=message,
                    evidence={
                        "join_has_df_assignments": has_assignments,
                        "probe_has_df_applied": probe_has_df,
                        "dynamic_filter_ids": df_ids,
                    },
                    operator_ids=operator_ids,
                )
            )

        return findings


registry.register(R4DynamicFiltering)
