---
phase: 04-rule-engine-13-deterministic-rules
verified: 2026-04-13T00:00:00Z
status: gaps_found
score: 3/5 must-haves verified
gaps:
  - truth: "Every rule ships with three fixture classes: synthetic-minimum, realistic-from-compose, and negative-control"
    status: failed
    reason: "R7 (CpuSkew) and D11 (CostVsActual) lack realistic-from-compose test classes. Both test files acknowledge three fixture categories in their docstrings but only implement synthetic + negative-control classes. No fixture JSON files from the Phase 3 compose corpus are loaded in either test file."
    artifacts:
      - path: "tests/rules/test_r7_skew.py"
        issue: "Only TestR7SyntheticMinimum and TestR7NegativeControl classes exist; no TestR7Realistic"
      - path: "tests/rules/test_d11_cost_vs_actual.py"
        issue: "Only TestD11SyntheticMinimum and TestD11NegativeControl classes exist; no TestD11Realistic"
    missing:
      - "TestR7Realistic class loading an ExecutedPlan from tests/fixtures/explain/480/*.json with injected cpu_time_ms values"
      - "TestD11Realistic class loading an EstimatedPlan fixture and an ExecutedPlan fixture with diverging row counts"

  - truth: "Every rule threshold is data-driven with a parameterized test that proves at least one negative-control starts or stops triggering when the threshold changes"
    status: failed
    reason: "The only parametrize in tests/rules/ is test_threshold_defaults_match_citations in test_thresholds.py, which only spot-checks that default float values equal their citation keywords. It does NOT demonstrate that changing a threshold via env var causes a negative-control to start or stop triggering. Individual rules have test_custom_threshold_respected methods but those are standalone assertions, not parameterized negative-control toggles."
    artifacts:
      - path: "tests/rules/test_thresholds.py"
        issue: "Parametrize covers citation-keyword spot-check only; no negative-control toggle pattern"
    missing:
      - "A parametrize test that changes at least one threshold (e.g., skew_ratio, scan_selectivity_threshold, broadcast_max_bytes) and asserts a test case flips from 'no finding' to 'finding' or vice versa"

  - truth: "ruff check src/mcp_trino_optimizer/rules/ passes with 0 errors"
    status: failed
    reason: "9 ruff errors currently exist: 7x RUF100 (unused noqa ARG002 directives) across d11_cost_vs_actual.py, r2_partition_pruning.py, r3_predicate_pushdown.py, r5_broadcast_too_big.py, r7_cpu_skew.py, r8_exchange_volume.py, r9_low_selectivity.py; plus 2x F401 unused imports (Any, PlanNode) in r3_predicate_pushdown.py. All are auto-fixable with --fix."
    artifacts:
      - path: "src/mcp_trino_optimizer/rules/r3_predicate_pushdown.py"
        issue: "Unused import Any (F401), unused import PlanNode (F401), unused noqa ARG002 (RUF100)"
      - path: "src/mcp_trino_optimizer/rules/d11_cost_vs_actual.py"
        issue: "Unused noqa ARG002 directive (RUF100)"
      - path: "src/mcp_trino_optimizer/rules/r2_partition_pruning.py"
        issue: "Unused noqa ARG002 directive (RUF100)"
      - path: "src/mcp_trino_optimizer/rules/r5_broadcast_too_big.py"
        issue: "Unused noqa ARG002 directive (RUF100)"
      - path: "src/mcp_trino_optimizer/rules/r7_cpu_skew.py"
        issue: "Unused noqa ARG002 directive (RUF100)"
      - path: "src/mcp_trino_optimizer/rules/r8_exchange_volume.py"
        issue: "Unused noqa ARG002 directive (RUF100)"
      - path: "src/mcp_trino_optimizer/rules/r9_low_selectivity.py"
        issue: "Unused noqa ARG002 directive (RUF100)"
    missing:
      - "Run: uv run ruff check --fix src/mcp_trino_optimizer/rules/ to auto-fix all 9 errors"
