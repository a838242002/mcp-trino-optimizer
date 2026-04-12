---
phase: 03-plan-parser-normalizer
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - src/mcp_trino_optimizer/parser/__init__.py
  - src/mcp_trino_optimizer/parser/models.py
  - src/mcp_trino_optimizer/parser/parser.py
  - src/mcp_trino_optimizer/parser/normalizer.py
  - src/mcp_trino_optimizer/ports/plan_source.py
  - src/mcp_trino_optimizer/ports/__init__.py
  - src/mcp_trino_optimizer/adapters/offline/json_plan_source.py
  - src/mcp_trino_optimizer/adapters/trino/live_plan_source.py
  - tests/parser/__init__.py
  - tests/parser/test_models.py
  - tests/parser/test_parser.py
  - tests/parser/test_normalizer.py
  - tests/adapters/test_offline_plan_source.py
  - tests/adapters/test_port_conformance.py
autonomous: true
requirements:
  - PLN-01
  - PLN-02
  - PLN-03
  - PLN-04
  - PLN-05
  - PLN-07

must_haves:
  truths:
    - "EXPLAIN (FORMAT JSON) fixture parses into EstimatedPlan with typed PlanNode tree"
    - "EXPLAIN ANALYZE text fixture parses into ExecutedPlan with per-operator CPU, wall, rows, bytes, memory"
    - "Unknown node types and fields produce SchemaDriftWarning, never exceptions"
    - "ScanFilterAndProject nodes are decomposed into TableScan + Filter + Project before consumers see them"
    - "IcebergTableScan nodes expose iceberg_split_count, iceberg_file_count, iceberg_partition_spec_id"
    - "model_extra preserves all original fields not mapped to typed attributes"
    - "PlanSource protocol returns EstimatedPlan and ExecutedPlan instead of ExplainPlan"
  artifacts:
    - path: "src/mcp_trino_optimizer/parser/models.py"
      provides: "PlanNode, EstimatedPlan, ExecutedPlan, SchemaDriftWarning, CostEstimate, OutputSymbol"
      contains: "class PlanNode"
    - path: "src/mcp_trino_optimizer/parser/parser.py"
      provides: "parse_estimated_plan, parse_executed_plan"
      exports: ["parse_estimated_plan", "parse_executed_plan"]
    - path: "src/mcp_trino_optimizer/parser/normalizer.py"
      provides: "normalize_plan_tree"
      contains: "ScanFilterAndProject"
    - path: "src/mcp_trino_optimizer/parser/__init__.py"
      provides: "Public API re-exports"
      contains: "parse_estimated_plan"
    - path: "src/mcp_trino_optimizer/ports/plan_source.py"
      provides: "Updated PlanSource protocol with EstimatedPlan/ExecutedPlan"
      contains: "class EstimatedPlan"
  key_links:
    - from: "src/mcp_trino_optimizer/parser/parser.py"
      to: "src/mcp_trino_optimizer/parser/models.py"
      via: "imports PlanNode, EstimatedPlan, ExecutedPlan"
      pattern: "from.*models import"
    - from: "src/mcp_trino_optimizer/parser/parser.py"
      to: "src/mcp_trino_optimizer/parser/normalizer.py"
      via: "calls normalize_plan_tree after building tree"
      pattern: "normalize_plan_tree"
    - from: "src/mcp_trino_optimizer/adapters/offline/json_plan_source.py"
      to: "src/mcp_trino_optimizer/parser/parser.py"
      via: "calls parse_estimated_plan/parse_executed_plan"
      pattern: "parse_estimated_plan"
    - from: "src/mcp_trino_optimizer/ports/plan_source.py"
      to: "src/mcp_trino_optimizer/parser/models.py"
      via: "re-exports EstimatedPlan, ExecutedPlan from parser.models"
      pattern: "EstimatedPlan"
---

<objective>
Build the typed plan parser, pydantic models, and normalizer that convert raw Trino EXPLAIN output into
`EstimatedPlan` and `ExecutedPlan` domain types, replacing the Phase 2 placeholder `ExplainPlan`.

