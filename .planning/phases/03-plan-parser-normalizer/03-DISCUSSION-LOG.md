# Phase 3: Plan Parser & Normalizer - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-12
**Phase:** 03-plan-parser-normalizer
**Areas discussed:** Parser output hierarchy, Version-drift tolerance, Fixture capture strategy, Normalization scope

---

## Parser Output Hierarchy

### ExplainPlan relationship

| Option | Description | Selected |
|--------|-------------|----------|
| Replace ExplainPlan entirely | Phase 3 introduces EstimatedPlan and ExecutedPlan as the new domain types. ExplainPlan is removed from ports. Clean break. | ✓ |
| Inherit from ExplainPlan | EstimatedPlan(ExplainPlan) and ExecutedPlan(ExplainPlan) extend the base. Existing code still works. | |
| You decide | Claude picks whichever produces the cleanest API. | |

**User's choice:** Replace ExplainPlan entirely
**Notes:** User asked for explanation of EstimatedPlan/ExecutedPlan vs ExplainPlan and ports/plan_source.py relationship. Explanation provided covering: ExplainPlan is a thin Phase 2 placeholder; EstimatedPlan has typed tree from EXPLAIN; ExecutedPlan adds runtime metrics from EXPLAIN ANALYZE.

### Model location

| Option | Description | Selected |
|--------|-------------|----------|
| New parser/ subpackage | src/mcp_trino_optimizer/parser/ with models.py, parser.py, normalizer.py. Keeps parsing separate from ports and adapters. | ✓ |
| Under ports/ | Extend ports/plan_source.py with the full model hierarchy. | |
| You decide | Claude picks the cleanest module layout. | |

**User's choice:** New parser/ subpackage

### Raw dict bag approach

| Option | Description | Selected |
|--------|-------------|----------|
| Pydantic model with model_extra | Use ConfigDict(extra='allow'). Known fields are typed; unknown land in model_extra. No duplication. | ✓ |
| Explicit raw: dict field | Every PlanNode has raw: dict holding ALL original fields. Typed fields extracted separately. Duplication but explicit. | |
| You decide | Claude picks for rule engine downstream needs. | |

**User's choice:** Pydantic model with model_extra

### PlanNode tree structure

| Option | Description | Selected |
|--------|-------------|----------|
| Generic PlanNode + operator_type field | One PlanNode model with operator_type: str. Rules match on strings. Tolerates unknown operators. | ✓ |
| Subclasses per operator type | Base PlanNode with subclasses: TableScanNode, JoinNode, etc. More type safety but brittle. | |
| You decide | Claude picks for rule engine pattern-matching needs. | |

**User's choice:** Generic PlanNode + operator_type field

---

## Version-Drift Tolerance

### Schema drift surfacing

| Option | Description | Selected |
|--------|-------------|----------|
| Field on the plan result | Plan carries schema_drift_warnings: list[SchemaDriftWarning]. Programmatic inspection + structlog. | ✓ |
| Structured log only | Warnings via structlog events. Not on the plan object. | |
| You decide | Claude picks for rule signal needs. | |

**User's choice:** Field on the plan result

### Parsing strictness

| Option | Description | Selected |
|--------|-------------|----------|
| Lenient with warnings | Parse what we can, record drift warnings, never raise. Maximizes compatibility. | ✓ |
| Strict on structure, lenient on fields | Top-level must match or raise. Individual fields are lenient. | |
| You decide | Claude picks the right balance. | |

**User's choice:** Lenient with warnings

### Version count

| Option | Description | Selected |
|--------|-------------|----------|
| Start with exactly 3 | 429, middle (~450-460), 480+. Add more when real drift discovered. | ✓ |
| 5 versions for broader coverage | 429, ~440, ~455, ~470, 480+. More fixtures to maintain. | |
| You decide | Claude picks coverage vs maintenance balance. | |

**User's choice:** Start with exactly 3

---

## Fixture Capture Strategy

### Capture method

| Option | Description | Selected |
|--------|-------------|----------|
| Live capture from docker-compose | Run real queries against Phase 2 Trino stack. Swap image tag for multi-version. Authentic output. | ✓ |
| Hand-crafted synthetic JSON | Manually construct fixtures. No docker dependency. Risk of inaccuracy. | |
| You decide | Claude picks for fixture fidelity. | |

**User's choice:** Live capture from docker-compose

### Fixture location

| Option | Description | Selected |
|--------|-------------|----------|
| tests/fixtures/explain/ | tests/fixtures/explain/{version}/{query_name}.json. Co-located with tests. | ✓ |
| src/mcp_trino_optimizer/parser/fixtures/ | Ship inside package. Accessible at runtime. Larger package. | |
| You decide | Claude picks most practical location. | |

**User's choice:** tests/fixtures/explain/

### Snapshot strategy

| Option | Description | Selected |
|--------|-------------|----------|
| Snapshot the parsed output | Parse fixtures through parser, snapshot EstimatedPlan/ExecutedPlan. Drift shows as diff. | ✓ |
| Snapshot the raw JSON | Snapshot raw fixture files. Detects fixture edits, not parsing correctness. | |
| You decide | Claude picks for max CI value. | |

**User's choice:** Snapshot the parsed output

---

## Normalization Scope

### Normalization approach

| Option | Description | Selected |
|--------|-------------|----------|
| In-place normalization | Parser normalizes as it builds. Consumers always see canonical form. One tree. | ✓ |
| Separate normalized view | Raw tree + second normalized tree. More flexible, more complex. | |
| You decide | Claude picks for cleanest rule interface. | |

**User's choice:** In-place normalization

### Iceberg extraction depth

| Option | Description | Selected |
|--------|-------------|----------|
| PLN-04 minimum: split count, file count, partition spec ID | Exactly what requirements specify. More added when Phase 4 rules need it. | ✓ |
| Extract all available Iceberg metadata | Parse every Iceberg-specific field. More upfront, risk over-engineering. | |
| You decide | Claude picks based on Phase 4 rule needs. | |

**User's choice:** PLN-04 minimum

### Additional normalizations

| Option | Description | Selected |
|--------|-------------|----------|
| Just PLN-05: ScanFilterProject + Project | Only what requirements specify. Other quirks handled per-rule in Phase 4. | ✓ |
| Add Exchange normalization | Also normalize Exchange variants. Useful for Phase 4 rules R7/R8. | |
| You decide | Claude picks based on Phase 4 needs. | |

**User's choice:** Just PLN-05

---

## Claude's Discretion

- Exact pydantic model field names/types for PlanNode common fields
- Whether EstimatedPlan/ExecutedPlan share a common base class
- Plan type detection heuristic from JSON content
- IcebergTableScan detail string parsing approach
- Query selection for fixture capture
- Syrupy snapshot configuration
- Tree-walking utility method signatures

## Deferred Ideas

- Exchange normalization — Phase 4 per-rule
- Additional Iceberg metadata extraction — Phase 4 when needed
- Additional Trino fixture versions — when drift discovered
- Distributed plan typed parsing — deferred unless Phase 4 rules need it
