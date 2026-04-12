"""Internal ExplainPlan dataclass for TrinoClient's raw EXPLAIN output.

This is an internal implementation detail of the Trino adapter layer.
It is NOT part of the public port contract.

Phase 3: ExplainPlan was removed from ports/plan_source.py and moved here.
The public port contract now uses EstimatedPlan and ExecutedPlan from the
parser subpackage. LivePlanSource bridges from this internal type to the
typed domain objects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class ExplainPlan:
    """Minimum-viable internal type for raw TrinoClient EXPLAIN output.

    Used internally by TrinoClient and bridged to EstimatedPlan/ExecutedPlan
    by LivePlanSource. Not exported from the ports package.

    Attributes:
        plan_json: The raw parsed JSON dict from EXPLAIN (FORMAT JSON).
        plan_type: One of "estimated" (EXPLAIN), "executed" (EXPLAIN ANALYZE),
            or "distributed" (EXPLAIN (TYPE DISTRIBUTED)).
        source_trino_version: Trino version string from the live adapter, or
            ``None`` for offline mode where no cluster is involved.
        raw_text: The original text for round-trip fidelity. For EXPLAIN ANALYZE,
            this is the complete text output (since ANALYZE does not support FORMAT JSON).
    """

    plan_json: dict[str, Any]
    plan_type: Literal["estimated", "executed", "distributed"]
    source_trino_version: str | None = None
    raw_text: str = field(default="")