Purpose: The parser is the foundation for Phase 4's rule engine. Every rule reads typed `PlanNode` trees
with per-operator metrics, Iceberg details, and version-drift tolerance. Without a typed parser, rules
would need to navigate raw dicts -- fragile, untestable, and version-dependent.

Output: New `parser/` subpackage (models, parser, normalizer), updated ports and adapters, comprehensive
unit tests.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md
@.planning/phases/03-plan-parser-normalizer/03-CONTEXT.md
@.planning/phases/03-plan-parser-normalizer/03-RESEARCH.md

<interfaces>
<!-- Key types and contracts the executor needs. Extracted from codebase. -->

From src/mcp_trino_optimizer/ports/plan_source.py (BEING REPLACED):
```python
@dataclass
class ExplainPlan:
    plan_json: dict[str, Any]
    plan_type: Literal["estimated", "executed", "distributed"]
    source_trino_version: str | None = None
    raw_text: str = field(default="")

@runtime_checkable
class PlanSource(Protocol):
    async def fetch_plan(self, sql: str) -> ExplainPlan: ...
    async def fetch_analyze_plan(self, sql: str) -> ExplainPlan: ...
    async def fetch_distributed_plan(self, sql: str) -> ExplainPlan: ...
```

From src/mcp_trino_optimizer/ports/__init__.py:
```python
__all__ = ["CatalogSource", "ExplainPlan", "PlanSource", "StatsSource"]
```

From src/mcp_trino_optimizer/adapters/offline/json_plan_source.py:
```python
class OfflinePlanSource:
    async def fetch_plan(self, sql: str) -> ExplainPlan: ...
    async def fetch_analyze_plan(self, sql: str) -> ExplainPlan: ...
    async def fetch_distributed_plan(self, sql: str) -> ExplainPlan: ...
```

From src/mcp_trino_optimizer/adapters/trino/live_plan_source.py:
```python
class LivePlanSource:
    def __init__(self, client: TrinoClient) -> None: ...
    async def fetch_plan(self, sql: str) -> ExplainPlan: ...
    async def fetch_analyze_plan(self, sql: str) -> ExplainPlan: ...
    async def fetch_distributed_plan(self, sql: str) -> ExplainPlan: ...
```

