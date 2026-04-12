# Phase 3: Plan Parser & Normalizer - Research

**Researched:** 2026-04-12
**Domain:** Trino EXPLAIN plan parsing, typed model construction, version-drift tolerance
**Confidence:** HIGH (EXPLAIN JSON structure verified via Trino source + docs; EXPLAIN ANALYZE limitation confirmed via grammar)

## Summary

Phase 3 converts raw Trino EXPLAIN output into typed `EstimatedPlan` and `ExecutedPlan` pydantic models. The research uncovered a **critical architectural constraint**: Trino's `EXPLAIN ANALYZE` does NOT support `FORMAT JSON` -- it outputs TEXT only. This shapes the entire `ExecutedPlan` strategy. For `EXPLAIN (FORMAT JSON)`, the output is a well-defined tree of nodes with `id`, `name`, `descriptor`, `outputs`, `details`, `estimates`, and `children` fields. The parser must handle both the clean JSON path (estimated plans) and a text-or-API-based path (executed plans).

The Iceberg-specific operator name in EXPLAIN output is `ScanFilterAndProject` (fused scan+filter+project) or just `TableScan`. Split count and file count are runtime metrics not present in EXPLAIN (FORMAT JSON) -- they appear only during execution. Partition spec ID can be inferred from the table metadata in the descriptor. The multi-version fixture corpus requires capturing real EXPLAIN output from Trino 429, ~455, and 480 via the docker-compose stack with image tag swaps.

**Primary recommendation:** Build `EstimatedPlan` from `EXPLAIN (FORMAT JSON)` with a clean JSON-to-pydantic pipeline. For `ExecutedPlan`, parse the EXPLAIN ANALYZE text output into the same typed tree, augmenting nodes with runtime metrics extracted via regex-based text parsing. This avoids depending on Trino's internal `/ui/api/query/{queryId}` API which is undocumented and may change between versions.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01 (replace ExplainPlan entirely):** Phase 3 removes the `ExplainPlan` dataclass from `ports/plan_source.py` and introduces `EstimatedPlan` and `ExecutedPlan` as the new domain types. `PlanSource.fetch_plan()` returns `EstimatedPlan`; `PlanSource.fetch_analyze_plan()` returns `ExecutedPlan`. The `OfflinePlanSource` and `LivePlanSource` adapters update their return types accordingly. Clean break -- no inheritance from the old placeholder.
- **D-02 (new parser/ subpackage):** The typed plan models and parsing logic live in a new `src/mcp_trino_optimizer/parser/` subpackage with `__init__.py`, `models.py`, `parser.py`, and `normalizer.py`.
- **D-03 (generic PlanNode with operator_type field):** One `PlanNode` pydantic model with `operator_type: str` and typed common fields. No subclasses per operator type.
- **D-04 (pydantic model_extra for raw dict bag):** `PlanNode` uses `model_config = ConfigDict(extra='allow')`. `model_extra` IS the raw bag.
- **D-05 (schema_drift_warnings on plan result):** `EstimatedPlan` and `ExecutedPlan` carry a `schema_drift_warnings: list[SchemaDriftWarning]` field.
- **D-06 (lenient parsing):** Never raise on unexpected structure. Unknown node types, missing fields produce warnings, never exceptions.
- **D-07 (3 Trino versions):** Fixture corpus: Trino 429, ~450-460, and 480+.
- **D-08 (live capture from docker-compose):** Fixtures captured by running real queries against the Phase 2 docker-compose stack.
- **D-09 (fixtures at tests/fixtures/explain/):** `tests/fixtures/explain/{version}/{query_name}.json`.
- **D-10 (snapshot parsed output):** Syrupy snapshot tests parse fixtures through the parser and snapshot the result.
- **D-11 (in-place normalization):** ScanFilterProject never visible to consumers.
- **D-12 (Iceberg extraction = PLN-04 minimum):** Split count, file count, partition spec identifier.
- **D-13 (normalization scope = PLN-05 only):** Only ScanFilterProject collapse and Project wrapper walk-through.

### Claude's Discretion
- Exact pydantic model field names and types for PlanNode common fields
- Whether EstimatedPlan and ExecutedPlan share a common base class
- How the parser detects plan_type from JSON content
- Exact SchemaDriftWarning structure beyond mandatory fields
- How IcebergTableScan detail strings are parsed
- Which queries to run for fixture capture
- Exact syrupy snapshot configuration
- PlanSource protocol signature change coordination
- Tree-walking utility methods (find_nodes_by_type, walk)

