# Phase 4: Rule Engine & 13 Deterministic Rules - Research

**Researched:** 2026-04-13
**Domain:** Python plugin registry, deterministic rule engine, Trino EXPLAIN JSON plan analysis, Iceberg metadata tables
**Confidence:** HIGH (architecture/stack), HIGH (plan node fields from verified fixtures), MEDIUM (Trino version-specific behavior for I8/R2)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**D-01 (single `rules/` package):** All rule-engine code lives in
`src/mcp_trino_optimizer/rules/` — one subpackage, no split:
- `rules/__init__.py` — public API re-exports
- `rules/engine.py` — `RuleEngine` class
- `rules/registry.py` — plugin registry
- `rules/findings.py` — `RuleFinding`, `RuleError`, `RuleSkipped`, `EngineResult` type alias, `Severity` enum
- `rules/thresholds.py` — `RuleThresholds(BaseSettings)` with env overrides
- `rules/r1_missing_stats.py` through `rules/r9_low_selectivity_scan.py`
- `rules/i1_small_files.py`, `rules/i3_delete_files.py`, `rules/i6_stale_snapshots.py`, `rules/i8_partition_transform.py`
- `rules/d11_cost_vs_actual.py`

**D-02 (discriminated union):** Three distinct pydantic models with `kind` literal discriminator. `EngineResult = RuleFinding | RuleError | RuleSkipped`.

**D-03 (4-tier severity):** `Severity = Literal["critical", "high", "medium", "low"]` — no "info" tier.

**D-04 (standalone `rules/thresholds.py`):** `RuleThresholds(BaseSettings)` with `env_prefix='TRINO_RULE_'`. Each threshold carries a citation comment. Default values are provided in CONTEXT.md verbatim.

**D-05 (engine-internal fetch):** `RuleEngine` takes `StatsSource | None`, `CatalogSource | None`, and `RuleThresholds` as constructor arguments. Prefetches union of all required evidence exactly once. Offline mode = `None` sources — rules requiring unavailable evidence emit `RuleSkipped`.

**D-06 (per-requirements):** Each rule is a `Rule` subclass with `rule_id: ClassVar[str]`, `evidence_requirement: ClassVar[EvidenceRequirement]`, and `check(plan: BasePlan, evidence: EvidenceBundle) -> list[RuleFinding]` (pure, deterministic, sync).

### Claude's Discretion

- Whether the registry uses `@registry.register` decorator or `registry.register(Rule)` explicit call — either is fine.
- Exact `EvidenceBundle` dataclass fields.
- Whether rules are sync or async `check()` methods — sync preferred (no I/O in rule bodies).
- How `BasePlan.walk()` / `find_nodes_by_type()` are used inside individual rules.
- Exact structure of the `evidence` dict in `RuleFinding`.

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope.

</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| RUL-01 | Plugin registry; Rule base class with deterministic `check()` | Decorator-registration pattern; ABC-based Rule class |
| RUL-02 | Evidence requirement enum; engine prefetches union once | EvidenceRequirement enum + EvidenceBundle dataclass |
| RUL-03 | Rules requiring unavailable evidence emit `rule_skipped`, not exception | Engine pre-check on source availability |
| RUL-04 | Rule failure isolation — one crash emits `rule_error`, others continue | Try/except in engine run loop |
| RUL-05 | `RuleFinding` with rule_id, severity, confidence, message, evidence payload, operator_ids | Locked in D-02 |
| RUL-06 | Three fixture classes per rule: synthetic-minimum, realistic-from-compose, negative-control | Fixture organization pattern |
| RUL-07 | R1 — missing/stale table statistics | SHOW STATS + divergence from plan estimates vs actuals |
| RUL-08 | R2 — partition pruning failure | TableScan descriptor `constraint on [col]` indicator; splits/input_rows ratio |
| RUL-09 | R3 — predicate pushdown failure | `filterPredicate` in descriptor; function-wrapped column detection |
| RUL-10 | R4 — dynamic filtering not applied | `dynamicFilterAssignments` in InnerJoin + `dynamicFilters` in ScanFilter probe |
| RUL-11 | R5 — large build side / broadcast too big | Join `distribution = REPLICATED` + build-side `outputSizeInBytes` estimate |
| RUL-12 | R6 — join order inversion | Join `distribution` type + probe/build `outputRowCount` ratio from estimates |
| RUL-13 | R7 — CPU/wall-time skew | Per-stage CPU time variance; requires `ExecutedPlan` |
| RUL-14 | R8 — excessive exchange volume | Exchange node `outputSizeInBytes` vs scan `outputSizeInBytes` |
| RUL-15 | R9 — low-selectivity scan | Scan `input_bytes` vs `output_bytes` ratio |
| RUL-16 | I1 — Iceberg small-files explosion | `iceberg_file_count` / `iceberg_split_count` + `$files` avg size |
| RUL-17 | I3 — Iceberg delete-file accumulation | `$files` WHERE `content IN (1,2)` cross-reference workaround for Trino #28910 |
| RUL-18 | I6 — stale snapshot accumulation | `$snapshots` count + oldest `committed_at` |
| RUL-19 | I8 — partition transform mismatch | TableScan constraint detail lines + predicate alignment check |
| RUL-20 | D11 — cost-vs-actual divergence | `estimates[0].outputRowCount` vs `output_rows` (ExecutedPlan only) |
| RUL-21 | All thresholds data-driven with citation comments, config-overridable | RuleThresholds pattern |

</phase_requirements>

---

## Summary

Phase 4 builds the deterministic rule engine — a plugin registry that runs 13 rules against `EstimatedPlan` / `ExecutedPlan` objects, each rule declaring its evidence requirements so the engine can prefetch evidence once and route correctly. The architecture is fully decided in CONTEXT.md (D-01 through D-06); this research focuses on the three open questions: (1) exact plan node fields for each rule's detection logic, (2) the partition-transform mismatch detection pattern for I8 and R2, and (3) the `$files` cross-reference workaround for I3.

**Primary recommendation:** Rules are pure functions — `check(plan, evidence) -> list[RuleFinding]` with no I/O, no side effects, and no shared state. The engine wraps each call in try/except and the isolated-failure guarantee is straightforward. The hardest implementation work is rule detection logic, not infrastructure.

