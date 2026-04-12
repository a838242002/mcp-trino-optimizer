---
phase: 02-trino-adapter-read-only-gate
plan: "02"
subsystem: adapter-layer
tags:
  - hexagonal-architecture
  - ports-and-adapters
  - offline-mode
  - domain-types
dependency_graph:
  requires:
    - "01-06-phase1-complete"  # project scaffold with pyproject.toml, src layout
  provides:
    - "PlanSource Protocol (ports/plan_source.py)"
    - "StatsSource Protocol (ports/stats_source.py)"
    - "CatalogSource Protocol (ports/catalog_source.py)"
    - "ExplainPlan domain dataclass"
    - "OfflinePlanSource adapter (adapters/offline/json_plan_source.py)"
  affects:
    - "Phase 3 plan parser — will extend ExplainPlan with typed hierarchy"
    - "Phase 4 rule engine — consumes PlanSource/StatsSource/CatalogSource ports"
    - "Phase 8 MCP tools — offline_analyze tool will use OfflinePlanSource"
tech_stack:
  added:
    - "orjson — used for fast JSON parsing in OfflinePlanSource"
  patterns:
    - "runtime_checkable Protocol for duck-type-safe port contracts"
    - "Literal['estimated', 'executed', 'distributed'] for plan_type exhaustiveness"
    - "1MB byte-level size cap enforced before parsing (T-02-05)"
key_files:
  created:
    - src/mcp_trino_optimizer/ports/__init__.py
    - src/mcp_trino_optimizer/ports/plan_source.py
    - src/mcp_trino_optimizer/ports/stats_source.py
    - src/mcp_trino_optimizer/ports/catalog_source.py
    - src/mcp_trino_optimizer/adapters/__init__.py
    - src/mcp_trino_optimizer/adapters/offline/__init__.py
    - src/mcp_trino_optimizer/adapters/offline/json_plan_source.py
    - tests/adapters/__init__.py
    - tests/adapters/test_ports.py
    - tests/adapters/test_offline_plan_source.py
    - tests/adapters/test_port_conformance.py
  modified: []
decisions:
  - "ExplainPlan.raw_text field added (not in CONTEXT.md D-21) for round-trip fidelity — needed so Phase 8 can echo back exact input without re-serializing"
  - "OfflinePlanSource._detect_plan_type() uses known runtime metric key heuristic (cpuTimeMillis etc.) rather than a discriminator field — Trino EXPLAIN JSON has no explicit type flag"
  - "_parse_json rejects non-dict JSON values (arrays, scalars) with ValueError — EXPLAIN JSON is always an object"
metrics:
  duration_minutes: 5
  completed_date: "2026-04-12"
  tasks_completed: 2
  tasks_total: 2
  files_created: 11
  files_modified: 0
  tests_added: 33
  tests_passing: 33
---

# Phase 02 Plan 02: Hexagonal Ports + OfflinePlanSource Summary

**One-liner:** Three runtime_checkable Protocol ports (PlanSource, StatsSource, CatalogSource) plus ExplainPlan domain dataclass and OfflinePlanSource adapter that parses raw EXPLAIN JSON with 1MB cap and heuristic plan-type detection.

## What Was Built

### Hexagonal Ports (Task 1)

Three Protocol definitions forming the hexagonal adapter boundary described in K-Decision #5:

- **`PlanSource`** — `fetch_plan`, `fetch_analyze_plan`, `fetch_distributed_plan` (all async). Shared by live and offline adapters.
- **`StatsSource`** — `fetch_table_stats`, `fetch_system_runtime` (all async). For table statistics and system.runtime queries.
- **`CatalogSource`** — `fetch_iceberg_metadata`, `fetch_catalogs`, `fetch_schemas` (all async). For Iceberg metadata table queries.

All three use `@runtime_checkable` so `isinstance()` checks work in conformance tests. The ports package has zero imports from `adapters/` — decoupling is enforced by a static AST test.

**`ExplainPlan` domain dataclass** with fields:
- `plan_json: dict[str, Any]` — raw parsed JSON
- `plan_type: Literal["estimated", "executed", "distributed"]`
- `source_trino_version: str | None` — None for offline mode
- `raw_text: str` — original JSON for round-trip fidelity

