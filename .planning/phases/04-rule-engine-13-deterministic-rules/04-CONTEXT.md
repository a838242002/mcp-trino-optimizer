# Phase 4: Rule Engine & 13 Deterministic Rules - Context

**Gathered:** 2026-04-13
**Status:** Ready for planning

<domain>
## Phase Boundary

A plugin registry + execution engine that runs 13 deterministic rules against
`EstimatedPlan` / `ExecutedPlan` objects (from Phase 3), fetches the required
evidence (stats, Iceberg metadata) once per analysis, and returns structured
`RuleFinding | RuleError | RuleSkipped` results. All 13 rules (R1–R9, I1/I3/I6/I8,
D11) are implemented. No recommendation engine, no rewrites, no MCP tool wiring —
those are Phases 5, 6, 8.

</domain>

<decisions>
## Implementation Decisions

### Module Topology
- **D-01 (single `rules/` package):** All rule-engine code lives in
  `src/mcp_trino_optimizer/rules/` — one subpackage, no split:
  - `rules/__init__.py` — public API re-exports
  - `rules/engine.py` — `RuleEngine` class
  - `rules/registry.py` — plugin registry
  - `rules/findings.py` — `RuleFinding`, `RuleError`, `RuleSkipped`, `EngineResult` type alias, `Severity` enum
  - `rules/thresholds.py` — `RuleThresholds(BaseSettings)` with env overrides
  - `rules/r1_missing_stats.py` through `rules/r9_low_selectivity_scan.py`
  - `rules/i1_small_files.py`, `rules/i3_delete_files.py`, `rules/i6_stale_snapshots.py`, `rules/i8_partition_transform.py`
  - `rules/d11_cost_vs_actual.py`
  Phase 8 tools will import findings and call `RuleEngine` from `rules`.

### RuleFinding Type System
- **D-02 (discriminated union):** Three distinct pydantic models with `kind` literal
  discriminator. `EngineResult = RuleFinding | RuleError | RuleSkipped`.
  Engine returns `list[EngineResult]`.

  ```python
  class RuleFinding(BaseModel):
      kind: Literal['finding'] = 'finding'
      rule_id: str
      severity: Severity
      confidence: float          # 0.0–1.0
      message: str
      evidence: dict[str, Any]   # machine-readable; schema is rule-specific
      operator_ids: list[str]    # specific plan node IDs the rule matched

  class RuleError(BaseModel):
      kind: Literal['error'] = 'error'
      rule_id: str
      error_type: str            # e.g. 'ValueError', 'KeyError'
      message: str

  class RuleSkipped(BaseModel):
      kind: Literal['skipped'] = 'skipped'
      rule_id: str
      reason: str                # e.g. 'offline_mode', 'capability_below_minimum'

  EngineResult = RuleFinding | RuleError | RuleSkipped
  ```

- **D-03 (4-tier severity):** `Severity = Literal["critical", "high", "medium", "low"]`
  — no "info" tier. Maps to "must fix / should fix / consider / low priority".

### Threshold Configuration
- **D-04 (standalone `rules/thresholds.py`):** `RuleThresholds(BaseSettings)` with
  `env_prefix='TRINO_RULE_'`. Each threshold carries a citation comment citing the
  source (Trino docs, Iceberg spec, or empirical benchmark). Example:

  ```python
  class RuleThresholds(BaseSettings):
      # R1 / D11: cost-vs-actual divergence
      # Cite: >5× divergence is the threshold used in Trino's own cost-model tests
      stats_divergence_factor: float = 5.0

      # R5: broadcast join size ceiling
      # Cite: Trino default broadcast_max_memory = 100MB
      broadcast_max_bytes: int = 100 * 1024 * 1024

      # R7: CPU/wall skew — p99/p50 ratio
      # Cite: empirical; 5× is the threshold where Trino support flags skew issues
      skew_ratio: float = 5.0

      # R9: scan selectivity floor
      # Cite: Trino perf guide — <10% selectivity = missing partition pruning candidate
      scan_selectivity_threshold: float = 0.10

      # I1: small-file size floor
      # Cite: Iceberg best-practices — target 128MB–512MB; <16MB is small
      small_file_bytes: int = 16 * 1024 * 1024

      model_config = SettingsConfigDict(env_prefix='TRINO_RULE_')
  ```

  CI has a parameterized test proving each threshold is data-driven (a negative-
  control starts or stops triggering when the threshold is changed).

### Evidence Injection
- **D-05 (engine-internal fetch):** `RuleEngine` takes `StatsSource | None` and
  `CatalogSource | None` as constructor arguments plus `RuleThresholds`. Before
  running rules, it collects the union of all declared evidence requirements,
  prefetches the union exactly once, and passes an `EvidenceBundle` to each rule.
  Offline mode is signaled by `stats_source=None` / `catalog_source=None` —
  rules requiring unavailable evidence emit `RuleSkipped`.

  ```python
  class RuleEngine:
      def __init__(
          self,
          stats_source: StatsSource | None,
          catalog_source: CatalogSource | None,
          thresholds: RuleThresholds,
      ) -> None: ...

      async def run(
          self, plan: BasePlan, table: str | None = None
      ) -> list[EngineResult]: ...
  ```

  Isolated exception handling: one crashing rule emits `RuleError` and execution
  continues for all remaining rules.