Trino EXPLAIN (FORMAT JSON) node structure (from 03-RESEARCH.md):
```json
{
  "id": "6",
  "name": "Output",
  "descriptor": {"columnNames": "[returnflag]"},
  "outputs": [{"symbol": "returnflag", "type": "varchar(1)"}],
  "details": [],
  "estimates": [{"outputRowCount": 10.0, "outputSizeInBytes": 60.0, "cpuCost": 34780027.7, "memoryCost": 0.0, "networkCost": 60.0}],
  "children": [...]
}
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Parser models and dual-path parser</name>
  <files>
    src/mcp_trino_optimizer/parser/__init__.py
    src/mcp_trino_optimizer/parser/models.py
    src/mcp_trino_optimizer/parser/parser.py
    tests/parser/__init__.py
    tests/parser/test_models.py
    tests/parser/test_parser.py
  </files>
  <read_first>
    src/mcp_trino_optimizer/ports/plan_source.py
    src/mcp_trino_optimizer/ports/__init__.py
    .planning/phases/03-plan-parser-normalizer/03-RESEARCH.md
    .planning/phases/03-plan-parser-normalizer/03-CONTEXT.md
  </read_first>
  <behavior>
    - Test: PlanNode with known fields populates typed attributes; unknown fields land in model_extra
    - Test: PlanNode.raw property returns model_extra dict
    - Test: PlanNode.operator_type property returns name
    - Test: CostEstimate parses outputRowCount, outputSizeInBytes, cpuCost, memoryCost, networkCost
    - Test: OutputSymbol parses symbol and type
    - Test: SchemaDriftWarning has node_path, field_name, description, severity fields
    - Test: EstimatedPlan has root PlanNode + schema_drift_warnings list + source_trino_version
    - Test: ExecutedPlan has root PlanNode + schema_drift_warnings list + source_trino_version
    - Test: parse_estimated_plan parses valid EXPLAIN JSON into EstimatedPlan with typed tree
    - Test: parse_estimated_plan with unknown node type returns node with operator_type set, no exception
    - Test: parse_estimated_plan with unknown fields preserves them in model_extra
    - Test: parse_estimated_plan with missing optional fields (no estimates, no details) still parses
    - Test: parse_estimated_plan with completely invalid JSON raises ParseError
    - Test: parse_estimated_plan with wrong top-level structure (list instead of dict) raises ParseError
    - Test: parse_estimated_plan records SchemaDriftWarning for nodes with unexpected structure
    - Test: parse_executed_plan parses EXPLAIN ANALYZE text output into ExecutedPlan with per-operator metrics
    - Test: parse_executed_plan extracts cpu_time_ms, wall_time_ms, input_rows, input_bytes, output_rows, output_bytes, peak_memory_bytes per node
    - Test: parse_executed_plan with malformed text line records SchemaDriftWarning, does not raise
    - Test: EstimatedPlan.walk() yields all nodes in DFS order
    - Test: EstimatedPlan.find_nodes_by_type("TableScan") returns only TableScan nodes
    - Test: IcebergTableScan node populates iceberg_split_count, iceberg_file_count, iceberg_partition_spec_id from EXPLAIN ANALYZE text details
  </behavior>
  <action>
Create the `src/mcp_trino_optimizer/parser/` subpackage per D-02:

**models.py** (per D-03, D-04, D-05):
- `CostEstimate(BaseModel)`: fields `output_row_count: float | None`, `output_size_in_bytes: float | None`, `cpu_cost: float | None`, `memory_cost: float | None`, `network_cost: float | None`. Use `model_config = ConfigDict(populate_by_name=True)` with `Field(alias=...)` for camelCase JSON keys (`outputRowCount` -> `output_row_count`, etc.).
- `OutputSymbol(BaseModel)`: fields `symbol: str`, `type: str`.
- `SchemaDriftWarning(BaseModel)`: fields `node_path: str`, `field_name: str | None = None`, `description: str`, `severity: Literal["info", "warning"] = "warning"`.
- `PlanNode(BaseModel)`: `model_config = ConfigDict(extra="allow", populate_by_name=True)`. Fields: `id: str`, `name: str` (the operator type), `descriptor: dict[str, str] = {}`, `outputs: list[OutputSymbol] = []`, `details: list[str] = []`, `estimates: list[CostEstimate] = []`, `children: list[PlanNode] = []`. Runtime metric fields (all `None` for estimated): `cpu_time_ms: float | None = None`, `wall_time_ms: float | None = None`, `input_rows: int | None = None`, `input_bytes: int | None = None`, `output_rows: int | None = None`, `output_bytes: int | None = None`, `peak_memory_bytes: int | None = None`, `physical_input_bytes: int | None = None`, `spilled_bytes: int | None = None`, `blocked_time_ms: float | None = None`. Iceberg fields (per D-12): `iceberg_split_count: int | None = None`, `iceberg_file_count: int | None = None`, `iceberg_partition_spec_id: int | None = None`. Properties: `operator_type -> str` (returns `self.name`), `raw -> dict[str, Any]` (returns `self.model_extra or {}`).
- `ParseError(Exception)`: raised only on truly unparseable input.
- `BasePlan(BaseModel)`: shared base with `root: PlanNode`, `schema_drift_warnings: list[SchemaDriftWarning] = []`, `source_trino_version: str | None = None`, `raw_text: str = ""`. Methods: `walk() -> Iterator[PlanNode]` (DFS traversal), `find_nodes_by_type(operator_type: str) -> list[PlanNode]`.
- `EstimatedPlan(BasePlan)`: `plan_type: Literal["estimated"] = "estimated"`.
- `ExecutedPlan(BasePlan)`: `plan_type: Literal["executed"] = "executed"`.

**parser.py** (per D-06):
- `parse_estimated_plan(json_text: str, trino_version: str | None = None) -> EstimatedPlan`: Parse the JSON via `orjson.loads()`. Build a PlanNode tree recursively from the JSON dict. For each node, map known Trino JSON camelCase fields to PlanNode typed fields. Unknown fields are automatically captured by `model_extra`. If the top-level JSON is not a dict or is invalid JSON, raise `ParseError`. For any unexpected structure within the tree (e.g., missing `id` or `name` on a child), create a SchemaDriftWarning and use defaults. Call `normalize_plan_tree()` on the built tree before returning.
- `parse_executed_plan(text: str, trino_version: str | None = None) -> ExecutedPlan`: Parse EXPLAIN ANALYZE text output. Use regex patterns to extract tree structure from indentation, operator names from lines like `- OperatorName[details]` or `└─ OperatorName[details]`, and per-operator metrics from lines containing `CPU:`, `Output:`, `Input:`, `Peak memory:`. Build a PlanNode tree with runtime metric fields populated. Record SchemaDriftWarning for any line that cannot be parsed. For Iceberg scans, extract split count, file count from detail lines (patterns like `Input: N rows (XMB), N splits`, `Files read: N`). Call `normalize_plan_tree()` on the built tree before returning.
- Helper `_build_node(node_dict: dict, path: str, warnings: list) -> PlanNode`: Recursive builder for estimated plan nodes.

**__init__.py**:
```python
from mcp_trino_optimizer.parser.models import (
    BasePlan, CostEstimate, EstimatedPlan, ExecutedPlan,
    OutputSymbol, ParseError, PlanNode, SchemaDriftWarning,
)
from mcp_trino_optimizer.parser.parser import parse_estimated_plan, parse_executed_plan

