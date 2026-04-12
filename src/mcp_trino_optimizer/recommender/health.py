"""Iceberg table health aggregation (REC-06).

Aggregates I1/I3/I6/I8 rule findings by table into structured
IcebergTableHealth objects with health score classification and
templated narratives.

T-05-07: Health narrative templates use only evidence dict numeric/enum
fields and table_name -- no RuleFinding.message interpolation.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from mcp_trino_optimizer.recommender.models import IcebergTableHealth
from mcp_trino_optimizer.rules.findings import RuleFinding

ICEBERG_RULES: frozenset[str] = frozenset({"I1", "I3", "I6", "I8"})
"""Set of Iceberg-specific rule IDs for health aggregation."""

# Rules that trigger "critical" health score when severity is high or critical
_CRITICAL_RULES: frozenset[str] = frozenset({"I1", "I3"})

HEALTH_NARRATIVE = "Table {table_name}: health={health_score}. {details}"
"""Template for health narrative. Uses only structured fields, never RuleFinding.message."""


def _extract_table_name(finding: RuleFinding) -> str:
    """Extract table_name from finding evidence, falling back to 'unknown_table'.

    Iceberg rules may store table_name in evidence if the caller provides it.
    If not present, falls back to 'unknown_table'.
    """
    return str(finding.evidence.get("table_name", "unknown_table"))


def _compute_health_score(
    findings: list[RuleFinding],
) -> str:
    """Classify health score from a group of findings.

    Rules:
    - "critical" if any I1 or I3 finding has severity in ("critical", "high")
    - "degraded" if any findings exist (I6, I8, or I1/I3 with lower severity)
    - "healthy" if no findings (won't occur in practice since we filter)
    """
    for f in findings:
        if f.rule_id in _CRITICAL_RULES and f.severity in ("critical", "high"):
            return "critical"
    # Any Iceberg finding present -> degraded
    if findings:
        return "degraded"
    return "healthy"


def _extract_small_file_ratio(evidence: dict[str, Any]) -> float | None:
    """Extract small file ratio from I1 evidence.

    I1 metadata path: median_file_size_bytes / threshold_bytes.
    I1 split-count path: no ratio available, return None.
    """
    median = evidence.get("median_file_size_bytes")
    threshold = evidence.get("threshold_bytes")
    if median is not None and threshold is not None and threshold > 0:
        return float(median) / float(threshold)
    return None


def _build_details(
    table_name: str,
    findings_by_rule: dict[str, list[RuleFinding]],
) -> str:
    """Build details string for the narrative."""
    parts: list[str] = []
    if "I1" in findings_by_rule:
        parts.append("Small file fragmentation detected")
    if "I3" in findings_by_rule:
        parts.append("Delete file accumulation detected")
    if "I6" in findings_by_rule:
        parts.append("Stale snapshot accumulation detected")
    if "I8" in findings_by_rule:
        parts.append("Partition transform misalignment detected")
    return "; ".join(parts) if parts else "No issues detected"


def _build_compaction_reference(
    findings_by_rule: dict[str, list[RuleFinding]],
    table_name: str,
) -> str | None:
    """Build last_compaction_reference from findings.

    I1/I3 -> ALTER TABLE ... EXECUTE optimize
    I6 -> ALTER TABLE ... EXECUTE expire_snapshots
    """
    if "I1" in findings_by_rule or "I3" in findings_by_rule:
        return f"Run: ALTER TABLE {table_name} EXECUTE optimize"
    if "I6" in findings_by_rule:
        return f"Run: ALTER TABLE {table_name} EXECUTE expire_snapshots"
    return None


def aggregate_iceberg_health(
    findings: list[RuleFinding],
) -> list[IcebergTableHealth]:
    """Aggregate Iceberg rule findings into per-table health summaries.

    Filters to I1/I3/I6/I8 findings, groups by table_name extracted from
    evidence, and builds an IcebergTableHealth for each table.

    Args:
        findings: All RuleFinding objects from the rule engine.

    Returns:
        List of IcebergTableHealth objects, one per table with Iceberg findings.
        Empty list if no Iceberg findings.
    """
    # Filter to Iceberg rules only
    iceberg_findings = [f for f in findings if f.rule_id in ICEBERG_RULES]
    if not iceberg_findings:
        return []

    # Group by table_name
    by_table: dict[str, list[RuleFinding]] = defaultdict(list)
    for f in iceberg_findings:
        table = _extract_table_name(f)
        by_table[table].append(f)

    results: list[IcebergTableHealth] = []
    for table_name, table_findings in sorted(by_table.items()):
        # Sub-group by rule_id for field extraction
        findings_by_rule: dict[str, list[RuleFinding]] = defaultdict(list)
        for f in table_findings:
            findings_by_rule[f.rule_id].append(f)

        # Extract field values from evidence
        small_file_ratio: float | None = None
        for f in findings_by_rule.get("I1", []):
            ratio = _extract_small_file_ratio(f.evidence)
            if ratio is not None:
                small_file_ratio = ratio
                break

        delete_file_ratio: float | None = None
        for f in findings_by_rule.get("I3", []):
            dr = f.evidence.get("delete_ratio")
            if dr is not None:
                delete_file_ratio = float(dr)
                break

        snapshot_count: int | None = None
        for f in findings_by_rule.get("I6", []):
            sc = f.evidence.get("snapshot_count")
            if sc is not None:
                snapshot_count = int(sc)
                break

        partition_spec_evolution: str | None = None
        for f in findings_by_rule.get("I8", []):
            col = f.evidence.get("constraint_column", "unknown")
            is_day = f.evidence.get("is_day_aligned", True)
            is_hour = f.evidence.get("is_hour_aligned", False)
            alignment = "hour-aligned" if is_hour else "sub-hour"
            partition_spec_evolution = (
                f"Column '{col}' constraint is {alignment}, not day-aligned"
            )
            break

        health_score = _compute_health_score(table_findings)
        details = _build_details(table_name, findings_by_rule)
        narrative = HEALTH_NARRATIVE.format(
            table_name=table_name,
            health_score=health_score,
            details=details,
        )
        compaction_ref = _build_compaction_reference(findings_by_rule, table_name)

        results.append(
            IcebergTableHealth(
                table_name=table_name,
                snapshot_count=snapshot_count,
                small_file_ratio=small_file_ratio,
                delete_file_ratio=delete_file_ratio,
                partition_spec_evolution=partition_spec_evolution,
                last_compaction_reference=compaction_ref,
                health_score=health_score,  # type: ignore[arg-type]
                narrative=narrative,
            )
        )

    return results


__all__ = [
    "ICEBERG_RULES",
    "aggregate_iceberg_health",
]
