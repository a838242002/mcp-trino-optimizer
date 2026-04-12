"""Parser domain models: PlanNode, EstimatedPlan, ExecutedPlan, SchemaDriftWarning.

IMPORTANT: Do NOT add `from __future__ import annotations` to this file.
Pydantic v2 models must have runtime-evaluable annotations. PEP 563 deferred
evaluation breaks model_extra access and forward-reference resolution.

All models are defined at module scope per Phase 1 UAT lesson.
"""

from typing import Any, Iterator, Literal

from pydantic import BaseModel, ConfigDict, Field


class ParseError(Exception):
    """Raised when input is completely unparseable (invalid JSON, wrong structure).

    Schema drift within a parseable plan produces SchemaDriftWarning, never this.
    Only raised for:
    - Invalid JSON (JSON decode error)
    - Wrong top-level structure (list instead of dict)
    """


class CostEstimate(BaseModel):
    """Cost estimate entry from the Trino EXPLAIN JSON estimates list.

    Trino EXPLAIN JSON uses camelCase keys; this model maps them to snake_case.
    All fields are optional because not all estimates are present for every node.
    """

    model_config = ConfigDict(populate_by_name=True)

    output_row_count: float | None = Field(default=None, alias="outputRowCount")
    output_size_in_bytes: float | None = Field(default=None, alias="outputSizeInBytes")
    cpu_cost: float | None = Field(default=None, alias="cpuCost")
    memory_cost: float | None = Field(default=None, alias="memoryCost")
    network_cost: float | None = Field(default=None, alias="networkCost")


class OutputSymbol(BaseModel):
    """An output column symbol from a plan node."""

    symbol: str
    type: str


class SchemaDriftWarning(BaseModel):
    """Structured warning for unexpected schema elements in plan output.

    Used to track version drift without raising exceptions. Consumers can inspect
    these warnings to understand which parts of the plan could not be fully parsed.
    """

    node_path: str
    """Location in the plan tree, e.g. 'root.children[0].children[1]'."""

    field_name: str | None = None
    """The specific field that triggered the warning, if applicable."""

    description: str
    """Human-readable description of what was unexpected."""

    severity: Literal["info", "warning"] = "warning"
    """Severity level. 'info' for benign drift, 'warning' for potentially impactful."""


class PlanNode(BaseModel):
    """A single node in a Trino plan tree.

    Uses ConfigDict(extra='allow') so unknown/version-specific fields from
    Trino EXPLAIN JSON are automatically captured in model_extra. Access them
    via the .raw property.

    Note: Do NOT use `from __future__ import annotations` in this file.
    Pydantic 2 requires runtime annotation evaluation for model_extra handling.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    # ── Core EXPLAIN JSON fields ───────────────────────────────────────────
    id: str
    name: str
    """The operator type name, e.g. 'TableScan', 'InnerJoin', 'Aggregate'."""

    descriptor: dict[str, str] = Field(default_factory=dict)
    """Operator-specific descriptor key/value pairs from EXPLAIN JSON."""

    outputs: list[OutputSymbol] = Field(default_factory=list)
    """Output column symbols."""

    details: list[str] = Field(default_factory=list)
    """Human-readable detail strings (filter predicates, table names, etc.)."""

    estimates: list[CostEstimate] = Field(default_factory=list)
    """CBO cost estimates. ScanFilterAndProject has 3 entries: scan/filter/project."""

    children: list["PlanNode"] = Field(default_factory=list)
    """Child nodes forming the plan tree."""

    # ── Runtime metrics (populated only for ExecutedPlan nodes) ───────────
    cpu_time_ms: float | None = None
    wall_time_ms: float | None = None
    input_rows: int | None = None
    input_bytes: int | None = None
    output_rows: int | None = None
    output_bytes: int | None = None
    peak_memory_bytes: int | None = None
    physical_input_bytes: int | None = None
    spilled_bytes: int | None = None
    blocked_time_ms: float | None = None

    # ── Iceberg-specific fields (PLN-04) ───────────────────────────────────
    iceberg_split_count: int | None = None
    """Number of Iceberg splits read during execution (EXPLAIN ANALYZE only)."""

    iceberg_file_count: int | None = None
    """Number of Iceberg files read during execution (EXPLAIN ANALYZE only)."""

    iceberg_partition_spec_id: int | None = None
    """Iceberg partition spec identifier (from table metadata)."""

    # ── Properties ────────────────────────────────────────────────────────

    @property
    def operator_type(self) -> str:
        """Alias for name. Used by rules for clarity: node.operator_type == 'TableScan'."""
        return self.name

    @property
    def raw(self) -> dict[str, Any]:
        """Access model_extra as the raw dict bag (PLN-02).

        Contains all original JSON fields not mapped to typed attributes.
        Use this to access version-specific fields that are not yet in the schema.
        """
        return self.model_extra or {}


class BasePlan(BaseModel):
    """Shared base for EstimatedPlan and ExecutedPlan.

    Contains the plan tree, drift warnings, version info, and traversal methods.
    """

    root: PlanNode
    """Root node of the plan tree."""

    schema_drift_warnings: list[SchemaDriftWarning] = Field(default_factory=list)
    """Warnings about unexpected structure encountered during parsing."""

    source_trino_version: str | None = None
    """Trino version string from the adapter, or None for offline mode."""

    raw_text: str = ""
    """Original raw text (JSON or EXPLAIN ANALYZE text) for round-trip fidelity."""

    def walk(self) -> Iterator[PlanNode]:
        """Yield all nodes in DFS (depth-first, pre-order) traversal.

        Root is yielded first, then children recursively.
        """
        stack = [self.root]
        while stack:
            node = stack.pop(0)
            yield node
            stack = list(node.children) + stack

    def find_nodes_by_type(self, operator_type: str) -> list[PlanNode]:
        """Return all nodes with the given operator_type (name).

        Args:
            operator_type: The operator type name to match, e.g. 'TableScan'.

        Returns:
            List of matching PlanNode objects in DFS order.
        """
        return [node for node in self.walk() if node.name == operator_type]


class EstimatedPlan(BasePlan):
    """A plan built from EXPLAIN (FORMAT JSON) output.

    Contains CBO cost estimates and the operator tree, but no runtime metrics.
    Iceberg split/file counts are None (execution-time metrics).
    """

    plan_type: Literal["estimated"] = "estimated"


class ExecutedPlan(BasePlan):
    """A plan built from EXPLAIN ANALYZE text output.

    Contains per-operator runtime metrics (CPU, wall time, rows, bytes, memory)
    extracted via regex parsing of the EXPLAIN ANALYZE text format.
    """

    plan_type: Literal["executed"] = "executed"
