---
phase: 04-rule-engine-13-deterministic-rules
plan: "03"
subsystem: rules
tags: [rule-engine, r5-broadcast, r6-join-order, r7-cpu-skew, r8-exchange-volume, r9-low-selectivity, d11-cost-vs-actual]
dependency_graph:
  requires:
    - 04-01-rule-infrastructure  # Rule ABC, EvidenceBundle, registry singleton
    - 04-02-general-rules-r1-r4  # R1-R4 patterns to follow
    - 03-plan-parser-normalizer  # BasePlan, PlanNode, EstimatedPlan/ExecutedPlan, walk()
  provides:
    - rules/r5_broadcast_too_big.py  # R5BroadcastTooBig
    - rules/r6_join_order.py         # R6JoinOrderInversion
    - rules/r7_cpu_skew.py           # R7CpuSkew
    - rules/r8_exchange_volume.py    # R8ExchangeVolume
    - rules/r9_low_selectivity.py    # R9LowSelectivity
    - rules/d11_cost_vs_actual.py    # D11CostVsActual
  affects:
    - 04-04-iceberg-rules  # same registry singleton; I rules follow same pattern
    - 05-recommendation-engine  # consumes list[EngineResult] including R5-R9+D11
    - 08-mcp-tool-wiring  # invokes RuleEngine which now runs R1-R9+D11
tech_stack:
  added:
    - statistics.median (stdlib) — used in R7 for CPU skew median computation
  patterns:
    - RuleThresholds injected via constructor (thresholds: RuleThresholds | None = None)
    - safe_float() guards all CBO estimate reads (NaN → None)
    - T-04-13 guard: `if len(node.children) < 2: continue` in all join-processing rules
    - magnitude normalization for D11 divergence_factor (always ≥1.0 in evidence dict)
    - backwards chain-building for ExecutedPlan test helpers (tail-first avoids reference aliasing)
key_files:
  created:
    - src/mcp_trino_optimizer/rules/r5_broadcast_too_big.py
    - src/mcp_trino_optimizer/rules/r6_join_order.py
    - src/mcp_trino_optimizer/rules/r7_cpu_skew.py
    - src/mcp_trino_optimizer/rules/r8_exchange_volume.py
    - src/mcp_trino_optimizer/rules/r9_low_selectivity.py
    - src/mcp_trino_optimizer/rules/d11_cost_vs_actual.py
    - tests/rules/test_r5_broadcast_join.py
    - tests/rules/test_r6_join_order.py
    - tests/rules/test_r7_skew.py
    - tests/rules/test_r8_exchange.py
    - tests/rules/test_r9_low_selectivity.py
    - tests/rules/test_d11_cost_vs_actual.py
  modified: []
decisions:
  - "R7 threshold comparison is >= (fires at exactly skew_ratio) — plan spec says 'at threshold fires'"
  - "D11 evidence divergence_factor stores magnitude (max(ratio, 1/ratio)) so over- and under-estimates both show human-readable ≥1.0 value"
  - "R9 declares PLAN_ONLY evidence but only fires on ExecutedPlan (input_bytes/output_bytes are None for EstimatedPlan) — this is intentional; no external fetch needed"
  - "R6 uses 100x as fixed detection heuristic (not user-tunable) per plan spec; stats presence always suppresses"
metrics:
  duration_minutes: 35
  completed_date: "2026-04-13"
  tasks_completed: 2
  tasks_total: 2
  files_created: 12
  files_modified: 0
---

# Phase 4 Plan 3: General Rules R5-R9 + D11 Summary

**One-liner:** R5-R9 and D11 rules covering broadcast join sizing, join order inversion, CPU skew detection, exchange volume, low-selectivity scans, and CBO estimate divergence — all with threshold-driven, deterministic detection.

## Rules Implemented

### R5: BroadcastTooBig

- **Evidence:** PLAN_ONLY
- **Detection:** InnerJoin/SemiJoin nodes with `descriptor["distribution"] == "REPLICATED"`. Build side = `children[1]`. Fires when `build_side.estimates[0].output_size_in_bytes > thresholds.broadcast_max_bytes` (default 100 MB).
- **Severity:** high
- **Confidence:** 0.85 (CBO estimate; actual size may differ)
- **T-04-13 guard:** `if len(node.children) < 2: continue` — malformed joins skip safely
- **Evidence dict fields:** `distribution`, `build_side_estimated_bytes`, `threshold_bytes`

### R6: JoinOrderInversion

