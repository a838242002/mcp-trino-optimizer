---
phase: 2
slug: trino-adapter-read-only-gate
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-12
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
| **Estimated runtime** | ~15 seconds (unit), ~90 seconds (full with integration) |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest -m "not integration" --tb=short -q`
- **After every plan wave:** Run `uv run pytest --tb=short -q`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 02-01-01 | 01 | 1 | TRN-04, TRN-05 | T-02-01 | SqlClassifier rejects all write statements | unit | `uv run pytest tests/safety/test_sql_classifier.py -q` | ❌ W0 | ⬜ pending |
| 02-01-02 | 01 | 1 | TRN-05 | T-02-02 | Architectural test: every TrinoClient method with sql param calls assert_read_only first | unit | `uv run pytest tests/adapters/test_classifier_invariant.py -q` | ❌ W0 | ⬜ pending |
| 02-02-01 | 02 | 1 | TRN-01, TRN-03 | — | EXPLAIN JSON/ANALYZE/DISTRIBUTED fetched correctly | integration | `uv run pytest tests/integration/test_trino_adapter.py -q` | ❌ W0 | ⬜ pending |
| 02-02-02 | 02 | 1 | TRN-09 | T-02-03 | JWT never appears in any log line | unit | `uv run pytest tests/adapters/test_auth.py -q` | ❌ W0 | ⬜ pending |
| 02-03-01 | 03 | 2 | TRN-02, TRN-06 | T-02-04 | Cancel confirmed via DELETE /v1/query/{queryId} | integration | `uv run pytest tests/integration/test_cancel.py -q` | ❌ W0 | ⬜ pending |
| 02-03-02 | 03 | 2 | TRN-15 | — | Event loop never blocked > 100ms during concurrent queries | integration | `uv run pytest tests/integration/test_event_loop_lag.py -q` | ❌ W0 | ⬜ pending |
| 02-04-01 | 04 | 2 | TRN-07, TRN-08, TRN-14 | — | Version probe refuses Trino < 429 | unit + integration | `uv run pytest tests/adapters/test_capabilities.py -q` | ❌ W0 | ⬜ pending |
| 02-05-01 | 05 | 3 | TRN-10, TRN-12, TRN-13 | — | Iceberg metadata tables readable; offline produces same type as live | integration | `uv run pytest tests/integration/test_metadata.py -q` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/safety/test_sql_classifier.py` — stubs for TRN-04, TRN-05
- [ ] `tests/adapters/test_classifier_invariant.py` — architectural introspection test stub
- [ ] `tests/adapters/test_auth.py` — auth mode unit tests
- [ ] `tests/adapters/test_capabilities.py` — version probe unit tests
- [ ] `tests/integration/conftest.py` — testcontainers DockerCompose session fixture
- [ ] `tests/integration/fixtures.py` — DDL bypass helper for test seeding (D-25)

*Existing `tests/conftest.py` structlog fixture covers all phase requirements.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| JWT sidecar refresh picked up | TRN-09 | Requires external process updating env var | 1. Start server with JWT auth 2. Update MCPTO_TRINO_JWT env var 3. Issue new query 4. Verify new token used |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
