---
phase: 04-rule-engine-13-deterministic-rules
plan: 02
type: execute
wave: 2
depends_on:
  - 04-01-rule-infrastructure-PLAN.md
files_modified:
  - src/mcp_trino_optimizer/rules/r1_missing_stats.py
  - src/mcp_trino_optimizer/rules/r2_partition_pruning.py
  - src/mcp_trino_optimizer/rules/r3_predicate_pushdown.py
  - src/mcp_trino_optimizer/rules/r4_dynamic_filtering.py
  - tests/rules/test_r1_missing_stats.py
  - tests/rules/test_r2_partition_pruning.py
  - tests/rules/test_r3_predicate_pushdown.py
  - tests/rules/test_r4_dynamic_filtering.py
autonomous: true
requirements:
  - RUL-06
  - RUL-07
  - RUL-08
  - RUL-09
  - RUL-10
  - RUL-21

must_haves:
  truths:
    - "R1 fires on a TableScan node with NaN estimated outputRowCount or null table_stats.row_count"
    - "R1 does not fire when table_stats.row_count is present and estimates are not NaN"
    - "R2 fires when a scan has a filterPredicate but no 'constraint on [' in descriptor.table"
    - "R2 does not fire when descriptor.table contains 'constraint on [' (pruning applied)"
    - "R3 fires when filterPredicate contains a function-wrapped column (date(), cast(), year(), etc.)"
    - "R3 does not fire on a range predicate with no function wrapping"
    - "R4 fires on InnerJoin with equality join condition but no dynamicFilterAssignments in details"
    - "R4 does not fire when dynamicFilterAssignments present in join AND dynamicFilters present in probe scan"
    - "Each rule has synthetic-minimum, realistic (from Phase 3 fixtures), and negative-control tests"
  artifacts:
    - path: "src/mcp_trino_optimizer/rules/r1_missing_stats.py"
      provides: "R1MissingStats rule"
      exports: ["R1MissingStats"]
    - path: "src/mcp_trino_optimizer/rules/r2_partition_pruning.py"
      provides: "R2PartitionPruning rule"
      exports: ["R2PartitionPruning"]
    - path: "src/mcp_trino_optimizer/rules/r3_predicate_pushdown.py"
      provides: "R3PredicatePushdown rule"
      exports: ["R3PredicatePushdown"]
    - path: "src/mcp_trino_optimizer/rules/r4_dynamic_filtering.py"
      provides: "R4DynamicFiltering rule"
      exports: ["R4DynamicFiltering"]
  key_links:
    - from: "src/mcp_trino_optimizer/rules/r1_missing_stats.py"
      to: "src/mcp_trino_optimizer/rules/registry.py"
      via: "registry.register(R1MissingStats) at module level"
    - from: "tests/rules/test_r1_missing_stats.py"
      to: "tests/fixtures/explain/480/full_scan.json"
      via: "realistic fixture loaded from Phase 3 corpus"
---

<objective>
Implement rules R1–R4: the four plan-centric rules covering missing stats, partition pruning failure, predicate pushdown failure, and dynamic filtering. These are the highest-value rules because they represent the top two real-world performance cliffs (R2 / R4).

Purpose: Rules R1–R4 operate on EstimatedPlan (PLAN_ONLY or TABLE_STATS evidence) and cover the most common Trino performance problems. Shipping them unlocks the core value proposition of the tool.

Output: 4 rule files + 4 fully-implemented test files (3 fixture classes each).
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/04-rule-engine-13-deterministic-rules/04-CONTEXT.md
@.planning/phases/04-rule-engine-13-deterministic-rules/04-RESEARCH.md
@.planning/phases/04-rule-engine-13-deterministic-rules/04-01-SUMMARY.md

@src/mcp_trino_optimizer/rules/__init__.py
@src/mcp_trino_optimizer/rules/findings.py
@src/mcp_trino_optimizer/rules/evidence.py
@src/mcp_trino_optimizer/rules/base.py
@src/mcp_trino_optimizer/rules/registry.py
@src/mcp_trino_optimizer/rules/thresholds.py
@src/mcp_trino_optimizer/parser/models.py