---

# Phase 4: Rule Engine & 13 Deterministic Rules Verification Report

**Phase Goal:** The deterministic core of the product — a plugin registry of rules that each consume a typed plan plus declared evidence, produce structured `RuleFinding` objects pointing at specific plan operator IDs, and never let one rule's failure abort the analysis.
**Verified:** 2026-04-13
**Status:** gaps_found
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Plugin registry: new Rule subclass registered via decorator, engine runs it without touching engine code; engine prefetches evidence union once per analysis | VERIFIED | `registry.register()` works as both decorator and explicit call; `RuleEngine._prefetch_evidence()` collects union of requirements and fetches once; 14 rules run without engine modification |
| 2 | Isolated failure: crashing rule emits RuleError, unavailable evidence emits RuleSkipped, analysis completes | VERIFIED | `engine.py` lines 113-123 catch all exceptions per rule; RuleSkipped emitted for None sources; `test_engine_isolation.py` confirms |
| 3 | All 14 rules produce RuleFinding with rule_id, severity, confidence, message, machine-readable evidence, operator_ids | VERIFIED | All 14 rules exist and are registered; RuleFinding pydantic model enforces all fields; `uv run python -c "..."` returns 14 rule IDs |
| 4 | Each rule has three fixture classes: synthetic-minimum, realistic-from-compose, negative-control | FAILED | R7 and D11 are missing realistic-from-compose classes; I1/I3/I6/I8 cover all three categories via flat functions (test_realistic_* functions present) |
| 5 | Every threshold has sourced citation comment and is proven data-driven by parameterized test | FAILED | Citation comments exist in thresholds.py; individual custom-threshold tests exist per rule; but the SC requires a parameterized test showing negative-control toggles — only test_thresholds.py parametrize exists and it checks citation keywords, not behavior changes |

