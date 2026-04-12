---
phase: 05-recommendation-engine
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - src/mcp_trino_optimizer/recommender/__init__.py
  - src/mcp_trino_optimizer/recommender/models.py
  - src/mcp_trino_optimizer/recommender/scoring.py
  - src/mcp_trino_optimizer/recommender/impact.py
  - src/mcp_trino_optimizer/settings.py
  - tests/recommender/__init__.py
  - tests/recommender/conftest.py
  - tests/recommender/test_models.py
  - tests/recommender/test_scoring.py
  - tests/recommender/test_impact.py
autonomous: true
requirements:
  - REC-01
  - REC-02

must_haves:
  truths:
    - "RuleFinding objects are converted to Recommendation objects with a deterministic priority score"
    - "Priority score equals severity_weight * impact_score * confidence per D-01"
    - "Each recommendation exposes both a raw float priority_score and a P1/P2/P3/P4 tier label per D-03"
    - "Impact extractors exist for all 14 rules and are registered by rule_id per D-02"
    - "Rules without quantifiable evidence default to impact 0.5 per D-02"
  artifacts:
    - path: "src/mcp_trino_optimizer/recommender/models.py"
      provides: "Recommendation, ConsideredButRejected, IcebergTableHealth, BottleneckEntry, BottleneckRanking, RecommendationReport pydantic models"
      exports: ["Recommendation", "ConsideredButRejected", "IcebergTableHealth", "BottleneckEntry", "BottleneckRanking", "RecommendationReport", "PriorityTier"]
    - path: "src/mcp_trino_optimizer/recommender/scoring.py"
      provides: "Priority scoring: compute_priority, assign_tier"
      exports: ["compute_priority", "assign_tier", "SEVERITY_WEIGHTS"]
    - path: "src/mcp_trino_optimizer/recommender/impact.py"
      provides: "Impact extractor registry with per-rule extractors"
      exports: ["get_impact", "register_impact", "DEFAULT_IMPACT"]
  key_links:
    - from: "src/mcp_trino_optimizer/recommender/scoring.py"
      to: "src/mcp_trino_optimizer/recommender/impact.py"
      via: "scoring calls get_impact() to obtain the impact component"
      pattern: "get_impact"
    - from: "src/mcp_trino_optimizer/recommender/models.py"
      to: "src/mcp_trino_optimizer/rules/findings.py"
      via: "Recommendation.severity reuses the Severity literal type"
      pattern: "from mcp_trino_optimizer.rules.findings import Severity"
---

<objective>
Create the foundational pydantic models for the recommendation engine and implement the priority scoring formula with all 14 per-rule impact extractors.

Purpose: Establish the data contracts (Recommendation, IcebergTableHealth, BottleneckRanking, etc.) that all subsequent plans build on, plus the deterministic scoring pipeline (severity_weight x impact x confidence) with configurable tier thresholds.

Output: `recommender/` package with models, scoring, impact modules; extended Settings with recommender config; full test coverage for scoring and impact extraction.
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

<interfaces>
<!-- Key types and contracts the executor needs. Extracted from codebase. -->

From src/mcp_trino_optimizer/rules/findings.py:
```python
Severity = Literal["critical", "high", "medium", "low"]

class RuleFinding(BaseModel):
    kind: Literal["finding"] = "finding"
    rule_id: str
    severity: Severity
    confidence: float = Field(ge=0.0, le=1.0)
    message: str
    evidence: dict[str, Any]
    operator_ids: list[str]

class RuleError(BaseModel):
    kind: Literal["error"] = "error"
    rule_id: str
    error_type: str
    message: str

class RuleSkipped(BaseModel):
    kind: Literal["skipped"] = "skipped"
    rule_id: str
    reason: str

EngineResult = Annotated[RuleFinding | RuleError | RuleSkipped, Field(discriminator="kind")]
```

From src/mcp_trino_optimizer/rules/evidence.py:
```python
class EvidenceRequirement(Enum):
    PLAN_ONLY = "plan_only"
    PLAN_WITH_METRICS = "plan_with_metrics"
    TABLE_STATS = "table_stats"
    ICEBERG_METADATA = "iceberg_metadata"

def safe_float(val: Any) -> float | None:
    ...
```