<interfaces>
<!-- Key types from Plan 01 infrastructure. -->

From rules/findings.py:
```python
Severity = Literal["critical", "high", "medium", "low"]

class RuleFinding(BaseModel):
    kind: Literal["finding"] = "finding"
    rule_id: str
    severity: Severity
    confidence: float  # ge=0.0, le=1.0
    message: str
    evidence: dict[str, Any]
    operator_ids: list[str]
```

From rules/evidence.py:
```python
class EvidenceRequirement(Enum):
    PLAN_ONLY = "plan_only"
    PLAN_WITH_METRICS = "plan_with_metrics"
    TABLE_STATS = "table_stats"
    ICEBERG_METADATA = "iceberg_metadata"

@dataclass
class EvidenceBundle:
    plan: BasePlan
    table_stats: dict[str, Any] | None = None
    iceberg_snapshots: list[dict[str, Any]] | None = None
    iceberg_files: list[dict[str, Any]] | None = None

def safe_float(val: Any) -> float | None: ...
```

From rules/base.py:
```python
class Rule(ABC):
    rule_id: ClassVar[str]
    evidence_requirement: ClassVar[EvidenceRequirement]
    @abstractmethod
    def check(self, plan: BasePlan, evidence: EvidenceBundle) -> list[RuleFinding]: ...
```

From rules/registry.py:
```python
class RuleRegistry:
    def register(self, rule_cls: type[Rule]) -> type[Rule]: ...
    def all_rules(self) -> list[type[Rule]]: ...
registry = RuleRegistry()
```

From parser/models.py (scan node fields):
```python
class PlanNode(BaseModel):
    id: str
    name: str                           # operator_type alias
    descriptor: dict[str, str]          # "table", "filterPredicate", "dynamicFilters"
    details: list[str]                  # "dynamicFilterAssignments = {id -> #df_388}"
    estimates: list[CostEstimate]       # estimates[0].output_row_count may be NaN
    children: list[PlanNode]
    output_rows: int | None             # ExecutedPlan only
```

