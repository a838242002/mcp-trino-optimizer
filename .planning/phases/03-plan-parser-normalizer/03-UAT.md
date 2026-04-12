---
status: complete
phase: 03-plan-parser-normalizer
source: 03-01-SUMMARY.md, 03-02-SUMMARY.md
started: 2026-04-12T23:00:00Z
updated: 2026-04-12T23:30:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Parse EXPLAIN JSON into typed EstimatedPlan
expected: Running parse_estimated_plan() on a fixture file (e.g. tests/fixtures/explain/480/simple_select.json) returns an EstimatedPlan — not a dict, not an error. The root node has a non-empty id and name. Operator nodes carry CostEstimate entries (cpu_cost, memory_cost, etc.) as typed fields. All original JSON fields survive in node.model_extra (the raw bag).
result: pass

### 2. Parse EXPLAIN ANALYZE text into typed ExecutedPlan
expected: Running parse_executed_plan() on a .txt fixture (e.g. tests/fixtures/explain/480/simple_select_analyze.txt) returns an ExecutedPlan. Nodes expose cpu_time_ms, output_rows, input_rows, and peak_memory as typed numeric fields — no dict lookups needed. The test suite confirms this with pytest tests/parser/test_parser.py.
result: pass

### 3. ScanFilterAndProject normalization
expected: A plan node named ScanFilterAndProject is decomposed by the normalizer into a Project → Filter → TableScan chain (or Project → TableScan if no filter). After normalization, a walk looking for scan nodes finds the TableScan without needing to special-case ScanFilterAndProject. Confirmed by pytest tests/parser/test_normalizer.py passing.
result: pass

### 4. Schema drift tolerance — unknown fields and node types
expected: Passing a JSON fixture with an extra unknown field does not raise. The unknown field appears in node.model_extra. Passing a fixture with an unrecognised node type does not raise — instead a SchemaDriftWarning is recorded on the returned plan object. pytest tests/parser/test_models.py passes.
result: pass

### 5. Iceberg operator field extraction
expected: An IcebergTableScan node in an ExecutedPlan fixture exposes iceberg_split_count and iceberg_file_count as typed int fields. In an EstimatedPlan, those fields are None (runtime metrics unavailable from EXPLAIN JSON — by design). Confirmed by tests in test_parser.py covering the 480/iceberg_partition_filter fixtures.
result: issue
reported: "iceberg_split_count is None for the executed plan iceberg_partition_filter_analyze.txt. The fixture line has 'Splits: 1' but _INPUT_LINE_RE looks for 'N splits' (number-then-word format). The regex never matches this format. iceberg_file_count is also None — Files read: N format not present in these fixtures either."
severity: major

### 6. Multi-version fixture corpus parses clean
expected: Running pytest tests/parser/test_fixture_snapshots.py shows all fixture files (Trino 429, 455, 480) parse without error. The test discovers fixtures automatically. 84 tests pass, skipped count is small (type-specific tests for estimated vs executed). No failures.
result: pass

### 7. Syrupy snapshot gate catches regressions
expected: The snapshot file tests/parser/__snapshots__/test_fixture_snapshots.ambr exists and is committed. Running pytest tests/parser/test_fixture_snapshots.py with no code changes shows 0 snapshot diffs. If the parser output changes for any fixture, exactly that fixture's snapshot test fails with a readable diff rather than a crash.
result: pass

## Summary

total: 7
passed: 6
issues: 1
pending: 0
skipped: 0
blocked: 0

## Gaps

- truth: "An IcebergTableScan node in an ExecutedPlan exposes iceberg_split_count and iceberg_file_count as typed int fields"
  status: failed
  reason: "User reported: iceberg_split_count is None for the executed plan iceberg_partition_filter_analyze.txt. The fixture line has 'Splits: 1' but _INPUT_LINE_RE looks for 'N splits' (number-then-word format). The regex never matches this format. iceberg_file_count is also None — Files read: N format not present in these fixtures either."
  severity: major
  test: 5
  artifacts: []
  missing: []
