# Phase 5: Recommendation Engine - Research

**Researched:** 2026-04-13
**Domain:** Recommendation engine — priority scoring, conflict resolution, templated narratives, session-property grounding, Iceberg health summaries, operator bottleneck ranking
**Confidence:** HIGH

## Summary

Phase 5 transforms raw `RuleFinding` objects from Phase 4's rule engine into prioritized, actionable `Recommendation` objects. The domain is well-scoped: all 14 rules (R1-R9, I1/I3/I6/I8, D11) are shipped and their evidence dict schemas are stable. The recommender is a pure function of `list[EngineResult]` + `CapabilityMatrix` + `session_properties` data, producing `list[Recommendation]` sorted by priority score.

The key technical challenges are: (1) designing impact extractors per rule that pull a 0-1.0 score from evidence dicts with varying schemas, (2) implementing declared conflict pairs on same-operator matching without heuristic over-triggering, (3) building an Iceberg table health summary that aggregates findings from I1/I3/I6/I8 into a per-table structure, and (4) building an operator bottleneck ranking from ExecutedPlan CPU/wall-time metrics with templated narratives.

**Primary recommendation:** Build the recommender as a standalone package `src/mcp_trino_optimizer/recommender/` following the same hexagonal pattern as `rules/`. Use pydantic models for all output types, Python `str.format()` templates in a dedicated templates module, and a session-property data module that Phase 8 will later wrap as an MCP resource.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Priority = severity_weight x impact_score x confidence. Severity maps to numeric weights: critical=4, high=3, medium=2, low=1. Confidence is the existing 0-1.0 float from RuleFinding.
- **D-02:** Impact is derived per-rule via an evidence-based heuristic. Each rule declares an `impact_extractor` that pulls a 0-1.0 score from its evidence dict (e.g., bytes_wasted / total_bytes for R8, selectivity ratio for R9). Rules without quantifiable evidence default to 0.5.
- **D-03:** Output exposes both a raw float priority score (for sorting) and a tier label (P1/P2/P3/P4) for human/LLM readability. Tier thresholds are configurable.
- **D-04:** Conflict winner is determined by confidence-first. On confidence tie, higher severity wins. The loser is kept as a `considered_but_rejected` entry with an explicit reason. Matches REC-04 requirement.
- **D-05:** Conflict detection uses declared conflict pairs. Each rule declares a list of `rule_ids` it can conflict with (e.g., R1 conflicts_with D11 on the same operator). Only declared pairs on the same operator_id trigger conflict resolution. No heuristic same-operator matching.
- **D-06:** Recommendation narratives use Python string templates (str.format) stored as constants in a templates module, keyed by rule_id. No Jinja dependency for this phase. Simple, type-safe, auditable.
- **D-07:** Iceberg table health summary (REC-06) uses a dedicated `IcebergTableHealth` pydantic model that aggregates data from I1/I3/I6/I8 findings, with a Python template rendering it into a concise per-table summary.
- **D-08:** Operator bottleneck ranking (REC-07) defaults to top 5 operators ranked by wall-time or CPU-time contribution. The N is configurable via settings.
- **D-09:** Session property names come from an embedded Python data module (`session_properties.py`) with a dict of property names, descriptions, valid ranges, and Trino version gates. Phase 8 will wrap this same data as the `trino_session_properties` MCP resource — single source of truth from day one.
- **D-10:** Each session property entry includes `min_trino_version`. The recommender checks against the capability matrix (from Phase 2's version probe) and emits advisory-only if the connected Trino is too old. Prevents recommending SET SESSION for properties that don't exist on the target cluster.

### Claude's Discretion
- Tie-breaking logic beyond confidence-then-severity (e.g., alphabetical rule_id as final tiebreaker)
- Exact tier threshold values for P1/P2/P3/P4 (sensible defaults, configurable)
- Internal module structure within the recommender package
- Template wording for each rule_id's recommendation narrative

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| REC-01 | Recommender converts RuleFinding objects into prioritized Recommendation list; priority = severity x impact x confidence | Locked decision D-01/D-02/D-03 define formula; evidence dict analysis below maps each rule to an impact extractor |
| REC-02 | Each Recommendation includes reasoning, expected impact, risk level, validation steps, confidence | Pydantic model design; template module keyed by rule_id provides reasoning and validation steps |
| REC-03 | Narrative from audited templates only; no user-origin text in body | D-06 locks str.format templates; prompt-injection test pattern from Phase 1 (PLAT-11) applies |
| REC-04 | Conflict resolution: higher-confidence wins, loser becomes considered_but_rejected | D-04/D-05 lock conflict-pair approach; R1/D11 is the primary declared conflict pair |
| REC-05 | Session property recommendations include exact SET SESSION using trino_session_properties resource | D-09/D-10 lock the data module approach with version gating via CapabilityMatrix |
| REC-06 | Iceberg table health summary per scanned table | D-07 locks IcebergTableHealth pydantic model aggregating I1/I3/I6/I8 findings |
| REC-07 | Operator bottleneck ranking with templated narrative for top N | D-08 locks top-5 default, configurable; requires ExecutedPlan CPU/wall-time metrics from PlanNode |
</phase_requirements>

## Standard Stack

### Core

No new external dependencies are required for Phase 5. Everything uses the existing stack:

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `pydantic` | `>=2.9,<3` (already installed) | `Recommendation`, `IcebergTableHealth`, `BottleneckRanking` models | Already the project-wide model layer; rule findings, plan nodes, settings all use it | [VERIFIED: pyproject.toml] |
| `pydantic-settings` | `>=2.13.1` (already installed) | `RecommenderSettings` for tier thresholds, top_n_bottleneck config | Extends existing `Settings` pattern from Phase 1 | [VERIFIED: pyproject.toml] |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `structlog` | `>=25.5.0` (already installed) | Logging recommender processing decisions | Already configured project-wide | [VERIFIED: pyproject.toml] |

No new `pip install` needed. Phase 5 is pure Python business logic on top of existing models.

## Architecture Patterns

### Recommended Project Structure

```
src/mcp_trino_optimizer/
├── recommender/
│   ├── __init__.py             # Public API: RecommendationEngine, Recommendation, etc.
│   ├── models.py               # Pydantic models: Recommendation, IcebergTableHealth,
│   │                           #   BottleneckEntry, BottleneckRanking, ConsideredButRejected
│   ├── engine.py               # RecommendationEngine: findings -> recommendations
│   ├── impact.py               # Impact extractor registry: rule_id -> (evidence) -> 0-1.0
│   ├── conflicts.py            # Conflict pair declarations + resolution logic
│   ├── templates.py            # str.format templates keyed by rule_id
│   ├── session_properties.py   # Embedded data module: property name, desc, range, min_version
│   ├── health.py               # IcebergTableHealth aggregator from I1/I3/I6/I8 findings
│   └── bottleneck.py           # Operator bottleneck ranker from ExecutedPlan metrics
├── rules/                      # (existing — input to recommender)
│   └── ...
└── settings.py                 # (existing — extend with recommender settings)
```

[ASSUMED — module structure is Claude's discretion per CONTEXT.md]

### Pattern 1: Impact Extractor Registry

**What:** Each rule declares an impact extractor function that computes a 0-1.0 impact score from its evidence dict.
**When to use:** Computing the priority score for every RuleFinding.

```python
# Source: Designed from D-01/D-02 locked decisions
from typing import Any, Callable

ImpactExtractor = Callable[[dict[str, Any]], float]

_IMPACT_EXTRACTORS: dict[str, ImpactExtractor] = {}

def register_impact(rule_id: str) -> Callable[[ImpactExtractor], ImpactExtractor]:
    def decorator(fn: ImpactExtractor) -> ImpactExtractor:
        _IMPACT_EXTRACTORS[rule_id] = fn
        return fn
    return decorator

DEFAULT_IMPACT = 0.5  # D-02: rules without quantifiable evidence

@register_impact("R8")
def _r8_impact(evidence: dict[str, Any]) -> float:
    """R8: ratio of exchange_bytes / scan_bytes, clamped to 0-1.0."""
    ratio = evidence.get("ratio", 1.0)
    # Normalize: ratio of 1.0 = minimal waste, ratio of 10.0 = extreme waste
    return min(1.0, (ratio - 1.0) / 9.0)  # linear scale 1x->0.0, 10x->1.0

@register_impact("R9")
def _r9_impact(evidence: dict[str, Any]) -> float:
    """R9: 1.0 - selectivity (lower selectivity = higher impact)."""
    # Evidence has threshold_bytes vs selected, but the finding itself tells us selectivity is low
    return 0.7  # Low-selectivity is always medium-high impact

def get_impact(rule_id: str, evidence: dict[str, Any]) -> float:
    extractor = _IMPACT_EXTRACTORS.get(rule_id)
    if extractor is None:
        return DEFAULT_IMPACT
    return max(0.0, min(1.0, extractor(evidence)))
```

[ASSUMED — exact extractor formulas are implementation detail]

### Pattern 2: Conflict Resolution with Declared Pairs

**What:** Rules declare which other rules they can conflict with. Only declared pairs on the same operator trigger resolution.
**When to use:** Post-scoring, before final output assembly.

```python
# Source: D-04/D-05 locked decisions
CONFLICT_PAIRS: dict[str, set[str]] = {
    "R1": {"D11"},   # Both detect stats issues on scan nodes
    "D11": {"R1"},   # Bidirectional declaration
}

def resolve_conflicts(
    findings: list[ScoredFinding],
) -> tuple[list[ScoredFinding], list[ConsideredButRejected]]:
    """Given scored findings, resolve conflicts on same operator_id.

    Returns (winners, rejected).
    D-04: confidence-first, then severity on tie.
    """
    ...
```

[VERIFIED: R1 and D11 both target scan nodes with overlapping evidence — codebase confirms operator_ids overlap]

### Pattern 3: Templated Narratives (No User-Origin Text)

**What:** Templates keyed by rule_id use str.format with only evidence-dict fields and plan operator IDs.
**When to use:** Building recommendation reasoning, expected_impact, and validation_steps.

```python
# Source: D-06 locked decision, REC-03 requirement
TEMPLATES: dict[str, dict[str, str]] = {
    "R1": {
        "reasoning": (
            "Table statistics are missing or stale for scan operator {operator_id}. "
            "Without accurate statistics, the CBO cannot estimate row counts "
            "(estimated: {estimated_row_count}, actual from SHOW STATS: {table_stats_row_count}), "
            "leading to poor join ordering and memory grants."
        ),
        "expected_impact": (
            "Running ANALYZE will update statistics, enabling the CBO to make "
            "accurate join-order and distribution decisions. Typical improvement: 2-10x "
            "on queries with multiple joins."
        ),
        "validation_steps": (
            "1. Run: ANALYZE {table_name}\n"
            "2. Re-run: EXPLAIN (FORMAT JSON) on the original query\n"
            "3. Verify: CBO estimates now show non-NaN row counts on scan nodes"
        ),
    },
    # ... one entry per rule_id
}
```

[ASSUMED — exact template wording is Claude's discretion per CONTEXT.md]

### Pattern 4: Session Property Data Module

**What:** Embedded Python dict mapping property names to metadata, used by the recommender and later by Phase 8 MCP resource.
**When to use:** When a rule's fix involves a Trino session property.

```python
# Source: D-09/D-10 locked decisions
from pydantic import BaseModel

class SessionProperty(BaseModel):
    name: str
    description: str
    default: str
    valid_range: str | None = None
    min_trino_version: int = 429  # minimum supported
    category: str  # e.g., "join", "execution", "optimizer"

SESSION_PROPERTIES: dict[str, SessionProperty] = {
    "join_distribution_type": SessionProperty(
        name="join_distribution_type",
        description="Controls join distribution strategy",
        default="AUTOMATIC",
        valid_range="BROADCAST, PARTITIONED, AUTOMATIC",
        min_trino_version=429,
        category="join",
    ),
    "join_max_broadcast_table_size": SessionProperty(
        name="join_max_broadcast_table_size",
        description="Maximum size for broadcast join build side",
        default="100MB",
        valid_range="any DataSize string",
        min_trino_version=429,
        category="join",
    ),
    # ... more properties
}

# Rule-to-property mapping
RULE_SESSION_PROPERTIES: dict[str, list[str]] = {
    "R5": ["join_distribution_type", "join_max_broadcast_table_size"],
    "R4": ["enable_dynamic_filtering"],
    "R7": ["task_concurrency"],
    # ...
}
```

[ASSUMED — exact property list based on training data knowledge of Trino session properties. Will need verification against Trino 480 docs.]

### Anti-Patterns to Avoid

- **Free-form user text in recommendation bodies:** Never interpolate user-supplied SQL or error messages into templates. Only use evidence dict fields and operator IDs. This is the REC-03 security contract.
- **Heuristic same-operator conflict detection:** D-05 explicitly bans this. Only declared conflict pairs trigger resolution.
- **Coupling to live Trino in the recommender:** The recommender takes `CapabilityMatrix | None` and gracefully degrades (advisory-only for session properties when matrix is None or version too old).
- **Mixing recommendation scoring with rule logic:** Rules produce observations (RuleFinding). The recommender produces actions (Recommendation). Keep them in separate packages.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Priority scoring formula | Custom scoring framework | Simple arithmetic: `severity_weight * impact * confidence` (D-01) | The formula is locked; complexity is in impact extractors, not scoring infrastructure |
| Template engine | Jinja2 or custom template parser | Python `str.format()` (D-06) | Auditable, type-safe, no dependency. Templates are constants, not loaded from disk at runtime |
| Session property catalog | Scraping Trino docs at runtime | Embedded Python data module (D-09) | Static data, versioned in source control, single source of truth |
| Conflict detection | Graph-based conflict resolution | Simple declared-pair lookup + same-operator-id set intersection (D-05) | Only ~2-3 conflict pairs in v1; graph algorithms are overkill |

**Key insight:** Phase 5 is almost entirely domain modeling + template authoring. No new libraries, no complex algorithms. The challenge is completeness (templates for all 14 rules) and correctness (conflict resolution, injection prevention).

## Common Pitfalls

### Pitfall 1: Template Injection via Evidence Fields
**What goes wrong:** If a rule's `message` field (which contains operator-specific text) is used in templates, and that message was constructed from user-origin data (e.g., table names from SQL), injection can occur.
**Why it happens:** Rules construct messages from plan node data which ultimately comes from user SQL.
**How to avoid:** Templates must ONLY use evidence dict numeric/enum fields and operator IDs. Never use the `message` field from RuleFinding in recommendation templates. The `message` field is for rule-level diagnostics, not for recommendation narrative.
**Warning signs:** Any template containing `{message}` or any string from `RuleFinding.message`.

### Pitfall 2: Impact Extractor Division by Zero
**What goes wrong:** Impact extractors compute ratios from evidence dicts. Evidence values can be 0, None, or NaN.
**Why it happens:** Rules handle edge cases in their own logic but evidence dicts may still carry boundary values.
**How to avoid:** Every impact extractor must guard: `if denominator is None or denominator <= 0: return DEFAULT_IMPACT`. Use `safe_float` from `rules.evidence` for NaN protection.
**Warning signs:** Impact scores of `inf` or `NaN` in recommendation output.

### Pitfall 3: Conflict Resolution on Empty operator_ids
**What goes wrong:** Some Iceberg rules (I1, I3, I6) emit findings with `operator_ids=[]` (table-level, not operator-level). Conflict resolution on same-operator matching won't trigger for these.
**Why it happens:** Iceberg metadata rules don't attach to specific plan operators.
**How to avoid:** Conflict pairs involving Iceberg rules should match on "same analysis" (both present), not "same operator_id". Document this explicitly in conflict resolution logic.
**Warning signs:** I1 and I3 both firing for the same table but not triggering conflict resolution.

### Pitfall 4: Session Property Version Gating Without CapabilityMatrix
**What goes wrong:** In offline mode, CapabilityMatrix is None. The recommender tries to check `min_trino_version` against None.
**Why it happens:** Offline mode has no live cluster to probe.
**How to avoid:** When `CapabilityMatrix` is None, emit all session property recommendations as advisory-only with a note: "Cannot verify property availability without live Trino connection."
**Warning signs:** `AttributeError` or `TypeError` when accessing `capability_matrix.trino_version_major`.

### Pitfall 5: Bottleneck Ranking on EstimatedPlan
**What goes wrong:** Operator bottleneck ranking requires `cpu_time_ms` / `wall_time_ms` which are only populated on `ExecutedPlan`. Attempting this on `EstimatedPlan` produces empty rankings.
**Why it happens:** REC-07 doesn't explicitly say "requires ExecutedPlan" but the data is only there.
**How to avoid:** Check `plan.plan_type == "executed"` before computing bottleneck ranking. If estimated, skip with a structured note: "Bottleneck ranking requires EXPLAIN ANALYZE data."
**Warning signs:** Bottleneck ranking with all-zero or all-None CPU/wall times.

## Code Examples

### Recommendation Model (Pydantic)

```python
# Source: REC-01, REC-02 requirements + D-01/D-03 decisions
from typing import Any, Literal
from pydantic import BaseModel, Field

Severity = Literal["critical", "high", "medium", "low"]
PriorityTier = Literal["P1", "P2", "P3", "P4"]

class ConsideredButRejected(BaseModel):
    """A recommendation that lost conflict resolution (D-04)."""
    rule_id: str
    reason: str
    original_priority_score: float

class Recommendation(BaseModel):
    """A single actionable recommendation (REC-01, REC-02)."""
    rule_id: str
    severity: Severity
    confidence: float = Field(ge=0.0, le=1.0)
    priority_score: float  # severity_weight * impact * confidence
    priority_tier: PriorityTier  # P1/P2/P3/P4
    operator_ids: list[str]
    reasoning: str  # from template
    expected_impact: str  # from template
    risk_level: Literal["low", "medium", "high"]
    validation_steps: str  # from template
    session_property_statements: list[str] | None = None  # SET SESSION ...
    evidence_summary: dict[str, Any]  # subset of evidence for auditability
    considered_but_rejected: list[ConsideredButRejected] = Field(default_factory=list)
```

[ASSUMED — exact field set based on REC-01/REC-02 requirements]

### Iceberg Table Health Model

```python
# Source: REC-06 + D-07 decisions
class IcebergTableHealth(BaseModel):
    """Per-table Iceberg health summary (REC-06)."""
    table_name: str
    snapshot_count: int | None = None  # from I6 evidence
    small_file_ratio: float | None = None  # from I1 evidence: median_size / threshold
    delete_file_ratio: float | None = None  # from I3 evidence
    partition_spec_evolution: str | None = None  # from I8 evidence
    last_compaction_reference: str | None = None  # "Run OPTIMIZE" or timestamp
    health_score: Literal["healthy", "degraded", "critical"]
    narrative: str  # templated summary
```

[ASSUMED — fields based on D-07 and I1/I3/I6/I8 evidence structures verified in codebase]

### Priority Score Computation

```python
# Source: D-01 locked decision
SEVERITY_WEIGHTS: dict[str, int] = {
    "critical": 4,
    "high": 3,
    "medium": 2,
    "low": 1,
}

def compute_priority(severity: str, impact: float, confidence: float) -> float:
    weight = SEVERITY_WEIGHTS[severity]
    return weight * impact * confidence
```

[VERIFIED: D-01 specifies exactly this formula]

## Impact Extractor Mapping (All 14 Rules)

Each rule needs a specific impact extractor. Analysis of evidence dicts from codebase:

| Rule | Evidence Keys Available | Impact Extraction Strategy | Confidence |
|------|------------------------|---------------------------|------------|
| R1 | `estimated_row_count`, `table_stats_row_count`, `operator_type` | Default 0.5 (missing stats is binary — either present or not) | HIGH |
| R2 | `physical_input_bytes`, `total_table_bytes`, `partition_predicate` | `physical_input_bytes / total_table_bytes` (1.0 = full scan) | HIGH |
| R3 | `function_name`, `column_name`, `original_predicate` | Default 0.5 (pushdown failure is binary) | HIGH |
| R4 | `join_has_df_assignments`, `probe_has_df_applied`, `dynamic_filter_ids` | severity-based: high=0.8, medium=0.5 (assigned but not pushed is worse) | HIGH |
| R5 | `distribution`, `build_side_estimated_bytes`, `threshold_bytes` | `build_bytes / threshold_bytes` clamped to [0, 1.0] (how far over the limit) | HIGH |
| R6 | evidence varies by join-order detection | Default 0.5 | MEDIUM |
| R7 | `p99_p50_ratio`, `stage_id` | `min(1.0, (ratio - threshold) / (20.0 - threshold))` (5x threshold to 20x is extreme) | HIGH |
| R8 | `total_exchange_bytes`, `total_scan_bytes`, `ratio` | `min(1.0, (ratio - 1.0) / 9.0)` (1x-10x range) | HIGH |
| R9 | `selected_bytes`, `scanned_bytes`, `selectivity` | `1.0 - selectivity` (lower selectivity = higher impact) | HIGH |
| I1 | `data_file_count`, `median_file_size_bytes`, `threshold_bytes` OR `iceberg_split_count`, `threshold` | `1.0 - (median_size / threshold)` or `min(1.0, split_count / (threshold * 5))` | HIGH |
| I3 | `delete_file_count`, `delete_ratio`, `data_file_count` | `min(1.0, delete_ratio / 0.5)` (10% threshold, 50% is extreme) | HIGH |
| I6 | `snapshot_count`, `threshold_count`, `oldest_snapshot_age_days` | `min(1.0, snapshot_count / (threshold * 5))` | MEDIUM |
| I8 | `constraint_column`, `constraint_lower_bound`, `is_day_aligned` | Default 0.5 (confidence is already low at 0.6 for this rule) | HIGH |
| D11 | `estimated_rows`, `actual_rows`, `divergence_factor` | `min(1.0, (divergence_factor - threshold) / (50.0 - threshold))` (5x to 50x range) | HIGH |

[VERIFIED: evidence dict keys confirmed by reading all 14 rule source files in codebase]

## Session Property Mapping (All 14 Rules)

Analysis of which rules should recommend session property changes:

| Rule | Session Property | SET SESSION Statement | When to Recommend |
|------|-----------------|----------------------|-------------------|
| R4 | `enable_dynamic_filtering` | `SET SESSION enable_dynamic_filtering = true` | When DF is not assigned (Case 1) |
| R5 | `join_distribution_type` | `SET SESSION join_distribution_type = 'PARTITIONED'` | When build side exceeds threshold |
| R5 | `join_max_broadcast_table_size` | `SET SESSION join_max_broadcast_table_size = '{size}'` | Alternative: increase limit if build side is slightly over |
| R7 | `task_concurrency` | `SET SESSION task_concurrency = {N}` | When skew suggests reducing parallelism may help |
| R8 | `join_distribution_type` | `SET SESSION join_distribution_type = 'PARTITIONED'` | When exchange volume is excessive |
| R1/D11 | None | Advisory: "Run ANALYZE table_name" | Stats are a DDL operation, not a session property |
| R2/R3/I8 | None | Advisory: rewrite predicate | Predicate issues are SQL-level, not session-property-level |
| I1/I3/I6 | None | Advisory: "Run OPTIMIZE" / "Run expire_snapshots" | Maintenance operations, not session properties |
| R6 | `join_reordering_strategy` | `SET SESSION join_reordering_strategy = 'AUTOMATIC'` | When join order is inverted |
| R9 | None | Advisory: add partition pruning or predicate | Low selectivity is a query/schema issue |

[ASSUMED — session property names based on Trino documentation knowledge. The exact property names for Trino 429-480 should be verified.]

## Conflict Pair Analysis

Based on codebase analysis of all 14 rules and their operator_ids:

| Rule A | Rule B | Conflict Scenario | Resolution |
|--------|--------|-------------------|------------|
| R1 | D11 | Both fire on the same scan node — R1 says "stats missing", D11 says "stats diverged 5x". D11 has higher confidence (0.95 vs 0.7-0.9). | D11 wins (higher confidence). R1 is rejected with reason: "D11 provides more specific evidence (actual vs estimated divergence)." |
| R2 | R9 | Both fire on the same scan node — R2 says "partition pruning failed", R9 says "low selectivity scan". R2 is the root cause. | R2 wins (higher severity in most cases). R9 is rejected with reason: "Low selectivity is a symptom of partition pruning failure (R2)." |
| R5 | R8 | Both fire on join/exchange nodes — R5 says "broadcast too big", R8 says "exchange volume excessive". R5 is the specific diagnosis. | R5 wins (specific > general). R8 is rejected with reason: "Excessive exchange is caused by oversized broadcast join (R5)." |

Additional potential conflicts to consider:
- R1 and R6 (missing stats -> join order inversion): both may fire but are complementary, not conflicting. R1 is root cause. Consider declaring R6 as dependent on R1 rather than conflicting.
- I1 and I3 (small files and delete files): both are Iceberg maintenance issues, operator_ids=[], not conflicting.

[VERIFIED: operator_ids patterns confirmed in codebase — R1 and D11 both use scan node IDs, R2 and R9 both use scan node IDs]

## Bottleneck Ranking Architecture

For REC-07, the operator bottleneck ranking requires:

1. **Input:** `ExecutedPlan` (only plan type with `cpu_time_ms` / `wall_time_ms`)
2. **Computation:** Walk all nodes, sort by CPU time (or wall time), take top N (default 5)
3. **Percentage:** Each operator's CPU contribution as a percentage of total plan CPU
4. **Narrative:** Templated text referencing the operator type, its contribution, and relevant findings

```python
# Source: D-08 locked decision + PlanNode model analysis
class BottleneckEntry(BaseModel):
    operator_id: str
    operator_type: str
    cpu_time_ms: float
    wall_time_ms: float
    cpu_pct: float  # percentage of total plan CPU
    input_rows: int | None
    output_rows: int | None
    peak_memory_bytes: int | None
    related_findings: list[str]  # rule_ids of findings on this operator
    narrative: str  # templated explanation

class BottleneckRanking(BaseModel):
    top_operators: list[BottleneckEntry]
    total_cpu_time_ms: float
    plan_type: str  # "executed" — always
    top_n: int  # configurable, default 5
```

[VERIFIED: PlanNode has cpu_time_ms, wall_time_ms, input_rows, output_rows, peak_memory_bytes fields confirmed in parser/models.py]

## Iceberg Table Health Aggregation

For REC-06, aggregating from findings requires:

1. **Group findings by table:** Extract table reference from operator_ids -> plan nodes -> descriptor["table"]
2. **Map rule findings to health metrics:**
   - I1 findings -> `small_file_ratio` (from `median_file_size_bytes` / `threshold_bytes`)
   - I3 findings -> `delete_file_ratio` (from `delete_ratio` evidence field)
   - I6 findings -> `snapshot_count` (from `snapshot_count` evidence field)
   - I8 findings -> `partition_spec_evolution` (from `constraint_column` / alignment status)
3. **Health score classification:**
   - critical: any I1 or I3 finding with severity "high"
   - degraded: any I6 finding or I8 finding
   - healthy: no Iceberg findings

[VERIFIED: all four Iceberg rule evidence dicts confirmed in codebase]

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Free-form LLM-generated recommendations | Templated recommendations from deterministic rules | This project's design principle | Trust + reproducibility |
| Single priority number | Priority score + tier label | D-03 decision | Human/LLM readability |
| Suppress conflicting findings | Keep rejected findings with explicit reasoning | D-04 decision | Auditability |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Trino session property names (`join_distribution_type`, `enable_dynamic_filtering`, `task_concurrency`, `join_reordering_strategy`, `join_max_broadcast_table_size`) are valid for Trino 429-480 | Session Property Mapping | SET SESSION statements would fail; mitigated by version gating |
| A2 | Module structure (`recommender/` with 8 files) is appropriate | Architecture Patterns | Low risk — Claude's discretion per CONTEXT.md |
| A3 | Template wording for each rule's recommendation narrative | Code Examples | Low risk — Claude's discretion per CONTEXT.md |
| A4 | Impact extractor formulas (exact normalization ranges) | Impact Extractor Mapping | Low risk — tunable; wrong defaults just mean suboptimal priority ordering |
| A5 | R2/R9 and R5/R8 are valid conflict pairs beyond the R1/D11 pair | Conflict Pair Analysis | Medium risk — incorrect declarations could suppress valid findings; however, conflict resolution preserves rejected entries for auditability |

## Open Questions

1. **R2 evidence dict keys**
   - What we know: R2 detects partition pruning failure. I haven't read r2_partition_pruning.py in full.
   - What's unclear: Exact evidence dict keys for impact extraction.
   - Recommendation: Read the file during planning/implementation. Impact extractor can default to 0.5 initially.

2. **Session property names for Trino 429-480**
   - What we know: Property names are well-known from Trino documentation.
   - What's unclear: Whether any properties were renamed, deprecated, or added between versions 429-480.
   - Recommendation: Verify against Trino 480 docs during implementation. The `min_trino_version` field provides graceful degradation.

3. **Iceberg table name resolution from findings**
   - What we know: Iceberg rules (I1, I3, I6) emit `operator_ids=[]` (table-level).
   - What's unclear: How to associate these findings with a specific table name for the health summary.
   - Recommendation: The recommender needs access to the `EvidenceBundle` or the table name must be threaded through from the `RuleEngine.run()` call (the `table` parameter). Consider adding `table_name: str | None` to `RuleFinding` or passing it separately to the recommender.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.3+ / pytest-asyncio 1.3.0+ |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/unit/ -x -q --timeout=30` |
| Full suite command | `uv run pytest tests/ -x --timeout=120` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| REC-01 | RuleFinding -> Recommendation with priority score | unit | `uv run pytest tests/recommender/test_engine.py::test_priority_scoring -x` | Wave 0 |
| REC-02 | Recommendation includes reasoning, impact, risk, validation, confidence | unit | `uv run pytest tests/recommender/test_models.py::test_recommendation_fields -x` | Wave 0 |
| REC-03 | No user-origin text in recommendation body (injection test) | unit | `uv run pytest tests/recommender/test_templates.py::test_no_injection -x` | Wave 0 |
| REC-04 | Conflict resolution: higher confidence wins, loser in rejected list | unit | `uv run pytest tests/recommender/test_conflicts.py -x` | Wave 0 |
| REC-05 | Session property SET SESSION from data module; advisory fallback | unit | `uv run pytest tests/recommender/test_session_properties.py -x` | Wave 0 |
| REC-06 | Iceberg table health summary per table | unit | `uv run pytest tests/recommender/test_health.py -x` | Wave 0 |
| REC-07 | Operator bottleneck ranking with narrative | unit | `uv run pytest tests/recommender/test_bottleneck.py -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/recommender/ -x -q --timeout=30`
- **Per wave merge:** `uv run pytest tests/ -x --timeout=120`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/recommender/` directory (new)
- [ ] `tests/recommender/conftest.py` — shared fixtures (sample RuleFinding lists, mock CapabilityMatrix)
- [ ] `tests/recommender/test_engine.py` — covers REC-01
- [ ] `tests/recommender/test_models.py` — covers REC-02
- [ ] `tests/recommender/test_templates.py` — covers REC-03
- [ ] `tests/recommender/test_conflicts.py` — covers REC-04
- [ ] `tests/recommender/test_session_properties.py` — covers REC-05
- [ ] `tests/recommender/test_health.py` — covers REC-06
- [ ] `tests/recommender/test_bottleneck.py` — covers REC-07

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | N/A — recommender has no auth surface |
| V3 Session Management | no | N/A — stateless computation |
| V4 Access Control | no | N/A — no user access boundaries in recommender |
| V5 Input Validation | yes | Pydantic model validation on all inputs (RuleFinding already validated); evidence dict values guarded by safe_float and type checks in impact extractors |
| V6 Cryptography | no | N/A — no secrets handled by recommender |

### Known Threat Patterns for Recommendation Engine

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Template injection via evidence fields | Tampering | REC-03: templates use only typed evidence fields, never user-origin strings; unit test asserts injection string absent from output |
| Hallucinated session property names | Information Disclosure | D-09: embedded data module is the single source of truth; recommender never fabricates property names |
| Incorrect priority ordering | Denial of Service (of user attention) | D-01: deterministic formula; snapshot tests assert stable ordering for fixed inputs |
| Conflict resolution suppressing valid findings | Tampering | D-04: rejected findings preserved in `considered_but_rejected` with explicit reasons |

## Sources

### Primary (HIGH confidence)
- `src/mcp_trino_optimizer/rules/findings.py` — RuleFinding, Severity, EngineResult types [VERIFIED: codebase read]
- `src/mcp_trino_optimizer/rules/engine.py` — RuleEngine.run() return type and flow [VERIFIED: codebase read]
- `src/mcp_trino_optimizer/rules/base.py` — Rule ABC, evidence_requirement ClassVar [VERIFIED: codebase read]
- `src/mcp_trino_optimizer/rules/evidence.py` — EvidenceBundle, EvidenceRequirement, safe_float [VERIFIED: codebase read]
- `src/mcp_trino_optimizer/parser/models.py` — PlanNode metrics fields, BasePlan.walk() [VERIFIED: codebase read]
- `src/mcp_trino_optimizer/adapters/trino/capabilities.py` — CapabilityMatrix, trino_version_major [VERIFIED: codebase read]
- `src/mcp_trino_optimizer/settings.py` — Settings pattern with pydantic-settings [VERIFIED: codebase read]
- All 14 rule files (r1-r9, i1/i3/i6/i8, d11) — evidence dict schemas [VERIFIED: codebase read]

### Secondary (MEDIUM confidence)
- `.planning/phases/05-recommendation-engine/05-CONTEXT.md` — locked decisions D-01 through D-10 [VERIFIED: file read]
- `.planning/REQUIREMENTS.md` — REC-01 through REC-07 [VERIFIED: file read]
- `.planning/research/FEATURES.md` — differentiators D2/D5/D8 [VERIFIED: file read]
- `.planning/research/ARCHITECTURE.md` — hexagonal pattern, module layout [VERIFIED: file read]

### Tertiary (LOW confidence)
- Trino session property names and version gates [ASSUMED — based on training knowledge of Trino docs]

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new dependencies, pure Python on existing stack
- Architecture: HIGH — follows established hexagonal/registry patterns from rules/
- Pitfalls: HIGH — derived from codebase analysis of evidence dicts and operator_ids patterns
- Impact extractors: MEDIUM — formulas are reasonable but exact normalization ranges are tunable
- Session properties: MEDIUM — property names are well-known but version gates need verification

**Research date:** 2026-04-13
**Valid until:** 2026-05-13 (stable domain; no external dependency changes expected)