Phase 3 fixture paths (verified from corpus):
- tests/fixtures/explain/480/full_scan.json  -- EstimatedPlan, no partition constraint
- tests/fixtures/explain/480/iceberg_partition_filter.json  -- EstimatedPlan with "constraint on [ts]"
- tests/fixtures/explain/480/join.json  -- EstimatedPlan with InnerJoin + dynamicFilterAssignments
- tests/fixtures/explain/429/simple_select.json  -- ScanFilter with filterPredicate
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: R1 MissingStats + R2 PartitionPruning</name>
  <files>
    src/mcp_trino_optimizer/rules/r1_missing_stats.py
    src/mcp_trino_optimizer/rules/r2_partition_pruning.py
    tests/rules/test_r1_missing_stats.py
    tests/rules/test_r2_partition_pruning.py
  </files>
  <behavior>
    R1 tests:
    - Synthetic-minimum: Build a PlanNode with `estimates=[CostEstimate(outputRowCount=float('nan'))]` and name="TableScan". Provide EvidenceBundle(plan=..., table_stats=None). R1.check() returns a RuleFinding with rule_id="R1", severity="critical".
    - Synthetic with table_stats={"row_count": None}: R1 fires with severity="critical", evidence has "table_stats_row_count": None.
    - Negative-control: PlanNode with `estimates=[CostEstimate(outputRowCount=50000.0)]` and table_stats={"row_count": 50000.0, "columns": {...}}. R1.check() returns [].
    - Realistic: Load tests/fixtures/explain/480/full_scan.json, parse to EstimatedPlan, inject table_stats={"row_count": None}. R1 fires.

    R2 tests:
    - Synthetic-minimum: PlanNode with name="ScanFilter", descriptor={"table": "iceberg:schema.orders$data@123", "filterPredicate": "(ts > DATE '2025-01-01')"}. No "constraint on [" in table string. R2.check() returns RuleFinding with rule_id="R2", severity="high".
    - Negative-control: descriptor={"table": "iceberg:schema.orders$data@123 constraint on [ts]", "filterPredicate": "(ts > DATE '2025-01-01')"}. R2.check() returns [].
    - Scan with no filterPredicate at all: R2.check() returns [] (no predicate = no pruning opportunity missed).
    - Realistic: Load tests/fixtures/explain/480/full_scan.json (has scan without constraint). R2 fires on nodes that have filter but no constraint.
    - Realistic negative: Load tests/fixtures/explain/480/iceberg_partition_filter.json. R2 does NOT fire.
  </behavior>
  <action>
    **r1_missing_stats.py:**
    - rule_id = "R1"
    - evidence_requirement = EvidenceRequirement.TABLE_STATS
    - check() iterates all nodes via plan.walk()
    - For each node with operator_type in ("TableScan", "ScanFilter", "ScanFilterProject"):
      * Check estimates: if estimates list is non-empty and estimates[0].output_row_count is None or NaN (use safe_float) → stats missing
      * Also check evidence.table_stats: if None or table_stats.get("row_count") is None → no stats
      * Fire RuleFinding per scan node with missing stats
    - severity: "critical" (missing stats is the root cause of most join-order and cost issues)
    - confidence: 0.9 when table_stats.row_count is None, 0.7 when only NaN estimate
    - evidence dict: {"estimated_row_count": <float or None>, "table_stats_row_count": <float or None>, "operator_type": node.name}
    - operator_ids: [node.id]
    - Register: `registry.register(R1MissingStats)` at module bottom
    - DO NOT check if node has children — scan variants can be composite operators

    **r2_partition_pruning.py:**
    - rule_id = "R2"
    - evidence_requirement = EvidenceRequirement.TABLE_STATS (needs row_count for secondary signal)
    - check() iterates nodes, finds scan nodes with filterPredicate in descriptor
    - Detection: scan has filterPredicate (not empty) AND descriptor["table"] does NOT contain "constraint on ["
    - Use helper `_has_partition_constraint(node: PlanNode) -> bool` checking `"constraint on [" in node.descriptor.get("table", "")`
    - Only fire if the table is Iceberg (descriptor["table"] contains "iceberg:" prefix or "iceberg" catalog indicator)
    - confidence: 0.8 for EstimatedPlan (cannot check actual row ratio); higher confidence if ExecutedPlan with physical_input_bytes available
    - severity: "high"
    - evidence dict: {"filter_predicate": predicate_str, "table": table_str, "has_partition_constraint": False}
    - operator_ids: [node.id]
    - Pitfall: do NOT fire on scan nodes with NO filterPredicate (no predicate = no pushdown opportunity)
    - Version note: when plan.source_trino_version indicates Trino < 440, add note to evidence: "partial_alignment_pruning_unavailable" — but do not change severity
    - Register at module bottom

    Write tests un-skipping the stubs from Plan 01. Use `json.loads(Path("tests/fixtures/explain/480/...").read_text())` to load realistic fixtures; parse with the Phase 3 parser functions.
  </action>
  <verify>
    <automated>uv run pytest tests/rules/test_r1_missing_stats.py tests/rules/test_r2_partition_pruning.py -x -q</automated>
  </verify>
  <done>All R1 and R2 tests pass (synthetic-minimum, realistic, negative-control). Zero mypy errors in both rule files.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: R3 PredicatePushdown + R4 DynamicFiltering</name>
  <files>
    src/mcp_trino_optimizer/rules/r3_predicate_pushdown.py
    src/mcp_trino_optimizer/rules/r4_dynamic_filtering.py
    tests/rules/test_r3_predicate_pushdown.py
    tests/rules/test_r4_dynamic_filtering.py
  </files>
  <behavior>
    R3 tests:
    - Synthetic-minimum: PlanNode with descriptor={"filterPredicate": '("date"(ts) = DATE \'2025-01-15\')'}, name="ScanFilter". R3.check() returns RuleFinding with rule_id="R3", severity="high".
    - Additional synthetic cases: cast() wrap, year() wrap, month() wrap each fire R3.
    - Negative-control: descriptor={"filterPredicate": '(ts >= TIMESTAMP \'2025-01-15 00:00:00 UTC\' AND ts < TIMESTAMP \'2025-01-16 00:00:00 UTC\')'} — range predicate, no function wrap. R3.check() returns [].
    - Negative: no filterPredicate in descriptor → R3 returns [].
    - Realistic: Load tests/fixtures/explain/429/simple_select.json, check for filterPredicate field; if it has a function wrap, R3 fires; if not, serves as negative-control.

    R4 tests:
    - Synthetic-minimum: InnerJoin node with no "dynamicFilterAssignments" in details list AND probe-side scan has no "dynamicFilters" in descriptor. Probe join condition is equality (`id = id`). R4.check() returns RuleFinding with rule_id="R4", severity="medium".
    - Synthetic — filter declared but not pushed: InnerJoin has "dynamicFilterAssignments = {id -> #df_1}" in details, but probe scan has no "dynamicFilters" in descriptor. R4 fires with severity="high" (worse case).
    - Negative-control: InnerJoin has "dynamicFilterAssignments = {id -> #df_388}" in details AND probe-side ScanFilter has descriptor["dynamicFilters"] = "{id_0 = #df_388}". R4 returns [].
    - Realistic: Load tests/fixtures/explain/480/join.json. It should have dynamicFilterAssignments (Phase 3 corpus verified). R4 returns [] (dynamic filtering is working in this fixture).
  </behavior>
  <action>
    **r3_predicate_pushdown.py:**
    - rule_id = "R3"
    - evidence_requirement = EvidenceRequirement.PLAN_ONLY
    - check() finds nodes with name in ("ScanFilter", "ScanFilterProject", "Filter")
    - For each such node, read `descriptor.get("filterPredicate", "")`
    - Use sqlglot to parse the predicate string (dialect="trino"):
      ```python
      import sqlglot
      from sqlglot import exp
      try:
          parsed = sqlglot.parse_one(predicate_str, dialect="trino", error_level=sqlglot.ErrorLevel.RAISE)
      except sqlglot.errors.ParseError:
          # Unparseable predicate — conservative: don't fire R3
          continue
      ```
    - Walk the parsed AST looking for any `exp.Anonymous` or specific function types (`exp.TsOrDsToDate`, `exp.Cast`, `exp.Year`, `exp.Month`, `exp.Hour`, `exp.Trunc`) that wrap a `exp.Column` reference
    - Also detect via regex as fallback: pattern `r'\b(date|year|month|hour|cast|trunc|substring)\s*\('` in the predicate string (for cases where sqlglot parsing may differ)
    - severity: "high"
    - confidence: 0.85 when sqlglot confirms a function-wrapped column; 0.6 for regex-only detection
    - evidence dict: {"filter_predicate": predicate_str, "detected_functions": [list of function names found], "operator_type": node.name}
    - operator_ids: [node.id]
    - Message: "Filter predicate contains function-wrapped column(s) {functions} which prevent predicate pushdown and partition pruning."
    - Register at module bottom

    **r4_dynamic_filtering.py:**
    - rule_id = "R4"
    - evidence_requirement = EvidenceRequirement.PLAN_ONLY
    - check() finds all InnerJoin and SemiJoin nodes via plan.walk()
    - For each join node:
      * Check if any details string contains "dynamicFilterAssignments"
      * If NOT present: check if join has equality condition (look for "=" in descriptor or any detail line). If equality join, R4 fires (missing opportunity).
      * If PRESENT: find the probe side (children[0]), check if probe scan's descriptor has "dynamicFilters" key. If missing → filter declared but not pushed → R4 fires with higher severity.
    - Severity: "medium" for missing dynamic filter opportunity; "high" for declared-but-not-pushed
    - confidence: 0.7 for EstimatedPlan (cannot confirm at runtime); 0.9 for ExecutedPlan
    - evidence dict: {
        "join_has_df_assignments": bool,
        "probe_has_df_applied": bool,
        "dynamic_filter_ids": [extracted IDs from details],
      }
    - operator_ids: [join_node.id] + ([probe_node.id] if probe found)
    - Helper `_extract_df_ids(details: list[str]) -> list[str]`: regex `r"#df_\w+"` matches from details list
    - Helper `_get_probe_scan(join_node: PlanNode) -> PlanNode | None`: DFS into children[0] to find first scan-type node
    - Register at module bottom

    Un-skip and implement test files for R3 and R4. Use inline fixture building (PlanNode() construction) for synthetic-minimum tests. Use Phase 3 JSON fixture files for realistic tests.
  </action>
  <verify>
    <automated>uv run pytest tests/rules/test_r3_predicate_pushdown.py tests/rules/test_r4_dynamic_filtering.py -x -q</automated>
  </verify>
  <done>All R3 and R4 tests pass. `uv run pytest tests/rules/ -x -q` shows R1–R4 tests passing, remaining rule stubs skipped. Zero mypy errors in r3 and r4 files.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| plan.descriptor["filterPredicate"] → sqlglot parser | Predicate string from Trino plan is semi-trusted; parsing with sqlglot must not crash on malformed input |