**Score:** 3/5 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/mcp_trino_optimizer/rules/__init__.py` | Public API re-exports + 14 rule auto-imports | VERIFIED | 14 explicit named imports + all public symbols exported |
| `src/mcp_trino_optimizer/rules/findings.py` | RuleFinding/RuleError/RuleSkipped discriminated union, Severity | VERIFIED | D-02 and D-03 implemented correctly |
| `src/mcp_trino_optimizer/rules/registry.py` | Plugin registry with decorator pattern | VERIFIED | register() as both decorator and explicit call |
| `src/mcp_trino_optimizer/rules/thresholds.py` | RuleThresholds(BaseSettings), env_prefix='TRINO_RULE_', citation comments | VERIFIED | 11 threshold fields, all with citation comments, env_prefix set |
| `src/mcp_trino_optimizer/rules/base.py` | Rule ABC with ClassVar rule_id + evidence_requirement, sync check() | VERIFIED | Matches D-06 spec exactly |
| `src/mcp_trino_optimizer/rules/engine.py` | RuleEngine(stats_source, catalog_source, thresholds), async run(), prefetch once | VERIFIED | Matches D-05 spec; prefetch-once implemented |
| `src/mcp_trino_optimizer/rules/r1_missing_stats.py` | R1 rule | VERIFIED | Registered, produces RuleFinding |
| `src/mcp_trino_optimizer/rules/r2_partition_pruning.py` | R2 rule | VERIFIED | Registered |
| `src/mcp_trino_optimizer/rules/r3_predicate_pushdown.py` | R3 rule | VERIFIED (with ruff errors) | Has unused imports — ruff fails |
| `src/mcp_trino_optimizer/rules/r4_dynamic_filtering.py` | R4 rule | VERIFIED | Registered |
| `src/mcp_trino_optimizer/rules/r5_broadcast_too_big.py` | R5 rule | VERIFIED (with ruff errors) | Has unused noqa |
| `src/mcp_trino_optimizer/rules/r6_join_order.py` | R6 rule | VERIFIED | Registered |
| `src/mcp_trino_optimizer/rules/r7_cpu_skew.py` | R7 rule | VERIFIED (with ruff errors) | Has unused noqa |
| `src/mcp_trino_optimizer/rules/r8_exchange_volume.py` | R8 rule | VERIFIED (with ruff errors) | Has unused noqa |
| `src/mcp_trino_optimizer/rules/r9_low_selectivity.py` | R9 rule | VERIFIED (with ruff errors) | Has unused noqa |
| `src/mcp_trino_optimizer/rules/i1_small_files.py` | I1 rule | VERIFIED | Registered |
| `src/mcp_trino_optimizer/rules/i3_delete_files.py` | I3 rule | VERIFIED | Registered |
| `src/mcp_trino_optimizer/rules/i6_stale_snapshots.py` | I6 rule | VERIFIED | Registered |
| `src/mcp_trino_optimizer/rules/i8_partition_transform.py` | I8 rule | VERIFIED | Registered |
| `src/mcp_trino_optimizer/rules/d11_cost_vs_actual.py` | D11 rule | VERIFIED (with ruff errors) | Has unused noqa |
| `tests/rules/test_thresholds.py` | Parameterized data-driven threshold test | PARTIAL | Parametrize exists but only checks citation keywords, not negative-control toggle behavior |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `RuleEngine` | `registry.all_rules()` | iteration in `run()` | WIRED | Engine uses registry singleton by default |
| `RuleEngine` | `EvidenceRequirement` enum | prefetch union | WIRED | Union of all registered rule requirements computed |
| `RuleEngine` | `StatsSource.fetch_table_stats()` | `_prefetch_evidence()` | WIRED | Called once; result stored in EvidenceBundle |
| `RuleEngine` | `CatalogSource.fetch_iceberg_metadata()` | `_prefetch_evidence()` | WIRED | Called once for files + once for snapshots |
| `__init__.py` | all 14 rule modules | explicit named imports | WIRED | Import triggers `registry.register()` calls |
| `RuleThresholds` | `TRINO_RULE_` env vars | `env_prefix` in SettingsConfigDict | WIRED | Verified by test_thresholds.py env override tests |

### Data-Flow Trace (Level 4)

Not applicable — the rules package is a pure computation engine with no dynamic rendering. Data flows from `BasePlan` + `EvidenceBundle` inputs through deterministic `check()` methods to `list[RuleFinding]` outputs. All sources are pre-built objects passed as arguments; no external data fetching in rule bodies.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| 14 rules registered | `uv run python -c "import mcp_trino_optimizer.rules; from mcp_trino_optimizer.rules import registry; print(len(registry.all_rules()))"` | 14 | PASS |
| Tests pass (unit) | `uv run pytest -m "not integration" -x -q` | 550 passed, 12 skipped | PASS |
| mypy strict | `uv run mypy src/mcp_trino_optimizer/rules/ --strict` | Success: no issues found in 21 source files | PASS |
| ruff check | `uv run ruff check src/mcp_trino_optimizer/rules/` | 9 errors (RUF100 + F401) | FAIL |

### Requirements Coverage

| Requirement | Status | Evidence |
|-------------|--------|----------|
| RUL-01 (plugin registry, Rule base, deterministic check()) | SATISFIED | registry.py, base.py — working decorator + explicit registration |
| RUL-02 (evidence requirement enum, prefetch union once) | SATISFIED | evidence.py EvidenceRequirement enum; engine._prefetch_evidence() |
| RUL-03 (unavailable evidence → rule_skipped) | SATISFIED | engine.py lines 81-110 emit RuleSkipped with structured reason |
| RUL-04 (one crashing rule → rule_error, others continue) | SATISFIED | engine.py lines 113-123 catch per-rule exceptions |
| RUL-05 (RuleFinding with rule_id, severity, confidence, message, evidence, operator_ids) | SATISFIED | findings.py pydantic model enforces all fields |
| RUL-06 (three fixture classes per rule) | BLOCKED | R7 and D11 missing realistic-from-compose class |
| RUL-07..RUL-20 (specific rules R1-R9, I1/I3/I6/I8, D11) | SATISFIED | All 14 rule files exist and are registered |
| RUL-21 (thresholds data-driven with citation + parameterized test) | BLOCKED | Citation comments exist; individual rule tests show threshold respect; but no parameterized test demonstrating negative-control toggle behavior |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `src/mcp_trino_optimizer/rules/r3_predicate_pushdown.py` | 25 | `from typing import Any` unused import (F401) | Warning | Ruff CI failure |
| `src/mcp_trino_optimizer/rules/r3_predicate_pushdown.py` | 31 | `PlanNode` unused import (F401) | Warning | Ruff CI failure |
| `src/mcp_trino_optimizer/rules/r3_predicate_pushdown.py` | 108 | Unused `# noqa: ARG002` (RUF100) | Warning | Ruff CI failure |
| `src/mcp_trino_optimizer/rules/d11_cost_vs_actual.py` | 58 | Unused `# noqa: ARG002` (RUF100) | Warning | Ruff CI failure |
| `src/mcp_trino_optimizer/rules/r2_partition_pruning.py` | 77 | Unused `# noqa: ARG002` (RUF100) | Warning | Ruff CI failure |
| `src/mcp_trino_optimizer/rules/r5_broadcast_too_big.py` | 52 | Unused `# noqa: ARG002` (RUF100) | Warning | Ruff CI failure |
| `src/mcp_trino_optimizer/rules/r7_cpu_skew.py` | 48 | Unused `# noqa: ARG002` (RUF100) | Warning | Ruff CI failure |
| `src/mcp_trino_optimizer/rules/r8_exchange_volume.py` | 51 | Unused `# noqa: ARG002` (RUF100) | Warning | Ruff CI failure |
| `src/mcp_trino_optimizer/rules/r9_low_selectivity.py` | 53 | Unused `# noqa: ARG002` (RUF100) | Warning | Ruff CI failure |

