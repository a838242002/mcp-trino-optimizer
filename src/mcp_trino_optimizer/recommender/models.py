"""Recommendation engine pydantic models.

Defines the data contracts for the recommendation pipeline:
- Recommendation: a prioritized, actionable finding
- ConsideredButRejected: a finding that lost conflict resolution
- IcebergTableHealth: per-table health summary
- BottleneckEntry/BottleneckRanking: operator-level bottleneck analysis
- RecommendationReport: top-level report aggregating all outputs
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from mcp_trino_optimizer.rules.findings import Severity

PriorityTier = Literal["P1", "P2", "P3", "P4"]
"""Four-tier priority classification. P1 = must fix, P4 = low priority."""

RiskLevel = Literal["low", "medium", "high"]
"""Risk level for applying a recommendation."""

HealthScore = Literal["healthy", "degraded", "critical"]
"""Iceberg table health classification."""


class ConsideredButRejected(BaseModel):
    """A finding that was deprioritized during conflict resolution.

    Kept for auditability — the user can see why a rule's recommendation
    was not included in the final list.
    """

    rule_id: str
    """Rule that produced the original finding."""

    reason: str
    """Why this finding was rejected (e.g., 'Superseded by D11 with higher confidence')."""

    original_priority_score: float
    """The priority score the finding would have received."""


class Recommendation(BaseModel):
    """A prioritized, actionable optimization recommendation.

    Produced by scoring a RuleFinding through the priority formula
    (severity_weight * impact * confidence) and enriching it with
    narrative context.
    """

    rule_id: str
    """Stable rule identifier, e.g. 'R1', 'I3', 'D11'."""

    severity: Severity
    """Inherited from the original RuleFinding."""

    confidence: float = Field(ge=0.0, le=1.0)
    """Confidence score from the original RuleFinding."""

    priority_score: float
    """Raw float priority = severity_weight * impact * confidence."""

    priority_tier: PriorityTier
    """Human-readable tier label derived from priority_score."""

    operator_ids: list[str]
    """Plan node IDs that triggered this recommendation."""

    reasoning: str
    """Why this optimization matters — deterministic template output."""

    expected_impact: str
    """What improvement to expect if the recommendation is applied."""

    risk_level: RiskLevel
    """Risk of applying this recommendation."""

    validation_steps: str
    """How to verify the recommendation was effective."""

    session_property_statements: list[str] | None = None
    """Optional SET SESSION statements for session-property-based fixes."""

    evidence_summary: dict[str, Any]
    """Key evidence values supporting this recommendation."""

    considered_but_rejected: list[ConsideredButRejected] = Field(default_factory=list)
    """Findings that conflicted with this recommendation and lost."""


class IcebergTableHealth(BaseModel):
    """Per-table health summary aggregated from I1/I3/I6/I8 findings.

    Provides a concise view of Iceberg table maintenance status.
    """

    table_name: str
    """Fully qualified table name (catalog.schema.table)."""

    snapshot_count: int | None = None
    """Number of snapshots (from I6)."""

    small_file_ratio: float | None = None
    """Ratio of small files (from I1)."""

    delete_file_ratio: float | None = None
    """Ratio of delete files (from I3)."""

    partition_spec_evolution: str | None = None
    """Partition spec change description (from I8)."""

    last_compaction_reference: str | None = None
    """Reference to last compaction event, if available."""

    health_score: HealthScore
    """Overall health classification."""

    narrative: str
    """Human-readable health summary."""


class BottleneckEntry(BaseModel):
    """A single operator in the bottleneck ranking."""

    operator_id: str
    """Plan node ID."""

    operator_type: str
    """Operator type name (e.g., 'HashJoin', 'TableScan')."""

    cpu_time_ms: float
    """CPU time consumed by this operator."""

    wall_time_ms: float
    """Wall time consumed by this operator."""

    cpu_pct: float
    """Percentage of total CPU time consumed."""

    input_rows: int | None = None
    """Input rows processed, if available."""

    output_rows: int | None = None
    """Output rows produced, if available."""

    peak_memory_bytes: int | None = None
    """Peak memory usage, if available."""

    related_findings: list[str] = Field(default_factory=list)
    """Rule IDs that produced findings on this operator."""

    narrative: str
    """Human-readable description of this bottleneck."""


class BottleneckRanking(BaseModel):
    """Top-N operators ranked by resource consumption.

    Built from ExecutedPlan runtime metrics (D-08).
    """

    top_operators: list[BottleneckEntry]
    """Operators ranked by CPU time contribution."""

    total_cpu_time_ms: float
    """Total CPU time across all operators in the plan."""

    plan_type: str = "executed"
    """Plan type used for ranking (always 'executed' for bottleneck analysis)."""

    top_n: int
    """Number of top operators included."""


class RecommendationReport(BaseModel):
    """Top-level report aggregating all recommendation engine outputs.

    This is the final output of the recommendation pipeline, consumed
    by MCP tools in Phase 8.
    """

    recommendations: list[Recommendation]
    """Prioritized list of recommendations, sorted by priority_score descending."""

    iceberg_health: list[IcebergTableHealth] = Field(default_factory=list)
    """Per-table Iceberg health summaries."""

    bottleneck_ranking: BottleneckRanking | None = None
    """Operator bottleneck ranking (only available for ExecutedPlan)."""

    considered_but_rejected: list[ConsideredButRejected] = Field(default_factory=list)
    """All findings that lost conflict resolution, for auditability."""


__all__ = [
    "BottleneckEntry",
    "BottleneckRanking",
    "ConsideredButRejected",
    "HealthScore",
    "IcebergTableHealth",
    "PriorityTier",
    "Recommendation",
    "RecommendationReport",
    "RiskLevel",
]
