---
phase: 04-rule-engine-13-deterministic-rules
plan: "01"
subsystem: rules
tags: [rule-engine, findings, evidence, registry, thresholds, walk-fix]
dependency_graph:
  requires:
    - 03-plan-parser-normalizer  # BasePlan, PlanNode, EstimatedPlan, ExecutedPlan
    - 02-trino-adapter-read-only-gate  # StatsSource, CatalogSource ports
  provides:
    - rules/__init__.py  # public API
    - rules/findings.py  # RuleFinding, RuleError, RuleSkipped, EngineResult, Severity
    - rules/evidence.py  # EvidenceRequirement, EvidenceBundle, safe_float
    - rules/base.py  # Rule ABC
    - rules/registry.py  # RuleRegistry + registry singleton
    - rules/thresholds.py  # RuleThresholds(BaseSettings)
    - rules/engine.py  # RuleEngine async execution loop
  affects:
    - 04-02-rules-wave-2  # consumes Rule ABC, EvidenceBundle, registry singleton
    - 04-03-rules-wave-3  # same
    - 04-04-rules-wave-4  # same
    - 05-recommendation-engine  # consumes list[EngineResult]
    - 08-mcp-tool-wiring  # instantiates RuleEngine with live port adapters
tech_stack:
  added: []
  patterns:
    - pydantic v2 discriminated union with kind literal discriminator (EngineResult)
    - pydantic-settings BaseSettings with env_prefix for threshold config
    - Rule ABC with ClassVar[str] rule_id + ClassVar[EvidenceRequirement]
    - async RuleEngine with sync-only rule.check() + per-rule crash isolation
key_files:
  created:
    - src/mcp_trino_optimizer/rules/__init__.py
    - src/mcp_trino_optimizer/rules/findings.py
    - src/mcp_trino_optimizer/rules/evidence.py
    - src/mcp_trino_optimizer/rules/base.py
    - src/mcp_trino_optimizer/rules/registry.py
    - src/mcp_trino_optimizer/rules/thresholds.py
    - src/mcp_trino_optimizer/rules/engine.py
    - tests/unit/__init__.py
    - tests/unit/test_parser_walk.py
    - tests/rules/__init__.py
    - tests/rules/test_findings.py
    - tests/rules/test_registry.py
    - tests/rules/test_engine.py
    - tests/rules/test_engine_isolation.py
    - tests/rules/test_thresholds.py
    - tests/rules/test_r1_missing_stats.py
    - tests/rules/test_r2_partition_pruning.py
    - tests/rules/test_r3_predicate_pushdown.py
    - tests/rules/test_r4_dynamic_filtering.py
    - tests/rules/test_r5_broadcast_join.py
    - tests/rules/test_r6_join_order.py
    - tests/rules/test_r7_skew.py
    - tests/rules/test_r8_exchange.py
    - tests/rules/test_r9_low_selectivity.py
    - tests/rules/test_i1_small_files.py
    - tests/rules/test_i3_delete_files.py
    - tests/rules/test_i6_stale_snapshots.py
    - tests/rules/test_i8_partition_transform.py
    - tests/rules/test_d11_cost_vs_actual.py
  modified:
    - src/mcp_trino_optimizer/parser/models.py  # WR-01 comment added to walk()
decisions:
  - "D-02: RuleFinding/RuleError/RuleSkipped as pydantic discriminated union with kind literal"
  - "D-03: Severity = Literal['critical','high','medium','low'] — no info tier"
  - "D-04: RuleThresholds(BaseSettings) with env_prefix='TRINO_RULE_' and citation comments"
  - "D-05: RuleEngine prefetches evidence once before running all rules; None source = RuleSkipped"
  - "D-06: Rule ABC with ClassVar rule_id + evidence_requirement; sync check() returns list[RuleFinding]"
  - "T-04-03: table_str capped at 1000 chars before regex; re.match with anchored patterns"
metrics:
  duration_minutes: 35
  completed_date: "2026-04-12"
  tasks_completed: 2
  tasks_total: 2
  files_created: 29
  files_modified: 1
---

# Phase 4 Plan 1: Rule Infrastructure Summary

**One-liner:** Rule engine infrastructure with pydantic discriminated-union findings, EvidenceRequirement enum, RuleThresholds(BaseSettings), RuleRegistry decorator pattern, and async RuleEngine with prefetch-once + crash isolation.

## Walk() WR-01 Fix Confirmed

`BasePlan.walk()` in `src/mcp_trino_optimizer/parser/models.py` was already using `stack.pop()` (O(1)) at execution start. The WR-01 comment was added to document the fix:

```python
node = stack.pop()  # WR-01 fix: pop() from right end is O(1); pop(0) was O(n)
```

