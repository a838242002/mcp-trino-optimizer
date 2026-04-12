---
phase: 04-rule-engine-13-deterministic-rules
plan: 04
type: execute
wave: 4
depends_on:
  - 04-01-rule-infrastructure-PLAN.md
  - 04-02-general-rules-r1-r4-PLAN.md
  - 04-03-general-rules-r5-r9-d11-PLAN.md
files_modified:
  - src/mcp_trino_optimizer/rules/i1_small_files.py
  - src/mcp_trino_optimizer/rules/i3_delete_files.py
  - src/mcp_trino_optimizer/rules/i6_stale_snapshots.py
  - src/mcp_trino_optimizer/rules/i8_partition_transform.py
  - src/mcp_trino_optimizer/rules/__init__.py
  - tests/rules/test_i1_small_files.py
  - tests/rules/test_i3_delete_files.py
  - tests/rules/test_i6_stale_snapshots.py
  - tests/rules/test_i8_partition_transform.py
autonomous: true
requirements:
  - RUL-06
  - RUL-16
  - RUL-17
  - RUL-18
  - RUL-19
  - RUL-21

must_haves:
  truths:
    - "I1 fires when iceberg_files contains many small data files (median < small_file_bytes) or iceberg_split_count > threshold on the scan node"
    - "I1 does not fire when files are adequately sized and split count is normal"
    - "I3 fires when $files rows with content IN (1,2) exceed delete_file_count_threshold"
    - "I3 uses the $files cross-reference workaround (not $partitions) per Trino issue #28910"
    - "I6 fires when snapshot count > max_snapshot_count or oldest snapshot age > snapshot_retention_days"
    - "I6 does not fire on a table with few recent snapshots"
    - "I8 fires when scan has partition constraint but constraint boundaries are not aligned with the partition transform granularity"
    - "All four Iceberg rules emit RuleSkipped when catalog_source is None (offline mode)"
    - "All thresholds use RuleThresholds fields with citation comments"
    - "Each rule has synthetic-minimum, realistic (fabricated $files/$snapshots rows), and negative-control tests"
  artifacts:
    - path: "src/mcp_trino_optimizer/rules/i1_small_files.py"
      provides: "I1SmallFiles rule"
    - path: "src/mcp_trino_optimizer/rules/i3_delete_files.py"
      provides: "I3DeleteFiles rule"
    - path: "src/mcp_trino_optimizer/rules/i6_stale_snapshots.py"
      provides: "I6StaleSnapshots rule"
    - path: "src/mcp_trino_optimizer/rules/i8_partition_transform.py"
      provides: "I8PartitionTransform rule"
    - path: "src/mcp_trino_optimizer/rules/__init__.py"
      provides: "Updated public API including all 13 rules auto-imported"
  key_links:
    - from: "src/mcp_trino_optimizer/rules/i3_delete_files.py"
      to: "src/mcp_trino_optimizer/rules/evidence.py"
      via: "reads EvidenceBundle.iceberg_files, filters by content IN (1, 2) client-side"
    - from: "src/mcp_trino_optimizer/rules/i6_stale_snapshots.py"
      to: "src/mcp_trino_optimizer/rules/evidence.py"
      via: "reads EvidenceBundle.iceberg_snapshots"
    - from: "src/mcp_trino_optimizer/rules/i8_partition_transform.py"
      to: "src/mcp_trino_optimizer/parser/models.py"
      via: "reads PlanNode.descriptor['table'] for constraint detail; uses PlanNode.iceberg_partition_spec_id"
---

<objective>
Implement the four Iceberg-specific rules I1, I3, I6, I8. All require ICEBERG_METADATA evidence (CatalogSource). These rules close the Iceberg observability loop: small files, delete accumulation, stale snapshots, and partition transform misalignment.

Purpose: The Iceberg rules are the differentiators that make this tool more useful than generic EXPLAIN analysis. They provide evidence that cannot be obtained from the query plan alone — requires the $files/$snapshots metadata tables. They also complete the full set of 13 rules, satisfying RUL-06 (three fixture classes per rule) and RUL-21 (data-driven thresholds).

