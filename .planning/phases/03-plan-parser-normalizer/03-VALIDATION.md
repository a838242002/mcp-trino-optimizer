---
phase: 3
slug: plan-parser-normalizer
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-04-12
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
| 03-01-T1 | 01 | 1 | PLN-01, PLN-02, PLN-03, PLN-04, PLN-07 | T-03-01, T-03-04 | 1MB size cap + non-backtracking regex for DoS prevention | unit | `uv run pytest tests/parser/test_models.py tests/parser/test_parser.py -x` | ❌ W0 | ⬜ pending |
| 03-01-T2 | 01 | 1 | PLN-05 | — | N/A | unit | `uv run pytest tests/parser/test_normalizer.py tests/adapters/test_offline_plan_source.py tests/adapters/test_port_conformance.py -x` | ❌ W0 | ⬜ pending |
| 03-02-T1 | 02 | 2 | PLN-06 | — | N/A | capture | `uv run python scripts/capture_fixtures.py` | ❌ W0 | ⬜ pending |
| 03-02-T2 | 02 | 2 | PLN-06 | — | N/A | snapshot | `uv run pytest tests/parser/test_fixture_snapshots.py -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/parser/__init__.py` — package marker
- [ ] `tests/parser/test_models.py` — PlanNode, EstimatedPlan, ExecutedPlan model tests
- [ ] `tests/parser/test_parser.py` — JSON and text parsing tests
- [ ] `tests/parser/test_normalizer.py` — ScanFilterAndProject normalization tests
- [ ] `tests/parser/test_fixture_snapshots.py` — syrupy snapshot tests for multi-version fixtures
- [ ] `tests/fixtures/explain/` — fixture directory structure
- [ ] `scripts/capture_fixtures.py` — fixture capture script

*Existing infrastructure: pyproject.toml already has pytest, syrupy in dev deps.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Multi-version fixture capture from docker-compose | PLN-06 | Requires running 3 Trino versions sequentially | Run `scripts/capture_fixtures.py` with each Trino version tag |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 5s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
