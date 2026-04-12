# Phase 5: Recommendation Engine - Context

**Gathered:** 2026-04-13
**Status:** Ready for planning

<domain>
## Phase Boundary

Turn raw `RuleFinding` objects (from Phase 4's rule engine) into prioritized, actionable `Recommendation` objects. This phase delivers: priority scoring, conflict resolution for overlapping rules, audited narrative templates keyed by rule_id, session-property grounding, an Iceberg table health summary per scanned table, and an operator-level bottleneck ranking. No MCP tool wiring (Phase 8), no SQL rewrites (Phase 6), no comparison (Phase 7).

</domain>

<decisions>
## Implementation Decisions

### Priority Scoring Formula
- **D-01:** Priority = severity_weight x impact_score x confidence. Severity maps to numeric weights: critical=4, high=3, medium=2, low=1. Confidence is the existing 0-1.0 float from RuleFinding.
- **D-02:** Impact is derived per-rule via an evidence-based heuristic. Each rule declares an `impact_extractor` that pulls a 0-1.0 score from its evidence dict (e.g., bytes_wasted / total_bytes for R8, selectivity ratio for R9). Rules without quantifiable evidence default to 0.5.
- **D-03:** Output exposes both a raw float priority score (for sorting) and a tier label (P1/P2/P3/P4) for human/LLM readability. Tier thresholds are configurable.

### Conflict Resolution
- **D-04:** Conflict winner is determined by confidence-first. On confidence tie, higher severity wins. The loser is kept as a `considered_but_rejected` entry with an explicit reason. Matches REC-04 requirement.
- **D-05:** Conflict detection uses declared conflict pairs. Each rule declares a list of `rule_ids` it can conflict with (e.g., R1 conflicts_with D11 on the same operator). Only declared pairs on the same operator_id trigger conflict resolution. No heuristic same-operator matching.

### Template Design
- **D-06:** Recommendation narratives use Python string templates (str.format) stored as constants in a templates module, keyed by rule_id. No Jinja dependency for this phase. Simple, type-safe, auditable.
- **D-07:** Iceberg table health summary (REC-06) uses a dedicated `IcebergTableHealth` pydantic model that aggregates data from I1/I3/I6/I8 findings, with a Python template rendering it into a concise per-table summary.
- **D-08:** Operator bottleneck ranking (REC-07) defaults to top 5 operators ranked by wall-time or CPU-time contribution. The N is configurable via settings.

### Session Property Source
- **D-09:** Session property names come from an embedded Python data module (`session_properties.py`) with a dict of property names, descriptions, valid ranges, and Trino version gates. Phase 8 will wrap this same data as the `trino_session_properties` MCP resource — single source of truth from day one.
- **D-10:** Each session property entry includes `min_trino_version`. The recommender checks against the capability matrix (from Phase 2's version probe) and emits advisory-only if the connected Trino is too old. Prevents recommending SET SESSION for properties that don't exist on the target cluster.

### Claude's Discretion
- Tie-breaking logic beyond confidence-then-severity (e.g., alphabetical rule_id as final tiebreaker)
- Exact tier threshold values for P1/P2/P3/P4 (sensible defaults, configurable)
- Internal module structure within the recommender package
- Template wording for each rule_id's recommendation narrative

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Rule Engine (input contract)
- `src/mcp_trino_optimizer/rules/findings.py` -- Defines `RuleFinding`, `RuleError`, `RuleSkipped`, `Severity`, `EngineResult`
- `src/mcp_trino_optimizer/rules/engine.py` -- `RuleEngine.run()` returns `list[EngineResult]`; this is the input to the recommender
- `src/mcp_trino_optimizer/rules/registry.py` -- `RuleRegistry` pattern; recommender may need a similar registry for impact extractors

### Existing Architecture
- `src/mcp_trino_optimizer/ports/` -- Port ABCs (`PlanSource`, `StatsSource`, `CatalogSource`); recommender should follow the same hexagonal pattern
- `src/mcp_trino_optimizer/adapters/trino/client.py` -- Trino capability matrix (version probe) used for session-property version gating
- `src/mcp_trino_optimizer/config.py` -- `pydantic-settings` configuration; add recommender settings here

### Requirements
- `.planning/REQUIREMENTS.md` -- REC-01 through REC-07 define the acceptance criteria
- `.planning/ROADMAP.md` -- Phase 5 success criteria (5 testable assertions)

### Research
- `.planning/research/FEATURES.md` -- Differentiators D2 (session properties), D5 (table health), D8 (bottleneck ranking)
- `.planning/research/ARCHITECTURE.md` -- Ports-and-adapters design, rule engine architecture

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `RuleFinding` model (findings.py): severity, confidence, evidence dict, operator_ids -- direct input to recommender
- `Severity` literal type: `"critical" | "high" | "medium" | "low"` -- reuse for recommendation severity
- `RuleRegistry` pattern: decorator-based registration -- consider similar pattern for impact extractors or conflict declarations
- `pydantic-settings` config pattern in `config.py` -- extend with recommender settings (top_n_bottleneck, tier_thresholds)

### Established Patterns
- Hexagonal ports-and-adapters: all business logic behind port ABCs, adapters are swappable
- Pydantic models for all structured data: findings, plan nodes, config
- Rule isolation: one rule crashing doesn't abort the engine -- recommender should similarly isolate per-finding processing
- `EngineResult` discriminated union (kind field): consider similar pattern for recommendation output types

### Integration Points
- `RuleEngine.run()` output feeds directly into recommender input
- Trino capability matrix (version info) needed for session-property version gating (D-10)
- Phase 8 will wrap `session_properties.py` data module as an MCP resource
- Phase 8's `suggest_optimizations` tool will call the recommender service

</code_context>

<specifics>
## Specific Ideas

No specific requirements -- open to standard approaches within the decisions above.

</specifics>

<deferred>
## Deferred Ideas

None -- discussion stayed within phase scope.

</deferred>

---

*Phase: 05-recommendation-engine*
*Context gathered: 2026-04-13*
