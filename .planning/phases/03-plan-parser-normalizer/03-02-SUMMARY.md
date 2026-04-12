---
phase: "03-plan-parser-normalizer"
plan: "02"
subsystem: "parser"
tags: ["fixtures", "snapshot-tests", "syrupy", "multi-version", "trino-429", "trino-455", "trino-480"]
dependency_graph:
  requires:
    - "03-01: EstimatedPlan/ExecutedPlan parser models and normalizer"
  provides:
    - "tests/fixtures/explain/480/: 5 real EXPLAIN query pairs from Trino 480"
    - "tests/fixtures/explain/455/: 2 real EXPLAIN query pairs from Trino 455"
    - "tests/fixtures/explain/429/: 2 real EXPLAIN query pairs from Trino 429"
    - "tests/parser/test_fixture_snapshots.py: syrupy snapshot tests for all fixtures"
    - "scripts/capture_fixtures.py: repeatable fixture capture script"
  affects:
    - "src/mcp_trino_optimizer/parser/parser.py"
    - "tests/parser/__snapshots__/test_fixture_snapshots.ambr"
tech_stack:
  added: []
  patterns:
    - "syrupy snapshot tests parametrized over fixture files (auto-discovers new fixtures)"
    - "Fragment-map unwrapping for real Trino EXPLAIN JSON format ({'0': root, '1': ...})"
    - "Live fixture capture via docker-compose stack with Trino image tag swap for older versions"
    - "Minimal query set (simple_select, aggregate) for older Trino versions to avoid Lakekeeper compat issues"
key_files:
  created:
    - "scripts/capture_fixtures.py"
    - "tests/fixtures/explain/480/simple_select.json"
    - "tests/fixtures/explain/480/simple_select_analyze.txt"
    - "tests/fixtures/explain/480/full_scan.json"
    - "tests/fixtures/explain/480/full_scan_analyze.txt"
    - "tests/fixtures/explain/480/aggregate.json"
    - "tests/fixtures/explain/480/aggregate_analyze.txt"
    - "tests/fixtures/explain/480/join.json"
    - "tests/fixtures/explain/480/join_analyze.txt"
    - "tests/fixtures/explain/480/iceberg_partition_filter.json"
    - "tests/fixtures/explain/480/iceberg_partition_filter_analyze.txt"
    - "tests/fixtures/explain/455/simple_select.json"
    - "tests/fixtures/explain/455/simple_select_analyze.txt"
    - "tests/fixtures/explain/455/aggregate.json"
    - "tests/fixtures/explain/455/aggregate_analyze.txt"
    - "tests/fixtures/explain/429/simple_select.json"
    - "tests/fixtures/explain/429/simple_select_analyze.txt"
    - "tests/fixtures/explain/429/aggregate.json"
    - "tests/fixtures/explain/429/aggregate_analyze.txt"
    - "tests/parser/test_fixture_snapshots.py"
    - "tests/parser/__snapshots__/test_fixture_snapshots.ambr"
  modified:
    - "src/mcp_trino_optimizer/parser/parser.py"
decisions:
  - "Fragment-map unwrapping: real Trino EXPLAIN JSON uses {'0': <root_node>, '1': <fragment2>} format, not a bare node dict. _unwrap_fragment_map() added to parser to detect and extract fragment 0 as plan root. Produces SchemaDriftWarning(info) for multi-fragment plans."
  - "455/429 fixture set is minimal (simple_select + aggregate only): full query set deferred as older Trino versions may have Lakekeeper compatibility issues. Corpus is additive."
  - "Snapshot excludes raw_text field to keep diffs readable; the typed tree structure is the test target"
metrics:
  duration: "~25 minutes"
  completed_date: "2026-04-12"
  tasks_completed: 2
  files_changed: 22
---

# Phase 03 Plan 02: Fixture Corpus and Snapshot Tests Summary

**One-liner:** Live-captured multi-version Trino EXPLAIN fixture corpus (429/455/480) with syrupy snapshot tests and fragment-map parser fix.

## What Was Built

### Task 1: Fixture capture script and multi-version corpus

**scripts/capture_fixtures.py** — Standalone fixture capture script that:
- Connects to any Trino instance via `--host`/`--port` CLI args
- Creates `iceberg.test_fixtures.orders` (partitioned by day) if it doesn't exist
- Runs 5 reference queries (simple_select, full_scan, aggregate, join, iceberg_partition_filter)
- Captures `EXPLAIN (FORMAT JSON)` and `EXPLAIN ANALYZE` for each
- Saves results to `tests/fixtures/explain/{version}/{query_name}.json` and `.txt`
- Security: no credentials stored in fixture output (T-03-07 compliance)
- Supports `--minimal` flag to capture only simple_select + aggregate

**Captured corpus:**
- Trino 480: 5 query pairs (10 files) — full query set including Iceberg partition filter and self-join
- Trino 455: 2 query pairs (4 files) — minimal set (simple_select, aggregate)
- Trino 429: 2 query pairs (4 files) — minimal set (simple_select, aggregate)