Output: 4 rule files + 4 test files. Updated __init__.py that imports all 13 rules so a single import wires the registry.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/04-rule-engine-13-deterministic-rules/04-CONTEXT.md
@.planning/phases/04-rule-engine-13-deterministic-rules/04-RESEARCH.md
@.planning/phases/04-rule-engine-13-deterministic-rules/04-01-SUMMARY.md
@.planning/phases/04-rule-engine-13-deterministic-rules/04-03-SUMMARY.md

@src/mcp_trino_optimizer/rules/__init__.py
@src/mcp_trino_optimizer/rules/findings.py
@src/mcp_trino_optimizer/rules/evidence.py
@src/mcp_trino_optimizer/rules/base.py
@src/mcp_trino_optimizer/rules/registry.py
@src/mcp_trino_optimizer/rules/thresholds.py
@src/mcp_trino_optimizer/parser/models.py

<interfaces>
<!-- Key types from prior plans. -->

From rules/evidence.py:
```python
@dataclass
class EvidenceBundle:
    plan: BasePlan
    table_stats: dict[str, Any] | None = None
    iceberg_snapshots: list[dict[str, Any]] | None = None   # from $snapshots — I6
    iceberg_files: list[dict[str, Any]] | None = None       # from $files — I1, I3

# $files row schema (Iceberg spec, verified from trino docs):
# {
#   "content": int,          # 0=DATA, 1=POSITION_DELETES, 2=EQUALITY_DELETES
#   "file_path": str,
#   "file_format": str,
#   "record_count": int,
#   "file_size_in_bytes": int,
# }

# $snapshots row schema:
# {
#   "committed_at": str,     # ISO8601 timestamp string from Trino
#   "snapshot_id": int,
#   "parent_id": int | None,
#   "operation": str,        # "append", "replace", "overwrite", "delete"
#   "manifest_list": str,
#   "summary": dict,
# }
```

From rules/thresholds.py:
```python
class RuleThresholds(BaseSettings):
    small_file_bytes: int = 16 * 1024 * 1024          # I1
    small_file_split_count_threshold: int = 10_000    # I1
    delete_file_count_threshold: int = 100            # I3
    delete_ratio_threshold: float = 0.10              # I3
    max_snapshot_count: int = 50                      # I6
    snapshot_retention_days: int = 30                 # I6
    max_metadata_rows: int = 10_000                   # all Iceberg rules
```

From parser/models.py (Iceberg-specific fields on PlanNode):
```python
iceberg_split_count: int | None    # populated for ExecutedPlan only
iceberg_file_count: int | None     # populated for ExecutedPlan only
iceberg_partition_spec_id: int | None
descriptor: dict[str, str]         # "table" has "constraint on [col]" when pruning applied
details: list[str]                 # constraint detail lines with "::" prefix for ranges
```