### OfflinePlanSource Adapter (Task 2)

`adapters/offline/json_plan_source.py` implements `PlanSource` without a Trino connection:

- `fetch_plan(sql)` — treats `sql` as raw JSON text, auto-detects `plan_type` via runtime metric key heuristic
- `fetch_analyze_plan(sql)` — always returns `plan_type="executed"`
- `fetch_distributed_plan(sql)` — always returns `plan_type="distributed"`

Security controls (T-02-05):
- `_validate_size()` checks `len(text.encode("utf-8")) > 1_000_000` before parsing
- `_parse_json()` uses `orjson.loads()` — raises `ValueError("Invalid JSON: ...")` on failure
- Non-dict JSON (arrays, scalars) rejected with `ValueError`

D-15 compliance: no reference to `SqlClassifier` or any live-adapter read-only gate. Verified by AST scan test.

## Tests

| File | Tests | What They Cover |
|------|-------|----------------|
| `tests/adapters/test_ports.py` | 11 | Port Protocol shape, ExplainPlan fields, ports decoupling invariant |
| `tests/adapters/test_offline_plan_source.py` | 15 | Valid JSON, invalid JSON, size limit (over/at boundary), plan type detection, classifier-exempt |
| `tests/adapters/test_port_conformance.py` | 7 | isinstance checks, async method signatures, zero adapter imports in ports |

All 33 tests pass. Full suite (94 tests) passes with no regressions.

## Verification

```
uv run pytest tests/adapters/ -v -x          → 33 passed
uv run pytest -m "not integration" -x -q     → 94 passed
uv run mypy src/mcp_trino_optimizer/ports/ src/mcp_trino_optimizer/adapters/offline/ --strict → Success: no issues found in 6 source files
```

## Deviations from Plan

### Auto-additions (Rule 2)

**1. [Rule 2 - Missing] `raw_text` field on ExplainPlan**
- **Found during:** Task 1 implementation
- **Issue:** CONTEXT.md D-21 specifies three fields. The plan action already included `raw_text` in its code snippet, but CONTEXT.md did not list it.
- **Fix:** Added `raw_text: str = field(default="")` to ExplainPlan — required for Phase 8 offline tool to echo back user input without re-serializing (preserves whitespace, key order).
- **Files modified:** `src/mcp_trino_optimizer/ports/plan_source.py`

**2. [Rule 2 - Missing] Non-dict JSON rejection in `_parse_json`**
- **Found during:** Task 2 implementation
- **Issue:** Plan specified only "invalid JSON" rejection. A valid JSON array `[...]` is syntactically correct but semantically wrong for an EXPLAIN plan.
- **Fix:** Added `isinstance(result, dict)` check with descriptive ValueError.
- **Files modified:** `src/mcp_trino_optimizer/adapters/offline/json_plan_source.py`

### Mypy fixes (Rule 1)

**3. [Rule 1 - Bug] `_detect_plan_type` return type**
- `-> str` is too broad for a `Literal["estimated", "executed", "distributed"]` argument. Fixed to `-> Literal["estimated", "executed"]` (distributed is never returned by this heuristic).
- Removed stale `# type: ignore[return-value]` from `_parse_json`.

## Known Stubs

None. All implemented functionality is fully wired.

## Threat Flags

No new trust boundaries introduced beyond those in the plan's threat model.

| Flag | File | Description |
|------|------|-------------|
| (none) | — | T-02-05 mitigation is implemented (1MB cap + orjson parse) |

## Self-Check: PASSED

| Item | Status |
|------|--------|
| `src/mcp_trino_optimizer/ports/__init__.py` | FOUND |
| `src/mcp_trino_optimizer/ports/plan_source.py` | FOUND |
| `src/mcp_trino_optimizer/ports/stats_source.py` | FOUND |
| `src/mcp_trino_optimizer/ports/catalog_source.py` | FOUND |
| `src/mcp_trino_optimizer/adapters/offline/json_plan_source.py` | FOUND |
| `tests/adapters/test_offline_plan_source.py` | FOUND |
| `tests/adapters/test_port_conformance.py` | FOUND |
| Commit 6f5f806 (ports + ExplainPlan) | FOUND |
| Commit 8c14d7c (OfflinePlanSource + conformance tests) | FOUND |