### Rule Base Class & Registry
- **D-06 (per-requirements):** Each rule is a `Rule` subclass with:
  - `rule_id: ClassVar[str]` — unique identifier (e.g., `"R1"`, `"I3"`)
  - `evidence_requirement: ClassVar[EvidenceRequirement]` — enum value declaring
    what evidence the rule needs (`PLAN_ONLY | PLAN_WITH_METRICS | TABLE_STATS | ICEBERG_METADATA`)
  - `check(plan: BasePlan, evidence: EvidenceBundle) -> list[RuleFinding]` — pure,
    deterministic, sync method; returns empty list if rule does not trigger

  Plugin registry: decorator-based registration (`@registry.register`) or explicit
  `registry.register(RuleClass)` call — planner decides which pattern.

### Claude's Discretion
The planner may make concrete choices on the following without re-asking:
- Whether the registry uses a decorator (`@registry.register`) or an explicit
  call (`registry.register(Rule)`) — either is fine.
- Exact `EvidenceBundle` dataclass fields (what gets fetched for TABLE_STATS vs
  ICEBERG_METADATA — planner should infer from the specific rules' requirements).
- Whether rules are sync or async `check()` methods — sync is preferred (no I/O
  in rule bodies) but async is acceptable if there's a good reason.
- How `BasePlan.walk()` / `find_nodes_by_type()` are used inside individual rules
  — rule authors use the existing API from Phase 3 models.
- Exact structure of the `evidence` dict in `RuleFinding` — rule-specific, just
  must be JSON-serializable and reference the matching `operator_ids`.

</decisions>

<specifics>
## Specific Ideas

- The rule ID naming matches the REQUIREMENTS spec exactly: `R1`–`R9` for general
  rules, `I1`/`I3`/`I6`/`I8` for Iceberg rules, `D11` for the divergence rule.
  These IDs will be referenced by the recommendation engine (Phase 5) and MCP tools
  (Phase 8) — keep them stable.
- ROADMAP.md notes two research-needed items for specific rules:
  - **R2 / I8**: partition-transform semantics per Trino version (Trino issue #19266)
  - **I3**: `$files` cross-reference workaround for Trino issue #28910 (since
    `$partitions` does not expose delete metrics)
  These are not design decisions but implementation research needs — the researcher
  should investigate both before planning rules R2, I3, and I8.

</specifics>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase Requirements
- `.planning/REQUIREMENTS.md` §RUL-01..RUL-21 — the 21 requirements this phase delivers
- `.planning/ROADMAP.md` §Phase 4 — goal, success criteria (5), and research-needed notes

### Project Architecture & Constraints
- `.planning/STATE.md` — Key Decisions 1–16 (non-negotiable; Decision #10 = determinism constraint)
- `.planning/PROJECT.md` — Vision, constraints, "Determinism" constraint
- `.planning/phases/01-skeleton-safety-foundation/01-CONTEXT.md` — D-01 src-layout, D-04 tool auto-registration, D-12 stdout discipline
- `.planning/phases/02-trino-adapter-read-only-gate/02-CONTEXT.md` — D-01 hexagonal ports layout, D-22 docker-compose stack
- `.planning/phases/03-plan-parser-normalizer/03-CONTEXT.md` — D-01 EstimatedPlan/ExecutedPlan types, D-03 BasePlan base class

### Existing Code (Integration Points)
- `src/mcp_trino_optimizer/parser/models.py` — `PlanNode`, `BasePlan`, `EstimatedPlan`, `ExecutedPlan`, traversal methods
- `src/mcp_trino_optimizer/ports/plan_source.py` — `PlanSource` Protocol
- `src/mcp_trino_optimizer/ports/stats_source.py` — `StatsSource` Protocol (evidence for TABLE_STATS rules)
- `src/mcp_trino_optimizer/ports/catalog_source.py` — `CatalogSource` Protocol (evidence for ICEBERG_METADATA rules)
- `src/mcp_trino_optimizer/settings.py` — existing `Settings(BaseSettings)` class (pattern for `RuleThresholds`)

### Research Corpus
- `.planning/research/SUMMARY.md` §4.4 — Rule engine design patterns
- `.planning/research/ARCHITECTURE.md` — hexagonal ports overview; rule engine placement
- `.planning/research/PITFALLS.md` — determinism pitfalls, evidence prefetch design

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `BasePlan.walk()` — DFS traversal already available; rules use this to iterate all nodes
- `BasePlan.find_nodes_by_type(operator_type)` — find nodes by operator name; rules use this for targeted lookup
- `PlanNode.operator_type` — alias for `.name`; use consistently in rule bodies
- `PlanNode` runtime fields — `cpu_time_ms`, `wall_time_ms`, `input_rows`, `input_bytes`, `output_rows`, `output_bytes`, `peak_memory_bytes`, `iceberg_split_count`, `iceberg_file_count`, `iceberg_partition_spec_id` — all rules read from here
- `PlanNode.raw` — `model_extra` dict bag for version-specific fields not yet typed

### Established Patterns
- Pydantic v2 `BaseModel` with `ConfigDict(extra='allow')` for domain types (from Phase 3)
- `pydantic-settings BaseSettings` with `env_prefix` for config (see `settings.py`)
- Protocol-based ports (structural subtyping via `@runtime_checkable`) — rule engine should treat `StatsSource`/`CatalogSource` as ports, not concrete classes
- `anyio.to_thread.run_sync` for bridging sync calls in async context (already used by adapter)

### Integration Points
- `RuleEngine` will be instantiated by Phase 8 MCP tool handlers, passing the live port adapters from Phase 2
- `OfflinePlanSource` mode → `stats_source=None`, `catalog_source=None` → rules requiring those evidence types emit `RuleSkipped`
- Phase 5 recommendation engine consumes `list[EngineResult]` from `RuleEngine.run()` — keep the output type stable

</code_context>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 04-rule-engine-13-deterministic-rules*
*Context gathered: 2026-04-13*