__all__ = [
    "BasePlan", "CostEstimate", "EstimatedPlan", "ExecutedPlan",
    "OutputSymbol", "ParseError", "PlanNode", "SchemaDriftWarning",
    "parse_estimated_plan", "parse_executed_plan",
]
```

Keep pydantic models at module scope (Phase 1 UAT lesson -- no PEP 563 `from __future__ import annotations` in models.py). Do NOT use `from __future__ import annotations` in `models.py` -- use runtime type expressions for pydantic compatibility.

Tests go in `tests/parser/test_models.py` (model behavior) and `tests/parser/test_parser.py` (parsing logic). Use inline fixture dicts for unit tests (real captured fixtures are Plan 02's scope). For EXPLAIN ANALYZE text parsing tests, use representative text snippets modeled on the format documented in 03-RESEARCH.md.
  </action>
  <verify>
    <automated>cd /Users/allen/repo/mcp-trino-optimizer && uv run pytest tests/parser/ -x -v 2>&1 | tail -30</automated>
  </verify>
  <acceptance_criteria>
    - src/mcp_trino_optimizer/parser/models.py contains `class PlanNode(BaseModel)` with `model_config = ConfigDict(extra="allow"`
    - src/mcp_trino_optimizer/parser/models.py contains `class EstimatedPlan(BasePlan)` and `class ExecutedPlan(BasePlan)`
    - src/mcp_trino_optimizer/parser/models.py contains `class SchemaDriftWarning(BaseModel)` with `node_path: str`
    - src/mcp_trino_optimizer/parser/models.py contains `class ParseError(Exception)`
    - src/mcp_trino_optimizer/parser/models.py does NOT contain `from __future__ import annotations`
    - src/mcp_trino_optimizer/parser/parser.py contains `def parse_estimated_plan(` and `def parse_executed_plan(`
    - src/mcp_trino_optimizer/parser/__init__.py contains `parse_estimated_plan` and `parse_executed_plan` in __all__
    - tests/parser/test_models.py contains tests for PlanNode.raw, PlanNode.operator_type, model_extra preservation
    - tests/parser/test_parser.py contains tests for both estimated and executed plan parsing
    - tests/parser/test_parser.py contains a test that unknown node types do NOT raise exceptions
    - tests/parser/test_parser.py contains a test for SchemaDriftWarning generation
    - `uv run pytest tests/parser/ -x` exits 0
  </acceptance_criteria>
  <done>
    PlanNode, EstimatedPlan, ExecutedPlan, SchemaDriftWarning models exist with correct fields.
    parse_estimated_plan converts EXPLAIN JSON to typed tree. parse_executed_plan converts EXPLAIN ANALYZE text to typed tree.
    Unknown fields preserved in model_extra. Schema drift produces warnings, not exceptions.
    All parser unit tests pass.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Normalizer + port/adapter migration + integration tests</name>
  <files>
    src/mcp_trino_optimizer/parser/normalizer.py
    src/mcp_trino_optimizer/ports/plan_source.py
    src/mcp_trino_optimizer/ports/__init__.py
    src/mcp_trino_optimizer/adapters/offline/json_plan_source.py
    src/mcp_trino_optimizer/adapters/trino/live_plan_source.py
    tests/parser/test_normalizer.py
    tests/adapters/test_offline_plan_source.py
    tests/adapters/test_port_conformance.py
  </files>
  <read_first>
    src/mcp_trino_optimizer/parser/models.py
    src/mcp_trino_optimizer/parser/parser.py
    src/mcp_trino_optimizer/parser/__init__.py
    src/mcp_trino_optimizer/ports/plan_source.py
    src/mcp_trino_optimizer/ports/__init__.py
    src/mcp_trino_optimizer/adapters/offline/json_plan_source.py
    src/mcp_trino_optimizer/adapters/trino/live_plan_source.py
    tests/adapters/test_offline_plan_source.py
    tests/adapters/test_port_conformance.py
    .planning/phases/03-plan-parser-normalizer/03-RESEARCH.md
  </read_first>
  <behavior>
    - Test: normalize_plan_tree with ScanFilterAndProject node decomposes into Project(Filter(TableScan)) subtree
    - Test: normalize_plan_tree with ScanFilterAndProject without filter predicate decomposes into Project(TableScan)
    - Test: normalize_plan_tree with Project wrapper around TableScan is transparent to find_nodes_by_type("TableScan")
    - Test: normalize_plan_tree with no ScanFilterAndProject nodes returns tree unchanged
    - Test: normalize_plan_tree with nested ScanFilterAndProject (in children of joins) normalizes all instances
    - Test: ScanFilterAndProject estimates list split correctly (index 0=scan, 1=filter, 2=project)
    - Test: PlanSource protocol fetch_plan returns EstimatedPlan (not ExplainPlan)
    - Test: PlanSource protocol fetch_analyze_plan returns ExecutedPlan (not ExplainPlan)
    - Test: OfflinePlanSource.fetch_plan returns EstimatedPlan with typed PlanNode tree
    - Test: OfflinePlanSource.fetch_analyze_plan returns ExecutedPlan with parsed text
    - Test: OfflinePlanSource still enforces 1MB size cap
    - Test: OfflinePlanSource isinstance check against PlanSource protocol still passes
    - Test: LivePlanSource isinstance check against PlanSource protocol still passes
  </behavior>
  <action>
**normalizer.py** (per D-11, D-13):

Create `normalize_plan_tree(root: PlanNode, warnings: list[SchemaDriftWarning]) -> PlanNode`:
- Walk the tree recursively (depth-first, children first so bottom-up).
- For any node where `name == "ScanFilterAndProject"` (note: the actual Trino name is `ScanFilterAndProject`, NOT `ScanFilterProject` -- see 03-RESEARCH.md Pitfall 3):
  - Create a `TableScan` PlanNode with the table descriptor from the original node, using `estimates[0]` if available.
  - If the `details` list contains a filter predicate (heuristic: any detail string containing `WHERE` or a comparison operator like `=`, `>`, `<`, `!=`, `IN`, `BETWEEN`), create a `Filter` PlanNode wrapping the TableScan, with `estimates[1]` if available, and the filter expression stored in `details`.
  - Create a `Project` PlanNode wrapping the Filter (or TableScan if no filter), with `estimates[2]` if available, and the original `outputs`.
  - Replace the `ScanFilterAndProject` node in the parent's children list with the decomposed subtree.
  - Transfer Iceberg fields (`iceberg_*`) from the original node to the new `TableScan` node.
  - Unknown extra fields from the original node's `model_extra` go to the `TableScan` node.
- For `Project` wrapper walk-through: no structural change needed. The `find_nodes_by_type` method on BasePlan already walks through Project nodes since it does DFS on all children. The normalization just ensures `ScanFilterAndProject` is decomposed -- `Project` transparency is inherent in the tree walk.
- Generate new node IDs for decomposed nodes: `{original_id}_scan`, `{original_id}_filter`, `{original_id}_project`.

**Update ports/plan_source.py** (per D-01):
- Remove `ExplainPlan` dataclass entirely.
- Import `EstimatedPlan` and `ExecutedPlan` from `mcp_trino_optimizer.parser.models`.
- Update `PlanSource` protocol: `fetch_plan()` returns `EstimatedPlan`, `fetch_analyze_plan()` returns `ExecutedPlan`, `fetch_distributed_plan()` returns `EstimatedPlan` (distributed plans are still estimated-type, just with fragment info).
- Keep the `@runtime_checkable` decorator and `Protocol` base.

**Update ports/__init__.py**:
- Replace `ExplainPlan` export with `EstimatedPlan`, `ExecutedPlan`.
- Update `__all__` to `["CatalogSource", "EstimatedPlan", "ExecutedPlan", "PlanSource", "StatsSource"]`.

**Update adapters/offline/json_plan_source.py**:
- Import `parse_estimated_plan`, `parse_executed_plan` from `mcp_trino_optimizer.parser`.
- Import `EstimatedPlan`, `ExecutedPlan` from `mcp_trino_optimizer.parser.models`.
- `fetch_plan()`: validate size, call `parse_estimated_plan(sql)`, return the `EstimatedPlan`. The `sql` parameter is the raw JSON text.
- `fetch_analyze_plan()`: validate size, call `parse_executed_plan(sql)`, return the `ExecutedPlan`. The `sql` parameter is the raw EXPLAIN ANALYZE text.
- `fetch_distributed_plan()`: validate size, call `parse_estimated_plan(sql)`, return the `EstimatedPlan` (distributed plans are JSON format). Set `plan_type` to track it's distributed if needed, or just return as EstimatedPlan.
- Remove `_detect_plan_type()`, `_EXECUTED_PLAN_KEYS`, and `_parse_json()` helpers -- parsing now delegated to the parser module.
- Keep `_validate_size()` and `MAX_PLAN_BYTES` for security.

**Update adapters/trino/live_plan_source.py**:
- Change return types: `fetch_plan()` returns `EstimatedPlan`, `fetch_analyze_plan()` returns `ExecutedPlan`, `fetch_distributed_plan()` returns `EstimatedPlan`.
- The TrinoClient still returns ExplainPlan internally from Phase 2 -- wrap the result by calling `parse_estimated_plan(result.raw_text or orjson.dumps(result.plan_json).decode())` for estimated plans and `parse_executed_plan(result.raw_text)` for executed plans. This bridges Phase 2's TrinoClient output to Phase 3's typed domain.
- Import `parse_estimated_plan`, `parse_executed_plan` from `mcp_trino_optimizer.parser`.

**Update tests/adapters/test_offline_plan_source.py**:
- Update assertions: `fetch_plan()` returns `EstimatedPlan` (not `ExplainPlan`), `fetch_analyze_plan()` returns `ExecutedPlan`.
- Test that the returned objects have typed `root` PlanNode trees.
- Verify `OfflinePlanSource` still passes `isinstance(source, PlanSource)`.
- Verify 1MB size cap still works.

**Update tests/adapters/test_port_conformance.py**:
- Update type expectations from `ExplainPlan` to `EstimatedPlan`/`ExecutedPlan`.

Note: The TrinoClient's internal `_execute_explain` method still returns the old format. LivePlanSource now bridges by parsing. A future Phase 2 cleanup could update TrinoClient internals, but it is not required -- the port contract is clean.
  </action>
  <verify>
    <automated>cd /Users/allen/repo/mcp-trino-optimizer && uv run pytest tests/parser/ tests/adapters/test_offline_plan_source.py tests/adapters/test_port_conformance.py tests/adapters/test_ports.py -x -v 2>&1 | tail -40</automated>
  </verify>
  <acceptance_criteria>
    - src/mcp_trino_optimizer/parser/normalizer.py contains `def normalize_plan_tree(`
    - src/mcp_trino_optimizer/parser/normalizer.py contains string `ScanFilterAndProject` (exact Trino name)
    - src/mcp_trino_optimizer/ports/plan_source.py does NOT contain `class ExplainPlan`
    - src/mcp_trino_optimizer/ports/plan_source.py contains `EstimatedPlan` in fetch_plan return type
    - src/mcp_trino_optimizer/ports/plan_source.py contains `ExecutedPlan` in fetch_analyze_plan return type
    - src/mcp_trino_optimizer/ports/__init__.py contains `EstimatedPlan` and `ExecutedPlan` in __all__
    - src/mcp_trino_optimizer/ports/__init__.py does NOT contain `ExplainPlan`
    - src/mcp_trino_optimizer/adapters/offline/json_plan_source.py contains `parse_estimated_plan`
    - src/mcp_trino_optimizer/adapters/offline/json_plan_source.py does NOT contain `class ExplainPlan` or `_detect_plan_type`
    - tests/parser/test_normalizer.py contains test for ScanFilterAndProject decomposition
    - tests/adapters/test_offline_plan_source.py asserts return type is EstimatedPlan or ExecutedPlan
    - `uv run pytest tests/parser/ tests/adapters/ -x` exits 0
    - `uv run pytest tests/ -x --ignore=tests/integration` exits 0 (full non-integration suite still passes)
  </acceptance_criteria>
  <done>
    ScanFilterAndProject normalization decomposes fused nodes into TableScan + Filter + Project.
    ExplainPlan is completely removed from ports. PlanSource returns EstimatedPlan/ExecutedPlan.
    OfflinePlanSource and LivePlanSource updated. All existing tests pass with new types.
    No code anywhere imports ExplainPlan.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| User JSON input -> parser | Untrusted EXPLAIN JSON text from offline mode crosses into the parser |
| EXPLAIN ANALYZE text -> parser | Text output from Trino (trusted if live, untrusted if pasted) crosses into regex parsing |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-03-01 | D (Denial of Service) | parse_estimated_plan | mitigate | OfflinePlanSource already enforces 1MB size cap (MAX_PLAN_BYTES) before calling parser. Parser must not allocate unbounded memory for deeply nested trees -- cap recursion depth at 100 levels. |
| T-03-02 | T (Tampering) | model_extra raw bag | accept | model_extra preserves original fields for auditability. No user input flows back into SQL execution from model_extra -- it is read-only evidence for rules. Low risk. |
| T-03-03 | I (Information Disclosure) | SchemaDriftWarning | mitigate | Warnings may contain field names from the plan but never raw SQL or credentials. structlog redaction (Phase 1 PLAT-07) applies when warnings are logged. |
| T-03-04 | D (Denial of Service) | parse_executed_plan regex | mitigate | Cap input text size (same 1MB from OfflinePlanSource). Use non-backtracking regex patterns (no nested quantifiers). Set re.DOTALL only where needed. |
| T-03-05 | S (Spoofing) | PlanNode fields | accept | Malicious plan JSON could set misleading operator names or metrics. Rules should cross-validate evidence, not trust single fields blindly. This is inherent to offline mode and documented. |
</threat_model>

<verification>
1. `uv run pytest tests/parser/ -x -v` -- all parser tests pass
2. `uv run pytest tests/adapters/ -x -v` -- all adapter tests pass with new types
3. `uv run pytest tests/ -x --ignore=tests/integration` -- full non-integration suite passes
4. `uv run ruff check src/mcp_trino_optimizer/parser/` -- no lint errors
5. `grep -r "ExplainPlan" src/` returns zero matches (clean removal)
6. `grep -r "from.*plan_source import.*ExplainPlan" tests/` returns zero matches
</verification>

<success_criteria>
- EstimatedPlan and ExecutedPlan are the only plan domain types (ExplainPlan fully removed)
- EXPLAIN JSON parses into typed PlanNode trees with model_extra preservation
- EXPLAIN ANALYZE text parses into ExecutedPlan with per-operator runtime metrics
- ScanFilterAndProject normalized to TableScan + Filter + Project in all parsed trees
- Unknown nodes and fields produce SchemaDriftWarning, never exceptions
- IcebergTableScan nodes expose typed split_count, file_count, partition_spec_id fields
- All non-integration tests pass
</success_criteria>

<output>
After completion, create `.planning/phases/03-plan-parser-normalizer/03-01-SUMMARY.md`
</output>
