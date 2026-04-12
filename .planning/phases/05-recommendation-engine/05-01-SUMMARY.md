---
phase: "05"
plan: "01"
subsystem: recommender
tags: [models, scoring, impact, pydantic, deterministic]
dependency_graph:
  requires: [rules.findings.RuleFinding, rules.findings.Severity, rules.evidence.safe_float, settings.Settings]
  provides: [recommender.models.Recommendation, recommender.models.RecommendationReport, recommender.scoring.compute_priority, recommender.scoring.assign_tier, recommender.impact.get_impact]
  affects: [settings.Settings]
tech_stack:
  added: []
  patterns: [impact-extractor-registry, decorator-based-registration, safe-float-guards]
key_files:
  created:
    - src/mcp_trino_optimizer/recommender/__init__.py
    - src/mcp_trino_optimizer/recommender/models.py
    - src/mcp_trino_optimizer/recommender/scoring.py
    - src/mcp_trino_optimizer/recommender/impact.py
    - tests/recommender/__init__.py
    - tests/recommender/conftest.py
    - tests/recommender/test_models.py
    - tests/recommender/test_scoring.py
    - tests/recommender/test_impact.py
  modified:
    - src/mcp_trino_optimizer/settings.py
decisions:
  - "Impact extractors use actual evidence keys from rule source files (skew_ratio not p99_p50_ratio)"
  - "R2 defaults to 0.5 since rule evidence lacks byte-level scan metrics"
  - "R4 fixed at 0.7 impact since DF failure is consistently high-impact but not measurable from evidence"
metrics:
  duration: "6m 14s"
  completed: "2026-04-12T19:58:06Z"
  tasks_completed: 2
  tasks_total: 2
  tests_added: 79
  files_created: 9
  files_modified: 1
---

# Phase 5 Plan 1: Models, Scoring, and Impact Summary

Recommendation engine foundation: pydantic models, deterministic priority scoring formula (severity_weight x impact x confidence), and 14 per-rule impact extractors with safe numeric handling.

## Task Results

| Task | Name | Commit | Tests | Status |
|------|------|--------|-------|--------|
| 1 | Recommendation models + scoring + settings extension | `48f6786` | 30 | PASS |
| 2 | Impact extractor registry with per-rule extractors | `7d85afa` | 49 | PASS |

## Implementation Details

### Models (models.py)
- `PriorityTier = Literal["P1", "P2", "P3", "P4"]`
- `RiskLevel = Literal["low", "medium", "high"]`
- `HealthScore = Literal["healthy", "degraded", "critical"]`
- `ConsideredButRejected`: rule_id, reason, original_priority_score
- `Recommendation`: full recommendation with priority_score, priority_tier, reasoning, evidence_summary
- `IcebergTableHealth`: per-table health from I1/I3/I6/I8 findings
- `BottleneckEntry`/`BottleneckRanking`: operator-level CPU bottleneck analysis
- `RecommendationReport`: top-level aggregation of all outputs

### Scoring (scoring.py)
- `SEVERITY_WEIGHTS`: critical=4, high=3, medium=2, low=1
- `compute_priority(severity, impact, confidence)`: deterministic D-01 formula
- `assign_tier(score, thresholds)`: configurable P1/P2/P3/P4 classification (D-03)

### Impact Extractors (impact.py)
- Registry pattern with `@register_impact` decorator
- 14 extractors registered, one per rule
- Binary/default extractors: R1, R2, R3, R6, I8 (DEFAULT_IMPACT=0.5)
- Fixed high impact: R4 (0.7)
- Ratio-based: R5 (build/threshold), R7 (skew 5x-20x), R8 (exchange 1x-10x), R9 (1-selectivity)
- Iceberg-specific: I1 (file size), I3 (delete ratio), I6 (snapshot count)
- Divergence-based: D11 (5x-50x range)
- All extractors use safe_float() for NaN/None protection (T-05-01)
- get_impact() clamps result to [0.0, 1.0]

### Settings Extension
- `recommender_tier_p1/p2/p3`: configurable tier thresholds (env: MCPTO_RECOMMENDER_TIER_P1/P2/P3)
- `recommender_top_n_bottleneck`: top-N operators for bottleneck ranking (D-08)

## Decisions Made

1. **Evidence key alignment**: Used actual evidence dict keys from rule source files (e.g., `skew_ratio` from R7, `selectivity_ratio` from R9, `delete_ratio` from I3) rather than the plan's placeholder names.
2. **R2 impact defaults to 0.5**: The rule's evidence dict contains filter_predicate and table but no byte-level scan metrics, so impact cannot be quantified.
3. **R4 fixed at 0.7**: Dynamic filtering failures consistently cause significant extra I/O, but the exact waste is not measurable from plan evidence alone.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Corrected evidence key names in impact extractors**
- **Found during:** Task 2
- **Issue:** Plan specified `p99_p50_ratio` for R7 but actual evidence key is `skew_ratio`; plan specified `selectivity` for R9 but actual key is `selectivity_ratio`
- **Fix:** Read all 14 rule source files and used actual evidence dict keys
- **Files modified:** src/mcp_trino_optimizer/recommender/impact.py
- **Commit:** 7d85afa

## Verification

```
tests/recommender/test_models.py: 18 passed
tests/recommender/test_scoring.py: 12 passed
tests/recommender/test_impact.py: 49 passed
Total: 79 passed
Lint: All checks passed (ruff)
```

## Known Stubs

None -- all models are fully defined, all extractors are implemented with real logic.

## Self-Check: PASSED

- All 9 created files verified present
- Both commits (48f6786, 7d85afa) verified in git log
- 79 tests passing, lint clean