All fixtures are live captures from the docker-compose Trino stack with Lakekeeper REST catalog.

### Task 2: Syrupy snapshot tests for fixture corpus

**tests/parser/test_fixture_snapshots.py** — Five parametrized test functions that auto-discover all fixtures:

1. `test_fixture_parses_without_error` — parse succeeds, root non-None, at least 1 node, version set
2. `test_fixture_no_parse_error` — no ParseError raised for any fixture
3. `test_fixture_schema_drift_warnings_captured` — drift warnings are in plan object, not raised
4. `test_estimated_fixture_has_typed_cost_estimates` — EXPLAIN JSON fixtures have CostEstimate entries
5. `test_executed_fixture_has_runtime_metrics` — EXPLAIN ANALYZE fixtures have cpu_time_ms and output_rows
6. `test_fixture_snapshot` — parsed plan.model_dump(exclude={"raw_text"}) matches syrupy snapshot

18 snapshot files generated in `tests/parser/__snapshots__/test_fixture_snapshots.ambr`.

## Test Results

- `tests/parser/test_fixture_snapshots.py` — 84 passed, 12 skipped (estimated/executed type-specific tests)
- `tests/parser/` — 145 tests, all pass (18 snapshots pass)
- Full non-integration suite — 357 tests, all pass

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Real Trino EXPLAIN JSON uses fragment-keyed format, not bare node**

- **Found during:** Task 2 snapshot tests — `test_estimated_fixture_has_typed_cost_estimates` failed because no nodes had CostEstimate entries
- **Issue:** Real Trino `EXPLAIN (FORMAT JSON)` wraps fragment root nodes in a top-level dict keyed by fragment ID: `{"0": {<root_node>}, "1": {<fragment2>}}`. The existing parser treated the top-level dict as a node itself, producing `PlanNode(id='', name='Unknown')` with no typed fields populated.
- **Impact:** All real Trino fixtures would have parsed as empty single-node plans with no estimates, operators, or children. Phase 4 rules depending on the fixture corpus would have received empty trees.
- **Fix:** Added `_unwrap_fragment_map()` to `parser.py`. Detection: if all dict keys are digit strings (`"0"`, `"1"`, ...) and no `id`/`name` key exists at top level, treat as fragment map. Extract `data["0"]` as the root node. Multi-fragment plans produce a `SchemaDriftWarning(severity="info")` to document the discarded fragments.
- **Files modified:** `src/mcp_trino_optimizer/parser/parser.py`
- **Commit:** 0ed57a9
- **Backward compatibility:** Existing unit test fixtures in `test_parser.py` use the direct node format (with `id`/`name` at top level) — detection logic skips unwrapping for those, so all 273 prior tests still pass.

## Known Stubs

None. All fixtures are live-captured real Trino output. All snapshot tests are wired to the real parser.

## Threat Flags

No new security-relevant surface. Fixture files contain only EXPLAIN plan structure (no query results, no schema credentials). The `_unwrap_fragment_map` function operates on already-validated (size-capped) input. Fragment keys are validated as digit strings before use.

## Self-Check

### Files created:
- [x] `scripts/capture_fixtures.py`
- [x] `tests/fixtures/explain/480/simple_select.json`
- [x] `tests/fixtures/explain/480/simple_select_analyze.txt`
- [x] `tests/fixtures/explain/480/full_scan.json`
- [x] `tests/fixtures/explain/480/full_scan_analyze.txt`
- [x] `tests/fixtures/explain/480/aggregate.json`
- [x] `tests/fixtures/explain/480/aggregate_analyze.txt`
- [x] `tests/fixtures/explain/480/join.json`
- [x] `tests/fixtures/explain/480/join_analyze.txt`
- [x] `tests/fixtures/explain/480/iceberg_partition_filter.json`
- [x] `tests/fixtures/explain/480/iceberg_partition_filter_analyze.txt`
- [x] `tests/fixtures/explain/455/simple_select.json`
- [x] `tests/fixtures/explain/455/simple_select_analyze.txt`
- [x] `tests/fixtures/explain/455/aggregate.json`
- [x] `tests/fixtures/explain/455/aggregate_analyze.txt`
- [x] `tests/fixtures/explain/429/simple_select.json`
- [x] `tests/fixtures/explain/429/simple_select_analyze.txt`
- [x] `tests/fixtures/explain/429/aggregate.json`
- [x] `tests/fixtures/explain/429/aggregate_analyze.txt`
- [x] `tests/parser/test_fixture_snapshots.py`
- [x] `tests/parser/__snapshots__/test_fixture_snapshots.ambr`

### Commits:
- [x] f76dc83: feat(03-02): fixture capture script and multi-version corpus
- [x] 0ed57a9: feat(03-02): syrupy snapshot tests for fixture corpus

## Self-Check: PASSED
