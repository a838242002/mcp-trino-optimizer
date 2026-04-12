---
phase: 05-recommendation-engine
plan: 02
type: execute
wave: 2
depends_on: ["05-01"]
files_modified:
  - src/mcp_trino_optimizer/recommender/conflicts.py
  - src/mcp_trino_optimizer/recommender/templates.py
  - src/mcp_trino_optimizer/recommender/session_properties.py
  - src/mcp_trino_optimizer/recommender/engine.py
  - tests/recommender/test_conflicts.py
  - tests/recommender/test_templates.py
  - tests/recommender/test_session_properties.py
  - tests/recommender/test_engine.py
autonomous: true
requirements:
  - REC-02
  - REC-03
  - REC-04
  - REC-05

must_haves:
  truths:
    - "When R1 and D11 both fire on the same operator, D11 wins (higher confidence) and R1 is in considered_but_rejected"
    - "When R2 and R9 both fire on the same operator, R2 wins and R9 is rejected"
    - "When R5 and R8 fire on same exchange/join nodes, R5 wins and R8 is rejected"
    - "Recommendation narrative contains ONLY templated text; user-origin SQL injection attempt does NOT appear in output"
    - "Session property recommendations include exact SET SESSION statement from the data module"
    - "When CapabilityMatrix is None (offline), session property recommendations are advisory-only"
    - "When Trino version < min_trino_version for a property, recommendation says advisory-only"
    - "RecommendationEngine.recommend() returns a sorted RecommendationReport"
  artifacts:
    - path: "src/mcp_trino_optimizer/recommender/conflicts.py"
      provides: "Declared conflict pairs and resolution logic"
      exports: ["CONFLICT_PAIRS", "resolve_conflicts"]
    - path: "src/mcp_trino_optimizer/recommender/templates.py"
      provides: "str.format templates keyed by rule_id for reasoning, expected_impact, validation_steps"
      exports: ["TEMPLATES", "render_recommendation"]
    - path: "src/mcp_trino_optimizer/recommender/session_properties.py"
      provides: "Embedded Trino session property data module"
      exports: ["SessionProperty", "SESSION_PROPERTIES", "RULE_SESSION_PROPERTIES", "build_set_session_statements"]
    - path: "src/mcp_trino_optimizer/recommender/engine.py"
      provides: "RecommendationEngine orchestrating scoring, conflicts, templates, session properties"
      exports: ["RecommendationEngine"]
  key_links:
    - from: "src/mcp_trino_optimizer/recommender/engine.py"
      to: "src/mcp_trino_optimizer/recommender/scoring.py"
      via: "engine calls compute_priority + assign_tier for each finding"
      pattern: "compute_priority"
    - from: "src/mcp_trino_optimizer/recommender/engine.py"
      to: "src/mcp_trino_optimizer/recommender/conflicts.py"
      via: "engine calls resolve_conflicts after scoring"
      pattern: "resolve_conflicts"
    - from: "src/mcp_trino_optimizer/recommender/engine.py"
      to: "src/mcp_trino_optimizer/recommender/templates.py"
      via: "engine calls render_recommendation to produce narrative"
      pattern: "render_recommendation"
    - from: "src/mcp_trino_optimizer/recommender/engine.py"
      to: "src/mcp_trino_optimizer/recommender/session_properties.py"
      via: "engine calls build_set_session_statements for applicable rules"
      pattern: "build_set_session_statements"
---

<objective>
Implement conflict resolution, audited narrative templates, session property grounding, and wire them together in the RecommendationEngine.

Purpose: Deliver the core recommendation pipeline: findings -> scored recommendations -> conflict resolution -> templated narratives -> session property statements -> sorted RecommendationReport. The engine is the main entry point for Phase 8's `suggest_optimizations` tool.

Output: Four modules (conflicts, templates, session_properties, engine) with full test coverage including prompt-injection defense test.
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

<interfaces>
<!-- From Plan 01 outputs -->