---

## Standard Stack

All dependencies are already in `pyproject.toml` from Phases 1–3. Phase 4 adds no new third-party dependencies.

### Core (already installed)
| Library | Version | Purpose | Why Used |
|---------|---------|---------|----------|
| `pydantic` | `>=2.9,<3` | `RuleFinding`, `RuleError`, `RuleSkipped`, discriminated union | Locked in Phase 1 |
| `pydantic-settings` | `>=2.13.1` | `RuleThresholds(BaseSettings)` with `TRINO_RULE_` env prefix | Same pattern as `Settings` in `settings.py` |
| `pytest` | `>=8.3` | Test runner | Phase 1 |
| `pytest-asyncio` | `>=1.3.0` | Async engine tests | Phase 1 |
| `syrupy` | `>=5.1.0` | Snapshot tests for full `list[EngineResult]` output | Phase 3 already wired |

**No new packages required.** [VERIFIED: existing pyproject.toml]

---

## Architecture Patterns

### Recommended Module Layout

```
src/mcp_trino_optimizer/rules/
├── __init__.py          # Public API: RuleEngine, RuleFinding, RuleError, RuleSkipped,
│                        #   EngineResult, Severity, EvidenceRequirement
├── engine.py            # RuleEngine class — orchestrates prefetch + run loop
├── registry.py          # RuleRegistry — registration + lookup
├── findings.py          # RuleFinding, RuleError, RuleSkipped, EngineResult, Severity
├── base.py              # Rule ABC with rule_id, evidence_requirement, check()
├── thresholds.py        # RuleThresholds(BaseSettings) with TRINO_RULE_ prefix
├── evidence.py          # EvidenceRequirement enum + EvidenceBundle dataclass
├── r1_missing_stats.py
├── r2_partition_pruning.py
├── r3_predicate_pushdown.py
├── r4_dynamic_filtering.py
├── r5_broadcast_too_big.py
├── r6_join_order.py
├── r7_cpu_skew.py
├── r8_exchange_volume.py
├── r9_low_selectivity.py
├── i1_small_files.py
├── i3_delete_files.py
├── i6_stale_snapshots.py
├── i8_partition_transform.py
└── d11_cost_vs_actual.py
```

### Pattern 1: Rule ABC and Registration

```python
# Source: project conventions (CONTEXT.md D-06)
from abc import ABC, abstractmethod
from typing import ClassVar
from mcp_trino_optimizer.rules.evidence import EvidenceRequirement, EvidenceBundle
from mcp_trino_optimizer.rules.findings import RuleFinding
from mcp_trino_optimizer.parser.models import BasePlan

class Rule(ABC):
    rule_id: ClassVar[str]
    evidence_requirement: ClassVar[EvidenceRequirement]

    @abstractmethod
    def check(self, plan: BasePlan, evidence: EvidenceBundle) -> list[RuleFinding]:
        """Pure, deterministic, sync. No I/O. Return [] if rule does not trigger."""
        ...
```

### Pattern 2: Registry with Explicit Register Call

Use explicit `registry.register(RuleClass)` at module load time (called from each rule module). This avoids Python import-order fragility with decorators and makes the registration source of truth a single place in `engine.py` or `__init__.py`.

```python
# rules/registry.py
class RuleRegistry:
    def __init__(self) -> None:
        self._rules: dict[str, type[Rule]] = {}

    def register(self, rule_cls: type[Rule]) -> type[Rule]:
        """Register a Rule class. Returns the class unchanged (usable as decorator)."""
        self._rules[rule_cls.rule_id] = rule_cls
        return rule_cls

    def all_rules(self) -> list[type[Rule]]:
        return list(self._rules.values())

registry = RuleRegistry()
```

The `register()` method returns the class unchanged, so it can be used as either a decorator (`@registry.register`) or an explicit call (`registry.register(R1MissingStats)`). The planner may choose either pattern — both work.

### Pattern 3: EvidenceBundle Design

```python
# rules/evidence.py
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

class EvidenceRequirement(Enum):
    PLAN_ONLY = "plan_only"
    PLAN_WITH_METRICS = "plan_with_metrics"  # ExecutedPlan only
    TABLE_STATS = "table_stats"              # needs StatsSource
    ICEBERG_METADATA = "iceberg_metadata"    # needs CatalogSource

@dataclass
class EvidenceBundle:
    # Always present
    plan: BasePlan

    # Present when StatsSource available and rule requires TABLE_STATS
    table_stats: dict[str, Any] | None = None     # from StatsSource.fetch_table_stats

    # Present when CatalogSource available and rule requires ICEBERG_METADATA
    iceberg_snapshots: list[dict[str, Any]] | None = None  # $snapshots rows
    iceberg_files: list[dict[str, Any]] | None = None      # $files rows
```

**Key insight:** The engine calls `stats_source.fetch_table_stats()` and `catalog_source.fetch_iceberg_metadata()` once and populates the bundle before calling any rule. Rules read from the bundle — they never call sources directly.

### Pattern 4: Engine Run Loop with Isolated Failure

```python
# rules/engine.py (pseudocode — planner fills in exact implementation)
async def run(self, plan: BasePlan, table: str | None = None) -> list[EngineResult]:
    evidence = await self._prefetch_evidence(plan, table)
    results: list[EngineResult] = []
    for rule_cls in self._registry.all_rules():
        rule = rule_cls()
        if not self._evidence_available(rule.evidence_requirement):
            results.append(RuleSkipped(rule_id=rule.rule_id, reason=...))
            continue
        if not self._plan_compatible(rule.evidence_requirement, plan):
            results.append(RuleSkipped(rule_id=rule.rule_id, reason="requires_executed_plan"))
            continue
        try:
            findings = rule.check(plan, evidence)
            results.extend(findings)
        except Exception as exc:
            results.append(RuleError(
                rule_id=rule.rule_id,
                error_type=type(exc).__name__,
                message=str(exc),
            ))
    return results
```

### Anti-Patterns to Avoid

