"""Narrative templates for recommendation output (REC-03, T-05-03).

Each rule_id maps to a dict with keys: reasoning, expected_impact,
validation_steps, risk_level. Templates use ONLY typed evidence field
placeholders -- never RuleFinding.message (Pitfall 1 from RESEARCH.md).

Security: The render_recommendation function builds a safe_evidence dict
that only admits str/int/float values, then sanitizes strings to remove
dangerous characters. This prevents prompt injection from evidence values.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

# Identifier pattern: only values matching this are interpolated as-is.
# Allows: dotted identifiers (catalog.schema.table), snake_case, hyphens, numbers.
# Anything else (spaces, SQL keywords, injection attempts) => "[redacted]".
_IDENTIFIER_RE = re.compile(r"^[a-zA-Z0-9._\-/]+$")
_MAX_VALUE_LEN = 200

TEMPLATES: dict[str, dict[str, str]] = {
    "R1": {
        "reasoning": (
            "Table {table_name} at operator {operator_id} has missing or stale "
            "statistics. The optimizer cannot make informed decisions about join "
            "strategies, filter selectivity, or data distribution without accurate stats."
        ),
        "expected_impact": (
            "Running ANALYZE on {table_name} will provide the optimizer with accurate "
            "row counts and column statistics, potentially improving join order and "
            "distribution decisions."
        ),
        "validation_steps": (
            "1. Run ANALYZE {table_name}. "
            "2. Re-run EXPLAIN on the query. "
            "3. Verify the optimizer estimates are closer to actual values."
        ),
        "risk_level": "low",
    },
    "R2": {
        "reasoning": (
            "Partition pruning is not being applied at operator {operator_id}. "
            "The predicate {partition_predicate} does not match the table partition "
            "spec, causing a full scan of all partitions."
        ),
        "expected_impact": (
            "Aligning the predicate with the partition spec will reduce the number "
            "of data files scanned, potentially reducing I/O by an order of magnitude."
        ),
        "validation_steps": (
            "1. Rewrite the WHERE clause to use partition columns directly. "
            "2. Run EXPLAIN and verify partition pruning in the plan output. "
            "3. Compare scan statistics before and after."
        ),
        "risk_level": "low",
    },
    "R3": {
        "reasoning": (
            "Predicate pushdown failed at operator {operator_id}. The function "
            "{function_name} on column {column_name} prevents the connector from "
            "pushing the filter to the storage layer."
        ),
        "expected_impact": (
            "Rewriting the predicate to avoid wrapping {column_name} in "
            "{function_name} will allow the Iceberg connector to push the filter "
            "down, reducing bytes read from storage."
        ),
        "validation_steps": (
            "1. Rewrite the predicate to apply the function to the literal side. "
            "2. Run EXPLAIN and verify the filter appears in the TableScan node. "
            "3. Compare processed bytes before and after."
        ),
        "risk_level": "low",
    },
    "R4": {
        "reasoning": (
            "Dynamic filtering is not being applied at operator {operator_id}. "
            "This means the probe side of the join is scanning all data instead of "
            "being filtered by the build side values."
        ),
        "expected_impact": (
            "Enabling dynamic filtering will allow the probe side scan to skip "
            "data files that do not match the build side join keys, significantly "
            "reducing I/O on large tables."
        ),
        "validation_steps": (
            "1. Verify SET SESSION enable_dynamic_filtering = true. "
            "2. Re-run the query and check EXPLAIN ANALYZE for DynamicFilter stats. "
            "3. Compare input rows on the probe side before and after."
        ),
        "risk_level": "low",
    },
    "R5": {
        "reasoning": (
            "Broadcast join at operator {operator_id} is distributing "
            "{build_side_estimated_bytes} bytes to every worker. The current "
            "distribution strategy is {distribution}. This exceeds safe broadcast "
            "thresholds and may cause out-of-memory failures."
        ),
        "expected_impact": (
            "Switching to a partitioned join will distribute the data evenly "
            "across workers, reducing per-worker memory pressure and avoiding "
            "potential OOM crashes."
        ),
        "validation_steps": (
            "1. SET SESSION join_distribution_type = 'PARTITIONED'. "
            "2. Re-run EXPLAIN and verify the join uses partitioned distribution. "
            "3. Monitor peak memory per worker."
        ),
        "risk_level": "medium",
    },
    "R6": {
        "reasoning": (
            "Join order at operator {operator_id} appears suboptimal. The optimizer "
            "may be placing a larger table on the build side of the join due to "
            "inaccurate statistics."
        ),
        "expected_impact": (
            "Correcting join order by running ANALYZE on involved tables will help "
            "the optimizer choose the smaller table for the build side, reducing "
            "memory usage and improving join performance."
        ),
        "validation_steps": (
            "1. Run ANALYZE on all tables involved in the join. "
            "2. Re-run EXPLAIN and compare the join build/probe assignment. "
            "3. Check if the smaller table is now on the build side."
        ),
        "risk_level": "low",
    },
    "R7": {
        "reasoning": (
            "CPU skew detected at operator {operator_id} in stage {stage_id}. "
            "The P99/P50 CPU time ratio is {p99_p50_ratio}, indicating some "
            "workers are processing significantly more data than others."
        ),
        "expected_impact": (
            "Addressing data skew will distribute work more evenly, reducing "
            "wall clock time by avoiding a single slow worker bottleneck."
        ),
        "validation_steps": (
            "1. Examine the join/group-by keys for high-cardinality skew. "
            "2. Consider adding a salting key or pre-aggregation. "
            "3. Compare per-worker CPU time distribution after the fix."
        ),
        "risk_level": "medium",
    },
    "R8": {
        "reasoning": (
            "Exchange volume at operator {operator_id} shows a ratio of {ratio} "
            "between exchange bytes and scan bytes. This indicates excessive "
            "data shuffling across the network."
        ),
        "expected_impact": (
            "Reducing exchange volume by switching to partitioned joins or "
            "adding partition predicates will lower network I/O and improve "
            "query latency."
        ),
        "validation_steps": (
            "1. SET SESSION join_distribution_type = 'PARTITIONED'. "
            "2. Re-run EXPLAIN ANALYZE and compare exchange bytes. "
            "3. Verify network throughput metrics improved."
        ),
        "risk_level": "low",
    },
    "R9": {
        "reasoning": (
            "Low selectivity scan at operator {operator_id} with selectivity "
            "{selectivity}. The query is reading far more data than it ultimately "
            "needs, wasting I/O bandwidth."
        ),
        "expected_impact": (
            "Adding more selective predicates or partition filters will reduce "
            "the amount of data read from storage, improving query performance."
        ),
        "validation_steps": (
            "1. Add partition predicates to the WHERE clause. "
            "2. Consider pre-filtering with a subquery on indexed columns. "
            "3. Compare processed bytes before and after."
        ),
        "risk_level": "low",
    },
    "I1": {
        "reasoning": (
            "Table {table_name} has {data_file_count} data files with a median "
            "size of {median_file_size_bytes} bytes. Small files degrade scan "
            "performance due to excessive metadata overhead and poor I/O parallelism."
        ),
        "expected_impact": (
            "Running OPTIMIZE on {table_name} will compact small files into larger "
            "ones, reducing file listing overhead and improving scan throughput."
        ),
        "validation_steps": (
            "1. Run ALTER TABLE {table_name} EXECUTE optimize. "
            "2. Check file count and median size via metadata tables. "
            "3. Re-run the query and compare scan times."
        ),
        "risk_level": "low",
    },
    "I3": {
        "reasoning": (
            "Table {table_name} has {delete_file_count} delete files. "
            "Delete files cause merge-on-read overhead during scans, slowing "
            "down every query that touches this table."
        ),
        "expected_impact": (
            "Running OPTIMIZE will merge delete files into base data files, "
            "eliminating merge-on-read overhead for future queries."
        ),
        "validation_steps": (
            "1. Run ALTER TABLE {table_name} EXECUTE optimize. "
            "2. Verify delete file count is zero via metadata tables. "
            "3. Compare scan performance before and after."
        ),
        "risk_level": "low",
    },
    "I6": {
        "reasoning": (
            "Table {table_name} has {snapshot_count} snapshots. Excessive "
            "snapshots increase metadata size and slow down table operations "
            "like planning and file listing."
        ),
        "expected_impact": ("Expiring old snapshots will reduce metadata table size and improve query planning time."),
        "validation_steps": (
            "1. Run ALTER TABLE {table_name} EXECUTE expire_snapshots. "
            "2. Verify snapshot count via metadata tables. "
            "3. Compare planning time before and after."
        ),
        "risk_level": "low",
    },
    "I8": {
        "reasoning": (
            "Table {table_name} has a partition predicate on column "
            "{constraint_column} that does not align with the table partition "
            "spec. This prevents partition pruning."
        ),
        "expected_impact": (
            "Rewriting the predicate to match the partition transform will "
            "enable partition pruning, potentially reducing scanned partitions "
            "significantly."
        ),
        "validation_steps": (
            "1. Check the table partition spec via SHOW CREATE TABLE. "
            "2. Rewrite the WHERE clause to match the partition transform. "
            "3. Run EXPLAIN and verify partition pruning is active."
        ),
        "risk_level": "low",
    },
    "D11": {
        "reasoning": (
            "Cost model divergence at operator {operator_id} with a divergence "
            "factor of {divergence_factor}. The optimizer estimates differ "
            "significantly from actual execution metrics, indicating stale or "
            "missing statistics."
        ),
        "expected_impact": (
            "Running ANALYZE on the tables involved will update statistics, "
            "allowing the optimizer to make better decisions about join order, "
            "distribution, and memory allocation."
        ),
        "validation_steps": (
            "1. Run ANALYZE on all tables referenced in the query. "
            "2. Re-run EXPLAIN ANALYZE and compare estimated vs. actual rows. "
            "3. Verify the divergence factor has decreased."
        ),
        "risk_level": "low",
    },
}
"""Narrative templates keyed by rule_id.

