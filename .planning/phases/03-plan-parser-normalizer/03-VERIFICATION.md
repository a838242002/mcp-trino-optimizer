---
phase: 03-plan-parser-normalizer
verified: 2026-04-12T00:00:00Z
status: passed
score: 9/9 must-haves verified
overrides_applied: 0
---

# Phase 3: Plan Parser & Normalizer Verification Report

**Phase Goal:** Raw Trino `EXPLAIN` JSON is converted into two distinct typed plan classes (`EstimatedPlan` from `EXPLAIN`, `ExecutedPlan` from `EXPLAIN ANALYZE`) that tolerate version drift via per-node `raw` dict bags, normalize common operator variants (`ScanFilterProject`, `Project` wrappers), and expose Iceberg operator details (split count, file count, partition spec id). The multi-version fixture corpus that every rule will depend on is captured and snapshot-gated.
**Verified:** 2026-04-12
**Status:** PASSED
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| #  | Truth | Status | Evidence |
|----|-------|--------|---------|
| 1  | EXPLAIN (FORMAT JSON) fixture parses into EstimatedPlan with typed PlanNode tree | VERIFIED | `parse_estimated_plan` in `parser.py`; `EstimatedPlan(BasePlan)` in `models.py`; 357 tests pass including snapshot tests |
| 2  | EXPLAIN ANALYZE text fixture parses into ExecutedPlan with per-operator CPU, wall, rows, bytes, memory | VERIFIED | `parse_executed_plan` with `_CPU_LINE_RE`, `_OUTPUT_LINE_RE`, `_INPUT_LINE_RE`, `_PEAK_MEMORY_RE` regex; runtime fields on `PlanNode`; executed fixture snapshots present |
| 3  | Unknown node types and fields produce SchemaDriftWarning, never exceptions | VERIFIED | `_build_node` uses `model_extra` (ConfigDict `extra="allow"`); unknown name defaults to `"Unknown"` with warning; `SchemaDriftWarning` recorded rather than raising |
| 4  | ScanFilterAndProject nodes are decomposed into TableScan + Filter + Project before consumers see them | VERIFIED | `normalizer.py` has `SCAN_FILTER_AND_PROJECT = "ScanFilterAndProject"` and `_decompose_scan_filter_and_project`; called by both `parse_estimated_plan` and `parse_executed_plan` |
| 5  | IcebergTableScan nodes expose iceberg_split_count, iceberg_file_count, iceberg_partition_spec_id | VERIFIED | Typed fields on `PlanNode` (lines 115-122 of `models.py`); `_INPUT_LINE_RE` extracts splits; `_FILES_READ_RE` extracts file count; fields transferred in normalizer decomposition |
| 6  | model_extra preserves all original fields not mapped to typed attributes | VERIFIED | `ConfigDict(extra="allow")` on `PlanNode`; `.raw` property returns `model_extra or {}`; `_build_node` spreads `extra_fields` into `PlanNode.model_validate` |
| 7  | PlanSource protocol returns EstimatedPlan and ExecutedPlan instead of ExplainPlan | VERIFIED | `ports/plan_source.py` and `ports/__init__.py` export `EstimatedPlan`/`ExecutedPlan`; no `class ExplainPlan` in ports; `ExplainPlan` isolated to internal `adapters/trino/_explain_plan.py` |
| 8  | At least 3 Trino versions (429, ~455, 480) have captured EXPLAIN JSON and EXPLAIN ANALYZE text fixtures | VERIFIED | `tests/fixtures/explain/429/`, `455/`, `480/` each present; 9 valid JSON files; all 9 `_analyze.txt` files non-empty (15-50 lines each) |
| 9  | Syrupy snapshot tests gate the parsed output of every fixture in CI | VERIFIED | `tests/parser/test_fixture_snapshots.py` parametrized over all fixture files; `tests/parser/__snapshots__/test_fixture_snapshots.ambr` (3772 lines); `18 snapshots passed` in test run |

