---
phase: 05-recommendation-engine
plan: 03
type: execute
wave: 3
depends_on: ["05-02"]
files_modified:
  - src/mcp_trino_optimizer/recommender/health.py
  - src/mcp_trino_optimizer/recommender/bottleneck.py
  - src/mcp_trino_optimizer/recommender/engine.py
  - src/mcp_trino_optimizer/recommender/__init__.py
  - tests/recommender/test_health.py
  - tests/recommender/test_bottleneck.py
  - tests/recommender/test_engine_integration.py
autonomous: true
requirements:
  - REC-06
  - REC-07

must_haves:
  truths:
    - "Iceberg table health summary aggregates I1/I3/I6/I8 findings per table into a structured IcebergTableHealth object"
    - "Health score is 'critical' when any I1 or I3 finding has severity high, 'degraded' for I6/I8, 'healthy' otherwise"
    - "Operator bottleneck ranking produces top-N operators sorted by CPU time percentage"
    - "Bottleneck ranking requires ExecutedPlan; EstimatedPlan returns None with no error"
    - "RecommendationEngine.recommend() now populates iceberg_health and bottleneck_ranking in RecommendationReport"
    - "Full pipeline test: RuleEngine output -> RecommendationEngine -> complete RecommendationReport"
  artifacts:
    - path: "src/mcp_trino_optimizer/recommender/health.py"
      provides: "Iceberg table health aggregation from I1/I3/I6/I8 findings"
      exports: ["aggregate_iceberg_health"]
    - path: "src/mcp_trino_optimizer/recommender/bottleneck.py"
      provides: "Operator bottleneck ranking from ExecutedPlan metrics"
      exports: ["rank_bottlenecks"]
  key_links:
    - from: "src/mcp_trino_optimizer/recommender/engine.py"
      to: "src/mcp_trino_optimizer/recommender/health.py"
      via: "engine calls aggregate_iceberg_health with Iceberg findings"
      pattern: "aggregate_iceberg_health"
    - from: "src/mcp_trino_optimizer/recommender/engine.py"
      to: "src/mcp_trino_optimizer/recommender/bottleneck.py"
      via: "engine calls rank_bottlenecks with plan if ExecutedPlan"
      pattern: "rank_bottlenecks"
    - from: "src/mcp_trino_optimizer/recommender/bottleneck.py"
      to: "src/mcp_trino_optimizer/parser/models.py"
      via: "walks ExecutedPlan nodes for cpu_time_ms/wall_time_ms"
      pattern: "plan.walk()"
---

<objective>
Implement the two narrative differentiators: Iceberg table health summary and operator bottleneck ranking, then wire them into the RecommendationEngine and run a full integration test of the complete pipeline.

Purpose: Complete the recommendation engine by adding the Iceberg health aggregator (REC-06) and operator bottleneck ranker (REC-07), making the RecommendationReport fully populated. The full pipeline test validates that RuleEngine output flows through to a complete report.

Output: health.py, bottleneck.py modules; updated engine.py; integration-level test covering the full findings -> recommendations pipeline.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md
@.planning/phases/05-recommendation-engine/05-CONTEXT.md
@.planning/phases/05-recommendation-engine/05-RESEARCH.md
@.planning/phases/05-recommendation-engine/05-01-SUMMARY.md
@.planning/phases/05-recommendation-engine/05-02-SUMMARY.md

<interfaces>
<!-- From Plan 01 + Plan 02 outputs -->

From src/mcp_trino_optimizer/recommender/models.py:
```python
class IcebergTableHealth(BaseModel):
    table_name: str
    snapshot_count: int | None = None
    small_file_ratio: float | None = None
    delete_file_ratio: float | None = None
    partition_spec_evolution: str | None = None
    last_compaction_reference: str | None = None
    health_score: Literal["healthy", "degraded", "critical"]
    narrative: str

class BottleneckEntry(BaseModel):
    operator_id: str
    operator_type: str
    cpu_time_ms: float
    wall_time_ms: float
    cpu_pct: float
    input_rows: int | None = None
    output_rows: int | None = None
    peak_memory_bytes: int | None = None
    related_findings: list[str] = []
    narrative: str

class BottleneckRanking(BaseModel):
    top_operators: list[BottleneckEntry]
    total_cpu_time_ms: float
    plan_type: str = "executed"
    top_n: int

class RecommendationReport(BaseModel):
    recommendations: list[Recommendation]
    iceberg_health: list[IcebergTableHealth] = []
    bottleneck_ranking: BottleneckRanking | None = None
    considered_but_rejected: list[ConsideredButRejected] = []
```