Each template dict has: reasoning, expected_impact, validation_steps, risk_level.
Placeholders use evidence dict keys only -- never RuleFinding.message.
"""

_GENERIC_TEMPLATE: dict[str, str] = {
    "reasoning": "A performance issue was detected by rule {rule_id}.",
    "expected_impact": "Addressing this issue may improve query performance.",
    "validation_steps": "Re-run EXPLAIN ANALYZE after applying the fix.",
    "risk_level": "low",
}


def _sanitize_value(value: Any) -> str:
    """Sanitize a single evidence value for safe template interpolation.

    Only admits str/int/float. Strings must match the identifier pattern
    (alphanumeric, dots, underscores, hyphens, slashes -- no spaces or
    SQL keywords). Non-matching strings are replaced with '[redacted]'.

    This is the core defense against prompt injection (T-05-03).
    """
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        truncated = value[:_MAX_VALUE_LEN]
        # Only allow identifier-like strings (no spaces, no SQL keywords)
        if _IDENTIFIER_RE.match(truncated):
            return truncated
        return "[redacted]"
    return "N/A"


def render_recommendation(
    rule_id: str,
    evidence: dict[str, Any],
) -> dict[str, str]:
    """Render narrative fields for a recommendation.

    Builds a safe_evidence dict from the evidence, sanitizing all values
    to prevent injection. Uses defaultdict for missing keys (produces 'N/A').

    Args:
        rule_id: The rule identifier to look up in TEMPLATES.
        evidence: The evidence dict from the RuleFinding.

    Returns:
        Dict with keys: reasoning, expected_impact, validation_steps, risk_level.
    """
    template = TEMPLATES.get(rule_id, _GENERIC_TEMPLATE)

    # Build safe evidence: only str/int/float values, sanitized
    safe_evidence: dict[str, str] = {"rule_id": rule_id}
    for key, value in evidence.items():
        safe_evidence[key] = _sanitize_value(value)

    # Use defaultdict so missing keys produce "N/A"
    safe_map = defaultdict(lambda: "N/A", safe_evidence)

    return {
        "reasoning": template["reasoning"].format_map(safe_map),
        "expected_impact": template["expected_impact"].format_map(safe_map),
        "validation_steps": template["validation_steps"].format_map(safe_map),
        "risk_level": template["risk_level"],
    }


__all__ = [
    "TEMPLATES",
    "render_recommendation",
]
