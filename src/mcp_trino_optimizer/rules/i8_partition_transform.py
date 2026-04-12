"""I8 PartitionTransform — fires when a query predicate's boundary is not aligned
to the Iceberg partition transform granularity.

When a table uses day(ts) partitioning but a query's WHERE clause uses a sub-day
boundary (e.g. WHERE ts BETWEEN '2025-01-15 10:30:00' AND ...), Trino must read
the entire partition for the boundary day instead of skipping it. This causes
unnecessary I/O for all rows in that day partition.

Without access to the actual Iceberg partition spec (which requires catalog metadata
that is not always present in the plan), this rule uses best-effort detection:
any constraint range on a timestamp column whose lower bound is NOT day-aligned is
flagged as potentially misaligned. Confidence is deliberately low (0.6) to reflect
this uncertainty.

Evidence: ICEBERG_METADATA — requires CatalogSource. Engine emits RuleSkipped
when catalog_source is None (offline mode).

Detection:
  1. Find scan nodes whose descriptor["table"] contains "constraint on ["
  2. For each such node, look for detail lines containing "::" and range brackets
     "[[...UTC, ...UTC)]"
  3. Parse the lower bound timestamp from the range
  4. If lower bound is not day-aligned (hour != 0 or minute != 0 or second != 0)
     → emit finding with confidence=0.6

T-04-15 mitigation: cap detail strings at 1000 chars before regex; wrap in
try/except to catch any backtracking edge case.

References:
  - Trino issue #19266: partition-transform pruning semantics per Trino version
  - Iceberg partition spec: day/month/year transforms truncate to day/month/year UTC
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from mcp_trino_optimizer.parser.models import BasePlan, PlanNode
from mcp_trino_optimizer.rules.base import Rule
from mcp_trino_optimizer.rules.evidence import EvidenceBundle, EvidenceRequirement
from mcp_trino_optimizer.rules.findings import RuleFinding
from mcp_trino_optimizer.rules.registry import registry
from mcp_trino_optimizer.rules.thresholds import RuleThresholds

# T-04-15: cap detail string length before regex to bound regex work
_DETAIL_MAX_LEN = 1000

# Regex to extract the lower bound timestamp from a Trino constraint range detail line.
# Pattern: [[YYYY-MM-DD HH:MM:SS[.ffffff] UTC, ...]
# Uses a bounded non-backtracking pattern: explicit character classes, no .*
_LOWER_BOUND_RE = re.compile(r"\[\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:\.\d+)? UTC)")

# Regex to extract constraint column name from descriptor["table"]
_CONSTRAINT_COL_RE = re.compile(r"constraint on \[([^\]]+)\]")


def _parse_lower_bound(detail_line: str) -> datetime | None:
    """Extract and parse the lower bound timestamp from a Trino constraint detail line.

    Input example: "ts := ... :: [[2025-01-15 10:30:00 UTC, 2025-01-16 00:00:00 UTC)]"

    Returns None if no parseable lower bound is found.
    T-04-15: input must already be capped at _DETAIL_MAX_LEN before calling.
    """
    try:
        m = _LOWER_BOUND_RE.search(detail_line)
        if not m:
            return None
        ts_str = m.group(1).replace(" UTC", "+00:00")
        return datetime.fromisoformat(ts_str)
    except (ValueError, AttributeError):
        return None


def _is_day_aligned(dt: datetime) -> bool:
    """Return True if dt is exactly at midnight UTC (hour=0, minute=0, second=0, microsecond=0)."""
    return dt.hour == 0 and dt.minute == 0 and dt.second == 0 and dt.microsecond == 0


def _is_hour_aligned(dt: datetime) -> bool:
    """Return True if dt is exactly on the hour (minute=0, second=0, microsecond=0)."""
    return dt.minute == 0 and dt.second == 0 and dt.microsecond == 0


def _extract_constraint_column(table_str: str) -> str | None:
    """Extract the first constraint column name from a table descriptor string.

    Input: "iceberg:analytics.events constraint on [ts]"
    Returns: "ts"
    """
    m = _CONSTRAINT_COL_RE.search(table_str)
    return m.group(1) if m else None


def _check_node(node: PlanNode) -> list[RuleFinding]:
    """Check a single scan node for partition transform misalignment."""
    table_str = node.descriptor.get("table", "")
    if "constraint on [" not in table_str:
        return []

    constraint_col = _extract_constraint_column(table_str) or "unknown"
    findings: list[RuleFinding] = []

    for detail in node.details:
        # T-04-15: cap string length before regex to prevent catastrophic backtracking
        safe_detail = detail[:_DETAIL_MAX_LEN]

        if "::" not in safe_detail:
            continue

        lower_bound = _parse_lower_bound(safe_detail)
        if lower_bound is None:
            continue

        day_aligned = _is_day_aligned(lower_bound)
        hour_aligned = _is_hour_aligned(lower_bound)

        if day_aligned:
            # Day-aligned lower bound — partition pruning should work correctly
            continue

        evidence: dict[str, Any] = {
            "constraint_column": constraint_col,
            "constraint_lower_bound": lower_bound.isoformat(),
            "is_day_aligned": day_aligned,
            "is_hour_aligned": hour_aligned,
        }

        findings.append(
            RuleFinding(
                rule_id="I8",
                severity="medium",
                confidence=0.6,
                message=(
                    f"Partition constraint lower bound {lower_bound.strftime('%Y-%m-%d %H:%M:%S UTC')} "
                    f"on column '{constraint_col}' is not aligned to day boundary; "
                    "may not fully prune Iceberg partitions with day(ts) transform. "
                    "Rewrite predicate to use exact midnight UTC boundaries."
                ),
                evidence=evidence,
                operator_ids=[node.id],
            )
        )

    return findings


class I8PartitionTransform(Rule):
    """I8: Query predicate is not aligned to Iceberg partition transform granularity.

    Best-effort detection using plan constraint detail lines. Confidence=0.6 because
    without the actual partition spec from Iceberg metadata, we cannot confirm the
    transform granularity matches the detected misalignment.
    """

    rule_id = "I8"
    evidence_requirement = EvidenceRequirement.ICEBERG_METADATA

    def __init__(self, thresholds: RuleThresholds | None = None) -> None:
        # thresholds not used directly by I8 but kept for constructor consistency
        self._thresholds = thresholds or RuleThresholds()

    def check(self, plan: BasePlan, evidence: EvidenceBundle) -> list[RuleFinding]:
        """Detect partition transform misalignment from plan constraint detail lines."""
        findings: list[RuleFinding] = []

        scan_types = frozenset({"TableScan", "ScanFilter", "ScanFilterProject"})
        for node in plan.walk():
            if node.operator_type not in scan_types:
                continue
            findings.extend(_check_node(node))

        return findings


registry.register(I8PartitionTransform)