- **Rule reads from sources directly:** Rules must not call `StatsSource` or `CatalogSource` — the engine prefetches. Mixing I/O into rule bodies breaks determinism and testability.
- **Rule raises exceptions:** `check()` must return `[]` on no-match. Only truly unexpected bugs should bubble up (and those are caught by the engine).
- **Shared mutable state between rules:** Each `Rule` instance is created fresh per `run()` call. No class-level mutable state.
- **Rules comparing estimated row counts with `== 0`:** Trino emits `NaN` (as Python float `nan`) when stats are missing. Use `math.isnan()` checks, not `== 0`.
- **walk() O(n²) issue:** The current `BasePlan.walk()` uses `pop(0)` (WR-01 from Phase 3 review). Rules that call `walk()` will work correctly, but if WR-01 is not fixed in Phase 4's Wave 0 gap closure, all rules operating on deep trees will silently get suboptimal DFS order. **Fix `walk()` as a Wave 0 task before implementing rules.**

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Evidence requirement enum + skip logic | Custom condition trees | `EvidenceRequirement` enum + single engine check | Centralizes capability gating; all 13 rules get skip-for-free |
| NaN detection in CBO estimates | `if val == float('nan')` | `math.isnan(val)` or `val != val` | `float('nan') != float('nan')` in Python; equality check always False |
| Rule isolation | Outer try/except per-rule call site | Engine run loop wrapper (Pattern 4 above) | One place to change when error structure changes |
| Threshold magic numbers | Inline literals like `5.0` | `RuleThresholds` field with citation comment | Required by RUL-21; also enables parameterized tests |
| Iceberg delete-file count | Query `$partitions` for delete counts | Query `$files WHERE content IN (1, 2)` | Trino issue #28910: `$partitions` does not expose delete-file metrics |

---

## Rule Detection Patterns

This section maps each rule to the exact plan fields it uses. All field names are verified against the actual fixture corpus in `tests/fixtures/explain/`. [VERIFIED: fixture corpus]

### R1 — Missing/Stale Table Statistics

**Plan signal (EstimatedPlan or ExecutedPlan):**
- `estimates[0].outputRowCount` is `NaN` or missing on a `TableScan`/`ScanFilter`/`ScanFilterProject` node
- For `ExecutedPlan` (D11 variant): estimated `outputRowCount` diverges from actual `output_rows` by `> thresholds.stats_divergence_factor` (default 5×)

**Evidence requirement:** `TABLE_STATS` (reads `SHOW STATS FOR table` via `StatsSource`)
- `table_stats["row_count"]` is `None` → no stats collected → CRITICAL
- `table_stats["columns"][col]["null_fraction"]` all `None` → no column stats

**Key check:** `math.isnan(estimate.outputRowCount)` when `outputRowCount` is a float. Pydantic maps JSON `NaN` to Python `float('nan')`.

**Operator types to scan:** `TableScan`, `ScanFilter`, `ScanFilterProject` (all scan variants)

---

### R2 — Partition Pruning Failure

**Plan signal:**
The canonical signal for partition pruning being **applied** is the `constraint on [col]` suffix in the `TableScan` descriptor's `table` field:

```
# Partition pruning APPLIED (from fixture iceberg_partition_filter.json):
"table": "iceberg:test_fixtures.orders$data@7192078785404198795 constraint on [ts]"

# Partition pruning NOT applied (full scan):
"table": "iceberg:test_fixtures.orders$data@7192078785404198795"
```

[VERIFIED: `tests/fixtures/explain/480/iceberg_partition_filter.json`, `full_scan.json`]

**Secondary signal (ExecutedPlan only):** The EXPLAIN ANALYZE text line:
```
Input: 10 rows (533B), Physical input: 996B, Physical input time: 4.58us, Splits: 1
# (partition-filtered: 1 split out of 6 total)

Input: 20 rows (1.01kB), Physical input: 4.78kB, Physical input time: 26.79us, Splits: 6
# (full scan: 6 splits)
```
[VERIFIED: `tests/fixtures/explain/480/iceberg_partition_filter_analyze.txt`, `full_scan_analyze.txt`]

**Detection logic for R2:**
1. Find all scan nodes in the plan.
2. Check if the node's `descriptor["table"]` value contains `"constraint on ["`.
3. If the scan node has a `filterPredicate` in its descriptor that references a column but the table descriptor has NO `"constraint on ["` suffix → partition pruning failure.
4. In `ExecutedPlan`: if `input_rows ≈ total_table_row_count` (from `TABLE_STATS`) despite a predicate → pruning not applied.