Phase 3 iceberg fixture:
- tests/fixtures/explain/480/iceberg_partition_filter.json — has "constraint on [ts]" + detail lines
- tests/fixtures/explain/480/iceberg_partition_filter_analyze.txt — has constraint range lines with "::"
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: I1 SmallFiles + I3 DeleteFiles</name>
  <files>
    src/mcp_trino_optimizer/rules/i1_small_files.py
    src/mcp_trino_optimizer/rules/i3_delete_files.py
    tests/rules/test_i1_small_files.py
    tests/rules/test_i3_delete_files.py
  </files>
  <behavior>
    I1 tests:
    - Synthetic-minimum (via iceberg_files): EvidenceBundle with iceberg_files = 200 rows all with content=0, file_size_in_bytes=8*1024*1024 (8MB < 16MB threshold). I1 fires with rule_id="I1", severity="high".
    - Synthetic (via split count): Scan node with iceberg_split_count=15_000 (> 10_000 threshold) in an ExecutedPlan. I1 fires even with no iceberg_files in bundle.
    - Negative-control (good file size): iceberg_files with median file_size_in_bytes = 200*1024*1024 (200MB >> 16MB). I1 returns [].
    - Negative (low split count): iceberg_split_count=500, large files. I1 returns [].
    - Realistic: Fabricate 50 rows with varying sizes — 40 at 5MB, 10 at 300MB. Median ≈ 5MB < 16MB. I1 fires.

    I3 tests:
    - Synthetic-minimum: iceberg_files = 120 rows with content=1 (position deletes) + 20 rows with content=0 (data). delete_count=120 > threshold 100. I3 fires with rule_id="I3", severity="high".
    - Delete ratio test: 50 delete-file rows with record_count=50_000 each + 10 data rows with record_count=100_000 each. delete_records=2_500_000, data_records=1_000_000 → ratio=2.5 > 0.10 threshold. I3 fires.
    - Negative: 5 delete files (< 100 threshold) with low record count. I3 returns [].
    - Negative: No delete files at all (all content=0). I3 returns [].
    - Realistic: Mixed file list with 110 position deletes, 5 equality deletes, 200 data files. I3 fires (115 > 100 threshold).
  </behavior>
  <action>
    **i1_small_files.py:**
    - rule_id = "I1"
    - evidence_requirement = EvidenceRequirement.ICEBERG_METADATA
    - check() has two detection paths:
      1. **Plan-based path** (primary for ExecutedPlan): scan nodes with iceberg_split_count > thresholds.small_file_split_count_threshold → fire immediately with severity="high", confidence=0.9
      2. **Metadata path** (always attempted when iceberg_files available): filter files where content==0 (DATA files only). Compute median file_size_in_bytes. If median < thresholds.small_file_bytes → fire with severity="high", confidence=0.95
    - Both paths can fire simultaneously (different operator_ids)
    - Helper `_median_file_size(files: list[dict]) -> float | None`: filter content==0, get sizes, return statistics.median or None if empty
    - evidence dict for metadata path: {"data_file_count": n, "median_file_size_bytes": median, "threshold_bytes": thresholds.small_file_bytes}
    - evidence dict for plan path: {"iceberg_split_count": count, "threshold": thresholds.small_file_split_count_threshold}
    - operator_ids for plan path: [node.id for each offending scan node]
    - operator_ids for metadata path: [] (no specific operator — table-level finding)
    - Register at module bottom

    **i3_delete_files.py:**
    - rule_id = "I3"
    - evidence_requirement = EvidenceRequirement.ICEBERG_METADATA
    - check() reads evidence.iceberg_files (if None → return [] since engine would have skipped)
    - Filter delete files: `delete_files = [f for f in files if f.get("content") in (1, 2)]`
    - Filter data files: `data_files = [f for f in files if f.get("content") == 0]`
    - delete_file_count = len(delete_files)
    - delete_records = sum(f.get("record_count", 0) for f in delete_files)
    - data_records = sum(f.get("record_count", 0) for f in data_files)
    - Check 1: delete_file_count > thresholds.delete_file_count_threshold → fire (severity="high")
    - Check 2: if data_records > 0 and delete_records / data_records > thresholds.delete_ratio_threshold → fire (severity="high")
    - Note in evidence when result was truncated: if len(evidence.iceberg_files) >= thresholds.max_metadata_rows → add "metadata_truncated": True to evidence
    - If both checks fire, emit TWO separate RuleFinding objects with different messages (count-based and ratio-based)
    - confidence: 0.95 (actual file counts from metadata)
    - evidence dict: {"position_delete_count": n, "equality_delete_count": n, "delete_file_count": total, "data_file_count": n, "delete_records": n, "data_records": n, "delete_ratio": ratio}
    - operator_ids: [] (table-level finding)
    - Cite in code comment: Trino issue #28910 — $partitions does not expose delete metrics, hence $files workaround
    - Register at module bottom
  </action>
  <verify>
    <automated>uv run pytest tests/rules/test_i1_small_files.py tests/rules/test_i3_delete_files.py -x -q</automated>
  </verify>
  <done>All I1 and I3 tests pass (3+ fixture classes each). evidence dict contains all documented fields. Zero mypy errors in both rule files.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: I6 StaleSnapshots + I8 PartitionTransform + wire all 13 rules</name>
  <files>
    src/mcp_trino_optimizer/rules/i6_stale_snapshots.py
    src/mcp_trino_optimizer/rules/i8_partition_transform.py
    src/mcp_trino_optimizer/rules/__init__.py
    tests/rules/test_i6_stale_snapshots.py
    tests/rules/test_i8_partition_transform.py
  </files>
  <behavior>
    I6 tests:
    - Synthetic-minimum: iceberg_snapshots = 60 rows (> 50 threshold), all with recent committed_at. I6 fires on count alone with rule_id="I6", severity="medium".
    - Age test: 10 snapshots, oldest committed_at = (now - 40 days). Age > 30-day threshold. I6 fires.
    - Negative: 5 snapshots, oldest is 10 days ago. I6 returns [].
    - Both conditions: 60 snapshots AND oldest > 30 days. Both findings emitted (or single finding with both in evidence).
    - Realistic: 52 snapshots with varying committed_at values (mix of recent and old). I6 fires.

    I8 tests:
    - Synthetic-minimum: Plan has scan node with descriptor containing "constraint on [ts]" AND details containing a constraint line like "ts := ... :: [[2025-01-15 10:30:00 UTC, 2025-01-16 00:00:00 UTC)]". The start boundary (10:30 UTC) is not a day boundary (midnight UTC). I8 fires with rule_id="I8".
    - Aligned predicate (negative): Constraint range is "[[2025-01-15 00:00:00.000000 UTC, 2025-01-16 00:00:00.000000 UTC)]" — perfectly aligned. I8 returns [].
    - No constraint (negative): Scan has no "constraint on [" in descriptor. I8 returns [] (no pruning at all — R2 would handle this, not I8).
    - Realistic: Load tests/fixtures/explain/480/iceberg_partition_filter.json — parse the fixture and check if I8 fires or not (depend on actual constraint range in fixture).
    - Skipped: Pass plan with None catalog_source context — engine emits RuleSkipped (test the skip reason).

    Wiring test: import `mcp_trino_optimizer.rules` and confirm `registry.all_rules()` returns exactly 13 rules with IDs ["R1","R2","R3","R4","R5","R6","R7","R8","R9","I1","I3","I6","I8","D11"]. Wait — that's 14. Check: R1–R9 = 9, I1/I3/I6/I8 = 4, D11 = 1 → total = 14. But the phase goal says "13 rules". Recount from CONTEXT.md: R1–R9 (9) + I1/I3/I6/I8 (4) + D11 (1) = 14. The phase description says "13 rules" but CONTEXT.md lists 14 distinct IDs. The REQUIREMENTS confirm 14 rules (RUL-07 through RUL-20 = 14 items). Treat this as 13 naming convention from the spec (D11 was added as a bonus rule). Test should confirm all 14 rules are registered.
  </behavior>
  <action>
    **i6_stale_snapshots.py:**
    - rule_id = "I6"
    - evidence_requirement = EvidenceRequirement.ICEBERG_METADATA
    - check() reads evidence.iceberg_snapshots
    - If snapshots is None or empty → return []
    - Parse committed_at timestamps: try `datetime.fromisoformat(s["committed_at"].replace(" UTC", "+00:00"))` for each row; skip rows where parsing fails
    - snapshot_count = len(snapshots)
    - oldest_age_days = (datetime.now(UTC) - min(committed_at values)).days
    - Check 1: snapshot_count > thresholds.max_snapshot_count → fire severity="medium"
    - Check 2: oldest_age_days > thresholds.snapshot_retention_days → fire severity="low"
    - Emit separate RuleFinding for each triggered check
    - confidence: 0.9
    - evidence dict: {"snapshot_count": n, "threshold_count": max_count, "oldest_snapshot_age_days": days, "threshold_days": retention_days}
    - operator_ids: [] (table-level finding)
    - Use `from datetime import datetime, timezone, UTC` — Python 3.11+ has `datetime.UTC` constant
    - Register at module bottom

    **i8_partition_transform.py:**
    - rule_id = "I8"
    - evidence_requirement = EvidenceRequirement.ICEBERG_METADATA
    - check() finds scan nodes with "constraint on [" in descriptor["table"]
    - For each such node, look for constraint detail lines in node.details:
      * Detail lines containing "::" and timestamp range brackets like "[[...UTC, ...UTC)]"
      * Parse the lower bound timestamp from the range
    - Helper `_parse_lower_bound(detail_line: str) -> datetime | None`:
      * Regex: `r'\[\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:\.\d+)? UTC)'` to extract the lower bound
      * Parse as `datetime.fromisoformat(ts.replace(" UTC", "+00:00"))`
    - Helper `_is_day_aligned(dt: datetime) -> bool`: return `dt.hour == 0 and dt.minute == 0 and dt.second == 0`
    - Helper `_is_hour_aligned(dt: datetime) -> bool`: return `dt.minute == 0 and dt.second == 0`
    - If lower bound is not day-aligned for a column with "day" in partition spec hints → fire I8
    - NOTE: Without the actual partition spec from Iceberg metadata, we can only detect obvious misalignment. For v1, detect: any sub-day timestamp boundary in a constraint on a timestamp column is potentially misaligned. Lower confidence.
    - severity: "medium"
    - confidence: 0.6 (without knowing actual partition transform, this is best-effort)
    - evidence dict: {"constraint_column": col, "constraint_lower_bound": ts_str, "is_day_aligned": bool, "is_hour_aligned": bool}
    - operator_ids: [node.id]
    - Message: "Partition constraint lower bound {ts} is not aligned to day boundary; may not fully prune Iceberg partitions with day(ts) transform."
    - Version note: add to evidence when source_trino_version < "440" (approximate): "partial_pruning_unavailable_pre_trino_440"
    - Register at module bottom

    **rules/__init__.py update:**
    Add import statements for all 13 rule modules so that `import mcp_trino_optimizer.rules` triggers all registrations:
    ```python
    # Import all rule modules to trigger registry.register() calls at module load time.
    # Order matches rule ID sequence for readability; registration order does not affect behavior.
    import mcp_trino_optimizer.rules.r1_missing_stats  # noqa: F401
    import mcp_trino_optimizer.rules.r2_partition_pruning  # noqa: F401
    import mcp_trino_optimizer.rules.r3_predicate_pushdown  # noqa: F401
    import mcp_trino_optimizer.rules.r4_dynamic_filtering  # noqa: F401
    import mcp_trino_optimizer.rules.r5_broadcast_too_big  # noqa: F401
    import mcp_trino_optimizer.rules.r6_join_order  # noqa: F401
    import mcp_trino_optimizer.rules.r7_cpu_skew  # noqa: F401
    import mcp_trino_optimizer.rules.r8_exchange_volume  # noqa: F401
    import mcp_trino_optimizer.rules.r9_low_selectivity  # noqa: F401
    import mcp_trino_optimizer.rules.i1_small_files  # noqa: F401
    import mcp_trino_optimizer.rules.i3_delete_files  # noqa: F401
    import mcp_trino_optimizer.rules.i6_stale_snapshots  # noqa: F401
    import mcp_trino_optimizer.rules.i8_partition_transform  # noqa: F401
    import mcp_trino_optimizer.rules.d11_cost_vs_actual  # noqa: F401
    ```
    Place these imports AFTER all the `from .findings import ...` etc. re-exports. Keep existing public API re-exports intact.

    Un-skip and implement I6 and I8 test files. Use `datetime.now(UTC) - timedelta(days=40)` for age tests. Use inline fixture construction for I8 with synthetic PlanNode.
  </action>
  <verify>
    <automated>uv run pytest tests/rules/test_i6_stale_snapshots.py tests/rules/test_i8_partition_transform.py -x -q</automated>
  </verify>
  <done>All I6 and I8 tests pass. `uv run pytest tests/rules/ -q` shows ALL rule test files passing (zero skipped stubs remaining). `from mcp_trino_optimizer.rules import registry; print(len(registry.all_rules()))` outputs 14. Zero mypy errors.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| iceberg_files rows → I3 client-side filter | $files rows from CatalogSource; rule processes content field values from external Trino response |
