---
phase: "03-plan-parser-normalizer"
plan: "01"
subsystem: "parser"
tags: ["parser", "pydantic", "plan-tree", "normalization", "ports"]
dependency_graph:
  requires: []
  provides:
    - "EstimatedPlan: typed plan from EXPLAIN (FORMAT JSON)"
    - "ExecutedPlan: typed plan from EXPLAIN ANALYZE text"
    - "PlanNode: typed operator tree node with model_extra raw bag"
    - "normalize_plan_tree: ScanFilterAndProject decomposition"
    - "PlanSource protocol returning EstimatedPlan/ExecutedPlan"
  affects:
    - "src/mcp_trino_optimizer/ports/plan_source.py"
    - "src/mcp_trino_optimizer/ports/__init__.py"
    - "src/mcp_trino_optimizer/adapters/offline/json_plan_source.py"
    - "src/mcp_trino_optimizer/adapters/trino/live_plan_source.py"
tech_stack:
  added: []
  patterns:
    - "pydantic ConfigDict(extra='allow') as raw dict bag (model_extra IS the raw bag)"
    - "Dual-path parser: JSON for estimated, text/regex for executed"
    - "Bottom-up normalization: children normalized before parents"
    - "SchemaDriftWarning for unexpected structure, ParseError only for truly invalid input"
    - "ExplainPlan moved to adapters/trino/_explain_plan.py as internal bridge type"
key_files:
  created:
    - "src/mcp_trino_optimizer/parser/__init__.py"
    - "src/mcp_trino_optimizer/parser/models.py"
    - "src/mcp_trino_optimizer/parser/parser.py"
    - "src/mcp_trino_optimizer/parser/normalizer.py"
    - "src/mcp_trino_optimizer/adapters/trino/_explain_plan.py"
    - "tests/parser/__init__.py"
    - "tests/parser/test_models.py"
    - "tests/parser/test_parser.py"
    - "tests/parser/test_normalizer.py"
    - "tests/adapters/test_offline_plan_source_v2.py"
  modified:
    - "src/mcp_trino_optimizer/ports/plan_source.py"
    - "src/mcp_trino_optimizer/ports/__init__.py"
    - "src/mcp_trino_optimizer/adapters/offline/json_plan_source.py"
    - "src/mcp_trino_optimizer/adapters/trino/live_plan_source.py"
    - "src/mcp_trino_optimizer/adapters/trino/client.py"
    - "tests/adapters/test_offline_plan_source.py"
    - "tests/adapters/test_ports.py"
decisions:
  - "ExplainPlan moved to adapters/trino/_explain_plan.py as internal bridge; TrinoClient internals unchanged"
  - "normalizer filter heuristic uses SQL keywords + multi-char operators (!=, <>, >, <) not bare = to avoid false positives from table=schema.name descriptors"
  - "ports/plan_source.py imports from parser.models (parser is not adapters, no circular dependency)"
metrics:
  duration: "~45 minutes"
  completed_date: "2026-04-12"
  tasks_completed: 2
  files_changed: 17
---

# Phase 03 Plan 01: Parser Models and Normalizer Summary

**One-liner:** Pydantic-based typed EXPLAIN plan parser with dual JSON/text paths, ScanFilterAndProject decomposition, and clean ExplainPlan removal from ports.

## What Was Built

### Task 1: Parser models and dual-path parser

Created `src/mcp_trino_optimizer/parser/` subpackage with:

- **models.py**: `PlanNode` (with `ConfigDict(extra="allow")` for version-drift tolerance), `CostEstimate`, `OutputSymbol`, `SchemaDriftWarning`, `BasePlan`, `EstimatedPlan`, `ExecutedPlan`, `ParseError`. `model_extra` IS the raw dict bag (PLN-02). No PEP 563 import (pydantic runtime requirement).
- **parser.py**: `parse_estimated_plan()` (JSON path via orjson) and `parse_executed_plan()` (text/regex path for EXPLAIN ANALYZE). Both call `normalize_plan_tree()` before returning. Recursion depth capped at 100 levels (T-03-01 DoS mitigation).
- **normalizer.py**: `normalize_plan_tree()` performs bottom-up ScanFilterAndProject decomposition into Project(Filter(TableScan)) or Project(TableScan). Uses SQL keyword heuristics (WHERE, BETWEEN, LIKE, comparison operators) to detect filter predicates without false positives from `table=schema.name` descriptor lines.
- **`__init__.py`**: Public API re-exporting all domain types and parse functions.

### Task 2: Normalizer + port/adapter migration