From src/mcp_trino_optimizer/parser/models.py:
```python
class PlanNode(BaseModel):
    id: str
    name: str
    descriptor: dict[str, str] = Field(default_factory=dict)
    cpu_time_ms: float | None = None
    wall_time_ms: float | None = None
    input_rows: int | None = None
    output_rows: int | None = None
    peak_memory_bytes: int | None = None
    children: list["PlanNode"] = Field(default_factory=list)
    @property
    def operator_type(self) -> str: ...

class BasePlan(BaseModel):
    def walk(self) -> Iterator[PlanNode]: ...
    def find_nodes_by_type(self, operator_type: str) -> list[PlanNode]: ...

class EstimatedPlan(BasePlan): ...
class ExecutedPlan(BasePlan): ...
```

From src/mcp_trino_optimizer/adapters/trino/capabilities.py:
```python
@dataclass(frozen=True)
class CapabilityMatrix:
    trino_version: str
    trino_version_major: int
    catalogs: frozenset[str]
    iceberg_catalog_name: str | None
    iceberg_metadata_tables_available: bool
    probed_at: datetime
    version: int = 1
```

From src/mcp_trino_optimizer/settings.py:
```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MCPTO_", ...)
    # ... existing fields (transport, trino_*, etc.)
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Recommendation models + scoring + settings extension</name>
  <files>
    src/mcp_trino_optimizer/recommender/__init__.py,
    src/mcp_trino_optimizer/recommender/models.py,
    src/mcp_trino_optimizer/recommender/scoring.py,
    src/mcp_trino_optimizer/settings.py,
    tests/recommender/__init__.py,
    tests/recommender/conftest.py,
    tests/recommender/test_models.py,
    tests/recommender/test_scoring.py
  </files>
  <read_first>
    src/mcp_trino_optimizer/rules/findings.py,
    src/mcp_trino_optimizer/settings.py,
    src/mcp_trino_optimizer/parser/models.py,
    src/mcp_trino_optimizer/adapters/trino/capabilities.py
  </read_first>
  <behavior>
    - Test: Recommendation model validates all required fields (rule_id, severity, confidence, priority_score, priority_tier, operator_ids, reasoning, expected_impact, risk_level, validation_steps, confidence, evidence_summary)
    - Test: ConsideredButRejected model validates rule_id, reason, original_priority_score
    - Test: IcebergTableHealth model validates table_name, snapshot_count, small_file_ratio, delete_file_ratio, partition_spec_evolution, last_compaction_reference, health_score, narrative
    - Test: BottleneckEntry model validates operator_id, operator_type, cpu_time_ms, wall_time_ms, cpu_pct, related_findings, narrative
    - Test: BottleneckRanking model validates top_operators, total_cpu_time_ms, plan_type, top_n
    - Test: RecommendationReport model validates recommendations list, iceberg_health list, bottleneck_ranking optional, considered_but_rejected list
    - Test: compute_priority("critical", 0.8, 0.9) == 4 * 0.8 * 0.9 == 2.88
    - Test: compute_priority("low", 0.5, 0.5) == 1 * 0.5 * 0.5 == 0.25
    - Test: assign_tier returns P1 for scores >= 2.4 (configurable)
    - Test: assign_tier returns P4 for scores < 0.5 (configurable)
    - Test: SEVERITY_WEIGHTS maps critical=4, high=3, medium=2, low=1
    - Test: Settings accepts recommender fields (tier thresholds, top_n_bottleneck)
  </behavior>
  <action>
    1. Create `src/mcp_trino_optimizer/recommender/__init__.py` with public API exports:
       `Recommendation`, `ConsideredButRejected`, `IcebergTableHealth`, `BottleneckEntry`,
       `BottleneckRanking`, `RecommendationReport`, `PriorityTier`, `compute_priority`, `assign_tier`.

    2. Create `src/mcp_trino_optimizer/recommender/models.py` with pydantic models:
       - `PriorityTier = Literal["P1", "P2", "P3", "P4"]`
       - `RiskLevel = Literal["low", "medium", "high"]`
       - `HealthScore = Literal["healthy", "degraded", "critical"]`
       - `ConsideredButRejected(BaseModel)`: rule_id: str, reason: str, original_priority_score: float
       - `Recommendation(BaseModel)`: rule_id: str, severity: Severity (imported from rules.findings),
         confidence: float (Field ge=0.0, le=1.0), priority_score: float, priority_tier: PriorityTier,
         operator_ids: list[str], reasoning: str, expected_impact: str, risk_level: RiskLevel,
         validation_steps: str, session_property_statements: list[str] | None = None,
         evidence_summary: dict[str, Any], considered_but_rejected: list[ConsideredButRejected] = []
       - `IcebergTableHealth(BaseModel)`: table_name: str, snapshot_count: int | None = None,
         small_file_ratio: float | None = None, delete_file_ratio: float | None = None,
         partition_spec_evolution: str | None = None, last_compaction_reference: str | None = None,
         health_score: HealthScore, narrative: str
       - `BottleneckEntry(BaseModel)`: operator_id: str, operator_type: str, cpu_time_ms: float,
         wall_time_ms: float, cpu_pct: float, input_rows: int | None = None,
         output_rows: int | None = None, peak_memory_bytes: int | None = None,
         related_findings: list[str] = [], narrative: str
       - `BottleneckRanking(BaseModel)`: top_operators: list[BottleneckEntry],
         total_cpu_time_ms: float, plan_type: str = "executed", top_n: int
       - `RecommendationReport(BaseModel)`: recommendations: list[Recommendation],
         iceberg_health: list[IcebergTableHealth] = [], bottleneck_ranking: BottleneckRanking | None = None,
         considered_but_rejected: list[ConsideredButRejected] = []

    3. Create `src/mcp_trino_optimizer/recommender/scoring.py`:
       - `SEVERITY_WEIGHTS: dict[str, int] = {"critical": 4, "high": 3, "medium": 2, "low": 1}`
       - `def compute_priority(severity: str, impact: float, confidence: float) -> float`:
         returns `SEVERITY_WEIGHTS[severity] * impact * confidence`
       - `def assign_tier(score: float, thresholds: tuple[float, float, float] = (2.4, 1.2, 0.5)) -> PriorityTier`:
         P1 if score >= thresholds[0], P2 if >= thresholds[1], P3 if >= thresholds[2], else P4.
         Per D-03: thresholds are configurable.

    4. Extend `src/mcp_trino_optimizer/settings.py` — add to the Settings class:
       - `recommender_tier_p1: float = Field(default=2.4, description="Priority score threshold for P1 tier.")`
       - `recommender_tier_p2: float = Field(default=1.2, description="Priority score threshold for P2 tier.")`
       - `recommender_tier_p3: float = Field(default=0.5, description="Priority score threshold for P3 tier.")`
       - `recommender_top_n_bottleneck: int = Field(default=5, ge=1, le=50, description="Number of top operators in bottleneck ranking (D-08).")`

    5. Create `tests/recommender/__init__.py` (empty).

    6. Create `tests/recommender/conftest.py` with shared fixtures:
       - `sample_finding(rule_id, severity, confidence, evidence, operator_ids)` factory fixture
       - `sample_findings_r1_d11()` — R1 and D11 findings on the same operator (for conflict tests in Plan 02)
       - `sample_findings_all_rules()` — one finding per rule_id for full coverage
       - `mock_capability_matrix(trino_version_major=480)` fixture

    7. Create `tests/recommender/test_models.py` — model validation tests.
    8. Create `tests/recommender/test_scoring.py` — scoring formula + tier assignment tests.
  </action>
  <verify>
    <automated>cd /Users/allen/repo/mcp-trino-optimizer && uv run pytest tests/recommender/test_models.py tests/recommender/test_scoring.py -x -q --timeout=30</automated>
  </verify>
  <acceptance_criteria>
    - src/mcp_trino_optimizer/recommender/models.py contains `class Recommendation(BaseModel):`
    - src/mcp_trino_optimizer/recommender/models.py contains `class IcebergTableHealth(BaseModel):`
    - src/mcp_trino_optimizer/recommender/models.py contains `class BottleneckRanking(BaseModel):`
    - src/mcp_trino_optimizer/recommender/models.py contains `class RecommendationReport(BaseModel):`
    - src/mcp_trino_optimizer/recommender/scoring.py contains `SEVERITY_WEIGHTS`
    - src/mcp_trino_optimizer/recommender/scoring.py contains `def compute_priority(`
    - src/mcp_trino_optimizer/recommender/scoring.py contains `def assign_tier(`
    - src/mcp_trino_optimizer/settings.py contains `recommender_tier_p1`
    - src/mcp_trino_optimizer/settings.py contains `recommender_top_n_bottleneck`
    - tests/recommender/test_scoring.py exits 0
    - tests/recommender/test_models.py exits 0
  </acceptance_criteria>
  <done>All recommendation models defined, scoring formula produces correct results for all severity/impact/confidence combos, tier assignment is configurable, Settings extended. Tests green.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Impact extractor registry with per-rule extractors for all 14 rules</name>
  <files>
    src/mcp_trino_optimizer/recommender/impact.py,
    tests/recommender/test_impact.py
  </files>
  <read_first>
    src/mcp_trino_optimizer/rules/r1_missing_stats.py,
    src/mcp_trino_optimizer/rules/r2_partition_pruning.py,
    src/mcp_trino_optimizer/rules/r3_predicate_pushdown.py,
    src/mcp_trino_optimizer/rules/r4_dynamic_filtering.py,
    src/mcp_trino_optimizer/rules/r5_broadcast_too_big.py,
    src/mcp_trino_optimizer/rules/r6_join_order.py,
    src/mcp_trino_optimizer/rules/r7_cpu_skew.py,
    src/mcp_trino_optimizer/rules/r8_exchange_volume.py,
    src/mcp_trino_optimizer/rules/r9_low_selectivity.py,
    src/mcp_trino_optimizer/rules/i1_small_files.py,
    src/mcp_trino_optimizer/rules/i3_delete_files.py,
    src/mcp_trino_optimizer/rules/i6_stale_snapshots.py,
    src/mcp_trino_optimizer/rules/i8_partition_transform.py,
    src/mcp_trino_optimizer/rules/d11_cost_vs_actual.py,
    src/mcp_trino_optimizer/rules/evidence.py
  </read_first>
  <behavior>
    - Test: get_impact("R1", {}) returns DEFAULT_IMPACT (0.5)
    - Test: get_impact("R2", {"physical_input_bytes": 1000, "total_table_bytes": 1000}) returns ~1.0 (full scan)
    - Test: get_impact("R2", {"physical_input_bytes": 100, "total_table_bytes": 1000}) returns ~0.1
    - Test: get_impact("R5", {"build_side_estimated_bytes": 200_000_000, "threshold_bytes": 100_000_000}) returns 1.0 (2x over)
    - Test: get_impact("R7", {"p99_p50_ratio": 5.0}) returns ~0.0 (at threshold)
    - Test: get_impact("R7", {"p99_p50_ratio": 20.0}) returns 1.0 (extreme)
    - Test: get_impact("R8", {"ratio": 1.0}) returns 0.0 (no waste)
    - Test: get_impact("R8", {"ratio": 10.0}) returns 1.0 (extreme waste)
    - Test: get_impact("R9", {"selectivity": 0.01}) returns ~0.99
    - Test: get_impact("I1", {"median_file_size_bytes": 1_000_000, "threshold_bytes": 16_000_000}) returns high (small files)
    - Test: get_impact("I3", {"delete_ratio": 0.5}) returns 1.0
    - Test: get_impact("I6", {"snapshot_count": 500, "threshold_count": 100}) returns 1.0
    - Test: get_impact("D11", {"divergence_factor": 50.0}) returns 1.0
    - Test: get_impact("UNKNOWN_RULE", {}) returns DEFAULT_IMPACT (0.5)
    - Test: get_impact with None denominator values returns DEFAULT_IMPACT (no division by zero)
  </behavior>
  <action>
    Create `src/mcp_trino_optimizer/recommender/impact.py`:

    1. Define `ImpactExtractor = Callable[[dict[str, Any]], float]` type alias.
    2. Define `_IMPACT_EXTRACTORS: dict[str, ImpactExtractor] = {}` module-level registry.
    3. Define `DEFAULT_IMPACT = 0.5`.
    4. Define `register_impact(rule_id: str)` decorator that adds to `_IMPACT_EXTRACTORS`.
    5. Define `get_impact(rule_id: str, evidence: dict[str, Any]) -> float` that looks up
       the extractor, calls it, clamps result to [0.0, 1.0], returns DEFAULT_IMPACT on missing rule.

    6. Register extractors for all 14 rules. Read each rule's source file to confirm exact
       evidence dict keys. Use `safe_float` from `rules.evidence` for NaN protection.
       Guard all divisions: `if denominator is None or denominator <= 0: return DEFAULT_IMPACT`.

       Extractors (read actual evidence keys from rule source files):
       - R1: Default 0.5 (stats presence is binary)
       - R2: `physical_input_bytes / total_table_bytes` clamped [0, 1.0]
       - R3: Default 0.5 (pushdown failure is binary)
       - R4: Default 0.7 (severity-based; DF not applied is high impact)
       - R5: `min(1.0, build_side_estimated_bytes / threshold_bytes)` normalized
       - R6: Default 0.5 (join order is complex; confidence already accounts for severity)
       - R7: `min(1.0, (p99_p50_ratio - 5.0) / 15.0)` (5x threshold to 20x extreme)
       - R8: `min(1.0, (ratio - 1.0) / 9.0)` (1x no waste to 10x extreme)
       - R9: `1.0 - selectivity` where selectivity is from evidence
       - I1: `1.0 - min(1.0, median_file_size_bytes / threshold_bytes)` (smaller files = higher impact)
       - I3: `min(1.0, delete_ratio / 0.5)` (10% threshold, 50% extreme)
       - I6: `min(1.0, snapshot_count / (threshold_count * 5))` (threshold to 5x extreme)
       - I8: Default 0.5 (confidence already low at 0.6)
       - D11: `min(1.0, (divergence_factor - 5.0) / 45.0)` (5x threshold to 50x extreme)

    7. Create `tests/recommender/test_impact.py` with parameterized tests for each extractor,
       including edge cases: None values, zero denominators, NaN.
  </action>
  <verify>
    <automated>cd /Users/allen/repo/mcp-trino-optimizer && uv run pytest tests/recommender/test_impact.py -x -q --timeout=30</automated>
  </verify>
  <acceptance_criteria>
    - src/mcp_trino_optimizer/recommender/impact.py contains `DEFAULT_IMPACT = 0.5`
    - src/mcp_trino_optimizer/recommender/impact.py contains `def get_impact(`
    - src/mcp_trino_optimizer/recommender/impact.py contains `def register_impact(`
    - src/mcp_trino_optimizer/recommender/impact.py contains `@register_impact("R1")`
    - src/mcp_trino_optimizer/recommender/impact.py contains `@register_impact("D11")`
    - tests/recommender/test_impact.py exits 0
    - grep -c '@register_impact' src/mcp_trino_optimizer/recommender/impact.py returns 14 (one per rule)
  </acceptance_criteria>
  <done>Impact extractors registered for all 14 rules. Each guards against None/zero/NaN. Parameterized tests cover normal, edge, and missing-rule cases. All tests green.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| RuleFinding.evidence -> impact extractor | Evidence dicts originate from rule logic which processes user-origin SQL plans; numeric values could be unexpected (NaN, negative, extremely large) |
| RuleFinding.message -> recommendation narrative | User-origin text in message field must NEVER flow into recommendation body (handled in Plan 02 templates) |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-05-01 | Tampering | impact.py extractor | mitigate | Every extractor guards division-by-zero and NaN via safe_float(); result clamped to [0.0, 1.0] in get_impact() |
| T-05-02 | Denial of Service | scoring.py | accept | Priority score is bounded arithmetic (max = 4 * 1.0 * 1.0 = 4.0); no amplification vector |
</threat_model>

<verification>
All recommender model tests pass:
```bash
uv run pytest tests/recommender/ -x -q --timeout=30
```

Existing tests still pass:
```bash
uv run pytest tests/ -x --timeout=120
```

Lint clean:
```bash
uv run ruff check src/mcp_trino_optimizer/recommender/ tests/recommender/
```
</verification>

<success_criteria>
- Recommendation, IcebergTableHealth, BottleneckRanking, RecommendationReport models defined
- compute_priority(severity, impact, confidence) produces deterministic results matching D-01 formula
- assign_tier uses configurable thresholds from Settings
- Impact extractors exist for all 14 rules with safe numeric handling
- get_impact returns DEFAULT_IMPACT for unknown rules
- All tests pass, lint clean
</success_criteria>

<output>
After completion, create `.planning/phases/05-recommendation-engine/05-01-SUMMARY.md`
</output>