Verified by `tests/unit/test_parser_walk.py`:
- DFS pre-order: root -> A -> C -> B (4-node tree)
- 100-node chain: all 100 nodes returned in correct order

## Infrastructure Contract

### RuleFinding fields
```python
class RuleFinding(BaseModel):
    kind: Literal["finding"] = "finding"
    rule_id: str
    severity: Severity  # Literal["critical", "high", "medium", "low"]
    confidence: float   # Field(ge=0.0, le=1.0)
    message: str
    evidence: dict[str, Any]
    operator_ids: list[str]
```

### EvidenceBundle fields
```python
@dataclass
class EvidenceBundle:
    plan: BasePlan
    table_stats: dict[str, Any] | None = None
    iceberg_snapshots: list[dict[str, Any]] | None = None
    iceberg_files: list[dict[str, Any]] | None = None
```

### RuleEngine constructor signature
```python
class RuleEngine:
    def __init__(
        self,
        stats_source: StatsSource | None,
        catalog_source: CatalogSource | None,
        thresholds: RuleThresholds | None = None,
        registry: RuleRegistry | None = None,
    ) -> None: ...

    async def run(
        self, plan: BasePlan, table: str | None = None
    ) -> list[EngineResult]: ...
```

## Test Results

```
uv run pytest tests/rules/ tests/unit/test_parser_walk.py -x -q
30 passed, 14 skipped in 0.08s

uv run mypy src/mcp_trino_optimizer/rules/ --strict
Success: no issues found in 7 source files

uv run ruff check src/mcp_trino_optimizer/rules/ src/mcp_trino_optimizer/parser/models.py
All checks passed!
```

## Commits

| Hash | Message |
|------|---------|
| e8faa4b | feat(04-01): walk() WR-01 comment + test stubs for rules subpackage |
| 01d86ad | feat(04-01): implement rule engine infrastructure |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] walk() was already correct at execution start**
- **Found during:** Task 1
- **Issue:** The plan said to change `stack.pop(0)` to `stack.pop()`, but the existing code already used `stack.pop()`. A previous CI fix (commit 0a3a470 lineage) had already landed the correct implementation.
- **Fix:** Added the WR-01 comment only; no logic change needed.
- **Files modified:** src/mcp_trino_optimizer/parser/models.py

**2. [Rule 1 - Bug] ruff RUF003 ambiguous Unicode in citation comments**
- **Found during:** Task 2 ruff check
- **Issue:** Unicode multiplication sign (×) and en-dash (–) in citation comments triggered RUF003.
- **Fix:** Replaced × with x and – with - in three comment lines in thresholds.py.
- **Files modified:** src/mcp_trino_optimizer/rules/thresholds.py

**3. [Rule 2 - Missing] ruff auto-fix applied for import ordering, unused imports, unsorted __all__**
- **Found during:** Task 2 ruff check
- **Issue:** F401 unused import (ExecutedPlan in TYPE_CHECKING block of engine.py), I001 import order (evidence.py), RUF022 unsorted __all__ (3 files), RUF100 unused noqa directive.
- **Fix:** `ruff check --fix` applied 7 automatic fixes.
- **Files modified:** rules/__init__.py, rules/findings.py, rules/evidence.py, rules/engine.py

## Known Stubs

14 rule test stubs with `pytest.mark.skip` markers exist in tests/rules/:
- Wave 2: test_r1_missing_stats.py, test_r2_partition_pruning.py, test_r3_predicate_pushdown.py, test_r4_dynamic_filtering.py
- Wave 3: test_r5_broadcast_join.py, test_r6_join_order.py, test_r7_skew.py, test_r8_exchange.py, test_r9_low_selectivity.py, test_d11_cost_vs_actual.py
- Wave 4: test_i1_small_files.py, test_i3_delete_files.py, test_i6_stale_snapshots.py, test_i8_partition_transform.py

These are intentional — plan 04-01's goal is to create the stubs for Wave 2-4 rule implementations. They will be un-skipped in plans 04-02 through 04-04.

## Self-Check: PASSED

Files exist:
- src/mcp_trino_optimizer/rules/__init__.py: FOUND
- src/mcp_trino_optimizer/rules/findings.py: FOUND
- src/mcp_trino_optimizer/rules/evidence.py: FOUND
- src/mcp_trino_optimizer/rules/base.py: FOUND
- src/mcp_trino_optimizer/rules/registry.py: FOUND
- src/mcp_trino_optimizer/rules/thresholds.py: FOUND
- src/mcp_trino_optimizer/rules/engine.py: FOUND
- tests/unit/test_parser_walk.py: FOUND
- tests/rules/ (19 files): FOUND

Commits exist:
- e8faa4b: FOUND
- 01d86ad: FOUND