- **Evidence:** TABLE_STATS
- **Detection:** InnerJoin/SemiJoin nodes. Computes `probe_rows / build_rows` from `estimates[0].output_row_count`. Fires when ratio > 100x AND `evidence.table_stats` is None or lacks `row_count`. Stats presence always suppresses.
- **Severity:** medium
- **Confidence:** 0.6 (without stats, cannot prove inversion is wrong)
- **Threshold:** 100x is a fixed detection heuristic (citation: Trino join-reordering docs), not user-tunable
- **Evidence dict fields:** `probe_estimated_rows`, `build_estimated_rows`, `probe_to_build_ratio`, `stats_available`

### R7: CpuSkew

- **Evidence:** PLAN_WITH_METRICS (ExecutedPlan only)
- **Detection:** Collects `cpu_time_ms` from all nodes. Requires ≥3 non-None values. Fires when `max(cpu_time_ms) / median(cpu_time_ms) >= thresholds.skew_ratio` (default 5.0). Returns [] if median == 0.0.
- **Severity:** high
- **Confidence:** 0.8
- **operator_ids:** single id of the node with maximum cpu_time_ms
- **Evidence dict fields:** `max_cpu_ms`, `median_cpu_ms`, `skew_ratio`, `threshold`, `node_count`

### R8: ExchangeVolume

- **Evidence:** PLAN_ONLY
- **Detection:** Sums `output_size_in_bytes` from Exchange/LocalExchange/RemoteSource nodes vs TableScan/ScanFilter/ScanFilterProject nodes. Fires when `exchange_bytes > scan_bytes` and both > 0.
- **Severity:** medium
- **Confidence:** 0.75
- **Evidence dict fields:** `total_exchange_bytes`, `total_scan_bytes`, `ratio`

### R9: LowSelectivity

- **Evidence:** PLAN_ONLY (reads actual runtime bytes, effectively ExecutedPlan-only)
- **Detection:** Scan nodes (TableScan/ScanFilter/ScanFilterProject). Reads `node.input_bytes` and `node.output_bytes`. Fires when `output_bytes / input_bytes < thresholds.scan_selectivity_threshold` (default 0.10). Silently skips when either is None (EstimatedPlan case).
- **Severity:** medium
- **Confidence:** 0.9 (actual bytes are reliable)
- **Evidence dict fields:** `input_bytes`, `output_bytes`, `selectivity_ratio`, `threshold`, `table`

### D11: CostVsActual

- **Evidence:** PLAN_WITH_METRICS (ExecutedPlan only)
- **Detection:** Scan nodes. Computes `divergence = actual_output_rows / estimated_output_row_count`. Fires when `divergence > factor OR divergence < 1/factor`. Stores `magnitude = max(divergence, 1/divergence)` in evidence so the value is always ≥1.0 regardless of direction.
- **Severity:** high
- **Confidence:** 0.95 (direct measurement evidence)
- **Guards:** `safe_float()` for NaN estimates; `if estimated <= 0` and `if actual == 0`
- **Evidence dict fields:** `estimated_rows`, `actual_rows`, `divergence_factor` (magnitude), `threshold`

## Test Coverage

| Rule | Synthetic | Realistic | Negative | Total |
|------|-----------|-----------|----------|-------|
| R5   | 3         | 2         | 5        | 10    |
| R6   | 4         | 1         | 6        | 11    |
| R7   | 5         | 0         | 5        | 10    |
| R8   | 4         | 2         | 4        | 10    |
| R9   | 4         | 1         | 5        | 10    |
| D11  | 5         | 0         | 7        | 12    |

Full suite: 139 passed, 4 skipped (Iceberg Wave 4 stubs), 0 failures.

## Verification Results

```
uv run pytest tests/rules/test_r5_broadcast_join.py tests/rules/test_r6_join_order.py
  tests/rules/test_r7_skew.py tests/rules/test_r8_exchange.py
  tests/rules/test_r9_low_selectivity.py tests/rules/test_d11_cost_vs_actual.py -v
63 passed in 0.08s

uv run pytest tests/rules/ -q
139 passed, 4 skipped in 0.15s

uv run mypy src/mcp_trino_optimizer/rules/ --strict
Success: no issues found in 17 source files

Registry verification:
['R5', 'R6', 'R7', 'R8', 'R9', 'D11']
(R1-R4 registered by Wave 2; Wave 3 adds R5-R9+D11; Wave 4 will add I1/I3/I6/I8)
```

## Commits