| EvidenceBundle.table_stats → rule logic | Dict values from StatsSource are external data; rule must handle missing/None keys gracefully |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-04-06 | Denial of Service | R3 sqlglot.parse_one() | mitigate | Wrap in try/except sqlglot.errors.ParseError; fall back to regex detection; never crash on unparseable predicate |
| T-04-07 | Information Disclosure | R1/R2 evidence dict | accept | Evidence values are plan-derived strings (operator types, table names) — no user PII; these are safe to include in findings |
| T-04-08 | Tampering | R2 "constraint on [" string check | mitigate | Trino-format constraint strings are from the trusted Trino server response, not user input; no injection risk via descriptor field |
| T-04-09 | Spoofing | R4 dynamicFilterAssignments string match | accept | String matching on plan details is deterministic; malformed details worst case = false negative (rule doesn't fire), not a false positive |
</threat_model>

<verification>
```bash
# Run all R1–R4 tests
uv run pytest tests/rules/test_r1_missing_stats.py tests/rules/test_r2_partition_pruning.py tests/rules/test_r3_predicate_pushdown.py tests/rules/test_r4_dynamic_filtering.py -v

# Full rules suite (R1–R4 green, all others skipped, no errors)
uv run pytest tests/rules/ -q

# Type check
uv run mypy src/mcp_trino_optimizer/rules/r1_missing_stats.py src/mcp_trino_optimizer/rules/r2_partition_pruning.py src/mcp_trino_optimizer/rules/r3_predicate_pushdown.py src/mcp_trino_optimizer/rules/r4_dynamic_filtering.py --strict

# Confirm rules are registered
python -c "from mcp_trino_optimizer.rules import registry; import mcp_trino_optimizer.rules.r1_missing_stats, mcp_trino_optimizer.rules.r2_partition_pruning, mcp_trino_optimizer.rules.r3_predicate_pushdown, mcp_trino_optimizer.rules.r4_dynamic_filtering; print([r.rule_id for r in registry.all_rules()])"
```
</verification>

<success_criteria>
1. `uv run pytest tests/rules/test_r1_missing_stats.py tests/rules/test_r2_partition_pruning.py tests/rules/test_r3_predicate_pushdown.py tests/rules/test_r4_dynamic_filtering.py -x -q` — all pass
2. Each rule test file has: 1 synthetic-minimum, 1 realistic (from fixture corpus), 1 negative-control — minimum 3 tests per file
3. R1, R2, R3, R4 are registered in the global `registry` after import
4. `uv run pytest tests/rules/ -q` — no collection errors, no unexpected failures
5. `uv run mypy src/mcp_trino_optimizer/rules/ --strict` — zero errors
</success_criteria>

<output>
After completion, create `.planning/phases/04-rule-engine-13-deterministic-rules/04-02-SUMMARY.md` with:
- R1–R4 implemented and registered
- Detection logic details for each rule (fields checked, thresholds used)
- Any fixture-loading issues encountered
- Any deviations from the plan
</output>