| iceberg_snapshots committed_at strings → datetime parsing | Timestamp strings from Trino metadata table; parsing must not crash on unexpected format |
| plan.details[*] → I8 regex parsing | Detail strings from Trino EXPLAIN plan; regex must not backtrack catastrophically |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-04-14 | Denial of Service | I6 datetime.fromisoformat() on large snapshots list | accept | max_metadata_rows=10_000 caps the list size; parsing 10k timestamps is <1ms |
| T-04-15 | Denial of Service | I8 regex on details list | mitigate | Use re.search() with a bounded pattern; wrap in try/except to catch any backtracking edge case; cap detail string length at 1000 chars before regex |
| T-04-16 | Information Disclosure | I3 evidence dict with file path counts | accept | File counts and record counts are aggregate statistics, not PII; file paths are NOT included in evidence (only counts/ratios) |
| T-04-17 | Tampering | I1/I3 content field type checking | mitigate | Guard `f.get("content") in (1, 2)` — Python's `in` operator handles None and wrong types safely; no crash on malformed $files rows |
| T-04-18 | Spoofing | I6 snapshot_count threshold check | accept | Count from catalog metadata is trusted server response; no user can inject arbitrary snapshot counts |
| T-04-19 | Elevation of Privilege | rules/__init__.py auto-import all rules | mitigate | Side-effect imports are explicit (listed individually with noqa comments); no dynamic import via __import__() or importlib that could be hijacked |
</threat_model>

