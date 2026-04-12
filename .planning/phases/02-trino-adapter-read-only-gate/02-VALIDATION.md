---
phase: 2
slug: trino-adapter-read-only-gate
status: complete
nyquist_compliant: true
wave_0_complete: true
created: 2026-04-12
audited: 2026-04-12
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + pytest-asyncio 1.3.x |
| **Config file** | `pyproject.toml` [tool.pytest.ini_options] |
| **Quick run command** | `uv run pytest -m "not integration" --tb=short -q` |
| **Full suite command** | `uv run pytest --tb=short -q` |
| **Estimated runtime** | ~2 seconds (unit/non-integration), ~90 seconds (full with integration) |
| **Current result** | 201 passed (non-integration) |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest -m "not integration" --tb=short -q`
- **After every plan wave:** Run `uv run pytest --tb=short -q`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 2 seconds (actual) / 15 seconds (budget)

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 02-01-01 | 01 | 1 | TRN-04, TRN-05 | T-02-01 | SqlClassifier rejects all write statements | unit | `uv run pytest tests/safety/test_sql_classifier.py -q` | ✅ | ✅ green |
| 02-01-02 | 01 | 1 | TRN-05 | T-02-02 | Architectural test: every TrinoClient method with sql param calls assert_read_only first | unit | `uv run pytest tests/adapters/test_trino_client_invariant.py -q` | ✅ | ✅ green |
| 02-02-01 | 02 | 1 | TRN-01, TRN-03 | — | EXPLAIN JSON/ANALYZE/DISTRIBUTED fetched correctly | integration | `uv run pytest tests/integration/test_fetch_plans.py -q` | ✅ | ✅ green (integration, requires docker) |
| 02-02-02 | 02 | 1 | TRN-09 | T-02-03 | JWT never appears in any log line | unit | `uv run pytest tests/adapters/test_auth.py -q` | ✅ | ✅ green |
| 02-03-01 | 03 | 2 | TRN-02, TRN-06 | T-02-04 | Cancel confirmed via DELETE /v1/query/{queryId} | integration | `uv run pytest tests/integration/test_cancellation.py -q` | ✅ | ✅ green (integration, requires docker) |
| 02-03-02 | 03 | 2 | TRN-15 | — | Event loop never blocked > 100ms during concurrent queries | integration | `uv run pytest tests/integration/test_event_loop_lag.py -q` | ✅ | ✅ green (integration, requires docker) |
| 02-04-01 | 04 | 2 | TRN-07, TRN-08, TRN-14 | — | Version probe refuses Trino < 429 | unit + integration | `uv run pytest tests/adapters/test_capabilities.py -q` | ✅ | ✅ green |
| 02-05-01 | 05 | 3 | TRN-10, TRN-12, TRN-13 | — | Iceberg metadata tables readable; offline produces same type as live | integration | `uv run pytest tests/integration/test_metadata_tables.py -q` | ✅ | ✅ green (integration, requires docker) |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

**Note on file name deviations:** Executors used slightly different file names than the pre-execution plan (e.g., `test_trino_client_invariant.py` vs `test_classifier_invariant.py`, `test_cancellation.py` vs `test_cancel.py`, `test_fetch_plans.py` vs `test_trino_adapter.py`, `test_metadata_tables.py` vs `test_metadata.py`). All behaviors are covered.

---

## Wave 0 Requirements — Complete

- [x] `tests/safety/test_sql_classifier.py` — 64 parameterized cases for TRN-04, TRN-05
- [x] `tests/adapters/test_trino_client_invariant.py` — AST-based TRN-05 architectural guard (10 tests)
- [x] `tests/adapters/test_auth.py` — auth mode unit tests (Basic, JWT, no-auth, callable token)
- [x] `tests/adapters/test_capabilities.py` — version probe unit tests (12 tests)
- [x] `tests/integration/conftest.py` — testcontainers DockerCompose session fixture
- [x] `tests/integration/fixtures.py` — DDL bypass helper for test seeding (D-25)

**Additional tests delivered (beyond validation plan):**
- `tests/adapters/test_pool.py` — Pool + QueryIdCell + TimeoutResult (11 tests)
- `tests/adapters/test_query_logging.py` — Statement logging invariants (4 tests)
- `tests/adapters/test_auth_retry.py` — D-13 retry-once on 401 (6 tests)
- `tests/adapters/test_offline_plan_source.py` — OfflinePlanSource with 1MB cap (22 tests)
- `tests/adapters/test_port_conformance.py` — Port protocol conformance tests
- `tests/adapters/test_ports.py` — Port unit tests
- `tests/integration/test_auth.py` — Live auth integration tests
- `tests/integration/test_capabilities.py` — Live capability probe integration tests

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| JWT sidecar refresh picked up | TRN-09 | Requires external process updating env var | 1. Start server with JWT auth 2. Update MCPTO_TRINO_JWT env var 3. Issue new query 4. Verify new token used |

---

## Validation Sign-Off

- [x] All tasks have automated verification
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all requirements
- [x] No watch-mode flags
- [x] Feedback latency < 15s (actual: ~2s)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** 2026-04-12 — gsd-validate-phase audit

---

## Validation Audit 2026-04-12

| Metric | Count |
|--------|-------|
| Tasks in map | 8 |
| COVERED | 8 |
| PARTIAL | 0 |
| MISSING | 0 |
| Escalated to manual-only | 0 (pre-existing: 1 JWT sidecar) |
| Additional tests found (beyond plan) | 8 |