### Deferred Ideas (OUT OF SCOPE)
- Exchange normalization
- Additional Iceberg metadata extraction beyond split count, file count, partition spec ID
- Additional Trino fixture versions beyond 3
- Plan caching
- Distributed plan parsing beyond generic PlanNode tree
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| PLN-01 | Two distinct typed plan classes: EstimatedPlan and ExecutedPlan | EXPLAIN (FORMAT JSON) produces clean JSON for EstimatedPlan. EXPLAIN ANALYZE produces TEXT only -- ExecutedPlan requires text parsing or dual strategy. See Architecture Patterns section. |
| PLN-02 | Every parsed node preserves raw dict alongside typed fields | Pydantic `ConfigDict(extra='allow')` + `model_extra` confirmed as the right approach. See Code Examples. |
| PLN-03 | Parser extracts per-operator CPU time, wall time, input/output rows, bytes, peak memory, exchange metadata | These metrics are only available in EXPLAIN ANALYZE text output. JSON format not supported for EXPLAIN ANALYZE. See Critical Finding section. |
| PLN-04 | Iceberg-specific operators expose split count, file count, partition spec identifier | Split count and file count are runtime metrics visible only in EXPLAIN ANALYZE output. Partition spec ID available from table metadata. See Iceberg Extraction section. |
| PLN-05 | Normalizes ScanFilterProject into TableScan + filter + projection | ScanFilterProject is the fused operator name in Trino EXPLAIN. Details contain the three sub-component costs. See Normalization section. |
| PLN-06 | Multi-version fixture corpus from 3 Trino versions, syrupy-gated | Docker image tag swap approach verified. syrupy 5.1.0 already in dev deps. See Fixture Capture section. |
| PLN-07 | Schema drift produces structured warnings, never raises | Pydantic model_extra handles unknown fields automatically. Parser wraps all unexpected structure in SchemaDriftWarning. See Architecture Patterns. |
</phase_requirements>

## Critical Finding: EXPLAIN ANALYZE Does Not Support FORMAT JSON

**Confidence: HIGH** [VERIFIED: Trino ANTLR grammar SqlBase.g4]

The Trino SQL grammar defines:
- `EXPLAIN ('(' explainOption (',' explainOption)* ')')? statement` -- supports `FORMAT JSON`
- `EXPLAIN ANALYZE VERBOSE? statement` -- NO format option, TEXT only

This means:
1. `EXPLAIN (FORMAT JSON) SELECT ...` returns a single-row, single-column result containing a JSON string
2. `EXPLAIN ANALYZE SELECT ...` returns a single-row, single-column result containing a TEXT string (tree-formatted)
3. The current Phase 2 code (`EXPLAIN ANALYZE {sql}`) correctly sends this but the `_execute_explain` method falls back to `{"raw": plan_text}` when JSON parsing fails

**Impact on architecture:**
- `EstimatedPlan` can be built from clean JSON parsing -- straightforward
- `ExecutedPlan` requires parsing the TEXT output of EXPLAIN ANALYZE

