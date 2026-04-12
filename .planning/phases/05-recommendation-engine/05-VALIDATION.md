---
phase: 5
slug: recommendation-engine
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-13
---

# Phase 5 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x |
| **Config file** | `pyproject.toml` ([tool.pytest.ini_options]) |
| **Quick run command** | `uv run pytest tests/unit/recommender/ -x -q` |
| **Full suite command** | `uv run pytest tests/unit/recommender/ -v --tb=short` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/unit/recommender/ -x -q`
- **After every plan wave:** Run `uv run pytest tests/unit/recommender/ -v --tb=short`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD | 01 | 1 | REC-01 | — | Priority scoring deterministic | unit | `uv run pytest tests/unit/recommender/test_scorer.py -x` | ❌ W0 | ⬜ pending |
| TBD | 01 | 1 | REC-02 | — | Recommendation fields complete | unit | `uv run pytest tests/unit/recommender/test_models.py -x` | ❌ W0 | ⬜ pending |
| TBD | 01 | 1 | REC-03 | T-05-01 | No user-origin text in narrative | unit | `uv run pytest tests/unit/recommender/test_templates.py -x` | ❌ W0 | ⬜ pending |
| TBD | 02 | 1 | REC-04 | — | Conflict resolution deterministic | unit | `uv run pytest tests/unit/recommender/test_conflicts.py -x` | ❌ W0 | ⬜ pending |
| TBD | 02 | 1 | REC-05 | — | Session property from resource only | unit | `uv run pytest tests/unit/recommender/test_session_props.py -x` | ❌ W0 | ⬜ pending |
| TBD | 03 | 2 | REC-06 | — | Health summary from evidence only | unit | `uv run pytest tests/unit/recommender/test_table_health.py -x` | ❌ W0 | ⬜ pending |
| TBD | 03 | 2 | REC-07 | — | Bottleneck ranking from metrics only | unit | `uv run pytest tests/unit/recommender/test_bottleneck.py -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/unit/recommender/` — directory created with `__init__.py`
- [ ] `tests/unit/recommender/conftest.py` — shared fixtures (sample RuleFinding objects, mock EngineResult lists, mock CapabilityMatrix)

*Existing pytest infrastructure covers framework installation.*

---

## Manual-Only Verifications

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