- **ports/plan_source.py**: Removed `ExplainPlan` dataclass. `PlanSource` protocol now returns `EstimatedPlan`/`ExecutedPlan`. Imports `EstimatedPlan`/`ExecutedPlan` from `parser.models` (parser is not adapters — no hexagonal boundary violation).
- **ports/`__init__.py`**: Exports `EstimatedPlan`, `ExecutedPlan` instead of `ExplainPlan`.
- **adapters/offline/json_plan_source.py**: Delegates to `parse_estimated_plan`/`parse_executed_plan`. Removed `_detect_plan_type`, `_parse_json`, `_EXECUTED_PLAN_KEYS`. Kept `_validate_size` + empty-string check.
- **adapters/trino/live_plan_source.py**: Bridges TrinoClient's internal `ExplainPlan` to typed domain via parser (TrinoClient internals unchanged).
- **adapters/trino/_explain_plan.py**: New internal-only home for `ExplainPlan` (TrinoClient implementation detail, not public port type).

## Test Results

- `tests/parser/` — 61 tests, all pass
- `tests/adapters/` — 101 tests, all pass
- Full non-integration suite — 273 tests, all pass

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Filter predicate heuristic caused false positives**
- **Found during:** Task 2 normalizer test for "no filter" decomposition
- **Issue:** Original `_FILTER_INDICATORS` frozenset included bare `=` which matched `table = iceberg.schema.test_table` descriptor lines, incorrectly triggering a Filter node
- **Fix:** Replaced with `_FILTER_KEYWORDS` (SQL keywords: WHERE, BETWEEN, LIKE, etc.) + `_COMPARISON_OPS_RE` regex for multi-char operators only (!=, <>, >=, <=, >, <). Bare `=` no longer treated as a predicate indicator.
- **Files modified:** `src/mcp_trino_optimizer/parser/normalizer.py`
- **Commit:** e7cf715 (normalizer), 2992cf5 (final)

**2. [Rule 1 - Bug] Empty string input raised ParseError instead of ValueError**
- **Found during:** Task 2 when running existing test `test_empty_string_raises_value_error`
- **Issue:** Old `OfflinePlanSource._parse_json()` explicitly checked for empty string and raised `ValueError("Invalid JSON: input is empty")`. New parser raised `ParseError` for the same input.
- **Fix:** Added explicit empty-string check back to `OfflinePlanSource._validate_size()` to preserve the `ValueError` contract for this user-facing validation.
- **Files modified:** `src/mcp_trino_optimizer/adapters/offline/json_plan_source.py`
- **Commit:** 2992cf5

**3. [Rule 1 - Bug] ExplainPlan import in TrinoClient broke on ports removal**
- **Found during:** Task 2 when running full test suite after ports migration
- **Issue:** `TrinoClient` imported `ExplainPlan` from `ports.plan_source`. After removing it from ports, all TrinoClient-related tests failed to collect.
- **Fix:** Created `adapters/trino/_explain_plan.py` as the internal home for `ExplainPlan`. Updated `client.py` to import from there. TrinoClient internals unchanged per plan guidance.
- **Files modified:** `src/mcp_trino_optimizer/adapters/trino/client.py`, new `_explain_plan.py`
- **Commit:** 2992cf5

## Known Stubs

None. All parser functionality is fully wired — `parse_estimated_plan` and `parse_executed_plan` produce real typed trees from real input. `iceberg_split_count` and `iceberg_file_count` are `None` for EstimatedPlan (by design — they are runtime metrics not available in EXPLAIN JSON; see PLN-04 and 03-RESEARCH.md).

## Threat Flags

No new security-relevant surface introduced. The parser operates on already-validated (size-capped) input. `model_extra` is read-only evidence (T-03-02 accepted). SchemaDriftWarning output does not contain raw SQL or credentials (T-03-03 mitigated). Recursion depth capped at 100 (T-03-01 mitigated). EXPLAIN ANALYZE regex patterns use non-backtracking quantifiers (T-03-04 mitigated).

## Self-Check

### Files created:
- [x] `src/mcp_trino_optimizer/parser/__init__.py`
- [x] `src/mcp_trino_optimizer/parser/models.py`
- [x] `src/mcp_trino_optimizer/parser/parser.py`
- [x] `src/mcp_trino_optimizer/parser/normalizer.py`
- [x] `tests/parser/test_models.py`
- [x] `tests/parser/test_parser.py`
- [x] `tests/parser/test_normalizer.py`

### Commits:
- [x] 850dd52: test(03-01): add failing tests for parser models and dual-path parser
- [x] e7cf715: feat(03-01): implement parser models, dual-path parser, and normalizer
- [x] 7ea0562: test(03-01): add failing tests for normalizer and port/adapter migration
- [x] 2992cf5: feat(03-01): migrate ports/adapters from ExplainPlan to EstimatedPlan/ExecutedPlan

## Self-Check: PASSED