| Hash    | Message                                                                     |
|---------|-----------------------------------------------------------------------------|
| d67a28f | feat(04-03): implement R5 BroadcastTooBig, R6 JoinOrderInversion, R8 ExchangeVolume rules |
| 83b4757 | feat(04-03): implement R7 CpuSkew, R9 LowSelectivity, D11 CostVsActual rules |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `parse_estimated_plan` takes a JSON string, not a parsed dict**
- **Found during:** Task 1 realistic fixture tests (R5, R6, R8)
- **Issue:** Test files called `json.loads(fixture.read_text())` and passed the resulting dict to `parse_estimated_plan`. The function uses `orjson.loads` internally and requires raw string/bytes input, not a pre-parsed dict.
- **Fix:** Changed all fixture-loading lines from `json.loads(path.read_text())` + `parse_estimated_plan(raw)` to just `path.read_text()` + `parse_estimated_plan(json_text)`. Removed unused `import json` from affected test files.
- **Files modified:** tests/rules/test_r5_broadcast_join.py, tests/rules/test_r6_join_order.py, tests/rules/test_r8_exchange.py

**2. [Rule 1 - Bug] R7 threshold comparison was `>` instead of `>=`**
- **Found during:** Task 2 R7 test failure (test_at_threshold_fires)
- **Issue:** The rule used `ratio <= threshold: continue` (i.e. fires only when strictly greater). The plan spec says "at threshold fires" (ratio=5.0 with threshold=5.0 should fire).
- **Fix:** Changed `ratio <= self._thresholds.skew_ratio` to `ratio < self._thresholds.skew_ratio` so that exactly-at-threshold fires.
- **Files modified:** src/mcp_trino_optimizer/rules/r7_cpu_skew.py

**3. [Rule 1 - Bug] `_make_executed_plan` test helper built chain with reference aliasing**
- **Found during:** Task 2 R7 test — plan.walk() only returned 2 nodes instead of 5
- **Issue:** The forward-building loop `nodes[i] = PlanNode(..., children=[nodes[i+1]])` created a chain where `nodes[i+1]` always referenced the original leaf node (not the rebuilt chain). Only 2 nodes ended up in the walk.
- **Fix:** Rebuilt the helper to construct the chain backwards (tail-first), so each rebuilt node correctly wraps its downstream child.
- **Files modified:** tests/rules/test_r7_skew.py

**4. [Rule 2 - Missing] D11 evidence divergence_factor was raw ratio (could be <1.0)**
- **Found during:** Task 2 D11 over-estimate test — expected 100.0, got 0.01
- **Issue:** The plan spec's message template says "CBO estimate diverged {divergence:.1f}x" implying a human-readable magnitude. For over-estimates (estimated >> actual), `actual/estimated < 1.0` which is confusing. The test correctly expected 100.0 (magnitude).
- **Fix:** Added `magnitude = divergence if divergence >= 1.0 else (1.0 / divergence)` and stored `magnitude` in evidence dict as `divergence_factor`. Both directions still correctly trigger the threshold check.
- **Files modified:** src/mcp_trino_optimizer/rules/d11_cost_vs_actual.py

## Known Stubs

4 Iceberg rule test files remain skipped (Wave 4):
- tests/rules/test_i1_small_files.py
- tests/rules/test_i3_delete_files.py
- tests/rules/test_i6_stale_snapshots.py
- tests/rules/test_i8_partition_transform.py

## Threat Surface Scan

No new network endpoints, auth paths, file access patterns, or schema changes were introduced. All new code is pure in-process rule logic reading from pre-built plan objects. NaN/division-by-zero guards applied per T-04-11 and T-04-13 mitigations.

## Self-Check: PASSED

Files exist:
- src/mcp_trino_optimizer/rules/r5_broadcast_too_big.py: FOUND
- src/mcp_trino_optimizer/rules/r6_join_order.py: FOUND
- src/mcp_trino_optimizer/rules/r7_cpu_skew.py: FOUND
- src/mcp_trino_optimizer/rules/r8_exchange_volume.py: FOUND
- src/mcp_trino_optimizer/rules/r9_low_selectivity.py: FOUND
- src/mcp_trino_optimizer/rules/d11_cost_vs_actual.py: FOUND
- tests/rules/test_r5_broadcast_join.py: FOUND
- tests/rules/test_r6_join_order.py: FOUND
- tests/rules/test_r7_skew.py: FOUND
- tests/rules/test_r8_exchange.py: FOUND
- tests/rules/test_r9_low_selectivity.py: FOUND
- tests/rules/test_d11_cost_vs_actual.py: FOUND

Commits exist:
- d67a28f: FOUND
- 83b4757: FOUND