From src/mcp_trino_optimizer/recommender/models.py (created in Plan 01):
```python
PriorityTier = Literal["P1", "P2", "P3", "P4"]
RiskLevel = Literal["low", "medium", "high"]

class ConsideredButRejected(BaseModel):
    rule_id: str
    reason: str
    original_priority_score: float

class Recommendation(BaseModel):
    rule_id: str
    severity: Severity
    confidence: float
    priority_score: float
    priority_tier: PriorityTier
    operator_ids: list[str]
    reasoning: str
    expected_impact: str
    risk_level: RiskLevel
    validation_steps: str
    session_property_statements: list[str] | None = None
    evidence_summary: dict[str, Any]
    considered_but_rejected: list[ConsideredButRejected] = []

class RecommendationReport(BaseModel):
    recommendations: list[Recommendation]
    iceberg_health: list[IcebergTableHealth] = []
    bottleneck_ranking: BottleneckRanking | None = None
    considered_but_rejected: list[ConsideredButRejected] = []
```

From src/mcp_trino_optimizer/recommender/scoring.py (created in Plan 01):
```python
SEVERITY_WEIGHTS: dict[str, int] = {"critical": 4, "high": 3, "medium": 2, "low": 1}
def compute_priority(severity: str, impact: float, confidence: float) -> float: ...
def assign_tier(score: float, thresholds: tuple[float, float, float]) -> PriorityTier: ...
```

From src/mcp_trino_optimizer/recommender/impact.py (created in Plan 01):
```python
def get_impact(rule_id: str, evidence: dict[str, Any]) -> float: ...
DEFAULT_IMPACT = 0.5
```

From src/mcp_trino_optimizer/rules/findings.py:
```python
class RuleFinding(BaseModel):
    kind: Literal["finding"] = "finding"
    rule_id: str
    severity: Severity
    confidence: float
    message: str
    evidence: dict[str, Any]
    operator_ids: list[str]

EngineResult = Annotated[RuleFinding | RuleError | RuleSkipped, Field(discriminator="kind")]
```