**Score:** 9/9 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/mcp_trino_optimizer/parser/models.py` | PlanNode, EstimatedPlan, ExecutedPlan, SchemaDriftWarning, CostEstimate, OutputSymbol | VERIFIED | All classes present; `ConfigDict(extra="allow")`; no PEP 563 import |
| `src/mcp_trino_optimizer/parser/parser.py` | parse_estimated_plan, parse_executed_plan | VERIFIED | Both functions present; fragment-map unwrapping; recursion depth cap 100 |
| `src/mcp_trino_optimizer/parser/normalizer.py` | normalize_plan_tree with ScanFilterAndProject | VERIFIED | Present; `SCAN_FILTER_AND_PROJECT = "ScanFilterAndProject"`; filter heuristic avoids false positives |
| `src/mcp_trino_optimizer/parser/__init__.py` | Public API re-exports including parse_estimated_plan | VERIFIED | All 9 symbols in `__all__` |
| `src/mcp_trino_optimizer/ports/plan_source.py` | PlanSource with EstimatedPlan/ExecutedPlan return types | VERIFIED | Protocol returns `EstimatedPlan`/`ExecutedPlan`; no `ExplainPlan` class |
| `tests/fixtures/explain/480/simple_select.json` | EXPLAIN JSON from Trino 480 | VERIFIED | Valid JSON; live-captured |
| `tests/fixtures/explain/480/simple_select_analyze.txt` | EXPLAIN ANALYZE text from Trino 480 | VERIFIED | 16 lines, non-empty |
| `tests/fixtures/explain/429/simple_select.json` | EXPLAIN JSON from Trino 429 | VERIFIED | Valid JSON; live-captured |
| `tests/parser/test_fixture_snapshots.py` | Syrupy snapshot tests | VERIFIED | Parametrized; `assert snapshot_data == snapshot`; 84 tests pass |
| `scripts/capture_fixtures.py` | Fixture capture script | VERIFIED | Contains `EXPLAIN (FORMAT JSON)` and `EXPLAIN ANALYZE`; accepts `--version` arg |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `parser/parser.py` | `parser/models.py` | `from.*models import` | WIRED | `from mcp_trino_optimizer.parser.models import CostEstimate, EstimatedPlan, ...` |
| `parser/parser.py` | `parser/normalizer.py` | `normalize_plan_tree` | WIRED | Called at end of both `parse_estimated_plan` and `parse_executed_plan` |
| `adapters/offline/json_plan_source.py` | `parser/parser.py` | `parse_estimated_plan` | WIRED | `from mcp_trino_optimizer.parser import parse_estimated_plan, parse_executed_plan`; used in `fetch_plan`, `fetch_analyze_plan`, `fetch_distributed_plan` |
| `ports/plan_source.py` | `parser/models.py` | re-exports EstimatedPlan | WIRED | `from mcp_trino_optimizer.parser.models import EstimatedPlan, ExecutedPlan` |
| `test_fixture_snapshots.py` | `tests/fixtures/explain/` | loads fixtures via parse functions | WIRED | `FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "explain"`; calls `parse_estimated_plan`/`parse_executed_plan` |
| `test_fixture_snapshots.py` | syrupy snapshots | `assert ... == snapshot` | WIRED | `assert snapshot_data == snapshot` at line 239; 18 snapshots stored in `.ambr` file |

### Data-Flow Trace (Level 4)

Not applicable — this phase produces a parsing library, not a rendering component. Data flows are verified through the test suite (357 passing tests, 18 passing snapshots confirm real fixture data flows through the parser to typed model output).

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full non-integration test suite exits 0 | `uv run pytest tests/ -x --ignore=tests/integration -q` | 357 passed, 12 skipped, 18 snapshots passed in 1.63s | PASS |
| All JSON fixtures are valid JSON | `python3` json.load over all .json fixtures | 9 valid, 0 invalid | PASS |
| All _analyze.txt fixtures are non-empty | `wc -l` over all `*_analyze.txt` | All 9 files have 15-50 lines | PASS |
| ruff lint passes on parser module | `uv run ruff check src/.../parser/` | All checks passed | PASS |
| ExplainPlan absent from ports | `grep "class ExplainPlan" src/.../ports/plan_source.py` | NOT in ports | PASS |

### Requirements Coverage

| Requirement | Description | Status | Evidence |
|-------------|-------------|--------|---------|
| PLN-01 | Two distinct typed plan classes: EstimatedPlan and ExecutedPlan | SATISFIED | Both classes defined in `models.py`; returned by `parse_estimated_plan` / `parse_executed_plan` |
| PLN-02 | Every parsed node preserves `raw: dict` bag alongside typed fields | SATISFIED | `ConfigDict(extra="allow")` on `PlanNode`; `.raw` property returns `model_extra` |
| PLN-03 | Parser extracts per-operator CPU time, wall time, input/output rows, bytes, peak memory | SATISFIED | All fields on `PlanNode`; regex patterns in `parser.py` populate them for executed plans |
| PLN-04 | IcebergTableScan split count, file count, partition spec id as typed fields | SATISFIED | `iceberg_split_count`, `iceberg_file_count`, `iceberg_partition_spec_id` on `PlanNode`; extracted in `_extract_metrics_from_line` |
| PLN-05 | Normalizes `ScanFilterProject` into `TableScan + filter + projection` | SATISFIED | `normalizer.py` decomposes `ScanFilterAndProject`; Project/Filter/TableScan nodes created; DFS walk transparent through Project |
| PLN-06 | Multi-version fixture corpus (429, 455, 480); syrupy snapshot tests in CI | SATISFIED | All 3 version directories present with real captured fixtures; 18 syrupy snapshots gated in CI |
| PLN-07 | Unknown node type or schema drift produces `schema_drift_warning`, not exception | SATISFIED | `SchemaDriftWarning` entries appended to `warnings` list; `ParseError` only for truly invalid JSON |

### Anti-Patterns Found

| File | Pattern | Severity | Impact |
|------|---------|----------|--------|
| None | — | — | No stubs, placeholder returns, or hardcoded empty data found in parser module |

Notable: `models.py` correctly omits `from __future__ import annotations` (required for pydantic v2 runtime annotation evaluation). `parser.py` and `normalizer.py` use `from __future__ import annotations` appropriately (they do not define pydantic models).

### Human Verification Required

None. All observable truths are verifiable programmatically. The snapshot tests provide structural regression coverage for the fixture corpus.

### Gaps Summary

No gaps. All 9 must-have truths are verified. The phase goal is fully achieved:

- `EstimatedPlan` and `ExecutedPlan` are the only public plan domain types
- EXPLAIN JSON parses into typed `PlanNode` trees with `model_extra` preservation
- EXPLAIN ANALYZE text parses into `ExecutedPlan` with per-operator runtime metrics
- `ScanFilterAndProject` is normalized to `TableScan + Filter + Project` in all parsed trees (note: the phase goal mentions "ScanFilterProject" but the actual Trino operator name implemented is the correct "ScanFilterAndProject")
- Unknown nodes and fields produce `SchemaDriftWarning`, never exceptions
- Iceberg fields (`iceberg_split_count`, `iceberg_file_count`, `iceberg_partition_spec_id`) are typed fields on `PlanNode`
- Multi-version fixture corpus (429/455/480) exists with live-captured data
- Syrupy snapshot tests gate all parsed output in CI (18 snapshots, 357 tests pass)
- `ExplainPlan` fully removed from public ports; isolated to internal adapter bridge

---

_Verified: 2026-04-12_
_Verifier: Claude (gsd-verifier)_
