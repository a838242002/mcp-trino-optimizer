---
phase: 03-plan-parser-normalizer
plan: "03"
subsystem: parser
tags: [bug-fix, regex, iceberg, split-count, gap-closure]
dependency_graph:
  requires: [03-01, 03-02]
  provides: [iceberg_split_count from real Trino 480 EXPLAIN ANALYZE output]
  affects: [rule engine (Phase 4) — iceberg_split_count now reliable]
tech_stack:
  added: []
  patterns: [dual-regex fallback for evolving Trino output formats]
key_files:
  modified:
    - src/mcp_trino_optimizer/parser/parser.py
    - tests/parser/test_parser.py
    - tests/parser/__snapshots__/test_fixture_snapshots.ambr
decisions:
  - Keep legacy `N splits` group in _INPUT_LINE_RE for backward compat with existing test fixtures; add _SPLITS_RE as Trino 480+ fallback
  - Exclude `:=` column-assignment lines and `::` predicate-range lines from operator detection to prevent spurious child nodes
metrics:
  duration: ~10 minutes
  completed: "2026-04-12"
  tasks_completed: 4
  files_modified: 3
  tests_added: 2
  tests_updated: 9 snapshots
  test_count_before: 357
  test_count_after: 363
---

# Phase 3 Plan 03: Fix iceberg_split_count Regex — Splits: N Format (PLN-04)

**One-liner:** Fixed `iceberg_split_count` always-None bug by adding `_SPLITS_RE` for Trino 480+ `Splits: N` format and excluding `:=` column-assignment lines from operator detection.

## What Was Built

Fixed the regex mismatch that caused `iceberg_split_count` to always be `None` for real Trino 480 EXPLAIN ANALYZE output.

**Root cause (confirmed):** The `_INPUT_LINE_RE` regex had an optional group `(?:,\s*(?P<splits>\d+)\s*splits)?` expecting `N splits` (number-then-word), but real Trino 480 emits `Splits: N` on the Input summary line:

```
Input: 10 rows (533B), Physical input: 996B, Physical input time: 4.58us, Splits: 1, Splits generation wait time: 13.77ms
```

**Secondary bug found and fixed (deviation):** The parser was treating column-assignment lines like `amount := 3:amount:decimal(10,2)` as operator nodes, creating spurious `PlanNode` children (`status`, `ts`, `id`, `name`, `amount`) under `TableScan`. This caused the `Input:` summary line to be attributed to the `amount` pseudo-node instead of `TableScan`, so even the new `_SPLITS_RE` fix wouldn't have worked without also fixing operator detection.

## Changes

### `parser.py`

1. Added `_SPLITS_RE = re.compile(r"Splits:\s*(?P<splits>\d+)", re.IGNORECASE)` after `_INPUT_LINE_RE`
2. In `_extract_metrics_from_line`: applied `_SPLITS_RE` as fallback when legacy `splits` group does not match
3. In `_parse_explain_analyze_text`: added two `is_metric_line` guards:
   - `:=` in the stripped line → column-assignment detail, not an operator
   - `::` prefix → predicate-range continuation line, not an operator

### `test_parser.py`

Added two new tests to `TestParseExecutedPlan`:
- `test_iceberg_split_count_extracted_from_executed_plan` — asserts `iceberg_split_count == 1` from `iceberg_partition_filter_analyze.txt` (PLN-04)
- `test_iceberg_split_count_none_for_estimated_plan` — asserts `iceberg_split_count is None` for `iceberg_partition_filter.json` EstimatedPlan (by design, no runtime metrics)

### `test_fixture_snapshots.ambr`

Updated 9 snapshots. Changes:
- `iceberg_partition_filter_analyze` snapshot: `iceberg_split_count` field on `TableScan` now `1` instead of `None`
- All `*_analyze` fixture snapshots: removed spurious child nodes (column-assignment pseudo-operators) from `TableScan` and similar leaf nodes, significantly slimming the snapshot file (−699 lines)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed spurious child nodes from column-assignment lines**
- **Found during:** Task 2 (test execution)
- **Issue:** Lines like `amount := 3:amount:decimal(10,2)` were parsed as operator nodes because `amount` matched the CamelCase operator name pattern. This created bogus `PlanNode` children and caused the `Input:` summary line (with `Splits: N`) to be attributed to the `amount` pseudo-node instead of `TableScan`. The `iceberg_split_count` was set on `amount` but `find_scan()` found `TableScan` with `None`.
- **Fix:** Added `":=" in stripped_for_keyword` and `stripped_for_keyword.startswith("::")` guards to `is_metric_line` detection in `_parse_explain_analyze_text`
- **Files modified:** `src/mcp_trino_optimizer/parser/parser.py`
- **Commit:** 59a4a3f

## Success Criteria Verification

- [x] `iceberg_split_count` returns `1` for `iceberg_partition_filter_analyze.txt`
- [x] `iceberg_split_count` is `None` for `iceberg_partition_filter.json` (EstimatedPlan — by design)
- [x] All pre-existing tests still pass (363 total, up from 357)
- [x] New tests for `iceberg_split_count` pass (2 new tests)
- [x] Snapshots updated and committed

## Self-Check: PASSED

- [x] `src/mcp_trino_optimizer/parser/parser.py` — modified, committed in 59a4a3f
- [x] `tests/parser/test_parser.py` — modified, committed in 59a4a3f
- [x] `tests/parser/__snapshots__/test_fixture_snapshots.ambr` — updated, committed in 59a4a3f
- [x] Commit 59a4a3f exists: confirmed
- [x] 363 tests pass, 0 failures
