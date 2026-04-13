---
phase: 5
slug: recommendation-engine
status: complete
nyquist_compliant: true
wave_0_complete: true
created: 2026-04-13
updated: 2026-04-14
---

# Phase 5 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x |
| **Config file** | `pyproject.toml` ([tool.pytest.ini_options]) |
| **Quick run command** | `uv run pytest tests/recommender/ -x -q` |
| **Full suite command** | `uv run pytest tests/recommender/ -v --tb=short` |
| **Estimated runtime** | ~0.11 seconds |
| **Total tests** | 173 |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/recommender/ -x -q`
- **After every plan wave:** Run `uv run pytest tests/recommender/ -v --tb=short`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** <1 second

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 01-T1 | 01 | 1 | REC-01 | T-05-02 | Priority scoring deterministic | unit | `uv run pytest tests/recommender/test_scoring.py -x` | tests/recommender/test_scoring.py | ✅ green |
| 01-T1 | 01 | 1 | REC-02 | — | Recommendation fields complete | unit | `uv run pytest tests/recommender/test_models.py -x` | tests/recommender/test_models.py | ✅ green |
| 02-T2 | 02 | 2 | REC-03 | T-05-03 | No user-origin text in narrative | unit | `uv run pytest tests/recommender/test_templates.py -x` | tests/recommender/test_templates.py | ✅ green |
| 02-T1 | 02 | 2 | REC-04 | T-05-05 | Conflict resolution deterministic | unit | `uv run pytest tests/recommender/test_conflicts.py -x` | tests/recommender/test_conflicts.py | ✅ green |
| 02-T1 | 02 | 2 | REC-05 | T-05-04 | Session property from resource only | unit | `uv run pytest tests/recommender/test_session_properties.py -x` | tests/recommender/test_session_properties.py | ✅ green |
| 03-T1 | 03 | 3 | REC-06 | T-05-07 | Health summary from evidence only | unit | `uv run pytest tests/recommender/test_health.py -x` | tests/recommender/test_health.py | ✅ green |
| 03-T2 | 03 | 3 | REC-07 | T-05-08 | Bottleneck ranking from metrics only | unit | `uv run pytest tests/recommender/test_bottleneck.py -x` | tests/recommender/test_bottleneck.py | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

### Additional Coverage

| Test File | Tests | Coverage |
|-----------|-------|----------|
| test_impact.py | 49 | All 14 per-rule impact extractors with edge cases |
| test_engine.py | 8 | Engine pipeline: scoring, conflicts, session properties |
| test_engine_integration.py | 8 | Full pipeline: EngineResult -> RecommendationReport |
| conftest.py | — | Shared fixtures: sample_finding, mock plans |

---

## Wave 0 Requirements

- [x] `tests/recommender/` — directory created with `__init__.py`
- [x] `tests/recommender/conftest.py` — shared fixtures (sample RuleFinding objects, mock EngineResult lists)

*Existing pytest infrastructure covers framework installation.*

---

## Manual-Only Verifications

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 1s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** complete

---

## Validation Audit 2026-04-14

| Metric | Count |
|--------|-------|
| Gaps found | 0 |
| Resolved | 0 |
| Escalated | 0 |
| Requirements covered | 7/7 |
| Total tests | 173 |
| Test files | 10 |

All 7 requirements (REC-01 through REC-07) have automated verification covering the specified secure behaviors. Test paths corrected from pre-execution draft (`tests/unit/recommender/` -> `tests/recommender/`).