From src/mcp_trino_optimizer/recommender/engine.py (from Plan 02):
```python
class RecommendationEngine:
    def __init__(self, capability_matrix: CapabilityMatrix | None = None, settings: Settings | None = None): ...
    def recommend(self, engine_results: list[EngineResult]) -> RecommendationReport: ...
```

From src/mcp_trino_optimizer/parser/models.py:
```python
class PlanNode(BaseModel):
    id: str
    name: str
    descriptor: dict[str, str]
    cpu_time_ms: float | None = None
    wall_time_ms: float | None = None
    input_rows: int | None = None
    output_rows: int | None = None
    peak_memory_bytes: int | None = None
    children: list["PlanNode"]
    @property
    def operator_type(self) -> str: ...

class BasePlan(BaseModel):
    def walk(self) -> Iterator[PlanNode]: ...

class ExecutedPlan(BasePlan): ...
class EstimatedPlan(BasePlan): ...
```

From src/mcp_trino_optimizer/rules/findings.py:
```python
class RuleFinding(BaseModel):
    rule_id: str
    severity: Severity
    confidence: float
    evidence: dict[str, Any]
    operator_ids: list[str]
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Iceberg table health aggregator</name>
  <files>
    src/mcp_trino_optimizer/recommender/health.py,
    tests/recommender/test_health.py
  </files>
  <read_first>
    src/mcp_trino_optimizer/recommender/models.py,
    src/mcp_trino_optimizer/rules/i1_small_files.py,
    src/mcp_trino_optimizer/rules/i3_delete_files.py,
    src/mcp_trino_optimizer/rules/i6_stale_snapshots.py,
    src/mcp_trino_optimizer/rules/i8_partition_transform.py,
    src/mcp_trino_optimizer/rules/findings.py
  </read_first>
  <behavior>
    - Test: aggregate_iceberg_health with I1 finding (severity=high) for table "iceberg:db.orders" -> IcebergTableHealth with health_score="critical", small_file_ratio populated
    - Test: aggregate_iceberg_health with I6 finding (severity=medium) -> health_score="degraded", snapshot_count populated
    - Test: aggregate_iceberg_health with I1 + I3 + I6 findings for same table -> single IcebergTableHealth with all fields populated
    - Test: aggregate_iceberg_health with I1 for table A and I3 for table B -> two separate IcebergTableHealth objects
    - Test: aggregate_iceberg_health with no Iceberg findings -> empty list
    - Test: aggregate_iceberg_health with I8 finding -> partition_spec_evolution populated, health_score="degraded"
    - Test: health narrative is templated (contains table_name, not user SQL)
    - Test: health_score classification: any I1 or I3 severity=high -> critical; I6 or I8 -> degraded; none -> healthy
  </behavior>
  <action>
    Create `src/mcp_trino_optimizer/recommender/health.py`:

    1. Define Iceberg rule IDs constant: `ICEBERG_RULES = {"I1", "I3", "I6", "I8"}`.

    2. Define health narrative templates (str.format):
       ```python
       HEALTH_NARRATIVE = (
           "Table {table_name}: health={health_score}. "
           "{details}"
       )
       ```

    3. Define `aggregate_iceberg_health(findings: list[RuleFinding]) -> list[IcebergTableHealth]`:
       a. Filter findings to Iceberg rules only (rule_id in ICEBERG_RULES).
       b. Extract table_name from each finding's evidence dict. Iceberg rules store table
          reference in evidence. Read the actual rule source files to find the key name.
          For I1/I3/I6: look for `table_name` or similar in evidence. For I8: check evidence keys.
          If no table_name in evidence, use "unknown_table" as fallback.
       c. Group findings by table_name.
       d. For each table group:
          - I1 findings -> small_file_ratio from evidence `median_file_size_bytes / threshold_bytes`
            (or direct `small_file_ratio` if available). If median_file_size_bytes and threshold_bytes
            both present, compute ratio = median_file_size_bytes / threshold_bytes.
          - I3 findings -> delete_file_ratio from evidence `delete_ratio` field.
          - I6 findings -> snapshot_count from evidence `snapshot_count` field.
          - I8 findings -> partition_spec_evolution from evidence `constraint_column` + alignment info.
          - last_compaction_reference: "Run: ALTER TABLE {table_name} EXECUTE optimize" for I1/I3.
            "Run: ALTER TABLE {table_name} EXECUTE expire_snapshots" for I6.
          - health_score: "critical" if any finding has severity in ("critical", "high") and rule_id in ("I1", "I3"),
            "degraded" if any finding present, "healthy" if empty (this branch won't occur since we filter).
          - Render narrative from template.
       e. Return list of IcebergTableHealth objects.

    4. Create `tests/recommender/test_health.py` with tests per behavior list above.
       Build mock RuleFinding objects with appropriate evidence dicts for I1/I3/I6/I8.
  </action>
  <verify>
    <automated>cd /Users/allen/repo/mcp-trino-optimizer && uv run pytest tests/recommender/test_health.py -x -q --timeout=30</automated>
  </verify>
  <acceptance_criteria>
    - src/mcp_trino_optimizer/recommender/health.py contains `ICEBERG_RULES`
    - src/mcp_trino_optimizer/recommender/health.py contains `def aggregate_iceberg_health(`
    - src/mcp_trino_optimizer/recommender/health.py does NOT contain `{message}` (no RuleFinding.message in templates)
    - tests/recommender/test_health.py exits 0
  </acceptance_criteria>
  <done>Iceberg table health aggregator groups I1/I3/I6/I8 findings by table, populates all IcebergTableHealth fields, classifies health score, renders templated narrative. Tests green.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Operator bottleneck ranking + engine integration + full pipeline test</name>
  <files>
    src/mcp_trino_optimizer/recommender/bottleneck.py,
    src/mcp_trino_optimizer/recommender/engine.py,
    src/mcp_trino_optimizer/recommender/__init__.py,
    tests/recommender/test_bottleneck.py,
    tests/recommender/test_engine_integration.py
  </files>
  <read_first>
    src/mcp_trino_optimizer/recommender/models.py,
    src/mcp_trino_optimizer/recommender/engine.py,
    src/mcp_trino_optimizer/recommender/health.py,
    src/mcp_trino_optimizer/recommender/templates.py,
    src/mcp_trino_optimizer/parser/models.py,
    src/mcp_trino_optimizer/rules/findings.py,
    src/mcp_trino_optimizer/settings.py
  </read_first>
  <behavior>
    - Test: rank_bottlenecks on ExecutedPlan with 3 nodes (cpu=100, cpu=50, cpu=10) returns top 3 sorted by CPU, pct correct (62.5%, 31.25%, 6.25%)
    - Test: rank_bottlenecks with top_n=2 returns only top 2 operators
    - Test: rank_bottlenecks with related_findings correctly associates rule_ids to operator_ids
    - Test: rank_bottlenecks on EstimatedPlan returns None
    - Test: rank_bottlenecks on ExecutedPlan with all-None cpu_time_ms returns empty ranking
    - Test: bottleneck narrative is templated (contains operator_type and cpu_pct)
    - Test: Engine integration: findings with Iceberg rules -> iceberg_health populated in report
    - Test: Engine integration: findings + ExecutedPlan -> bottleneck_ranking populated in report
    - Test: Engine integration: findings + EstimatedPlan -> bottleneck_ranking is None
    - Test: Full pipeline: mixed EngineResult list (findings + errors + skips) -> complete RecommendationReport with recommendations sorted, conflicts resolved, health populated, bottleneck populated
  </behavior>
  <action>
    1. Create `src/mcp_trino_optimizer/recommender/bottleneck.py`:

       Define bottleneck narrative template:
       ```python
       BOTTLENECK_NARRATIVE = (
           "Operator {operator_id} ({operator_type}) consumed {cpu_pct:.1f}% of total CPU "
           "({cpu_time_ms:.0f}ms). {detail}"
       )
       ```

       Define `rank_bottlenecks(plan: BasePlan, findings: list[RuleFinding], top_n: int = 5) -> BottleneckRanking | None`:
       a. Check if plan is ExecutedPlan (import and isinstance check). If not, return None.
          This handles Pitfall 5 from RESEARCH.md.
       b. Walk all nodes, collect those with non-None cpu_time_ms.
       c. Compute total_cpu = sum of all cpu_time_ms.
       d. If total_cpu == 0 or no nodes with cpu_time_ms, return None.
       e. Sort by cpu_time_ms descending, take top_n.
       f. For each top node:
          - cpu_pct = (node.cpu_time_ms / total_cpu) * 100
          - related_findings = [f.rule_id for f in findings if node.id in f.operator_ids]
          - detail = "Related findings: {related}" if any, else "No specific findings for this operator."
          - Render narrative from template.
       g. Build and return BottleneckRanking.

    2. Update `src/mcp_trino_optimizer/recommender/engine.py`:

       Modify `RecommendationEngine.__init__` to accept an optional `plan: BasePlan | None = None` parameter.

       Modify `RecommendationEngine.recommend()`:
       - After building recommendations (existing logic), call:
         `iceberg_health = aggregate_iceberg_health(findings_only)` where findings_only
         is the filtered list of RuleFinding objects.
       - If self._plan is not None:
         `bottleneck = rank_bottlenecks(self._plan, findings_only, self._settings.recommender_top_n_bottleneck)`
       - Else: bottleneck = None.
       - Set `report.iceberg_health = iceberg_health` and `report.bottleneck_ranking = bottleneck`.

    3. Update `src/mcp_trino_optimizer/recommender/__init__.py`:
       - Export `aggregate_iceberg_health` from health module.
       - Export `rank_bottlenecks` from bottleneck module.

    4. Create `tests/recommender/test_bottleneck.py`:
       - Build mock ExecutedPlan and EstimatedPlan with PlanNode objects.
       - Test ranking, percentage computation, narrative rendering.
       - Test top_n limiting.
       - Test EstimatedPlan returns None.

    5. Create `tests/recommender/test_engine_integration.py`:
       - Full pipeline test: construct a realistic set of EngineResult objects
         (mix of RuleFinding for R1, R5, I1, I3, D11 + RuleError + RuleSkipped),
         build a mock ExecutedPlan, create RecommendationEngine, call recommend().
       - Assert: recommendations sorted by priority_score descending.
       - Assert: R1/D11 conflict resolved (D11 wins, R1 in considered_but_rejected).
       - Assert: R5 recommendation has SET SESSION statements.
       - Assert: iceberg_health has entries for tables with I1/I3 findings.
       - Assert: bottleneck_ranking is not None and has top operators.
       - Assert: report.considered_but_rejected is non-empty.
  </action>
  <verify>
    <automated>cd /Users/allen/repo/mcp-trino-optimizer && uv run pytest tests/recommender/test_bottleneck.py tests/recommender/test_engine_integration.py -x -q --timeout=30</automated>
  </verify>
  <acceptance_criteria>
    - src/mcp_trino_optimizer/recommender/bottleneck.py contains `def rank_bottlenecks(`
    - src/mcp_trino_optimizer/recommender/bottleneck.py contains `BOTTLENECK_NARRATIVE`
    - src/mcp_trino_optimizer/recommender/engine.py contains `aggregate_iceberg_health`
    - src/mcp_trino_optimizer/recommender/engine.py contains `rank_bottlenecks`
    - tests/recommender/test_bottleneck.py exits 0
    - tests/recommender/test_engine_integration.py exits 0
    - uv run pytest tests/recommender/ -x exits 0 (all recommender tests pass)
    - uv run pytest tests/ -x --timeout=120 exits 0 (full suite still passes)
  </acceptance_criteria>
  <done>Bottleneck ranking walks ExecutedPlan nodes, computes CPU percentages, associates related findings, renders narrative. Health aggregation and bottleneck ranking wired into RecommendationEngine. Full pipeline integration test validates complete flow from EngineResult -> RecommendationReport. All tests green including existing suite.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| RuleFinding.evidence -> health aggregation | Iceberg rule evidence dicts may contain user-origin table names from SQL; health narrative uses only structured fields |
| ExecutedPlan nodes -> bottleneck ranking | Plan node data originates from Trino EXPLAIN ANALYZE; numeric fields (cpu_time_ms etc.) are already typed by PlanNode model |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-05-07 | Tampering | health.py | mitigate | Health narrative templates use only evidence dict numeric/enum fields and table_name; no RuleFinding.message interpolation. Same safe_evidence pattern as templates.py |
| T-05-08 | Denial of Service | bottleneck.py | accept | Bottleneck ranking walks plan tree once (O(n) nodes); top_n is bounded by settings (max 50). No amplification vector |
| T-05-09 | Tampering | bottleneck.py narrative | mitigate | Bottleneck narrative uses only PlanNode typed fields (operator_type, cpu_time_ms) — no user-origin strings |
</threat_model>

<verification>
All recommender tests pass:
```bash
uv run pytest tests/recommender/ -x -q --timeout=30
```

Full test suite passes:
```bash
uv run pytest tests/ -x --timeout=120
```

Lint clean:
```bash
uv run ruff check src/mcp_trino_optimizer/recommender/ tests/recommender/
```

Type check:
```bash
uv run mypy src/mcp_trino_optimizer/recommender/ --strict
```
</verification>

<success_criteria>
- Iceberg table health summary aggregates I1/I3/I6/I8 per table with correct health_score classification
- Bottleneck ranking produces top-N operators sorted by CPU% from ExecutedPlan, returns None for EstimatedPlan
- RecommendationEngine.recommend() populates all RecommendationReport fields
- Full pipeline integration test validates end-to-end flow
- All recommender and existing tests pass, lint + type check clean
</success_criteria>

<output>
After completion, create `.planning/phases/05-recommendation-engine/05-03-SUMMARY.md`
</output>
