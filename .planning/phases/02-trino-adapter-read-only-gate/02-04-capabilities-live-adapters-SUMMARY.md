---
phase: "02"
plan: "04"
subsystem: "trino-adapter"
tags: ["capabilities", "version-probe", "live-adapters", "hexagonal", "ports-and-adapters"]
dependency_graph:
  requires:
    - "02-01 (classifier, SqlClassifier gate)"
    - "02-02 (ports: PlanSource, StatsSource, CatalogSource)"
    - "02-03 (TrinoClient, TrinoThreadPool, TimeoutResult)"
  provides:
    - "CapabilityMatrix + probe_capabilities"
    - "LivePlanSource (PlanSource implementation)"
    - "LiveStatsSource (StatsSource implementation)"
    - "LiveCatalogSource (CatalogSource implementation)"
  affects:
    - "Phase 4 rule engine (version-gated rules consume CapabilityMatrix)"
    - "02-05 integration tests (consume all four artifacts)"
tech_stack:
  added: []
  patterns:
    - "Frozen dataclass for immutable capability snapshot"
    - "TYPE_CHECKING guard to break circular import between adapters and client"
    - "Suffix allowlist for injection prevention before network call"
key_files:
  created:
    - "src/mcp_trino_optimizer/adapters/trino/capabilities.py"
    - "src/mcp_trino_optimizer/adapters/trino/live_plan_source.py"
    - "src/mcp_trino_optimizer/adapters/trino/live_stats_source.py"
    - "src/mcp_trino_optimizer/adapters/trino/live_catalog_source.py"
    - "tests/adapters/test_capabilities.py"
  modified: []
decisions:
  - "LivePlanSource raises TrinoTimeoutError on timeout (partial EXPLAIN plan is useless)"
  - "LiveStatsSource and LiveCatalogSource return partial data on timeout (best-effort is useful)"
  - "LiveCatalogSource suffix allowlist applied before TrinoClient call (defense-in-depth over T-02-13)"
  - "capabilities.py uses TYPE_CHECKING guard to avoid circular import with client.py"
metrics:
  duration_minutes: 20
  completed_date: "2026-04-12"
  tasks_completed: 2
  files_created: 5
  files_modified: 0
  tests_added: 12
---

# Phase 2 Plan 4: Capabilities + Live Adapters Summary

**One-liner:** Frozen CapabilityMatrix with Trino version gate (< 429 refused) plus three thin live adapter classes implementing the PlanSource/StatsSource/CatalogSource hexagonal port protocols via TrinoClient.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | CapabilityMatrix + version probe + refuse Trino < 429 | d9073c5 | `capabilities.py`, `test_capabilities.py` |
| 2 | Live port adapters (LivePlanSource, LiveStatsSource, LiveCatalogSource) | f3f192f | `live_plan_source.py`, `live_stats_source.py`, `live_catalog_source.py` |

## What Was Built

### Task 1: CapabilityMatrix + Version Probe

`capabilities.py` implements:
- `parse_trino_version(version_str)` — extracts leading numeric portion from strings like `"480"` or `"480-e"` using `re.compile(r"^(\d+)")`.
- `MINIMUM_TRINO_VERSION = 429` constant.
- `CapabilityMatrix` — frozen dataclass with fields: `trino_version`, `trino_version_major`, `catalogs` (frozenset), `iceberg_catalog_name`, `iceberg_metadata_tables_available`, `probed_at`.
- `probe_capabilities(client, settings)` — async coroutine that:
  1. Fetches version via `SELECT node_version FROM system.runtime.nodes LIMIT 1`
  2. Parses and gates on `< 429` → raises `TrinoVersionUnsupported`
  3. Enumerates catalogs via `SHOW CATALOGS`
  4. Probes Iceberg metadata availability if the configured catalog is found
  5. Returns immutable `CapabilityMatrix`

12 tests cover: version parsing edge cases, frozen dataclass invariant, mock-based probe flows (reject 428, accept 429/480, missing iceberg catalog).

### Task 2: Live Port Adapters

Three thin delegation classes that implement the hexagonal port protocols:

**LivePlanSource** (`live_plan_source.py`):
- Delegates `fetch_plan`, `fetch_analyze_plan`, `fetch_distributed_plan` to `TrinoClient`.
- Raises `TrinoTimeoutError` on `TimeoutResult` (partial EXPLAIN is not useful).

**LiveStatsSource** (`live_stats_source.py`):
- Delegates `fetch_table_stats` (wraps `TrinoClient.fetch_stats`) and `fetch_system_runtime`.
- Returns partial data on timeout (best-effort).
- Includes `_parse_show_stats()` helper to convert SHOW STATS FOR rows into the port return shape.

**LiveCatalogSource** (`live_catalog_source.py`):
- Delegates `fetch_iceberg_metadata` (wraps `TrinoClient.fetch_iceberg_metadata`), `fetch_catalogs`, `fetch_schemas`.
- **T-02-13 mitigation**: suffix allowlist (`snapshots`, `files`, `manifests`, `partitions`, `history`, `refs`) — `ValueError` raised before any network call for unknown suffixes.
- Catalog/schema identifiers double-quoted in SQL (passed through classifier inside TrinoClient).

## Deviations from Plan

None — plan executed exactly as written. The `mypy --strict` check on the full `adapters/trino/` directory shows a pre-existing `types-requests` stubs error in `auth.py` (from Plan 02-02), which is out of scope for this plan. All three new files pass `mypy --strict` cleanly in isolation.

## Threat Surface

| Flag | File | Description |
|------|------|-------------|
| Mitigated: T-02-13 | `live_catalog_source.py` | Suffix allowlist prevents injection before network call; catalog/schema quoted in SQL |
| Mitigated: T-02-14 | `capabilities.py` | Trino < 429 refused with structured `TrinoVersionUnsupported` error |

## Known Stubs

None — all data paths are wired to live TrinoClient methods.

## Self-Check

Files exist:
- `src/mcp_trino_optimizer/adapters/trino/capabilities.py` — YES
- `src/mcp_trino_optimizer/adapters/trino/live_plan_source.py` — YES
- `src/mcp_trino_optimizer/adapters/trino/live_stats_source.py` — YES
- `src/mcp_trino_optimizer/adapters/trino/live_catalog_source.py` — YES
- `tests/adapters/test_capabilities.py` — YES

Commits:
- `d9073c5` — feat(02-04): CapabilityMatrix + version probe + refuse Trino < 429
- `f3f192f` — feat(02-04): LivePlanSource + LiveStatsSource + LiveCatalogSource adapters

Test results: 201 passed, 0 failed (all non-integration tests).

## Self-Check: PASSED
