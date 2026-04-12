---
phase: 4
slug: rule-engine-13-deterministic-rules
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-13
---

# Phase 4 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + pytest-asyncio 1.x |
| **Config file** | `pyproject.toml` (`[tool.pytest.ini_options]`) |
| **Quick run command** | `uv run pytest -m "not integration" -x -q` |
| **Full suite command** | `uv run pytest -m "not integration" -x` |
| **Integration command** | `uv run pytest -m integration -x --timeout=300` |
| **Estimated runtime** | ~10 seconds (unit), ~5 min (integration) |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest -m "not integration" -x -q`
- **After every plan wave:** Run `uv run pytest -m "not integration" -x`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds (unit)

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 4-W0-01 | W0 | 0 | RUL-01 | — | N/A | unit | `uv run pytest tests/rules/test_registry.py -x -q` | ❌ W0 | ⬜ pending |
| 4-W0-02 | W0 | 0 | PLN-01 | — | N/A | unit | `uv run pytest tests/unit/test_parser_walk.py -x -q` | ❌ W0 | ⬜ pending |
| 4-01-01 | 01 | 1 | RUL-01,RUL-02 | — | N/A | unit | `uv run pytest tests/rules/test_engine.py -x -q` | ❌ W0 | ⬜ pending |
| 4-01-02 | 01 | 1 | RUL-03,RUL-04 | — | N/A | unit | `uv run pytest tests/rules/test_engine_isolation.py -x -q` | ❌ W0 | ⬜ pending |
| 4-01-03 | 01 | 1 | RUL-05 | — | N/A | unit | `uv run pytest tests/rules/test_findings.py -x -q` | ❌ W0 | ⬜ pending |
| 4-02-01 | 02 | 2 | RUL-07,RUL-21 | — | N/A | unit | `uv run pytest tests/rules/test_r1_missing_stats.py -x -q` | ❌ W0 | ⬜ pending |
| 4-02-02 | 02 | 2 | RUL-08,RUL-21 | — | N/A | unit | `uv run pytest tests/rules/test_r2_partition_pruning.py -x -q` | ❌ W0 | ⬜ pending |
| 4-02-03 | 02 | 2 | RUL-09,RUL-21 | — | N/A | unit | `uv run pytest tests/rules/test_r3_predicate_pushdown.py -x -q` | ❌ W0 | ⬜ pending |
| 4-02-04 | 02 | 2 | RUL-10,RUL-21 | — | N/A | unit | `uv run pytest tests/rules/test_r4_dynamic_filtering.py -x -q` | ❌ W0 | ⬜ pending |
| 4-03-01 | 03 | 3 | RUL-11,RUL-21 | — | N/A | unit | `uv run pytest tests/rules/test_r5_broadcast_join.py -x -q` | ❌ W0 | ⬜ pending |
| 4-03-02 | 03 | 3 | RUL-12,RUL-21 | — | N/A | unit | `uv run pytest tests/rules/test_r6_join_order.py -x -q` | ❌ W0 | ⬜ pending |
| 4-03-03 | 03 | 3 | RUL-13,RUL-21 | — | N/A | unit | `uv run pytest tests/rules/test_r7_skew.py -x -q` | ❌ W0 | ⬜ pending |
| 4-03-04 | 03 | 3 | RUL-14,RUL-21 | — | N/A | unit | `uv run pytest tests/rules/test_r8_exchange.py -x -q` | ❌ W0 | ⬜ pending |
| 4-03-05 | 03 | 3 | RUL-15,RUL-21 | — | N/A | unit | `uv run pytest tests/rules/test_r9_low_selectivity.py -x -q` | ❌ W0 | ⬜ pending |
| 4-04-01 | 04 | 4 | RUL-16,RUL-21 | — | N/A | unit | `uv run pytest tests/rules/test_i1_small_files.py -x -q` | ❌ W0 | ⬜ pending |
| 4-04-02 | 04 | 4 | RUL-17,RUL-21 | — | N/A | unit | `uv run pytest tests/rules/test_i3_delete_files.py -x -q` | ❌ W0 | ⬜ pending |
| 4-04-03 | 04 | 4 | RUL-18,RUL-21 | — | N/A | unit | `uv run pytest tests/rules/test_i6_stale_snapshots.py -x -q` | ❌ W0 | ⬜ pending |
| 4-04-04 | 04 | 4 | RUL-19,RUL-21 | — | N/A | unit | `uv run pytest tests/rules/test_i8_partition_transform.py -x -q` | ❌ W0 | ⬜ pending |
| 4-04-05 | 04 | 4 | RUL-20,RUL-21 | — | N/A | unit | `uv run pytest tests/rules/test_d11_cost_vs_actual.py -x -q` | ❌ W0 | ⬜ pending |
| 4-05-01 | 05 | 5 | RUL-21 | — | N/A | unit | `uv run pytest tests/rules/test_thresholds.py -x -q` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/rules/__init__.py` — rules test package
- [ ] `tests/rules/test_registry.py` — registry stub tests (RUL-01)
- [ ] `tests/rules/test_engine.py` — engine stub tests (RUL-01,02)
- [ ] `tests/rules/test_engine_isolation.py` — isolation stubs (RUL-03,04)
- [ ] `tests/rules/test_findings.py` — finding model stubs (RUL-05)
- [ ] `tests/rules/test_r1_missing_stats.py` through `test_d11_cost_vs_actual.py` — 13 rule test stubs
- [ ] `tests/rules/test_thresholds.py` — parameterized threshold data-driven test stub (RUL-21)
- [ ] `tests/unit/test_parser_walk.py` — walk() WR-01 fix regression test

*All stub tests start as `pytest.mark.skip("Wave 0 stub")` and are un-skipped as implementation lands.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| I3 delete-file detection on real Iceberg table | RUL-17 | Requires live Trino + Iceberg with actual delete files written | Run integration test after docker-compose stack is up with position deletes loaded |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
