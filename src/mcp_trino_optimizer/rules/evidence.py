"""Evidence types — EvidenceRequirement enum, EvidenceBundle dataclass, safe_float helper.

Rules declare their evidence requirement via the EvidenceRequirement enum.
The engine prefetches all required evidence once, bundles it in EvidenceBundle,
and passes the bundle to each rule's check() method.

safe_float is a helper for numeric comparisons that avoids NaN-silently-False.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mcp_trino_optimizer.parser.models import BasePlan


class EvidenceRequirement(Enum):
    """Declares what evidence a rule needs.

    PLAN_ONLY          — rule reads only PlanNode fields; no external calls needed.
    PLAN_WITH_METRICS  — rule needs ExecutedPlan runtime metrics (cpu_time_ms, etc.).
    TABLE_STATS        — rule needs SHOW STATS data from StatsSource.
    ICEBERG_METADATA   — rule needs $files/$snapshots from CatalogSource.
    """

    PLAN_ONLY = "plan_only"
    PLAN_WITH_METRICS = "plan_with_metrics"
    TABLE_STATS = "table_stats"
    ICEBERG_METADATA = "iceberg_metadata"


@dataclass
class EvidenceBundle:
    """Collected evidence passed to each rule's check() method.

    The engine populates this before running rules; rule bodies are pure sync
    functions that read from this bundle — no I/O allowed inside check().
    """

    plan: BasePlan
    """The plan being analyzed."""

    table_stats: dict[str, Any] | None = None
    """Output of StatsSource.fetch_table_stats(), or None if unavailable."""

    iceberg_snapshots: list[dict[str, Any]] | None = None
    """Rows from $snapshots metadata table, or None if unavailable."""

    iceberg_files: list[dict[str, Any]] | None = None
    """Rows from $files metadata table (capped by max_metadata_rows), or None if unavailable."""


def safe_float(val: Any) -> float | None:
    """Return None if val is None or NaN; otherwise return float(val).

    Use this before numeric comparisons to avoid the NaN-silently-False pitfall
    (NaN comparisons in Python always return False, hiding missing-data bugs).

    Examples:
        safe_float(None)  -> None
        safe_float(float("nan"))  -> None
        safe_float(42)    -> 42.0
        safe_float("5.5") -> 5.5
    """
    if val is None:
        return None
    f = float(val)
    return None if math.isnan(f) else f


__all__ = [
    "EvidenceBundle",
    "EvidenceRequirement",
    "safe_float",
]
