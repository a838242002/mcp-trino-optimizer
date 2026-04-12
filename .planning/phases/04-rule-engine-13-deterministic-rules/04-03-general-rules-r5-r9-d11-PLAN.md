---
phase: 04-rule-engine-13-deterministic-rules
plan: 03
type: execute
wave: 3
depends_on:
  - 04-01-rule-infrastructure-PLAN.md
  - 04-02-general-rules-r1-r4-PLAN.md
files_modified:
  - src/mcp_trino_optimizer/rules/r5_broadcast_too_big.py
  - src/mcp_trino_optimizer/rules/r6_join_order.py
  - src/mcp_trino_optimizer/rules/r7_cpu_skew.py
  - src/mcp_trino_optimizer/rules/r8_exchange_volume.py
  - src/mcp_trino_optimizer/rules/r9_low_selectivity.py
  - src/mcp_trino_optimizer/rules/d11_cost_vs_actual.py
  - tests/rules/test_r5_broadcast_join.py
  - tests/rules/test_r6_join_order.py
  - tests/rules/test_r7_skew.py
  - tests/rules/test_r8_exchange.py
  - tests/rules/test_r9_low_selectivity.py
  - tests/rules/test_d11_cost_vs_actual.py
autonomous: true
requirements:
  - RUL-06
  - RUL-11
  - RUL-12
  - RUL-13
  - RUL-14
  - RUL-15
  - RUL-20
  - RUL-21

must_haves:
  truths:
    - "R5 fires on REPLICATED join with build-side estimates exceeding broadcast_max_bytes"
    - "R5 does not fire on PARTITIONED join or small REPLICATED build side"
    - "R6 fires when probe-side row estimate is much larger than build-side estimate"
    - "R7 fires when max/median CPU ratio among operators exceeds skew_ratio threshold (ExecutedPlan only)"
    - "R7 emits RuleSkipped on EstimatedPlan (no metrics)"
    - "R8 fires when total exchange outputSizeInBytes exceeds total scan outputSizeInBytes"
    - "R9 fires when output_bytes / input_bytes < scan_selectivity_threshold on scan nodes"
    - "D11 fires when estimated outputRowCount diverges from actual output_rows by > stats_divergence_factor"
    - "D11 emits RuleSkipped on EstimatedPlan"
    - "Each rule has 3 fixture classes; negative-control tests are all implemented"
  artifacts:
    - path: "src/mcp_trino_optimizer/rules/r5_broadcast_too_big.py"
      provides: "R5BroadcastTooBig rule"
    - path: "src/mcp_trino_optimizer/rules/r6_join_order.py"
      provides: "R6JoinOrderInversion rule"
    - path: "src/mcp_trino_optimizer/rules/r7_cpu_skew.py"
      provides: "R7CpuSkew rule"
    - path: "src/mcp_trino_optimizer/rules/r8_exchange_volume.py"
      provides: "R8ExchangeVolume rule"
    - path: "src/mcp_trino_optimizer/rules/r9_low_selectivity.py"
      provides: "R9LowSelectivity rule"
    - path: "src/mcp_trino_optimizer/rules/d11_cost_vs_actual.py"
      provides: "D11CostVsActual rule"
  key_links:
    - from: "src/mcp_trino_optimizer/rules/r7_cpu_skew.py"
      to: "src/mcp_trino_optimizer/parser/models.py"
      via: "requires ExecutedPlan isinstance check; reads cpu_time_ms on nodes"
    - from: "src/mcp_trino_optimizer/rules/d11_cost_vs_actual.py"
      to: "src/mcp_trino_optimizer/parser/models.py"
      via: "reads estimates[0].output_row_count vs output_rows on ExecutedPlan nodes"
---

<objective>
Implement rules R5–R9 and D11: the join-analysis rules (broadcast size, join order), the execution-quality rules (CPU skew, exchange volume, low selectivity), and the statistical divergence rule. R7 and D11 require ExecutedPlan; all others work on EstimatedPlan.

Purpose: R5/R6 catch common join misconfigurations visible in estimated plans. R7/D11 close the loop on EXPLAIN ANALYZE evidence — the divergence and skew signals that justify running ANALYZE at all.

Output: 6 rule files + 6 fully-implemented test files (3 fixture classes each).
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/04-rule-engine-13-deterministic-rules/04-CONTEXT.md
@.planning/phases/04-rule-engine-13-deterministic-rules/04-RESEARCH.md
@.planning/phases/04-rule-engine-13-deterministic-rules/04-01-SUMMARY.md
@.planning/phases/04-rule-engine-13-deterministic-rules/04-02-SUMMARY.md