**Caveat (Trino issue #19266):** Closed Jan 2025 (PR #24740). Trino 480 can now prune partially-aligned predicates (e.g., `ts >= TIMESTAMP '2023-01-02 10:00:00 UTC'` on a `day(ts)` partition). Trino 429 cannot — that predicate gets a full scan. When `source_trino_version` < 440 (approximate), mark findings for partial-alignment predicates with lower confidence. [CITED: github.com/trinodb/trino/issues/19266]

---

### R3 — Predicate Pushdown Failure

**Plan signal:**
`ScanFilter` / `ScanFilterProject` descriptor's `filterPredicate` field contains a function-wrapped predicate:

```python
# In descriptor:
"filterPredicate": "(\"date\"(ts) = DATE '2025-01-15')"       # BAD: function wrap
"filterPredicate": "(ts >= ... AND ts < ...)"                  # GOOD: range predicate
"filterPredicate": "(cast(ts as date) = DATE '2025-01-15')"   # BAD: cast wrap
```

[VERIFIED: `tests/fixtures/explain/429/simple_select.json` shows `filterPredicate` field in `ScanFilter` descriptor]

**Detection logic:**
Parse the `filterPredicate` string looking for function call patterns wrapping a column name:
- `date(col)`, `cast(col as ...)`, `year(col)`, `month(col)`, `trunc(col, ...)`, `substring(col, ...)`, etc.

Use `sqlglot` to parse the predicate string: if any comparison's left/right side is a `FunctionCall` wrapping a plain `Column` reference, fire R3.

**Operator types:** `ScanFilter`, `ScanFilterProject`, `Filter` (post-normalization)

---

### R4 — Dynamic Filtering Not Applied

**Plan signals from fixture join.json / join_analyze.txt:** [VERIFIED]

In EXPLAIN JSON:
- `InnerJoin` node has `"dynamicFilterAssignments = {id -> #df_388}"` in its `details` list
- Probe-side `ScanFilter` has `"dynamicFilters": "{id_0 = #df_388}"` in its `descriptor`

In EXPLAIN ANALYZE text:
- `dynamicFilterAssignments = {id -> #df_447}` in InnerJoin details
- `Dynamic filters:` section under the ScanFilter operator with collected domain

**Detection logic:**
- R4 fires when an `InnerJoin` node does NOT have a `dynamicFilterAssignments` entry in its `details` or `descriptor`, but the join condition is on equality predicates that would normally be eligible for dynamic filtering.
- Also fires when `dynamicFilterAssignments` is present in the join but the probe-side scan has no corresponding `dynamicFilters` entry (filter declared but not pushed to scan).

**Evidence requirement:** `PLAN_ONLY` — detectable from plan structure alone. `ExecutedPlan` gives higher confidence via the `Dynamic filters: (none)` output.

---

### R5 — Large Build Side / Broadcast Too Big

**Plan signal (EstimatedPlan):**
`InnerJoin` / `SemiJoin` node with `distribution: "REPLICATED"` in descriptor AND the build side (second child = `LocalExchange` → `RemoteSource`) has high estimated `outputRowCount` or `outputSizeInBytes`.

From fixture join.json: `"distribution": "REPLICATED"` in the `InnerJoin` descriptor. [VERIFIED]

**Detection logic:**
1. Find `InnerJoin` nodes where `descriptor["distribution"] == "REPLICATED"`.
2. Find the build side (child that feeds into `LocalExchange[partitioning=SINGLE]`).
3. Check build-side `estimates[0].outputSizeInBytes > thresholds.broadcast_max_bytes` (default 100MB).

---

### R6 — Join Order Inversion

**Plan signal:**
`InnerJoin` node where the probe side (first child) has a much larger estimated row count than the build side, combined with missing statistics on the probe side (estimates are `NaN`).

**Detection logic:**
- Check `InnerJoin.children[0]` (probe side) vs `InnerJoin.children[1]` (build side) `estimates[0].outputRowCount`.
- If probe rows / build rows > threshold AND probe-side table has no stats (R1 condition) → R6.

**Evidence requirement:** `TABLE_STATS` (to confirm missing stats cause the inversion).

---

### R7 — CPU/Wall-Time Skew

**Plan signal (ExecutedPlan only):**
Per-stage CPU time variance. From the parsed `ExecutedPlan`, stage-level CPU and wall time are exposed at the fragment level in EXPLAIN ANALYZE text.

**Detection logic:**
- For each stage (fragment), `cpu_time_ms` is available on operator nodes.
- Within a stage, compare the max operator CPU time to the median (p99/p50 proxy).
- Threshold: `max_cpu / median_cpu > thresholds.skew_ratio` (default 5.0).

**Evidence requirement:** `PLAN_WITH_METRICS` (ExecutedPlan).

---

### R8 — Excessive Exchange Volume

**Plan signal:**
`Exchange` / `LocalExchange` / `RemoteSource` nodes where `estimates[0].outputSizeInBytes` exceeds the scan-level `outputSizeInBytes`.

**Detection logic:**
1. Sum all `Exchange` and `LocalExchange` node `outputSizeInBytes` estimates.
2. Sum all scan node `outputSizeInBytes` estimates.
3. If exchange total > scan total → R8.

---

### R9 — Low-Selectivity Scan

**Plan signal:**
For `EstimatedPlan`: scan node has `estimates[0].outputSizeInBytes` (after filter) significantly less than `estimates[0].cpuCost` / a proxy for raw bytes scanned.

For `ExecutedPlan`: `output_bytes / input_bytes < thresholds.scan_selectivity_threshold` (default 0.10).

**Evidence requirement:** `PLAN_ONLY` for estimated plan path; `PLAN_WITH_METRICS` for executed plan path (higher confidence).

---

### I1 — Iceberg Small-Files Explosion

**Plan signal + metadata:**
- Primary: `iceberg_split_count > 10000` (threshold: `thresholds.small_file_split_count_threshold`) on a scan node (ExecutedPlan).
- Secondary: `$files` metadata query via `CatalogSource.fetch_iceberg_metadata(..., suffix="files")` — compute median `file_size_in_bytes` from rows where `content = 0` (DATA files only). If median < `thresholds.small_file_bytes` (default 16MB) → I1.

**Evidence requirement:** `ICEBERG_METADATA`

**$files schema (verified from docs):** [CITED: trino.io/docs/current/connector/iceberg.html]
```
content         INTEGER  -- 0=DATA, 1=POSITION_DELETES, 2=EQUALITY_DELETES
file_path       VARCHAR
file_format     VARCHAR
record_count    BIGINT
file_size_in_bytes  BIGINT
```

---

### I3 — Iceberg Delete-File Accumulation

**The problem (Trino issue #28910):** [VERIFIED: github.com/trinodb/trino/issues/28910]
`$partitions` does NOT expose delete-file counts (`position_delete_file_count`, `equality_delete_file_count`). Issue is OPEN as of 2026-04. The linked PR #28911 is also open.

**Workaround — query `$files` directly:**
```sql
SELECT
    content,
    COUNT(*) AS file_count,
    SUM(record_count) AS total_delete_records
FROM iceberg.schema."table$files"
WHERE content IN (1, 2)  -- 1=position deletes, 2=equality deletes
GROUP BY content
```

This is expensive on large tables (scans all file metadata). For v1, it is the only available path. The query is issued via `CatalogSource.fetch_iceberg_metadata(..., suffix="files")` (which does `SELECT * FROM table$files`); the rule then filters client-side.

**Detection thresholds:**
- `delete_file_count > thresholds.delete_file_count_threshold` (suggested default: 100)
- `total_delete_records / total_data_records > thresholds.delete_ratio_threshold` (suggested default: 0.10)

**Evidence requirement:** `ICEBERG_METADATA`

---

### I6 — Stale Snapshot Accumulation

**Metadata query:** `CatalogSource.fetch_iceberg_metadata(..., suffix="snapshots")`

**$snapshots schema (verified):** [CITED: trino.io/docs/current/connector/iceberg.html]
```
committed_at    TIMESTAMP(3) WITH TIME ZONE
snapshot_id     BIGINT
parent_id       BIGINT
operation       VARCHAR  -- 'append', 'replace', 'overwrite', 'delete'
manifest_list   VARCHAR
summary         MAP(VARCHAR, VARCHAR)
```

**Detection logic:**
1. Count total snapshots: `len(snapshots) > thresholds.max_snapshot_count` (suggested default: 50)
2. Check oldest snapshot age: `now() - min(committed_at) > thresholds.snapshot_retention_days` (suggested default: 30 days)

**Evidence requirement:** `ICEBERG_METADATA`

---

### I8 — Partition Transform Mismatch

**Background (Trino issue #19266):** [CITED: github.com/trinodb/trino/issues/19266]
Issue closed Jan 2025 via PR #24740. The fix added partial partition pruning. However, the underlying pattern — a predicate that doesn't align with partition transform granularity — still results in extra files being scanned when it falls within a partition boundary. The rule detects misalignment even when some pruning occurs, to feed the Phase 6 rewrite engine.

**Iceberg partition transforms:** `identity`, `bucket(N)`, `truncate(N)`, `year`, `month`, `day`, `hour` [CITED: trino.io/docs/current/connector/iceberg.html]

**Plan signal (EstimatedPlan + ICEBERG_METADATA):**
The `TableScan` descriptor's `table` field contains `constraint on [col]` when a filter was pushed. The constraint detail line shows the actual range pushed:

```
# From iceberg_partition_filter_analyze.txt (Trino 480):
"ts := 4:ts:timestamp(6) with time zone"
"    :: [[2025-01-15 00:00:00.000000 UTC, 2025-01-16 00:00:00.000000 UTC)]"
```

A `day(ts)` partition transform aligns with day boundaries (midnight UTC). If the predicate was `ts = '2025-01-15'`, the constraint is `[2025-01-15 00:00:00 UTC, 2025-01-16 00:00:00 UTC)` — perfectly aligned.

A misaligned predicate would be: `ts >= '2025-01-15 10:00:00'` — constraint starts mid-day, cannot prune the first partition file.

**Detection logic:**
1. Find scan nodes with `"constraint on ["` in descriptor.
2. Parse the constraint range detail lines (lines with `::` prefix).
3. Query `$snapshots.summary` map for partition spec info, or check `iceberg_partition_spec_id` on the node.
4. Compare constraint boundaries against expected transform-aligned boundaries (e.g., for `day(ts)`: boundaries should be midnight UTC).

**Version note:** Trino 429 cannot prune partial-alignment predicates at all; Trino 480 can prune partially. The rule should lower confidence for Trino 429 cases where the constraint IS present (pruning applied) but boundaries are not transform-aligned. [CITED: github.com/trinodb/trino/issues/19266]

**Evidence requirement:** `ICEBERG_METADATA` (to retrieve partition spec for the table)

---

### D11 — Cost-vs-Actual Divergence

**Plan signal (ExecutedPlan only):**
Compare `estimates[0].outputRowCount` with `output_rows` for each scan node. Both are available on `ExecutedPlan` nodes.

```python
# From models.py: EstimatedPlan nodes have estimates, ExecutedPlan nodes have both
estimated = node.estimates[0].output_row_count  # may be NaN
actual = node.output_rows                        # int | None for ExecutedPlan
divergence = actual / estimated if estimated else None
```

**Detection logic:**
- Skip if `estimated` is `NaN` or `None` (stats missing — R1 handles that case).
- Skip if `actual` is `None` (not an ExecutedPlan or metric not parsed).
- Fire if `divergence > thresholds.stats_divergence_factor` or `divergence < 1 / thresholds.stats_divergence_factor` (both over-estimate and under-estimate).

**Evidence requirement:** `PLAN_WITH_METRICS` (ExecutedPlan)

---

## Common Pitfalls

### Pitfall 1: NaN estimates silently breaking comparisons

**What goes wrong:** Trino emits `"outputRowCount": NaN` in JSON when stats are absent. Python's `json.loads` converts this to `float('nan')`. `float('nan') > 1000000` is `False`, `float('nan') == 0` is `False` — every comparison is silent False. A rule checking `est_rows > threshold` never fires on tables with no stats.

**How to avoid:** Always guard with `math.isnan(val)` before numeric comparison. Add this as a utility function in `rules/evidence.py` or `findings.py`. [ASSUMED — behavior is standard Python float/NaN semantics, consistent with Pitfall 1 in PITFALLS.md]

### Pitfall 2: ScanFilterProject vs ScanFilter vs TableScan vs Filter confusion

**What goes wrong:** Trino uses multiple names for "scan + maybe filter + maybe project" depending on version and query shape. In Trino 429 fixtures, `ScanFilter` appears where Trino 480 uses `TableScan` (post-normalization). Rules must handle all variants.

**The normalizer is the fix:** Phase 3's normalizer decomposes `ScanFilterProject` into a `TableScan` child with filter metadata. Rules should use `find_nodes_by_type("TableScan")` and also handle `ScanFilter` / `ScanFilterProject` directly for safety, until the normalizer is confirmed to fully flatten all variants.

[VERIFIED: Trino 429 fixture shows `ScanFilter` as root scan node; Trino 480 fixture shows `TableScan` — normalization creates consistent output]

### Pitfall 3: walk() O(n²) bug must be fixed before rules run

**What goes wrong:** WR-01 from Phase 3 review: `BasePlan.walk()` uses `pop(0)` which is O(n) per step. For a 1000-node plan, walk() is O(n²). For a 100-node plan it's invisible; for large EXPLAIN ANALYZE output from TPC-DS queries, it will visibly slow rule execution.

**How to avoid:** Fix `walk()` in Wave 0 of Phase 4. The fix is trivial: `stack.pop()` (from right) + `stack.extend(reversed(node.children))`.

### Pitfall 4: Dynamic filter field location differs between EXPLAIN JSON and EXPLAIN ANALYZE text

**What goes wrong:** In EXPLAIN JSON, dynamic filter info appears in:
- `InnerJoin.details` list: `"dynamicFilterAssignments = {id -> #df_388}"` 
- `ScanFilter.descriptor["dynamicFilters"]`: `"{id_0 = #df_388}"`

In EXPLAIN ANALYZE text (parsed into `ExecutedPlan`), it appears as:
- `InnerJoin` detail string: `"dynamicFilterAssignments = {id -> #df_447}"`
- Separate block under ScanFilter: `"Dynamic filters: ..."` line

Rules must search both `node.descriptor` and `node.details` list, not just one. [VERIFIED: `join.json` and `join_analyze.txt`]

### Pitfall 5: `iceberg_split_count` only available in ExecutedPlan

**What goes wrong:** `iceberg_split_count` and `iceberg_file_count` on `PlanNode` are only populated when parsing EXPLAIN ANALYZE output (Phase 3 extracts them from the `Splits: N` line). They are `None` in `EstimatedPlan` nodes. Rules I1 (small files via split count) must require `PLAN_WITH_METRICS` for the plan-based path or fall back to `ICEBERG_METADATA`.

[VERIFIED: `models.py` docstrings — both fields are `None` for EstimatedPlan]

### Pitfall 6: Evidence prefetch requires table name, which may not be available

**What goes wrong:** `StatsSource.fetch_table_stats(catalog, schema, table)` and `CatalogSource.fetch_iceberg_metadata(catalog, schema, table, suffix)` require the table name. The table name must be extracted from plan node descriptor strings.

**Extraction pattern:** `PlanNode.descriptor["table"]` has format `"catalog:schema.table$data@snapshotId [constraint on [col]]"`. Need to parse out `catalog`, `schema.table` (strip `$data@...` suffix). This parsing belongs in a helper in `engine.py` or `evidence.py`, not in individual rules.

### Pitfall 7: `$files` query can be large

**What goes wrong:** For I1 and I3, `fetch_iceberg_metadata(suffix="files")` does `SELECT * FROM table$files`. On a large partitioned table with millions of files, this returns millions of rows to the client. The current `CatalogSource` port has no `LIMIT` parameter.

**Mitigation for v1:** Document that I1/I3 rules should gracefully handle large responses. For I3 the delete-file count query can be issued as a system-runtime query via `StatsSource.fetch_system_runtime()` with a COUNT aggregate — but this requires SQL sent to Trino. The simplest v1 path is `fetch_iceberg_metadata(suffix="files")` with client-side count, and a `max_files_metadata_rows` threshold to cap the response. [ASSUMED — port currently has no LIMIT support; planner should decide whether to add one]

---

## Code Examples

### EvidenceRequirement enum + RuleSkipped emission

```python
# Source: project CONTEXT.md D-05 + D-06 pattern
class EvidenceRequirement(Enum):
    PLAN_ONLY = "plan_only"
    PLAN_WITH_METRICS = "plan_with_metrics"
    TABLE_STATS = "table_stats"
    ICEBERG_METADATA = "iceberg_metadata"

# In engine.py — skip logic
if rule.evidence_requirement == EvidenceRequirement.ICEBERG_METADATA:
    if self._catalog_source is None:
        results.append(RuleSkipped(
            rule_id=rule.rule_id,
            reason="offline_mode_no_catalog_source",
        ))
        continue
if rule.evidence_requirement == EvidenceRequirement.PLAN_WITH_METRICS:
    if not isinstance(plan, ExecutedPlan):
        results.append(RuleSkipped(
            rule_id=rule.rule_id,
            reason="requires_executed_plan_estimated_plan_provided",
        ))
        continue
```

### Partition pruning detection from plan descriptor

```python
# Source: verified from tests/fixtures/explain/480/iceberg_partition_filter.json
def _has_partition_constraint(node: PlanNode) -> bool:
    table_str = node.descriptor.get("table", "")
    return "constraint on [" in table_str

def _get_filtered_columns(node: PlanNode) -> list[str]:
    """Extract column names from 'constraint on [col1, col2]' in descriptor."""
    import re
    table_str = node.descriptor.get("table", "")
    match = re.search(r"constraint on \[([^\]]+)\]", table_str)
    if match:
        return [c.strip() for c in match.group(1).split(",")]
    return []
```

### $files delete count query (I3 workaround)

```python
# Source: github.com/trinodb/trino/issues/28910 — verified workaround
# CatalogSource returns all rows from table$files (suffix="files")
# Rule-side filtering for delete files:
def _count_delete_files(files: list[dict]) -> dict:
    pos_delete_files = [f for f in files if f.get("content") == 1]
    eq_delete_files = [f for f in files if f.get("content") == 2]
    return {
        "position_delete_count": len(pos_delete_files),
        "position_delete_records": sum(f.get("record_count", 0) for f in pos_delete_files),
        "equality_delete_count": len(eq_delete_files),
        "equality_delete_records": sum(f.get("record_count", 0) for f in eq_delete_files),
        "data_file_count": len([f for f in files if f.get("content") == 0]),
    }
```

### RuleThresholds pattern (from CONTEXT.md D-04)

```python
# Source: CONTEXT.md D-04 — verbatim from decisions
from pydantic_settings import BaseSettings, SettingsConfigDict

class RuleThresholds(BaseSettings):
    model_config = SettingsConfigDict(env_prefix='TRINO_RULE_')

    # R1 / D11: cost-vs-actual divergence
    # Cite: >5× divergence is the threshold used in Trino's own cost-model tests
    stats_divergence_factor: float = 5.0

    # R5: broadcast join size ceiling
    # Cite: Trino default broadcast_max_memory = 100MB
    broadcast_max_bytes: int = 100 * 1024 * 1024

    # R7: CPU/wall skew — p99/p50 ratio
    # Cite: empirical; 5× is the threshold where Trino support flags skew issues
    skew_ratio: float = 5.0

    # R9: scan selectivity floor
    # Cite: Trino perf guide — <10% selectivity = missing partition pruning candidate
    scan_selectivity_threshold: float = 0.10

    # I1: small-file size floor
    # Cite: Iceberg best-practices — target 128MB–512MB; <16MB is small
    small_file_bytes: int = 16 * 1024 * 1024

    # I1: high split count threshold (EXPLAIN ANALYZE iceberg_split_count)
    # Cite: empirical — >10k splits is the boundary where Iceberg fragmentation hurts
    small_file_split_count_threshold: int = 10_000

    # I3: delete-file count threshold
    # Cite: Iceberg V2 best practices — >100 delete files triggers compaction
    delete_file_count_threshold: int = 100

    # I3: delete record ratio threshold (delete_records / total_records)
    # Cite: Iceberg documentation — >10% delete ratio impacts read performance
    delete_ratio_threshold: float = 0.10

    # I6: max retained snapshots
    # Cite: Iceberg default expire_snapshots retention is typically 5 snapshots minimum
    max_snapshot_count: int = 50

    # I6: snapshot age retention window
    # Cite: Iceberg default max_snapshot_age_ms = 5 days; 30 days is a conservative alert
    snapshot_retention_days: int = 30
```

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `float('nan')` is how Pydantic v2 surfaces JSON `NaN` in float fields | Pitfall 1, R1 detection | Rule would fire or not fire incorrectly on all missing-stats plans |
| A2 | `CatalogSource.fetch_iceberg_metadata(suffix="files")` returns all `$files` rows with no server-side LIMIT | Pitfall 7, I1/I3 | Large tables would cause memory issues in the engine |
| A3 | Trino versions between 429 and ~440 cannot do partial partition pruning (issue #19266 fix was post-440) | R2/I8 version note | May over-fire or under-fire R2/I8 on intermediate Trino versions |
| A4 | `node.descriptor["table"]` format `"catalog:schema.table$data@snapshotId"` is consistent across Trino 429–480 | Pitfall 6, R2/I8 table-name extraction | Table name extraction would fail on unexpected formats |
| A5 | The `$files` `content` column values are 0=DATA, 1=POSITION_DELETES, 2=EQUALITY_DELETES per Iceberg spec | I1/I3 | Would count wrong file types for delete-accumulation rule |

A5 is verified from official Trino docs. A1, A2, A3, A4 are ASSUMED based on training knowledge and fixture inspection but not confirmed via running code in this session.

---

## Open Questions

1. **Table name extraction from descriptor — catalog/schema/table parsing**
   - What we know: `descriptor["table"]` is `"iceberg:test_fixtures.orders$data@7192078785404198795 constraint on [ts]"` in Trino 480
   - What's unclear: Is this format identical in Trino 429? Does it change for non-Iceberg catalogs or for view-based queries?
   - Recommendation: Write the parser with a graceful fallback: if parsing fails, set `table` arg to `None` in `RuleEngine.run()` and skip all METADATA-requiring rules with `RuleSkipped(reason="table_name_unresolvable")`.

2. **`$files` response size for large tables (Pitfall 7)**
   - What we know: The `CatalogSource` port does `SELECT * FROM table$files` with no LIMIT
   - What's unclear: Whether Phase 4 should add a LIMIT parameter to the port, or whether the engine should cap at a configurable row count
   - Recommendation: Add `max_metadata_rows: int = 10000` to `RuleThresholds`. Engine truncates the response before passing to EvidenceBundle. Add a warning to the RuleFinding evidence when truncated.

3. **Trino 429 partition-pruning EXPLAIN signal**
   - What we know: Trino 480 shows `constraint on [ts]` in the descriptor when pruning applies
   - What's unclear: Does Trino 429 use the same signal, or was this added in a later version?
   - Recommendation: Run the fixture capture script against the Trino 429 docker container and check `iceberg_partition_filter.json`. The 429 fixture corpus does not currently include a partition-filter fixture. [ASSUMED]

---

## Environment Availability

Step 2.6: Phase 4 is code-only (Python source + test fixtures). No new external services beyond what was established in Phases 1–3. Environment availability check: SKIPPED (no new external dependencies).

The docker-compose stack (Trino 480 + Lakekeeper + MinIO + PostgreSQL) from Phase 2 is already available for any integration tests that need live evidence fetching. The `iceberg_partition_filter.json` fixture already exists in the Phase 3 corpus.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.3 + pytest-asyncio 1.3.0 |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/rules/ -x -q` |
| Full suite command | `uv run pytest tests/ -x -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| RUL-01 | Registry registers Rule subclass; engine runs it | unit | `pytest tests/rules/test_registry.py -x` | Wave 0 |
| RUL-02 | Engine prefetches evidence once; union of requirements | unit | `pytest tests/rules/test_engine.py::test_prefetch_once -x` | Wave 0 |
| RUL-03 | Offline mode skips ICEBERG_METADATA rules with `rule_skipped` | unit | `pytest tests/rules/test_engine.py::test_skip_offline -x` | Wave 0 |
| RUL-04 | Crashing rule emits `rule_error`; other rules complete | unit | `pytest tests/rules/test_engine.py::test_isolation -x` | Wave 0 |
| RUL-05 | RuleFinding has all required fields; discriminated union serializes correctly | unit | `pytest tests/rules/test_findings.py -x` | Wave 0 |
| RUL-06 | Each rule has synthetic, realistic, and negative-control fixtures | unit | `pytest tests/rules/test_r1*.py tests/rules/test_i*.py ... -x` | Wave 0 (stubs) |
| RUL-07 | R1 fires on NaN estimate; does not fire on complete stats | unit | `pytest tests/rules/test_r1_missing_stats.py -x` | Wave 1 |
| RUL-08 | R2 fires on full scan with predicate; not on scan with constraint | unit | `pytest tests/rules/test_r2_partition_pruning.py -x` | Wave 1 |
| RUL-09 | R3 fires on function-wrapped predicate; not on range predicate | unit | `pytest tests/rules/test_r3_predicate_pushdown.py -x` | Wave 1 |
| RUL-10 | R4 fires on join without dynamicFilters in probe scan; not on join with it | unit | `pytest tests/rules/test_r4_dynamic_filtering.py -x` | Wave 1 |
| RUL-11 | R5 fires on REPLICATED join with large build side | unit | `pytest tests/rules/test_r5_broadcast.py -x` | Wave 1 |
| RUL-12 | R6 fires on join with large probe/small build and missing stats | unit | `pytest tests/rules/test_r6_join_order.py -x` | Wave 1 |
| RUL-13 | R7 fires when max/median CPU ratio > 5×; not on uniform distribution | unit | `pytest tests/rules/test_r7_skew.py -x` | Wave 1 |
| RUL-14 | R8 fires when exchange bytes > scan bytes | unit | `pytest tests/rules/test_r8_exchange.py -x` | Wave 1 |
| RUL-15 | R9 fires when output/input bytes < 0.10 threshold | unit | `pytest tests/rules/test_r9_selectivity.py -x` | Wave 1 |
| RUL-16 | I1 fires on high split count; not on normal file counts | unit | `pytest tests/rules/test_i1_small_files.py -x` | Wave 2 |
| RUL-17 | I3 fires when delete file count > threshold from $files rows | unit | `pytest tests/rules/test_i3_delete_files.py -x` | Wave 2 |
| RUL-18 | I6 fires when snapshot count > 50 or oldest > 30 days | unit | `pytest tests/rules/test_i6_stale_snapshots.py -x` | Wave 2 |
| RUL-19 | I8 fires on misaligned partition predicate; not on aligned predicate | unit | `pytest tests/rules/test_i8_partition_transform.py -x` | Wave 2 |
| RUL-20 | D11 fires when estimated rows diverge > 5× from actual rows | unit | `pytest tests/rules/test_d11_cost_vs_actual.py -x` | Wave 2 |
| RUL-21 | Threshold override via env changes which fixture triggers | unit | `pytest tests/rules/test_thresholds.py -x` (parameterized) | Wave 0 |

### Sampling Rate

- **Per task commit:** `uv run pytest tests/rules/ -x -q`
- **Per wave merge:** `uv run pytest tests/ -x -q`
- **Phase gate:** `uv run pytest tests/ -q` (all green, no -x) before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `tests/rules/__init__.py` — package init
- [ ] `tests/rules/test_registry.py` — registry register/lookup
- [ ] `tests/rules/test_engine.py` — prefetch, skip, isolation, run loop
- [ ] `tests/rules/test_findings.py` — RuleFinding discriminated union round-trip
- [ ] `tests/rules/test_thresholds.py` — threshold env override + parameterized trigger test
- [ ] `tests/rules/conftest.py` — shared fixtures: minimal EstimatedPlan, minimal ExecutedPlan, stub StatsSource, stub CatalogSource
- [ ] Fix `BasePlan.walk()` WR-01: replace `pop(0)` with `pop()` + `extend(reversed(...))` in `src/mcp_trino_optimizer/parser/models.py:165`

---

## Security Domain

Rules are pure Python with no I/O. No new security surface is introduced in Phase 4.

The `RuleThresholds(BaseSettings)` class follows the same pattern as `Settings` — env vars only, `env_prefix='TRINO_RULE_'`, no secrets. No injection vectors.

The `evidence` dict in `RuleFinding` must contain only data derived from the plan or metadata sources — never user-supplied SQL or table/column names that could flow into recommendation templates. The `message` field is rule-authored (a static f-string with structured values), never free-form user text.

Security domain: SKIPPED (no new attack surface beyond existing ports already hardened in Phase 2).

---

## Sources

### Primary (HIGH confidence)
- `tests/fixtures/explain/480/iceberg_partition_filter.json` — partition constraint signal (`constraint on [ts]`) verified in plan descriptor
- `tests/fixtures/explain/480/join.json` — `dynamicFilterAssignments` and `dynamicFilters` field locations in InnerJoin and ScanFilter
- `tests/fixtures/explain/480/iceberg_partition_filter_analyze.txt` — `constraint on [ts]` in EXPLAIN ANALYZE TableScan; Splits count comparison
- `tests/fixtures/explain/480/full_scan_analyze.txt` — full scan Splits: 6 vs partition-filtered Splits: 1
- `tests/fixtures/explain/480/join_analyze.txt` — `Dynamic filters:` section format in EXPLAIN ANALYZE
- `tests/fixtures/explain/429/simple_select.json` — `ScanFilter` node (Trino 429 naming) with `filterPredicate` in descriptor
- `src/mcp_trino_optimizer/parser/models.py` — PlanNode fields, BasePlan.walk(), iceberg_split_count docstrings
- `src/mcp_trino_optimizer/ports/stats_source.py` — StatsSource.fetch_table_stats return schema
- `src/mcp_trino_optimizer/ports/catalog_source.py` — CatalogSource.fetch_iceberg_metadata interface

### Secondary (MEDIUM-HIGH confidence)
- [Trino Iceberg connector docs](https://trino.io/docs/current/connector/iceberg.html) — `$files` content values (0/1/2), `$snapshots` schema, `$partitions` limitations
- [Trino dynamic filtering docs](https://trino.io/docs/current/admin/dynamic-filtering.html) — `dynamicFilterAssignments`, `dynamicFilterSplitsProcessed` fields
- [Trino issue #28910](https://github.com/trinodb/trino/issues/28910) — OPEN; `$partitions` missing delete-file metrics; `$files` workaround confirmed
- [Trino issue #19266](https://github.com/trinodb/trino/issues/19266) — CLOSED Jan 2025; partial partition pruning fix; Trino 429 affected
- [CONTEXT.md D-01 through D-06] — locked decisions for module structure, type system, threshold config

### Tertiary (LOW confidence — flagged for validation)
- A1–A4 in Assumptions Log above (NaN behavior, $files LIMIT, version-specific constraint signal, descriptor format consistency)

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new deps; all patterns follow Phase 1–3 conventions
- Rule infrastructure (registry, engine, findings): HIGH — patterns are locked by CONTEXT.md decisions
- Rule detection logic for R1-R9 + D11: HIGH — verified against real fixture corpus
- Rule detection logic for I1/I3/I6/I8: MEDIUM-HIGH — verified $files schema; some details ASSUMED
- Trino version-specific behavior for R2/I8: MEDIUM — issue #19266 resolved, but exact version boundary for partial pruning is ASSUMED ~440

**Research date:** 2026-04-13
**Valid until:** 2026-07-13 (stable domain; Trino release cadence is ~monthly but plan JSON format is stable within major versions)
