---
phase: "05"
plan: "03"
subsystem: recommender
tags: [health, bottleneck, integration, iceberg, pipeline]
dependency_graph:
  requires: [recommender.models, recommender.scoring, recommender.impact, recommender.conflicts, recommender.templates, recommender.engine, rules.findings, parser.models, settings.Settings]
  provides: [recommender.health.aggregate_iceberg_health, recommender.bottleneck.rank_bottlenecks]
  affects: [recommender.engine.RecommendationEngine, recommender.__init__]
tech_stack:
  added: []
  patterns: [table-grouped-health-aggregation, cpu-percentage-bottleneck-ranking, executed-plan-gate]
key_files:
  created:
    - src/mcp_trino_optimizer/recommender/health.py
    - src/mcp_trino_optimizer/recommender/bottleneck.py
    - tests/recommender/test_health.py
    - tests/recommender/test_bottleneck.py
    - tests/recommender/test_engine_integration.py
  modified:
    - src/mcp_trino_optimizer/recommender/engine.py
    - src/mcp_trino_optimizer/recommender/__init__.py
decisions:
  - "Iceberg findings without table_name in evidence fall back to 'unknown_table' since rules do not currently include table_name in evidence dicts"
  - "Bottleneck ranking returns None (not empty) for EstimatedPlan or all-None CPU -- callers check for None"
  - "Health score classification: I1/I3 with severity high/critical -> critical; any Iceberg finding -> degraded"
metrics:
  duration: "7m 23s"
  completed: "2026-04-12T20:22:13Z"
  tasks_completed: 2
  tasks_total: 2
  tests_added: 27
  files_created: 5
  files_modified: 2
---

# Phase 5 Plan 3: Health, Bottleneck, and Integration Summary

Iceberg table health aggregator groups I1/I3/I6/I8 findings per table with critical/degraded classification; operator bottleneck ranker walks ExecutedPlan for top-N CPU consumers; full pipeline integration test validates complete EngineResult to RecommendationReport flow.

## Task Results

| Task | Name | Commit | Tests | Status |
|------|------|--------|-------|--------|
| 1 | Iceberg table health aggregator | `cb394a2` | 12 | PASS |
| 2 | Bottleneck ranking + engine integration + full pipeline | `6abbacf` | 15 | PASS |

## Implementation Details

### Health Aggregation (health.py)
- `ICEBERG_RULES = {"I1", "I3", "I6", "I8"}` constant for filtering
- `aggregate_iceberg_health(findings)` groups by table_name from evidence, falls back to "unknown_table"
- Health score classification: I1/I3 severity high/critical -> "critical"; any Iceberg finding -> "degraded"
- I1 -> small_file_ratio computed from median_file_size_bytes / threshold_bytes
- I3 -> delete_file_ratio from evidence delete_ratio
- I6 -> snapshot_count from evidence
- I8 -> partition_spec_evolution from constraint_column + alignment info
- Compaction references: optimize for I1/I3, expire_snapshots for I6
- Templated narrative uses only structured fields (T-05-07), never RuleFinding.message

### Bottleneck Ranking (bottleneck.py)
- `rank_bottlenecks(plan, findings, top_n=5)` walks ExecutedPlan once (O(n))
- Returns None for EstimatedPlan (isinstance check, Pitfall 5)
- Returns None when no nodes have cpu_time_ms or total_cpu == 0
- Computes cpu_pct = (node.cpu_time_ms / total_cpu) * 100
- Associates related_findings by matching node.id in finding.operator_ids
- Narrative uses only PlanNode typed fields (T-05-09)
- top_n bounded by settings (max 50, T-05-08)

### Engine Integration (engine.py updates)
- RecommendationEngine.__init__ accepts optional `plan: BasePlan | None` parameter
- recommend() calls aggregate_iceberg_health(findings) after building recommendations
- recommend() calls rank_bottlenecks(plan, findings, top_n) when plan is provided
- RecommendationReport now fully populated with iceberg_health and bottleneck_ranking

### Full Pipeline Integration Test
- Mixed EngineResult list: R1, D11, R5, I1, I3 findings + RuleError + RuleSkipped
- Validates: recommendations sorted by priority_score descending
- Validates: R1/D11 conflict resolved (D11 wins, R1 in considered_but_rejected)
- Validates: iceberg_health populated with critical health score
- Validates: bottleneck_ranking populated from ExecutedPlan
- Validates: errors and skips filtered out (T-05-06)

## Decisions Made

1. **Table name fallback**: Iceberg rules (I1/I3/I6/I8) do not currently store `table_name` in their evidence dicts. The health aggregator extracts `table_name` from evidence when present and falls back to `"unknown_table"` otherwise. This is forward-compatible -- if rules add table_name to evidence in the future, it will be picked up automatically.
2. **None vs empty for bottleneck**: `rank_bottlenecks` returns `None` (not an empty BottleneckRanking) when the plan is not ExecutedPlan or has no CPU metrics. Callers check `report.bottleneck_ranking is not None`.
3. **Health score thresholds**: I1/I3 with severity "high" or "critical" produce health_score="critical". All other Iceberg findings produce "degraded". This matches the plan's specified classification.

## Deviations from Plan

None -- plan executed exactly as written.

## Verification

```
tests/recommender/test_health.py: 12 passed
tests/recommender/test_bottleneck.py: 8 passed
tests/recommender/test_engine_integration.py: 7 passed
Total recommender suite: 173 passed
Full test suite: 732 passed, 33 skipped
Lint: All checks passed (ruff)
```

## Known Stubs

None -- all modules are fully implemented with real logic.

## Threat Flags

None -- no new security surface beyond what the plan's threat model covers (T-05-07, T-05-08, T-05-09 all mitigated).

## Self-Check: PASSED

- All 5 created files verified present on disk
- Both commits (cb394a2, 6abbacf) verified in git log
- 173 recommender tests passing, 732 total tests passing, lint clean