@src/mcp_trino_optimizer/rules/__init__.py
@src/mcp_trino_optimizer/rules/findings.py
@src/mcp_trino_optimizer/rules/evidence.py
@src/mcp_trino_optimizer/rules/base.py
@src/mcp_trino_optimizer/rules/registry.py
@src/mcp_trino_optimizer/rules/thresholds.py
@src/mcp_trino_optimizer/parser/models.py

<interfaces>
<!-- Key types. Same infrastructure as Plan 02. -->

From rules/evidence.py:
```python
class EvidenceRequirement(Enum):
    PLAN_ONLY = "plan_only"
    PLAN_WITH_METRICS = "plan_with_metrics"   # R7, D11 — ExecutedPlan required
    TABLE_STATS = "table_stats"               # R6 needs this
    ICEBERG_METADATA = "iceberg_metadata"

@dataclass
class EvidenceBundle:
    plan: BasePlan
    table_stats: dict[str, Any] | None = None  # R6 reads this

def safe_float(val: Any) -> float | None: ...  # NaN-safe float conversion
```

From parser/models.py (execution metrics — ExecutedPlan nodes):
```python
class PlanNode(BaseModel):
    id: str
    name: str
    descriptor: dict[str, str]          # "distribution" for InnerJoin
    estimates: list[CostEstimate]       # estimates[0].output_row_count, output_size_in_bytes
    children: list[PlanNode]
    # ExecutedPlan fields:
    cpu_time_ms: float | None
    input_bytes: int | None
    output_bytes: int | None
    output_rows: int | None

class CostEstimate(BaseModel):
    output_row_count: float | None = Field(alias="outputRowCount")
    output_size_in_bytes: float | None = Field(alias="outputSizeInBytes")

class ExecutedPlan(BasePlan):
    plan_type: Literal["executed"] = "executed"

class EstimatedPlan(BasePlan):
    plan_type: Literal["estimated"] = "estimated"
```

From rules/thresholds.py (relevant fields):
```python
class RuleThresholds(BaseSettings):
    broadcast_max_bytes: int = 100 * 1024 * 1024  # R5
    skew_ratio: float = 5.0                         # R7
    scan_selectivity_threshold: float = 0.10        # R9
    stats_divergence_factor: float = 5.0            # D11
```

