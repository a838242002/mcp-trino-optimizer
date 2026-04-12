---
phase: "02"
plan: "05"
subsystem: integration-test-harness
tags: [integration, docker-compose, testcontainers, ci, trino, iceberg, lakekeeper]
dependency_graph:
  requires: ["02-03", "02-04"]
  provides: ["integration-test-harness", "ci-integration-job"]
  affects: [".github/workflows/ci.yml", "tests/integration/"]
tech_stack:
  added:
    - testcontainers[trino,minio]>=4.14.2 (DockerCompose session fixture)
    - trino.dbapi direct DBAPI for test DDL bypass (D-25)
  patterns:
    - session-scoped DockerCompose fixture with lazy testcontainers import
    - DDL bypass via raw trino-python-client, never TrinoClient
    - @pytest.mark.integration opt-in marker for docker-dependent tests
key_files:
  created:
    - .testing/docker-compose.yml
    - .testing/trino/etc/catalog/iceberg.properties
    - tests/integration/__init__.py
    - tests/integration/conftest.py
    - tests/integration/fixtures.py
    - tests/integration/test_fetch_plans.py
    - tests/integration/test_cancellation.py
    - tests/integration/test_auth.py
    - tests/integration/test_capabilities.py
    - tests/integration/test_metadata_tables.py
    - tests/integration/test_event_loop_lag.py
  modified:
    - .github/workflows/ci.yml
    - .env.example
    - CONTRIBUTING.md
decisions:
  - "Lazy testcontainers import in conftest.py guards non-integration runs from ModuleNotFoundError"
  - "DDL bypass (seed_iceberg_table) uses raw trino.dbapi.connect, not TrinoClient, per D-25"
  - "CI integration job fires on push-to-main only (not on PRs) to avoid burning Docker minutes on every PR"
  - "JWT auth integration test skipped with TODO for Phase 9 (requires JWT issuer in compose)"
  - "TrinoClient.probe_capabilities is a stub in Plan 03; test_capabilities calls the module-level probe_capabilities from capabilities.py directly"
metrics:
  duration_minutes: 25
  completed_date: "2026-04-12"
  tasks_completed: 2
  tasks_total: 2
  files_created: 11
  files_modified: 3
requirements_delivered:
  - TRN-01
  - TRN-02
  - TRN-03
  - TRN-06
  - TRN-07
  - TRN-08
  - TRN-09
  - TRN-10
  - TRN-11
  - TRN-14
  - TRN-15
---

# Phase 02 Plan 05: Integration Harness & CI Summary

**One-liner:** Docker-compose stack (Trino 480 + Lakekeeper + Postgres + MinIO) with testcontainers session fixture, 6 integration test files covering all TRN requirements, and CI integration job wired for push-to-main.

## What Was Built

### Task 1: Docker-compose stack + testcontainers fixtures + DDL helper

- **`.testing/docker-compose.yml`** — 8-service stack: `postgres:16-alpine` (Lakekeeper metadata), `minio/minio` (object store), `createbuckets` (mc init job), `migrate` (Lakekeeper DB migration), `lakekeeper` (REST Iceberg catalog), `bootstrap` (POST /management/v1/bootstrap), `initwarehouse` (POST /management/v1/warehouse), `trinodb/trino:480` (query engine). All ports bound to 127.0.0.1. Network: `mcp-trino-test`.
- **`.testing/trino/etc/catalog/iceberg.properties`** — Iceberg connector pointing at Lakekeeper REST catalog with MinIO S3 storage.
- **`tests/integration/conftest.py`** — Session-scoped `compose_stack` (DockerCompose with lazy import), `trino_host`, `seeded_stack` (seeds test table once per session), and `trino_client` fixtures.
- **`tests/integration/fixtures.py`** — DDL bypass helper using raw `trino.dbapi.connect` (not TrinoClient) for CREATE TABLE / INSERT seeding (D-25 / T-02-15).

### Task 2: Integration tests + CI wiring + docs

Six integration test files, each `@pytest.mark.integration`:

| File | TRN requirements | Coverage |
|------|-----------------|----------|
| `test_fetch_plans.py` | TRN-01, TRN-09 | EXPLAIN JSON / ANALYZE / DISTRIBUTED + Iceberg table |
| `test_cancellation.py` | TRN-06 | Timeout returns TimeoutResult, concurrent queries, cancel by ID |
| `test_auth.py` | TRN-03 | auth_mode=none success, basic auth path, JWT skipped (Phase 9) |
| `test_capabilities.py` | TRN-07, TRN-08, TRN-14 | Detects Trino 480, iceberg catalog, metadata tables available, frozen dataclass |
| `test_metadata_tables.py` | TRN-10 | All 6 Iceberg metadata tables + system.runtime.queries |
| `test_event_loop_lag.py` | TRN-02, TRN-15 | 50ms ticker asserts no gap > 100ms during 4 concurrent queries |

**CI:** `.github/workflows/ci.yml` integration job changed from `if: false` to `if: github.event_name == 'push' && github.ref == 'refs/heads/main'`.

**`.env.example`** updated with full `MCPTO_TRINO_*` variable reference (all commented out per T-02-16).

**`CONTRIBUTING.md`** updated with SqlClassifier invariant, `assert_read_only` requirement, and DDL boundary documentation.

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| 1 | `fec1135` | feat(02-05): docker-compose stack + testcontainers fixtures + DDL bypass helper |
| 2 | `35ce171` | feat(02-05): integration tests + CI wiring + docs update |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Lazy testcontainers import to prevent non-integration test failures**
- **Found during:** Task 2 verification (running `uv run pytest -m "not integration" -x`)
- **Issue:** `tests/integration/conftest.py` imported `testcontainers.compose.DockerCompose` at module level. pytest collects all `conftest.py` files before running any test, causing `ModuleNotFoundError: No module named 'testcontainers'` even for non-integration runs on machines where dev extras are not fully installed.
- **Fix:** Moved `from testcontainers.compose import DockerCompose` inside the `compose_stack` fixture body with a `pytest.skip()` fallback. Used `TYPE_CHECKING` guard for the type annotation. Non-integration runs now collect cleanly.
- **Files modified:** `tests/integration/conftest.py`
- **Commit:** `35ce171`

## Known Stubs

None — this plan is an integration test harness, not a production feature. The `TrinoClient.probe_capabilities` stub (returns `{}`) from Plan 03 is bypassed by calling `probe_capabilities()` from `capabilities.py` directly in `test_capabilities.py`. That stub is tracked in the Plan 03 summary and resolved in Plan 04.

## Threat Flags

None — no new network endpoints, auth paths, or trust boundaries introduced beyond what the plan's threat model documents (T-02-15, T-02-16, T-02-17 are all mitigated as designed).

## Self-Check: PASSED

Files created/exist:
- .testing/docker-compose.yml: FOUND
- .testing/trino/etc/catalog/iceberg.properties: FOUND
- tests/integration/__init__.py: FOUND
- tests/integration/conftest.py: FOUND
- tests/integration/fixtures.py: FOUND
- tests/integration/test_fetch_plans.py: FOUND
- tests/integration/test_cancellation.py: FOUND
- tests/integration/test_auth.py: FOUND
- tests/integration/test_capabilities.py: FOUND
- tests/integration/test_metadata_tables.py: FOUND
- tests/integration/test_event_loop_lag.py: FOUND

Commits exist:
- fec1135: FOUND
- 35ce171: FOUND

Non-integration suite: 201 passed, 21 deselected