All 9 errors are auto-fixable with `uv run ruff check --fix src/mcp_trino_optimizer/rules/`.

### Gaps Summary

Three gaps block phase completion:

**Gap 1 — Ruff errors (9 fixable):** The 04-04-SUMMARY claims "All checks passed" but the current state of the repository has 9 ruff errors. This appears to be a regression introduced between the summary and now — the 04-04 executor noted it ran `ruff check --fix` but 9 errors remain. These are all auto-fixable (run `uv run ruff check --fix src/mcp_trino_optimizer/rules/`).

**Gap 2 — Missing realistic-from-compose fixture classes (2 rules):** R7 (CpuSkew) and D11 (CostVsActual) are the only two rules that cannot be tested with real compose fixtures because they require ExecutedPlan with actual CPU metrics. The test files document this limitation in their docstrings (noting "three fixture classes" but only listing synthetic + negative). The ROADMAP SC-4 specifically requires realistic-from-compose fixture class for every rule. A realistic test could load an EstimatedPlan fixture and cast it or note that compose-captured ExecutedPlan fixtures aren't available yet — but the SC is not met as-is.

**Gap 3 — SC-5 parameterized threshold data-driven proof:** The ROADMAP requires a "parameterized test that proves the thresholds are actually data-driven" where "at least one negative-control starts or stops triggering." The existing `@pytest.mark.parametrize` in test_thresholds.py checks citation keywords against default float values — it does not demonstrate behavioral changes. Individual `test_custom_threshold_respected` methods exist per rule but are not parameterized. A new parametrized test sweeping threshold values and asserting finding count changes would satisfy this requirement.

---

_Verified: 2026-04-13T00:00:00Z_
_Verifier: Claude (gsd-verifier)_