From src/mcp_trino_optimizer/adapters/trino/capabilities.py:
```python
@dataclass(frozen=True)
class CapabilityMatrix:
    trino_version_major: int
    ...
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Conflict resolution + session property data module</name>
  <files>
    src/mcp_trino_optimizer/recommender/conflicts.py,
    src/mcp_trino_optimizer/recommender/session_properties.py,
    tests/recommender/test_conflicts.py,
    tests/recommender/test_session_properties.py
  </files>
  <read_first>
    src/mcp_trino_optimizer/recommender/models.py,
    src/mcp_trino_optimizer/recommender/scoring.py,
    src/mcp_trino_optimizer/rules/findings.py,
    src/mcp_trino_optimizer/adapters/trino/capabilities.py,
    src/mcp_trino_optimizer/rules/r5_broadcast_too_big.py,
    src/mcp_trino_optimizer/rules/r4_dynamic_filtering.py,
    src/mcp_trino_optimizer/rules/r7_cpu_skew.py,
    src/mcp_trino_optimizer/rules/r6_join_order.py
  </read_first>
  <behavior>
    - Test: resolve_conflicts with R1(conf=0.8) + D11(conf=0.95) on same operator -> D11 wins, R1 rejected
    - Test: resolve_conflicts with R2(sev=high) + R9(sev=medium) on same operator -> R2 wins
    - Test: resolve_conflicts with R5(sev=high) + R8(sev=medium) on overlapping nodes -> R5 wins
    - Test: resolve_conflicts with same-confidence same-severity -> tiebreak by rule_id alphabetically
    - Test: resolve_conflicts with no conflicts -> all findings pass through, empty rejected list
    - Test: resolve_conflicts with findings on DIFFERENT operators -> no conflict triggered
    - Test: Iceberg rules (I1, I3, I6 with operator_ids=[]) on same analysis -> conflict resolved on "same analysis" basis, not operator_id
    - Test: SessionProperty model validates name, description, default, valid_range, min_trino_version, category
    - Test: SESSION_PROPERTIES contains "join_distribution_type", "enable_dynamic_filtering", "task_concurrency", "join_reordering_strategy", "join_max_broadcast_table_size"
    - Test: RULE_SESSION_PROPERTIES maps R4 -> ["enable_dynamic_filtering"], R5 -> ["join_distribution_type", "join_max_broadcast_table_size"]
    - Test: build_set_session_statements("R5", cap_matrix_480) returns ["SET SESSION join_distribution_type = 'PARTITIONED'"]
    - Test: build_set_session_statements("R5", None) returns advisory-only list (no SET SESSION)
    - Test: build_set_session_statements("R5", cap_matrix_old) for property with min_version > old returns advisory-only
    - Test: build_set_session_statements("R1", cap_matrix_480) returns [] (R1 has no session properties)
  </behavior>
  <action>
    1. Create `src/mcp_trino_optimizer/recommender/conflicts.py`:

       Define a `ScoredFinding` dataclass (or use a NamedTuple) that pairs a `RuleFinding`
       with its `priority_score` for conflict resolution input.

       Define `CONFLICT_PAIRS: dict[str, set[str]]` — bidirectional declared conflict pairs per D-05:
       ```python
       CONFLICT_PAIRS = {
           "R1": {"D11"},
           "D11": {"R1"},
           "R2": {"R9"},
           "R9": {"R2"},
           "R5": {"R8"},
           "R8": {"R5"},
       }
       ```

       Define `resolve_conflicts(scored: list[ScoredFinding]) -> tuple[list[ScoredFinding], list[ConsideredButRejected]]`:
       - Group scored findings by operator_id sets.
       - For findings with `operator_ids == []` (Iceberg table-level rules), group by
         "same analysis" — all empty-operator findings form one group.
       - Within each group, check all pairs against CONFLICT_PAIRS.
       - For each declared conflict pair on same operator/group:
         winner = higher confidence (D-04). On tie: higher severity. On tie: alphabetically
         lower rule_id (Claude's discretion tiebreaker).
       - Return (winners, list of ConsideredButRejected with reason string).

    2. Create `src/mcp_trino_optimizer/recommender/session_properties.py`:

       Define `SessionProperty(BaseModel)`:
         name: str, description: str, default: str, valid_range: str | None = None,
         min_trino_version: int = 429, category: str,
         set_session_template: str (e.g. "SET SESSION {name} = 'PARTITIONED'")

       Define `SESSION_PROPERTIES: dict[str, SessionProperty]` with entries for:
       - `join_distribution_type`: default "AUTOMATIC", min_version 429, category "join",
         set_session_template "SET SESSION join_distribution_type = 'PARTITIONED'"
       - `join_max_broadcast_table_size`: default "100MB", min_version 429, category "join",
         set_session_template "SET SESSION join_max_broadcast_table_size = '200MB'"
       - `enable_dynamic_filtering`: default "true", min_version 429, category "join",
         set_session_template "SET SESSION enable_dynamic_filtering = true"
       - `task_concurrency`: default "16", min_version 429, category "execution",
         set_session_template "SET SESSION task_concurrency = 8"
       - `join_reordering_strategy`: default "AUTOMATIC", min_version 429, category "optimizer",
         set_session_template "SET SESSION join_reordering_strategy = 'AUTOMATIC'"

       Define `RULE_SESSION_PROPERTIES: dict[str, list[str]]`:
       ```python
       {
           "R4": ["enable_dynamic_filtering"],
           "R5": ["join_distribution_type", "join_max_broadcast_table_size"],
           "R6": ["join_reordering_strategy"],
           "R7": ["task_concurrency"],
           "R8": ["join_distribution_type"],
       }
       ```

       Define `build_set_session_statements(rule_id: str, capability_matrix: CapabilityMatrix | None) -> list[str]`:
       - Look up rule_id in RULE_SESSION_PROPERTIES. If missing, return [].
       - For each property name, look up in SESSION_PROPERTIES.
       - If capability_matrix is None: return advisory strings like
         "-- Advisory: SET SESSION {name} = ... (cannot verify property availability without live Trino connection)"
       - If capability_matrix.trino_version_major < property.min_trino_version: return advisory
         "-- Advisory: SET SESSION {name} = ... (requires Trino >= {min_version}, connected to {actual})"
       - Otherwise: return the set_session_template string.

    3. Create tests for both modules.
  </action>
  <verify>
    <automated>cd /Users/allen/repo/mcp-trino-optimizer && uv run pytest tests/recommender/test_conflicts.py tests/recommender/test_session_properties.py -x -q --timeout=30</automated>
  </verify>
  <acceptance_criteria>
    - src/mcp_trino_optimizer/recommender/conflicts.py contains `CONFLICT_PAIRS`
    - src/mcp_trino_optimizer/recommender/conflicts.py contains `def resolve_conflicts(`
    - src/mcp_trino_optimizer/recommender/conflicts.py contains `"R1": {"D11"}`
    - src/mcp_trino_optimizer/recommender/session_properties.py contains `class SessionProperty(`
    - src/mcp_trino_optimizer/recommender/session_properties.py contains `SESSION_PROPERTIES`
    - src/mcp_trino_optimizer/recommender/session_properties.py contains `RULE_SESSION_PROPERTIES`
    - src/mcp_trino_optimizer/recommender/session_properties.py contains `def build_set_session_statements(`
    - tests/recommender/test_conflicts.py exits 0
    - tests/recommender/test_session_properties.py exits 0
  </acceptance_criteria>
  <done>Conflict pairs declared for R1/D11, R2/R9, R5/R8. Resolution is confidence-first, severity-second, rule_id-third. Session property data module covers R4/R5/R6/R7/R8 with version gating. Advisory fallback works for offline mode and old Trino versions. All tests green.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Narrative templates + RecommendationEngine + prompt-injection test</name>
  <files>
    src/mcp_trino_optimizer/recommender/templates.py,
    src/mcp_trino_optimizer/recommender/engine.py,
    src/mcp_trino_optimizer/recommender/__init__.py,
    tests/recommender/test_templates.py,
    tests/recommender/test_engine.py
  </files>
  <read_first>
    src/mcp_trino_optimizer/recommender/models.py,
    src/mcp_trino_optimizer/recommender/scoring.py,
    src/mcp_trino_optimizer/recommender/impact.py,
    src/mcp_trino_optimizer/recommender/conflicts.py,
    src/mcp_trino_optimizer/recommender/session_properties.py,
    src/mcp_trino_optimizer/rules/findings.py,
    src/mcp_trino_optimizer/rules/engine.py,
    src/mcp_trino_optimizer/settings.py
  </read_first>
  <behavior>
    - Test: render_recommendation("R1", evidence={"operator_id": "0", "table_name": "orders"}) produces non-empty reasoning, expected_impact, validation_steps, risk_level
    - Test: render_recommendation for all 14 rule_ids produces valid output (no KeyError)
    - Test: render_recommendation("R1", evidence containing malicious SQL "'; DROP TABLE users; --") does NOT include that string in reasoning/expected_impact/validation_steps
    - Test: TEMPLATES dict has entries for all 14 rule_ids
    - Test: RecommendationEngine.recommend(findings=[R1_finding]) returns RecommendationReport with 1 recommendation sorted by priority_score descending
    - Test: RecommendationEngine.recommend(findings=[R1, D11 on same op]) returns 1 recommendation (D11) + 1 considered_but_rejected (R1)
    - Test: RecommendationEngine.recommend with R5 finding returns recommendation with session_property_statements containing "SET SESSION"
    - Test: RecommendationEngine.recommend with R1 finding returns recommendation with session_property_statements = None (R1 has no session properties)
    - Test: RecommendationEngine.recommend filters out RuleError and RuleSkipped from EngineResult list
    - Test: RecommendationEngine.recommend with empty findings list returns empty report
    - Test: RecommendationEngine.recommend with capability_matrix=None produces advisory-only session statements
  </behavior>
  <action>
    1. Create `src/mcp_trino_optimizer/recommender/templates.py`:

       Define `TEMPLATES: dict[str, dict[str, str]]` with entries for all 14 rule_ids.
       Each entry has keys: "reasoning", "expected_impact", "validation_steps", "risk_level".
       Templates use ONLY evidence dict field placeholders (e.g., `{operator_id}`, `{table_name}`,
       numeric fields) and NEVER `{message}` from RuleFinding.message (Pitfall 1 from RESEARCH.md).

       Template format placeholders per rule (use `.get()` with defaults for missing keys):
       - R1: `{operator_id}`, `{table_name}` — reasoning about missing/stale stats, validation: run ANALYZE
       - R2: `{operator_id}`, `{partition_predicate}` — partition pruning failure, validation: check EXPLAIN
       - R3: `{operator_id}`, `{function_name}`, `{column_name}` — pushdown failure, validation: rewrite predicate
       - R4: `{operator_id}` — dynamic filtering not applied, validation: check session property
       - R5: `{operator_id}`, `{distribution}`, `{build_side_estimated_bytes}` — broadcast too big, validation: SET SESSION
       - R6: `{operator_id}` — join order inversion, validation: check EXPLAIN after ANALYZE
       - R7: `{operator_id}`, `{p99_p50_ratio}`, `{stage_id}` — CPU skew, validation: check stage metrics
       - R8: `{operator_id}`, `{ratio}` — exchange volume, validation: SET SESSION partitioned
       - R9: `{operator_id}`, `{selectivity}` — low selectivity, validation: add partition predicates
       - I1: `{table_name}`, `{data_file_count}`, `{median_file_size_bytes}` — small files, validation: run OPTIMIZE
       - I3: `{table_name}`, `{delete_file_count}` — delete files, validation: run OPTIMIZE
       - I6: `{table_name}`, `{snapshot_count}` — stale snapshots, validation: run expire_snapshots
       - I8: `{table_name}`, `{constraint_column}` — partition mismatch, validation: rewrite predicate
       - D11: `{operator_id}`, `{divergence_factor}` — cost divergence, validation: run ANALYZE

       Define `render_recommendation(rule_id: str, evidence: dict[str, Any]) -> dict[str, str]`:
       - Look up template by rule_id. If missing, return generic fallback.
       - Create a safe_evidence dict: for each key in evidence, keep only str/int/float values.
         This prevents any complex object injection.
       - Use `template.format_map(defaultdict(lambda: "N/A", safe_evidence))` to render
         each field. This ensures missing keys produce "N/A" not KeyError.
       - Return dict with keys "reasoning", "expected_impact", "validation_steps", "risk_level".

    2. Create `src/mcp_trino_optimizer/recommender/engine.py`:

       ```python
       class RecommendationEngine:
           def __init__(
               self,
               capability_matrix: CapabilityMatrix | None = None,
               settings: Settings | None = None,
           ) -> None: ...

           def recommend(
               self,
               engine_results: list[EngineResult],
           ) -> RecommendationReport: ...
       ```

       The `recommend` method:
       a. Filter engine_results to only RuleFinding objects (skip RuleError, RuleSkipped).
       b. For each RuleFinding: compute impact via `get_impact(finding.rule_id, finding.evidence)`.
       c. Compute priority via `compute_priority(finding.severity, impact, finding.confidence)`.
       d. Assign tier via `assign_tier(score, settings tier thresholds)`.
       e. Build list of ScoredFinding objects.
       f. Call `resolve_conflicts(scored)` to get (winners, rejected).
       g. For each winner: call `render_recommendation(rule_id, evidence)` for narrative.
       h. For each winner: call `build_set_session_statements(rule_id, capability_matrix)`.
       i. Construct `Recommendation` objects from winners.
       j. Sort recommendations by priority_score descending.
       k. Return `RecommendationReport(recommendations=..., considered_but_rejected=rejected)`.
         (iceberg_health and bottleneck_ranking are populated in Plan 03.)

    3. Update `src/mcp_trino_optimizer/recommender/__init__.py` to export `RecommendationEngine`.

    4. Create `tests/recommender/test_templates.py`:
       - Test all 14 templates render without error.
       - Test prompt-injection: inject `"'; DROP TABLE users; --"` as a value in evidence dict,
         assert it does NOT appear in any rendered field. The safe_evidence filter + template-only
         rendering should sanitize this. Per REC-03.
       - Test missing evidence keys produce "N/A" fallback.

    5. Create `tests/recommender/test_engine.py`:
       - Test full pipeline: findings -> recommendations sorted by score.
       - Test conflict resolution in pipeline (R1 + D11 same operator).
       - Test session property wiring (R5 finding -> SET SESSION in output).
       - Test offline mode (cap_matrix=None -> advisory).
       - Test empty input.
       - Test mixed EngineResult (findings + errors + skips -> only findings processed).
  </action>
  <verify>
    <automated>cd /Users/allen/repo/mcp-trino-optimizer && uv run pytest tests/recommender/test_templates.py tests/recommender/test_engine.py -x -q --timeout=30</automated>
  </verify>
  <acceptance_criteria>
    - src/mcp_trino_optimizer/recommender/templates.py contains `TEMPLATES`
    - src/mcp_trino_optimizer/recommender/templates.py contains `def render_recommendation(`
    - grep -c 'rule_id' src/mcp_trino_optimizer/recommender/templates.py shows entries for R1-R9, I1, I3, I6, I8, D11
    - src/mcp_trino_optimizer/recommender/engine.py contains `class RecommendationEngine:`
    - src/mcp_trino_optimizer/recommender/engine.py contains `def recommend(`
    - tests/recommender/test_templates.py contains `DROP TABLE` (the injection test)
    - tests/recommender/test_templates.py exits 0
    - tests/recommender/test_engine.py exits 0
  </acceptance_criteria>
  <done>Narrative templates for all 14 rules render safely with no user-origin text injection. RecommendationEngine orchestrates scoring -> conflict resolution -> templates -> session properties -> sorted output. Prompt-injection test proves REC-03. All tests green.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| RuleFinding.evidence -> template rendering | Evidence values originate from user SQL via plan parsing; must be sanitized before template interpolation |
| RuleFinding.message -> recommendation body | message field may contain user-origin text; NEVER used in templates (Pitfall 1) |
| Session property names -> SET SESSION output | Property names must come from embedded data module, never from user input or evidence |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-05-03 | Tampering | templates.py | mitigate | Templates use ONLY typed evidence fields via safe_evidence filter; RuleFinding.message is never interpolated. Unit test injects SQL injection string and asserts absence from output (REC-03) |
| T-05-04 | Information Disclosure | session_properties.py | mitigate | Property names come exclusively from SESSION_PROPERTIES dict (D-09); build_set_session_statements never fabricates names. Test with stub resource verifies advisory fallback |
| T-05-05 | Tampering | conflicts.py | accept | Conflict resolution preserves rejected findings in considered_but_rejected with explicit reasons (D-04); no findings silently dropped |
| T-05-06 | Elevation of Privilege | engine.py | mitigate | Engine filters EngineResult to only RuleFinding kind; RuleError/RuleSkipped are excluded from recommendation pipeline. No dynamic code execution |
</threat_model>

<verification>
All recommender tests pass:
```bash
uv run pytest tests/recommender/ -x -q --timeout=30
```

Prompt injection defense verified:
```bash
uv run pytest tests/recommender/test_templates.py::test_no_injection -x -v
```

Existing tests unaffected:
```bash
uv run pytest tests/ -x --timeout=120
```

Lint clean:
```bash
uv run ruff check src/mcp_trino_optimizer/recommender/ tests/recommender/
```
</verification>

<success_criteria>
- Conflict resolution correctly handles R1/D11, R2/R9, R5/R8 declared pairs
- Templates exist for all 14 rules with no user-origin text in output
- Session property data module covers R4/R5/R6/R7/R8 with version gating
- RecommendationEngine.recommend() produces sorted RecommendationReport
- Prompt-injection test proves REC-03 compliance
- All tests pass, lint clean
</success_criteria>

<output>
After completion, create `.planning/phases/05-recommendation-engine/05-02-SUMMARY.md`
</output>