<verification>
```bash
# Run I1–I8 tests
uv run pytest tests/rules/test_i1_small_files.py tests/rules/test_i3_delete_files.py tests/rules/test_i6_stale_snapshots.py tests/rules/test_i8_partition_transform.py -v

# Full rules suite — all 14 rule test files green (14 rules: R1-R9, I1/I3/I6/I8, D11)
uv run pytest tests/rules/ -q

# Complete test suite
uv run pytest tests/ -q

# Confirm all 14 rules registered after single import
python -c "
import mcp_trino_optimizer.rules
from mcp_trino_optimizer.rules import registry
ids = sorted(r.rule_id for r in registry.all_rules())
print(ids)
assert len(ids) == 14, f'Expected 14 rules, got {len(ids)}'
"

# Type check entire rules package
uv run mypy src/mcp_trino_optimizer/rules/ --strict

# Lint
uv run ruff check src/mcp_trino_optimizer/rules/
```
</verification>

<success_criteria>
1. All 4 Iceberg rule test files pass (synthetic-minimum, realistic, negative-control each)
2. `uv run pytest tests/rules/ -q` — all rule test files green, zero skipped stubs, zero collection errors
3. `uv run pytest tests/ -q` — full suite green (no regressions from prior phases)
4. `import mcp_trino_optimizer.rules; registry.all_rules()` returns 14 Rule subclasses
5. `uv run mypy src/mcp_trino_optimizer/rules/ --strict` — zero type errors
6. `uv run ruff check src/mcp_trino_optimizer/rules/` — zero lint errors
7. Each RuleThresholds field used by I1/I3/I6 has a citation comment in thresholds.py (verified by grep)
</success_criteria>

<output>
After completion, create `.planning/phases/04-rule-engine-13-deterministic-rules/04-04-SUMMARY.md` with:
- I1, I3, I6, I8 implemented and registered
- Total registered rules: 14 (R1–R9, I1/I3/I6/I8, D11)
- Phase 4 completion checklist against success criteria from ROADMAP.md
- Any deviations from this plan
- Ready-to-run command for Phase 5 planning
</output>