Phase 3 fixture for join: tests/fixtures/explain/480/join.json — has InnerJoin with "distribution": "REPLICATED"
Phase 3 fixture for full scan: tests/fixtures/explain/480/full_scan.json — has scan nodes for R8/R9 testing
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: R5 BroadcastTooBig + R6 JoinOrderInversion + R8 ExchangeVolume</name>
  <files>
    src/mcp_trino_optimizer/rules/r5_broadcast_too_big.py
    src/mcp_trino_optimizer/rules/r6_join_order.py
    src/mcp_trino_optimizer/rules/r8_exchange_volume.py
    tests/rules/test_r5_broadcast_join.py
    tests/rules/test_r6_join_order.py
    tests/rules/test_r8_exchange.py
  </files>
  <behavior>
    R5 tests:
    - Synthetic-minimum: InnerJoin node with descriptor={"distribution": "REPLICATED"}. Build-side (children[1]) has estimates[0].output_size_in_bytes = 200 * 1024 * 1024 (200MB > 100MB threshold). R5 fires with rule_id="R5", severity="high".
    - Negative (small build): build-side estimates[0].output_size_in_bytes = 10 * 1024 * 1024 (10MB). R5 returns [].
    - Negative (PARTITIONED): descriptor={"distribution": "PARTITIONED"}. R5 returns [] regardless of size.
    - Realistic: Load tests/fixtures/explain/480/join.json; InnerJoin has REPLICATED distribution — check if build side estimate exceeds threshold (adjust test expectation based on actual fixture data).

    R6 tests:
    - Synthetic-minimum: InnerJoin where children[0] (probe) has estimates[0].output_row_count = 1_000_000 and children[1] (build) has estimates[0].output_row_count = 1_000. Ratio = 1000×. TABLE_STATS with probe table having row_count=None (no stats). R6 fires with rule_id="R6", severity="medium".
    - Negative: probe has 1M rows, build has 500K rows (2× ratio, below any reasonable threshold). R6 returns [].
    - Negative: Large probe but stats ARE present (table_stats.row_count is not None). R6 returns [] (CBO may have valid reason for this order).

    R8 tests:
    - Synthetic-minimum: Plan with Exchange node having estimates[0].output_size_in_bytes = 500MB. Scan node has estimates[0].output_size_in_bytes = 100MB. Exchange/scan ratio > 1. R8 fires with rule_id="R8", severity="medium".
    - Negative: Exchange size = 10MB, scan size = 100MB. R8 returns [].
    - Negative: No Exchange nodes at all. R8 returns [].
    - Realistic: Load full_scan.json; check for Exchange nodes and compute ratio.
  </behavior>
  <action>
    **r5_broadcast_too_big.py:**
    - rule_id = "R5"
    - evidence_requirement = EvidenceRequirement.PLAN_ONLY
    - check() finds all InnerJoin and SemiJoin nodes
    - For each join where `descriptor.get("distribution") == "REPLICATED"`:
      * Find build side = children[1] (or children[-1] — build is the right side)
      * Walk the build side subtree to find the first Exchange or LocalExchange node; use its estimates, OR use the direct child's estimates if no Exchange found
      * `build_bytes = safe_float(build_node.estimates[0].output_size_in_bytes if build_node.estimates else None)`
      * If build_bytes is not None and build_bytes > thresholds.broadcast_max_bytes → fire
    - severity: "high"
    - confidence: 0.85 (CBO estimate; actual size may differ)
    - evidence dict: {"distribution": "REPLICATED", "build_side_estimated_bytes": build_bytes, "threshold_bytes": thresholds.broadcast_max_bytes}
    - Constructor accepts `thresholds: RuleThresholds | None = None`; use `RuleThresholds()` if None
    - Register at module bottom

    **r6_join_order.py:**
    - rule_id = "R6"
    - evidence_requirement = EvidenceRequirement.TABLE_STATS
    - check() finds InnerJoin and SemiJoin nodes
    - For each join:
      * probe_rows = safe_float(children[0].estimates[0].output_row_count) if estimates present
      * build_rows = safe_float(children[1].estimates[0].output_row_count) if estimates present
      * Skip if either is None or NaN
      * If probe_rows / build_rows > 100.0 AND evidence.table_stats is None or table_stats.get("row_count") is None → fire R6
      * Threshold 100× is not a RuleThreshold field (it's a detection heuristic, not user-tunable) — use constant with citation comment
    - severity: "medium"
    - confidence: 0.6 (join order may be intentional; without stats we can't prove it)
    - evidence dict: {"probe_estimated_rows": probe_rows, "build_estimated_rows": build_rows, "probe_to_build_ratio": ratio, "stats_available": bool}
    - Register at module bottom

    **r8_exchange_volume.py:**
    - rule_id = "R8"
    - evidence_requirement = EvidenceRequirement.PLAN_ONLY
    - check() computes two sums across the whole plan:
      * exchange_bytes: sum of output_size_in_bytes from all Exchange, LocalExchange, RemoteSource nodes
      * scan_bytes: sum of output_size_in_bytes from all TableScan, ScanFilter, ScanFilterProject nodes
    - Use safe_float() for each value; skip None estimates
    - If exchange_bytes > scan_bytes and exchange_bytes > 0 and scan_bytes > 0 → fire
    - severity: "medium"
    - confidence: 0.75
    - evidence dict: {"total_exchange_bytes": exchange_bytes, "total_scan_bytes": scan_bytes, "ratio": ratio}
    - operator_ids: list of all exchange node IDs
    - Register at module bottom

    Un-skip and implement tests. Build PlanNode trees inline for synthetic tests. Use fixtures for realistic tests.
  </action>
  <verify>
    <automated>uv run pytest tests/rules/test_r5_broadcast_join.py tests/rules/test_r6_join_order.py tests/rules/test_r8_exchange.py -x -q</automated>
  </verify>
  <done>All R5, R6, R8 tests pass (synthetic + realistic + negative-control). Zero mypy errors.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: R7 CpuSkew + R9 LowSelectivity + D11 CostVsActual</name>
  <files>
    src/mcp_trino_optimizer/rules/r7_cpu_skew.py
    src/mcp_trino_optimizer/rules/r9_low_selectivity.py
    src/mcp_trino_optimizer/rules/d11_cost_vs_actual.py
    tests/rules/test_r7_skew.py
    tests/rules/test_r9_low_selectivity.py
    tests/rules/test_d11_cost_vs_actual.py
  </files>
  <behavior>
    R7 tests:
    - Synthetic-minimum (ExecutedPlan): Plan with 5 operators with cpu_time_ms = [100, 100, 100, 100, 500]. Max=500, median=100. Ratio=5.0. R7 fires with rule_id="R7" (at threshold). Test also with ratio=5.1 (fires) and ratio=4.9 (does not fire).
    - Negative (uniform): All operators have cpu_time_ms=100. R7 returns [].
    - Skipped on EstimatedPlan: Pass an EstimatedPlan instance (not ExecutedPlan). The engine handles the skip, but R7.check() on an EstimatedPlan should simply return [] (the engine already filtered by PLAN_WITH_METRICS — but the rule should still be safe).

    R9 tests:
    - Synthetic-minimum (EstimatedPlan): TableScan node with input_bytes=1_000_000 and output_bytes=50_000 (5% selectivity < 10% threshold). R9 fires with rule_id="R9", severity="medium".
    - Negative: output_bytes=200_000 (20% selectivity > 10%). R9 returns [].
    - Both None case: input_bytes or output_bytes is None. R9 returns [] (cannot compute).
    - Realistic: Load full_scan.json EstimatedPlan; check selectivity ratio on scan nodes.

    D11 tests:
    - Synthetic-minimum (ExecutedPlan): PlanNode with estimates=[CostEstimate(outputRowCount=1000.0)] and output_rows=10_000. Ratio = 10.0 > 5.0 threshold. D11 fires with rule_id="D11", severity="high".
    - Under-estimate case: estimated=10_000, actual=100. Ratio = 100× in inverse direction. D11 fires.
    - Negative: estimated=1000, actual=1200. Ratio=1.2 (within threshold). D11 returns [].
    - NaN estimate: estimates[0].output_row_count = NaN. D11 returns [] (safe_float returns None → skip).
    - Realistic: Would need an execute fixture; use synthetic ExecutedPlan with metrics inline.
  </behavior>
  <action>
    **r7_cpu_skew.py:**
    - rule_id = "R7"
    - evidence_requirement = EvidenceRequirement.PLAN_WITH_METRICS
    - check() collects cpu_time_ms from ALL nodes via plan.walk() where cpu_time_ms is not None
    - If fewer than 3 nodes have cpu_time_ms → return [] (insufficient data)
    - Compute: max_cpu, and median (use statistics.median from stdlib — no numpy)
    - If median == 0.0 → return [] (avoid division by zero)
    - If max_cpu / median > thresholds.skew_ratio → fire
    - severity: "high" (skew above threshold is almost always a real problem)
    - confidence: 0.8
    - evidence dict: {"max_cpu_ms": max_cpu, "median_cpu_ms": median, "skew_ratio": ratio, "threshold": thresholds.skew_ratio, "node_count": len(cpu_values)}
    - operator_ids: [id of the node with max cpu_time_ms]
    - Message: "CPU time skew detected: max {max_cpu:.1f}ms vs median {median:.1f}ms ({ratio:.1f}× ratio > {threshold}× threshold)"
    - Register at module bottom

    **r9_low_selectivity.py:**
    - rule_id = "R9"
    - evidence_requirement = EvidenceRequirement.PLAN_ONLY (works on both estimated and executed)
    - For EstimatedPlan: use estimates[0].output_size_in_bytes vs... actually for estimated plan the scan input bytes is not directly available in estimates. Use the scan node's output_bytes field (input_bytes is only for ExecutedPlan). Fall back to: if output_size_in_bytes in estimates is very low relative to cpuCost proxy — but this is unreliable. Better: use ExecutedPlan path for concrete detection, use PLAN_ONLY evidence but check for actual input_bytes/output_bytes on nodes.
    - Approach: check node.input_bytes and node.output_bytes (both available on PlanNode, populated for ExecutedPlan). For EstimatedPlan these will be None → skip silently. This means R9 effectively only fires on ExecutedPlan but declares PLAN_ONLY evidence (no external fetch needed).
    - For scan nodes where input_bytes is not None and output_bytes is not None and input_bytes > 0:
      * ratio = output_bytes / input_bytes
      * If ratio < thresholds.scan_selectivity_threshold → fire
    - severity: "medium"
    - confidence: 0.9 (actual bytes are reliable)
    - evidence dict: {"input_bytes": input_bytes, "output_bytes": output_bytes, "selectivity_ratio": ratio, "threshold": thresholds.scan_selectivity_threshold, "table": node.descriptor.get("table", "")}
    - operator_ids: [node.id]
    - Register at module bottom

    **d11_cost_vs_actual.py:**
    - rule_id = "D11"
    - evidence_requirement = EvidenceRequirement.PLAN_WITH_METRICS
    - check() iterates all scan nodes (TableScan, ScanFilter, ScanFilterProject) in plan.walk()
    - For each scan node:
      * estimated = safe_float(node.estimates[0].output_row_count) if node.estimates else None
      * actual = node.output_rows (int | None)
      * Skip if estimated is None or actual is None or actual == 0
      * divergence = actual / estimated if estimated > 0 else None
      * Also check inverse: if estimated / actual > threshold (CBO severely over-estimates)
      * Fire if divergence > factor OR divergence < 1/factor
    - severity: "high"
    - confidence: 0.95 (actual vs estimate is direct evidence)
    - evidence dict: {"estimated_rows": estimated, "actual_rows": actual, "divergence_factor": divergence, "threshold": thresholds.stats_divergence_factor}
    - operator_ids: [node.id]
    - Message: "CBO estimate {estimated:.0f} rows diverged {divergence:.1f}× from actual {actual} rows (threshold: {factor}×)"
    - Register at module bottom

    Un-skip and implement all three test files. Use `statistics` module for median in R7 tests too.
  </action>
  <verify>
    <automated>uv run pytest tests/rules/test_r7_skew.py tests/rules/test_r9_low_selectivity.py tests/rules/test_d11_cost_vs_actual.py -x -q</automated>
  </verify>
  <done>R7, R9, D11 tests all pass. `uv run pytest tests/rules/ -q` shows R1–R9 + D11 green, I1/I3/I6/I8 stubs still skipped. Zero mypy errors across all 6 new rule files.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| PlanNode.cpu_time_ms → R7 statistics.median() | CPU time values from EXPLAIN ANALYZE text parsing; should be validated as non-negative |
| PlanNode.estimates[0].output_size_in_bytes → R5/R8 | CBO estimates are from Trino plan JSON; may be NaN or None |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-04-10 | Denial of Service | R7 statistics.median() on large node list | accept | plan.walk() on largest realistic Trino plan is <10k nodes; stdlib statistics.median() is O(n log n); no DoS risk at this scale |
| T-04-11 | Tampering | D11 divergence calculation with NaN estimates | mitigate | safe_float() guards all estimate reads; division by zero guarded by `if estimated > 0`; both directions checked (over and under estimate) |
| T-04-12 | Information Disclosure | R5/R8 evidence dict with byte estimates | accept | Byte estimates are CBO internals from the Trino plan — no user PII or secrets |
| T-04-13 | Denial of Service | R6 join-child indexing (children[0], children[1]) | mitigate | Guard with `if len(node.children) < 2: continue` before accessing children[1]; single-child joins are malformed but must not crash |
</threat_model>

<verification>
```bash
# Run all R5–R9 + D11 tests
uv run pytest tests/rules/test_r5_broadcast_join.py tests/rules/test_r6_join_order.py tests/rules/test_r7_skew.py tests/rules/test_r8_exchange.py tests/rules/test_r9_low_selectivity.py tests/rules/test_d11_cost_vs_actual.py -v

# Full rules suite — R1–R9 + D11 green, I rules skipped
uv run pytest tests/rules/ -q

# Type check all 6 new rule files
uv run mypy src/mcp_trino_optimizer/rules/r5_broadcast_too_big.py src/mcp_trino_optimizer/rules/r6_join_order.py src/mcp_trino_optimizer/rules/r7_cpu_skew.py src/mcp_trino_optimizer/rules/r8_exchange_volume.py src/mcp_trino_optimizer/rules/r9_low_selectivity.py src/mcp_trino_optimizer/rules/d11_cost_vs_actual.py --strict

# Confirm all 10 rules registered
python -c "
from mcp_trino_optimizer.rules import registry
import mcp_trino_optimizer.rules.r5_broadcast_too_big
import mcp_trino_optimizer.rules.r6_join_order
import mcp_trino_optimizer.rules.r7_cpu_skew
import mcp_trino_optimizer.rules.r8_exchange_volume
import mcp_trino_optimizer.rules.r9_low_selectivity
import mcp_trino_optimizer.rules.d11_cost_vs_actual
print([r.rule_id for r in registry.all_rules()])
"
```
</verification>

<success_criteria>
1. All 6 test files pass with synthetic-minimum + realistic + negative-control per rule
2. R5, R6, R7, R8, R9, D11 are registered in global `registry`
3. R7 and D11 return [] when called on EstimatedPlan (engine skips them via PLAN_WITH_METRICS, but rule bodies are also safe)
4. `uv run pytest tests/rules/ -q` — 10 rule test files green, 4 Iceberg rule stubs still skipped, zero collection errors
5. `uv run mypy src/mcp_trino_optimizer/rules/ --strict` — zero errors
</success_criteria>

<output>
After completion, create `.planning/phases/04-rule-engine-13-deterministic-rules/04-03-SUMMARY.md` with:
- R5–R9 + D11 implemented and registered
- Detection logic details and thresholds used
- Any tricky fixture construction (inline PlanNode tree patterns that worked)
- Any deviations from this plan
</output>