**Source:** [Trino ANTLR grammar](https://github.com/trinodb/trino/blob/master/core/trino-grammar/src/main/antlr4/io/trino/grammar/sql/SqlBase.g4), [GitHub issue #5786](https://github.com/trinodb/trino/issues/5786) (still open -- JSON format for EXPLAIN ANALYZE not implemented)

### Strategy for ExecutedPlan

**Recommended approach: Parse EXPLAIN ANALYZE text output**

The EXPLAIN ANALYZE text output has a consistent structure:
```
Query: ...
Fragment N [TYPE]
    CPU: Xms, Scheduled: Xms, Blocked Xs (Input: Xs, Output: Xs), Input: N rows (XMB)
    Peak memory usage: XMB, Tasks count: N
    Output layout: [col1, col2, ...]
    └─ Operator [TYPE]
        Layout: [col1 type, col2 type]
        Estimates: {rows: N (XB), cpu: X, memory: X, network: X}
        CPU: X% (Xms), Scheduled: X% (Xms), Blocked: X% (Xms), Output: N rows (XMB)
        Input avg.: N rows, Input std.dev.: X%
        └─ Child Operator
```

Per-operator metrics available in text output: [VERIFIED: Trino docs + source PlanNodeStats.java]
- `planNodeCpuTime` -- CPU time consumed
- `planNodeScheduledTime` -- wall/scheduled time
- `planNodeBlockedTime` -- time spent blocked
- `planNodeInputPositions` / `planNodeInputDataSize` -- input rows and bytes
- `planNodeOutputPositions` / `planNodeOutputDataSize` -- output rows and bytes
- `planNodePhysicalInputDataSize` -- physical input bytes
- `planNodeSpilledDataSize` -- spilled data size

**Alternative considered and rejected: `/ui/api/query/{queryId}` API**

Trino's internal UI API at `/ui/api/query/{queryId}` returns full QueryInfo JSON with per-operator stats. However:
- It is an internal/undocumented API (not part of the client protocol spec)
- It may change between Trino versions without notice
- It requires the query to still be in Trino's memory (queries are purged after completion)
- It adds a second HTTP call per analysis
- The EXPLAIN ANALYZE text format is the official, documented contract

**Alternative considered and rejected: Combine EXPLAIN JSON + run query + StatementStats**

Running the query via `/v1/statement` provides `StatementStats` in the response, but `StatementStats` and `StageStats` only contain aggregate metrics (total CPU, rows, bytes) -- NOT per-operator breakdowns. [VERIFIED: Trino StatementStats.java, StageStats.java source]

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `pydantic` | `>=2.9,<3` | PlanNode, EstimatedPlan, ExecutedPlan models with `ConfigDict(extra='allow')` | Already a project dependency; `model_extra` gives us raw dict bag for free | [VERIFIED: pyproject.toml]
| `orjson` | `>=3.10` | Fast JSON parsing of EXPLAIN output | Already a project dependency; 3-5x faster than stdlib json | [VERIFIED: pyproject.toml]
| `structlog` | `>=25.5.0` | Schema drift warning logging | Already a project dependency | [VERIFIED: pyproject.toml]

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `syrupy` | `>=5.1.0` | Snapshot tests for parsed plan output | Already in dev deps; used for PLN-06 fixture gating | [VERIFIED: pyproject.toml]
| `re` (stdlib) | n/a | Regex parsing of EXPLAIN ANALYZE text output | For extracting per-operator metrics from text format |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Text parsing for EXPLAIN ANALYZE | `/ui/api/query/{queryId}` internal API | Internal API is richer but undocumented, version-fragile, requires query to be in memory |
| Text parsing for EXPLAIN ANALYZE | Wait for Trino to implement FORMAT JSON (#5786) | Issue has been open since 2020; no ETA |
| `model_extra` for raw bag | Explicit `raw: dict[str, Any]` field | `model_extra` avoids data duplication; pydantic handles it natively |

**No new dependencies needed.** All required libraries are already in the project.

## Architecture Patterns

### Recommended Project Structure
```
src/mcp_trino_optimizer/parser/
    __init__.py           # Public API: parse_estimated, parse_executed
    models.py             # PlanNode, EstimatedPlan, ExecutedPlan, SchemaDriftWarning
    parser.py             # JSON-to-typed-tree (estimated) + text-to-typed-tree (executed)
    normalizer.py         # ScanFilterProject collapse, Project walk-through

tests/fixtures/explain/
    480/
        simple_select.json           # EXPLAIN (FORMAT JSON) output
        simple_select_analyze.txt    # EXPLAIN ANALYZE text output
        join_query.json
        join_query_analyze.txt
        aggregate_query.json
        aggregate_query_analyze.txt
        iceberg_scan.json
        iceberg_scan_analyze.txt
    455/
        ... (same set)
    429/
        ... (same set)
```

Note: EXPLAIN ANALYZE fixtures must be `.txt` files (not `.json`) because EXPLAIN ANALYZE does not support FORMAT JSON.

### Pattern 1: Dual-Path Parser

**What:** The parser has two entry points -- one for EXPLAIN JSON, one for EXPLAIN ANALYZE text.
**When to use:** Always -- this is the fundamental architecture.

```python
# parser/__init__.py
from mcp_trino_optimizer.parser.models import EstimatedPlan, ExecutedPlan
from mcp_trino_optimizer.parser.parser import parse_estimated_plan, parse_executed_plan

__all__ = ["parse_estimated_plan", "parse_executed_plan", "EstimatedPlan", "ExecutedPlan"]
```

### Pattern 2: PlanNode with model_extra

**What:** Single generic PlanNode with typed common fields; unknown fields preserved in model_extra.
**When to use:** For every node in both estimated and executed plans.

```python
# Source: pydantic docs on extra='allow'
from pydantic import BaseModel, ConfigDict

class PlanNode(BaseModel):
    model_config = ConfigDict(extra="allow")

    # Core fields present in all plan nodes
    id: str
    name: str  # operator type, e.g. "TableScan", "InnerJoin"
    descriptor: dict[str, str] = {}
    outputs: list[OutputSymbol] = []
    details: list[str] = []
    estimates: list[CostEstimate] = []
    children: list["PlanNode"] = []

    # Runtime metrics (populated only for ExecutedPlan nodes)
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

    # Iceberg-specific (populated by normalizer for IcebergTableScan nodes)
    iceberg_split_count: int | None = None
    iceberg_file_count: int | None = None
    iceberg_partition_spec_id: int | None = None

    @property
    def operator_type(self) -> str:
        """Alias for name, for rule matching clarity."""
        return self.name

    @property
    def raw(self) -> dict[str, Any]:
        """Access model_extra as the raw dict bag (PLN-02)."""
        return self.model_extra or {}
```

### Pattern 3: Lenient Parsing with Drift Warnings

**What:** Parser never raises on unexpected structure; records warnings instead.
**When to use:** For all parsing operations.

```python
class SchemaDriftWarning(BaseModel):
    node_path: str           # e.g. "root.children[0].children[1]"
    field_name: str | None   # field that triggered the warning
    description: str         # human-readable description
    severity: Literal["info", "warning"] = "warning"
```

### Pattern 4: EXPLAIN JSON Node Structure

**What:** The actual structure of Trino EXPLAIN (FORMAT JSON) output. [VERIFIED: Trino source JsonRenderer.java + PR #12694]

```json
{
  "id": "6",
  "name": "Output",
  "descriptor": {
    "columnNames": "[returnflag]"
  },
  "outputs": [
    {
      "symbol": "returnflag",
      "type": "varchar(1)"
    }
  ],
  "details": [],
  "estimates": [
    {
      "outputRowCount": 10.0,
      "outputSizeInBytes": 60.0,
      "cpuCost": 34780027.7,
      "memoryCost": 0.0,
      "networkCost": 60.0
    }
  ],
  "children": [
    {
      "id": "5",
      "name": "Aggregate",
      "descriptor": {
        "type": "FINAL",
        "keys": "[returnflag]",
        "hash": "[]"
      },
      "outputs": [...],
      "details": [...],
      "estimates": [...],
      "children": [...]
    }
  ]
}
```

Key node names observed in Trino EXPLAIN output: [ASSUMED -- based on Trino source code review]
- `Output` -- final output node
- `Aggregate` -- with `descriptor.type` = PARTIAL, FINAL, SINGLE
- `TableScan` -- table scan (generic)
- `ScanFilterAndProject` -- fused scan+filter+project (this is the actual Trino name, NOT "ScanFilterProject")
- `Filter` -- standalone filter
- `Project` -- standalone projection
- `InnerJoin`, `LeftJoin`, `RightJoin`, `FullJoin`, `CrossJoin` -- join types
- `RemoteExchange` -- exchange node with `descriptor.type` = GATHER, REPARTITION, REPLICATE
- `LocalExchange` -- local exchange
- `RemoteSource` -- in distributed plans, references other fragments
- `SemiJoin` -- semi-join
- `SortOutput` -- sorting
- `TopN` -- top-N
- `Limit` -- limit
- `MarkDistinct` -- for DISTINCT operations
- `EnforceSingleRow` -- scalar subquery enforcement
- `Values` -- VALUES clause

### Pattern 5: ScanFilterAndProject Normalization

**What:** The fused `ScanFilterAndProject` node is decomposed into equivalent `TableScan` + `Filter` + `Project` nodes.
**When to use:** In-place during parsing, before any consumer sees the tree.

The `ScanFilterAndProject` node in Trino's EXPLAIN output contains the details of all three operations in its `details` list. The details typically contain:
- Table reference (e.g., `iceberg.schema.table`)
- Filter predicate (e.g., `WHERE ts > TIMESTAMP '...'`)
- Output columns (projection)

The `estimates` list for `ScanFilterAndProject` contains **three** `CostEstimate` entries: one for Scan, one for Filter, one for Project.

Normalization approach:
1. Detect nodes where `name == "ScanFilterAndProject"`
2. Create a `TableScan` node with scan details and scan estimates
3. If a filter predicate exists in details, wrap in a `Filter` node with filter estimates
4. Wrap in a `Project` node with project estimates and the original output symbols
5. Replace the fused node in the tree with this decomposed subtree

### Anti-Patterns to Avoid
- **Subclassing PlanNode per operator type:** Creates a combinatorial explosion; use `operator_type` string matching instead. [CITED: CONTEXT.md D-03]
- **Duplicating data in raw + typed fields:** Use `model_extra` as the raw bag -- no duplication. [CITED: CONTEXT.md D-04]
- **Raising exceptions on unknown nodes:** Produces `SchemaDriftWarning` instead. [CITED: CONTEXT.md D-06]
- **Assuming EXPLAIN ANALYZE returns JSON:** It returns TEXT only. Any code that tries `json.loads()` on EXPLAIN ANALYZE output will fail.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| JSON field preservation | Custom dict merging | Pydantic `ConfigDict(extra='allow')` + `model_extra` | Handles unknown fields automatically, zero code |
| Snapshot testing | Custom diff comparison | `syrupy` snapshot assertions | Purpose-built, handles update workflow, CI-friendly |
| JSON parsing | Custom parser | `orjson.loads()` | Fast, handles edge cases, already in deps |
| Plan tree walking | Ad-hoc recursive functions | Generic `walk()` / `find_nodes_by_type()` methods on plan | Write once, reuse in every rule |

**Key insight:** The biggest temptation is to hand-roll a "smart" JSON-to-model mapper. Use pydantic's built-in field mapping + extra handling instead.

## Iceberg Extraction Details

### What's Available in EXPLAIN (FORMAT JSON)

For an Iceberg table scan, the EXPLAIN (FORMAT JSON) output shows: [ASSUMED -- needs verification via fixture capture]
- `name`: `"TableScan"` or `"ScanFilterAndProject"`
- `descriptor.table`: The fully qualified table name (e.g., `iceberg.schema.table`)
- `details`: Contains filter predicates and column references
- `estimates`: CBO cost estimates (rows, bytes, CPU, memory, network)

**NOT available in EXPLAIN (FORMAT JSON):**
- Split count (runtime planning metric)
- File count (runtime planning metric)
- Partition spec ID (metadata, not in plan JSON)

### What's Available in EXPLAIN ANALYZE Text Output

For executed plans, the text output includes: [ASSUMED -- needs verification via fixture capture]
- Per-operator input/output rows and bytes
- CPU and scheduled time per operator
- Physical input data size
- Potentially split statistics in VERBOSE mode

### PLN-04 Strategy

Given that split count and file count are NOT in the EXPLAIN JSON:

1. **Split count and file count:** Extract from EXPLAIN ANALYZE text output where available. For estimated plans, these fields will be `None` -- they are execution-time metrics.
2. **Partition spec ID:** Query via the existing `CatalogSource` port (Iceberg `$partitions` metadata table) or extract from the table's metadata. This is NOT in the plan output itself.
3. **For offline mode:** Accept that split_count and file_count may be `None` unless the user provides EXPLAIN ANALYZE output.

The CONTEXT.md says "sourced from the operator's raw detail string and cross-checked against the multi-version fixture snapshots." This implies the information comes from parsing operator details in the plan output. During fixture capture, we need to verify exactly what Iceberg-specific details appear in:
- `EXPLAIN (FORMAT JSON)` for Iceberg table scans
- `EXPLAIN ANALYZE` text output for Iceberg table scans
- `EXPLAIN ANALYZE VERBOSE` text output for Iceberg table scans

## Fixture Capture Strategy

### Query Set for Fixtures

Minimum set (covers all required operator types): [ASSUMED -- informed by CONTEXT.md discretion]

1. `simple_select` -- `SELECT id, name FROM iceberg.test_schema.test_table WHERE id > 1`
2. `full_scan` -- `SELECT * FROM iceberg.test_schema.test_table`
3. `aggregate` -- `SELECT name, COUNT(*) FROM iceberg.test_schema.test_table GROUP BY name`
4. `join` -- Self-join or join with a second table to get join operators
5. `iceberg_partition_filter` -- `SELECT * FROM iceberg.test_schema.test_table WHERE ts >= TIMESTAMP '2025-01-16 00:00:00 UTC'` (partition-pruning query)

For each query, capture:
- `EXPLAIN (FORMAT JSON) <query>` -- save as `.json`
- `EXPLAIN ANALYZE <query>` -- save as `.txt`
- `EXPLAIN ANALYZE VERBOSE <query>` -- save as `_verbose.txt`

### Multi-Version Capture Process

1. Use the existing `.testing/docker-compose.yml` with `trinodb/trino:480`
2. Seed the Iceberg table via existing `tests/integration/fixtures.py`
3. Run all queries, save outputs to `tests/fixtures/explain/480/`
4. Change `docker-compose.yml` image to `trinodb/trino:455` (or nearest available), repeat
5. Change to `trinodb/trino:429`, repeat
6. Script this as `scripts/capture_fixtures.py`

**Important:** Trino image tags are exact version numbers (e.g., `trinodb/trino:429`, `trinodb/trino:455`). All are available on Docker Hub. [ASSUMED -- needs verification of specific middle version availability]

### Fixture File Naming Convention

```
tests/fixtures/explain/
    480/
        simple_select.json           # EXPLAIN (FORMAT JSON)
        simple_select_analyze.txt    # EXPLAIN ANALYZE
        full_scan.json
        full_scan_analyze.txt
        aggregate.json
        aggregate_analyze.txt
        join.json
        join_analyze.txt
        iceberg_partition_filter.json
        iceberg_partition_filter_analyze.txt
    455/
        ...
    429/
        ...
```

## Common Pitfalls

### Pitfall 1: EXPLAIN ANALYZE FORMAT JSON Assumption
**What goes wrong:** Code assumes EXPLAIN ANALYZE returns JSON. Parser crashes or returns empty plans.
**Why it happens:** EXPLAIN (FORMAT JSON) works fine; developers assume EXPLAIN ANALYZE has the same option.
**How to avoid:** Two separate parsing paths. `parse_estimated_plan()` expects JSON; `parse_executed_plan()` expects TEXT.
**Warning signs:** `json.JSONDecodeError` on EXPLAIN ANALYZE output; `{"raw": text}` fallback in current code.

### Pitfall 2: Node Name Instability Across Versions
**What goes wrong:** Node names or descriptor keys change between Trino versions. Parser breaks.
**Why it happens:** The EXPLAIN JSON format is explicitly NOT guaranteed to be backward compatible. [CITED: https://trino.io/docs/current/sql/explain.html -- "The output format is not guaranteed to be backward compatible across Trino versions."]
**How to avoid:** Lenient parsing (D-06). All field access via `getattr(node, field, default)` pattern. Unknown fields go to `model_extra`.
**Warning signs:** `SchemaDriftWarning` entries in parsed output.

### Pitfall 3: ScanFilterAndProject vs ScanFilterProject Naming
**What goes wrong:** Code looks for node name "ScanFilterProject" but Trino uses "ScanFilterAndProject".
**Why it happens:** The PROJECT.md and CONTEXT.md use the shorthand "ScanFilterProject" while Trino uses "ScanFilterAndProject".
**How to avoid:** During fixture capture, verify the exact node name. Use a constant for the name.
**Warning signs:** Normalization never triggers; rules see fused nodes.

### Pitfall 4: CostEstimate List Position for ScanFilterAndProject
**What goes wrong:** Parser takes the wrong estimate when ScanFilterAndProject has 3 estimate entries.
**Why it happens:** The fused node contains separate estimates for Scan, Filter, and Project in a single `estimates` list.
**How to avoid:** Document the list position convention (index 0 = scan, 1 = filter, 2 = project) and verify via fixtures.
**Warning signs:** Wildly wrong cost numbers on decomposed nodes.

### Pitfall 5: pydantic model_extra with PEP 563
**What goes wrong:** `from __future__ import annotations` breaks `model_extra` access at runtime.
**Why it happens:** PEP 563 defers annotation evaluation; pydantic 2 handles this but `model_extra` dict access patterns can be surprising.
**How to avoid:** Keep pydantic models at module scope (Phase 1 UAT lesson). Test `model_extra` access explicitly.
**Warning signs:** `model_extra` is `None` when it should have data.

### Pitfall 6: Iceberg Details Not in Plan JSON
**What goes wrong:** Parser expects split count, file count in EXPLAIN JSON but they're not there.
**Why it happens:** These are runtime metrics determined during split planning, not at EXPLAIN time.
**How to avoid:** Accept `None` for Iceberg runtime fields on EstimatedPlan. Populate only from EXPLAIN ANALYZE text output or metadata table queries.
**Warning signs:** Iceberg fields always `None` even for Iceberg tables.

## Code Examples

### EXPLAIN (FORMAT JSON) Parsing

```python
# Source: pydantic docs + Trino EXPLAIN JSON structure
import orjson
from pydantic import BaseModel, ConfigDict

class CostEstimate(BaseModel):
    output_row_count: float | None = None
    output_size_in_bytes: float | None = None
    cpu_cost: float | None = None
    memory_cost: float | None = None
    network_cost: float | None = None

class OutputSymbol(BaseModel):
    symbol: str
    type: str

class PlanNode(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    id: str
    name: str
    descriptor: dict[str, str] = {}
    outputs: list[OutputSymbol] = []
    details: list[str] = []
    estimates: list[CostEstimate] = []
    children: list["PlanNode"] = []

    # Runtime fields (None for estimated plans)
    cpu_time_ms: float | None = None
    wall_time_ms: float | None = None
    # ... etc

def parse_estimated_plan(json_text: str, trino_version: str | None = None) -> EstimatedPlan:
    """Parse EXPLAIN (FORMAT JSON) output into an EstimatedPlan."""
    warnings: list[SchemaDriftWarning] = []
    try:
        raw = orjson.loads(json_text)
    except Exception as e:
        raise ParseError(f"Invalid JSON: {e}") from e

    root = _parse_node(raw, path="root", warnings=warnings)
    root = normalize_tree(root, warnings=warnings)

    return EstimatedPlan(
        root=root,
        source_trino_version=trino_version,
        schema_drift_warnings=warnings,
    )
```

### EXPLAIN ANALYZE Text Parsing

```python
# Source: Trino EXPLAIN ANALYZE output format (docs + captured examples)
import re

# Example EXPLAIN ANALYZE text patterns:
# "CPU: 157.00ms (53.40%), Scheduled: 158.00ms (37.71%)"
# "Output: 818058 rows (22.62MB)"
# "Input avg.: 818058.00 rows, Input std.dev.: 0.00%"

_CPU_PATTERN = re.compile(r"CPU:\s+([\d.]+)(ms|s|us)")
_SCHEDULED_PATTERN = re.compile(r"Scheduled:\s+([\d.]+)(ms|s|us)")
_OUTPUT_PATTERN = re.compile(r"Output:\s+(\d+)\s+rows\s+\(([\d.]+)(B|kB|MB|GB)\)")
_INPUT_PATTERN = re.compile(r"Input:\s+(\d+)\s+rows\s+\(([\d.]+)(B|kB|MB|GB)\)")

def parse_executed_plan(text: str, trino_version: str | None = None) -> ExecutedPlan:
    """Parse EXPLAIN ANALYZE text output into an ExecutedPlan."""
    warnings: list[SchemaDriftWarning] = []
    # Parse fragments, operators, and metrics from text
    root = _parse_analyze_text(text, warnings=warnings)
    root = normalize_tree(root, warnings=warnings)

    return ExecutedPlan(
        root=root,
        source_trino_version=trino_version,
        schema_drift_warnings=warnings,
        # Top-level query metrics extracted from header
        total_cpu_time_ms=...,
        total_wall_time_ms=...,
        peak_memory_bytes=...,
    )
```

### Syrupy Snapshot Test Pattern

```python
# Source: syrupy docs + project conventions
import pytest
from syrupy.assertion import SnapshotAssertion
from pathlib import Path

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "explain"

@pytest.mark.parametrize("version", ["429", "455", "480"])
def test_estimated_plan_snapshot(version: str, snapshot: SnapshotAssertion) -> None:
    """Parsed EstimatedPlan matches snapshot for each Trino version."""
    fixture_path = FIXTURE_DIR / version / "simple_select.json"
    json_text = fixture_path.read_text()
    plan = parse_estimated_plan(json_text, trino_version=version)
    assert plan.model_dump(exclude_none=True) == snapshot

@pytest.mark.parametrize("version", ["429", "455", "480"])
def test_executed_plan_snapshot(version: str, snapshot: SnapshotAssertion) -> None:
    """Parsed ExecutedPlan matches snapshot for each Trino version."""
    fixture_path = FIXTURE_DIR / version / "simple_select_analyze.txt"
    text = fixture_path.read_text()
    plan = parse_executed_plan(text, trino_version=version)
    assert plan.model_dump(exclude_none=True) == snapshot
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `HTTP+SSE` MCP transport | Streamable HTTP | MCP spec 2025-03-26 | Transport layer (Phase 1, not this phase) |
| `ExplainPlan` placeholder (Phase 2) | `EstimatedPlan` + `ExecutedPlan` typed trees | Phase 3 (this phase) | Full typed plan access for rules |
| Assumed EXPLAIN ANALYZE has JSON format | TEXT-only confirmed | Trino grammar (all versions) | Must parse text for executed plans |

**Deprecated/outdated:**
- `ExplainPlan` dataclass in `ports/plan_source.py` -- replaced by `EstimatedPlan` and `ExecutedPlan`
- Phase 2's `_detect_plan_type` heuristic in `OfflinePlanSource` -- replaced by explicit parse entry points

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Trino EXPLAIN node name for fused scan+filter+project is "ScanFilterAndProject" (not "ScanFilterProject") | Architecture Patterns / Pitfall 3 | Normalization never triggers; must verify during fixture capture |
| A2 | Trino EXPLAIN (FORMAT JSON) estimates list has 3 entries for ScanFilterAndProject (scan, filter, project) | Pitfall 4 | Wrong cost attribution on decomposed nodes |
| A3 | Iceberg split count and file count are NOT available in EXPLAIN (FORMAT JSON) output | Iceberg Extraction | If available, simpler extraction; verify during fixture capture |
| A4 | Trino versions 429, 455, 480 all have compatible docker images on Docker Hub | Fixture Capture | Middle version may need adjustment |
| A5 | EXPLAIN ANALYZE text output format is consistent enough across Trino 429-480 for regex parsing | Architecture | If format changed significantly, need version-specific parsers |
| A6 | The specific Iceberg operator details (partition spec, etc.) visible in EXPLAIN ANALYZE text output | PLN-04 | May need to rely on metadata table queries via CatalogSource instead |

## Open Questions

1. **Exact ScanFilterAndProject node name and structure**
   - What we know: Trino fuses scan+filter+project into a single node. Various references use different names.
   - What's unclear: Is it "ScanFilterAndProject" or "ScanFilterProject" or just appears as "TableScan" with extra details?
   - Recommendation: Capture fixture from live Trino 480 and inspect. This is the first task in the plan.

2. **Iceberg details visible in EXPLAIN output**
   - What we know: Split count and file count are runtime metrics. Partition spec is metadata.
   - What's unclear: What Iceberg-specific information appears in the `details` field of an IcebergTableScan in EXPLAIN JSON vs EXPLAIN ANALYZE text?
   - Recommendation: Capture Iceberg table fixtures and inspect. If no split/file info in EXPLAIN ANALYZE text, document that PLN-04's "split count, file count" come from metadata table queries, not plan parsing.

3. **EXPLAIN ANALYZE text format stability across versions**
   - What we know: The format is text-based and has been consistent in documented examples.
   - What's unclear: Whether the exact regex patterns for metric extraction work across Trino 429-480.
   - Recommendation: Capture fixtures from all 3 versions, build regexes against 480, validate against 429 and 455.

4. **Whether to refactor Phase 2's EXPLAIN ANALYZE flow**
   - What we know: Phase 2 sends `EXPLAIN ANALYZE {sql}` (no FORMAT JSON) and falls back to `{"raw": plan_text}`.
   - What's unclear: Should Phase 3 change the TrinoClient to send `EXPLAIN ANALYZE VERBOSE {sql}` for richer metrics?
   - Recommendation: Start with regular EXPLAIN ANALYZE. Add VERBOSE as a follow-up if needed for PLN-04 Iceberg details.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Docker | Fixture capture, integration tests | Yes | 29.3.1 | -- |
| Docker Compose | Fixture capture, integration tests | Yes | v5.1.1 | -- |
| Python 3.11+ | Runtime | Via uv | 3.12 (project venv) | -- |
| uv | Package management | Yes | 0.11.6 | -- |
| Trino 480 image | Fixture capture | Available on Docker Hub | 480 | -- |
| Trino 455 image | Fixture capture | Assumed available | 455 | Use nearest available version |
| Trino 429 image | Fixture capture | Assumed available | 429 | Use nearest available version |

**Missing dependencies with no fallback:** None

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.3+ with pytest-asyncio 1.3.0+ |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/ -x --ignore=tests/integration -k "parser"` |
| Full suite command | `uv run pytest tests/ -x --ignore=tests/integration` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PLN-01 | Parser produces EstimatedPlan from JSON, ExecutedPlan from text | unit | `uv run pytest tests/parser/test_parser.py -x` | No -- Wave 0 |
| PLN-02 | model_extra preserves unknown fields | unit | `uv run pytest tests/parser/test_models.py::test_model_extra -x` | No -- Wave 0 |
| PLN-03 | ExecutedPlan nodes have CPU, wall, rows, bytes, memory metrics | unit | `uv run pytest tests/parser/test_parser.py::test_executed_metrics -x` | No -- Wave 0 |
| PLN-04 | IcebergTableScan exposes split_count, file_count, partition_spec_id | unit | `uv run pytest tests/parser/test_iceberg.py -x` | No -- Wave 0 |
| PLN-05 | ScanFilterAndProject normalized to TableScan+filter+project | unit | `uv run pytest tests/parser/test_normalizer.py -x` | No -- Wave 0 |
| PLN-06 | Multi-version fixtures parse without error, syrupy snapshot gated | snapshot | `uv run pytest tests/parser/test_snapshots.py -x` | No -- Wave 0 |
| PLN-07 | Unknown nodes produce SchemaDriftWarning, not exceptions | unit | `uv run pytest tests/parser/test_parser.py::test_schema_drift -x` | No -- Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/parser/ -x`
- **Per wave merge:** `uv run pytest tests/ -x --ignore=tests/integration`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/parser/__init__.py` -- package marker
- [ ] `tests/parser/test_models.py` -- PlanNode, EstimatedPlan, ExecutedPlan model tests
- [ ] `tests/parser/test_parser.py` -- JSON and text parsing tests
- [ ] `tests/parser/test_normalizer.py` -- ScanFilterAndProject normalization tests
- [ ] `tests/parser/test_iceberg.py` -- Iceberg field extraction tests
- [ ] `tests/parser/test_snapshots.py` -- syrupy snapshot tests for multi-version fixtures
- [ ] `tests/fixtures/explain/` -- fixture directory structure
- [ ] Fixture capture script: `scripts/capture_fixtures.py`

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | N/A -- parser is pure data transformation |
| V3 Session Management | No | N/A |
| V4 Access Control | No | N/A |
| V5 Input Validation | Yes | Pydantic model validation; size cap inherited from OfflinePlanSource (1MB) |
| V6 Cryptography | No | N/A |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Oversized plan JSON / text input | Denial of Service | 1MB size cap on OfflinePlanSource (already implemented in Phase 2). Parser should not amplify memory usage beyond input size. |
| Malicious content in plan node details | Information Disclosure | Plan details are untrusted content -- wrap in envelope per PLAT-11 when surfacing to MCP tools (Phase 8 concern, not Phase 3). |
| Regex DoS on EXPLAIN ANALYZE text | Denial of Service | Use non-backtracking regex patterns. Limit input size. Set parsing timeout. |

## Project Constraints (from CLAUDE.md)

- **Tech stack:** Python 3.11+, `uv` package manager, `pyproject.toml`, official `mcp` SDK, HTTP REST Trino client
- **Safety:** Read-only by default, all executed queries logged
- **Determinism:** Rule engine output must be deterministic given identical input -- parser output must therefore be deterministic
- **Testing:** `pytest>=8` + `pytest-asyncio>=1.3.0` + `syrupy>=5.1.0`
- **Lint/format:** `ruff>=0.15.10`
- **Type check:** `mypy>=1.11` in strict mode
- **Logging:** `structlog` to stderr only
- **Plan parsing:** Hand-rolled over `EXPLAIN (FORMAT JSON)`. No library exists. Build typed pydantic models from fixtures.
- **Pydantic models:** Must be at module scope (PEP 563 / FastMCP compatibility lesson from Phase 1)
- **Commit conventions:** `feat(03): ...` for code, `docs(03): ...` for docs, `test(03): ...` for test-only

## Sources

### Primary (HIGH confidence)
- [Trino EXPLAIN docs](https://trino.io/docs/current/sql/explain.html) -- FORMAT JSON structure, backward compatibility warning
- [Trino EXPLAIN ANALYZE docs](https://trino.io/docs/current/sql/explain-analyze.html) -- text output format, VERBOSE option, per-operator metrics
- [Trino ANTLR grammar](https://github.com/trinodb/trino/blob/master/core/trino-grammar/src/main/antlr4/io/trino/grammar/sql/SqlBase.g4) -- confirms EXPLAIN ANALYZE does NOT support FORMAT option
- [Trino PlanNodeStats.java](https://github.com/trinodb/trino/blob/master/core/trino-main/src/main/java/io/trino/sql/planner/planprinter/PlanNodeStats.java) -- per-operator runtime metric fields
- [Trino JsonRenderer.java](https://github.com/trinodb/trino/blob/master/core/trino-main/src/main/java/io/trino/sql/planner/planprinter/JsonRenderer.java) -- JSON output node structure
- [Trino StatementStats.java](https://github.com/trinodb/trino/blob/master/client/trino-client/src/main/java/io/trino/client/StatementStats.java) -- confirms no per-operator stats in /v1/statement response
- [Trino PR #12694](https://github.com/trinodb/trino/pull/12694) -- EXPLAIN (TYPE LOGICAL, FORMAT JSON) implementation with example output
- [GitHub issue #5786](https://github.com/trinodb/trino/issues/5786) -- JSON format for EXPLAIN ANALYZE still open
- [Pydantic ConfigDict extra='allow'](https://docs.pydantic.dev/latest/concepts/config/#extra-attributes) -- model_extra behavior
- [Trino client protocol](https://trino.io/docs/current/develop/client-protocol.html) -- /v1/statement response structure

### Secondary (MEDIUM confidence)
- [Trino Cost in EXPLAIN](https://trino.io/docs/current/optimizer/cost-in-explain.html) -- ScanFilterAndProject estimate format
- [Trino Iceberg connector](https://trino.io/docs/current/connector/iceberg.html) -- table metadata, partition spec

### Tertiary (LOW confidence)
- Node name "ScanFilterAndProject" -- inferred from Trino source references and documentation. Needs fixture verification.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all libraries already in project, no new deps needed
- Architecture (EstimatedPlan from JSON): HIGH -- EXPLAIN JSON format well-documented
- Architecture (ExecutedPlan from text): MEDIUM -- text parsing approach sound but exact format needs fixture verification
- Normalization (ScanFilterAndProject): MEDIUM -- exact node name and details structure needs fixture verification
- Iceberg extraction: LOW -- split count and file count availability in plan output unconfirmed
- Pitfalls: HIGH -- EXPLAIN ANALYZE JSON limitation is the critical discovery

**Research date:** 2026-04-12
**Valid until:** 2026-05-12 (30 days -- Trino EXPLAIN format is stable within major versions)
