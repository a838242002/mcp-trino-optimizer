---
phase: 3
slug: plan-parser-normalizer
status: complete
nyquist_compliant: true
wave_0_complete: true
created: 2026-04-12
last_audited: 2026-04-12
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.3+ with pytest-asyncio 1.3.0+ |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `uv run pytest tests/parser/ -x` |
| **Full suite command** | `uv run pytest tests/ -x --ignore=tests/integration` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/parser/ -x`
- **After every plan wave:** Run `uv run pytest tests/ -x --ignore=tests/integration`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 03-01-T1 | 01 | 1 | PLN-01, PLN-02, PLN-03, PLN-04, PLN-07 | T-03-01, T-03-04 | 1MB size cap + non-backtracking regex for DoS prevention | unit | `uv run pytest tests/parser/test_models.py tests/parser/test_parser.py -x` | ✅ | ✅ green |
| 03-01-T2 | 01 | 1 | PLN-05 | — | N/A | unit | `uv run pytest tests/parser/test_normalizer.py tests/adapters/test_offline_plan_source.py tests/adapters/test_port_conformance.py -x` | ✅ | ✅ green |
| 03-02-T1 | 02 | 2 | PLN-06 | — | N/A | capture | `uv run python scripts/capture_fixtures.py` | ✅ | ✅ green |
| 03-02-T2 | 02 | 2 | PLN-06 | — | N/A | snapshot | `uv run pytest tests/parser/test_fixture_snapshots.py -x` | ✅ | ✅ green |
| 03-03-T1 | 03 | gap | PLN-04 | — | N/A | unit | `uv run pytest tests/parser/test_parser.py -k "iceberg_split_count" -x` | ✅ | ✅ green |
| 03-03-T2 | 03 | gap | PLN-04 | — | N/A | snapshot | `uv run pytest tests/parser/test_fixture_snapshots.py -x` | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Requirement Coverage

| Requirement | Status | Evidence |
|-------------|--------|---------|
| PLN-01 | COVERED | `test_parses_valid_explain_json_into_estimated_plan`, `test_parses_explain_analyze_text_into_executed_plan`, `test_estimated_plan_has_plan_type_estimated`, `test_executed_plan_has_plan_type_executed` |
| PLN-02 | COVERED | `test_plan_node_raw_property_returns_model_extra`, `test_plan_node_raw_empty_dict_when_no_extras`, `test_plan_node_unknown_fields_preserved_in_model_extra`, `test_unknown_fields_preserved_in_model_extra` |
| PLN-03 | COVERED | `test_executed_plan_extracts_cpu_time`, `test_executed_plan_extracts_output_rows`, `test_executed_plan_extracts_wall_time`, `test_executed_plan_extracts_output_bytes`, `test_executed_plan_extracts_input_bytes`, `test_executed_plan_extracts_peak_memory` |
| PLN-04 | COVERED + manual | `test_iceberg_scan_extracts_split_count`, `test_iceberg_scan_extracts_file_count`, `test_iceberg_fields_transferred_to_table_scan`, `test_iceberg_split_count_extracted_from_executed_plan` (real Trino 480 fixture, Splits: N format), `test_iceberg_split_count_none_for_estimated_plan`; `iceberg_partition_spec_id` is manual-only (see below) |
| PLN-05 | COVERED | `test_scan_filter_and_project_decomposes_into_project_filter_tablescan`, `test_project_transparent_to_find_nodes_by_type`, `test_nested_scan_filter_and_project_all_normalized` |
| PLN-06 | COVERED | `test_fixture_parses_without_error`, `test_fixture_no_parse_error`, `test_fixture_snapshot` (18 snapshots, 3 Trino versions) |
| PLN-07 | COVERED | `test_unknown_node_type_does_not_raise`, `test_schema_drift_warning_for_missing_id`, `test_fixture_schema_drift_warnings_captured` |

---

## Wave 0 Requirements

- [x] `tests/parser/__init__.py` — package marker
- [x] `tests/parser/test_models.py` — PlanNode, EstimatedPlan, ExecutedPlan model tests
- [x] `tests/parser/test_parser.py` — JSON and text parsing tests
- [x] `tests/parser/test_normalizer.py` — ScanFilterAndProject normalization tests
- [x] `tests/parser/test_fixture_snapshots.py` — syrupy snapshot tests for multi-version fixtures
- [x] `tests/fixtures/explain/` — fixture directory structure (429, 455, 480)
- [x] `scripts/capture_fixtures.py` — fixture capture script

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Multi-version fixture capture from docker-compose | PLN-06 | Requires running 3 Trino versions sequentially | Run `scripts/capture_fixtures.py` with each Trino version tag |
| `iceberg_partition_spec_id` extraction | PLN-04 | Field is not present in any Trino EXPLAIN JSON or EXPLAIN ANALYZE text for Trino 429–480; the field is declared on the model for forward-compatibility. Verify when a Trino version emits partition spec ID in EXPLAIN output. | Check `EXPLAIN (FORMAT JSON)` output of an Iceberg query for a `partitionSpecId` or `specId` field; update `_build_node` regex/mapping when found. |

---

## Validation Audit 2026-04-12 (pass 1)

| Metric | Count |
|--------|-------|
| Gaps found | 2 |
| Resolved (new tests) | 1 (PLN-03: wall_time_ms, input_bytes, output_bytes, peak_memory_bytes) |
| Escalated to manual-only | 1 (PLN-04: iceberg_partition_spec_id not in Trino EXPLAIN output) |

## Validation Audit 2026-04-12 (pass 2 — gap closure 03-03)

| Metric | Count |
|--------|-------|
| Gaps found | 1 (PLN-04: iceberg_split_count always None on real Trino 480 fixtures) |
| Resolved (new tests) | 2 (test_iceberg_split_count_extracted_from_executed_plan, test_iceberg_split_count_none_for_estimated_plan) |
| Root cause fixed | Column-assignment lines (`:=`) misclassified as operator nodes; _SPLITS_RE added for Trino 480+ `Splits: N` format |
| Escalated | 0 |
| Total tests after | 363 (parser: 151, full suite: 363) |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 5s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** passed — 2026-04-12 (gap closure audit complete, 363/363 non-integration tests green)
