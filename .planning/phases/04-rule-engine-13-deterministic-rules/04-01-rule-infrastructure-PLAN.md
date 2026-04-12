---
phase: 04-rule-engine-13-deterministic-rules
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - src/mcp_trino_optimizer/parser/models.py
  - src/mcp_trino_optimizer/rules/__init__.py
  - src/mcp_trino_optimizer/rules/findings.py
  - src/mcp_trino_optimizer/rules/evidence.py
  - src/mcp_trino_optimizer/rules/base.py
  - src/mcp_trino_optimizer/rules/registry.py
  - src/mcp_trino_optimizer/rules/thresholds.py
  - src/mcp_trino_optimizer/rules/engine.py
  - tests/rules/__init__.py
  - tests/rules/test_registry.py
  - tests/rules/test_engine.py
  - tests/rules/test_engine_isolation.py
  - tests/rules/test_findings.py
  - tests/rules/test_thresholds.py
  - tests/unit/test_parser_walk.py
autonomous: true
requirements:
  - RUL-01
  - RUL-02
  - RUL-03
  - RUL-04
  - RUL-05
  - RUL-21

must_haves:
  truths:
    - "BasePlan.walk() uses stack.pop() (right-end), not pop(0), and extends with reversed children"
    - "RuleFinding, RuleError, RuleSkipped are discriminated-union pydantic models with kind literals"
    - "Severity is Literal['critical', 'high', 'medium', 'low'] — no 'info' tier"
    - "EvidenceRequirement has four values: PLAN_ONLY, PLAN_WITH_METRICS, TABLE_STATS, ICEBERG_METADATA"
    - "RuleThresholds(BaseSettings) has env_prefix='TRINO_RULE_' and all citation comments"
    - "RuleEngine.run() prefetches evidence once, skips unavailable-evidence rules, isolates crashing rules"
    - "All test stubs for rules and engine exist in tests/rules/ before rule implementation begins"
  artifacts:
    - path: "src/mcp_trino_optimizer/parser/models.py"
      provides: "Fixed BasePlan.walk() — stack.pop() not pop(0)"
    - path: "src/mcp_trino_optimizer/rules/__init__.py"
      provides: "Public API re-exports for rules package"
    - path: "src/mcp_trino_optimizer/rules/findings.py"
      provides: "RuleFinding, RuleError, RuleSkipped, EngineResult, Severity"
    - path: "src/mcp_trino_optimizer/rules/evidence.py"
      provides: "EvidenceRequirement enum, EvidenceBundle dataclass, safe_float helper"
    - path: "src/mcp_trino_optimizer/rules/base.py"
      provides: "Rule ABC with rule_id, evidence_requirement, check()"
    - path: "src/mcp_trino_optimizer/rules/registry.py"
      provides: "RuleRegistry with register() and all_rules()"
    - path: "src/mcp_trino_optimizer/rules/thresholds.py"
      provides: "RuleThresholds(BaseSettings) with TRINO_RULE_ prefix and citations"
    - path: "src/mcp_trino_optimizer/rules/engine.py"
      provides: "RuleEngine with async run(), prefetch, skip, isolation"
    - path: "tests/rules/test_registry.py"
      provides: "Registry unit tests"
    - path: "tests/rules/test_engine.py"
      provides: "Engine prefetch-once + skip + run-loop tests"
    - path: "tests/rules/test_engine_isolation.py"
      provides: "Crashing rule isolation tests"
    - path: "tests/rules/test_findings.py"
      provides: "Discriminated-union round-trip tests"
    - path: "tests/rules/test_thresholds.py"
      provides: "Parameterized threshold data-driven tests"
    - path: "tests/unit/test_parser_walk.py"
      provides: "walk() WR-01 regression test"
  key_links:
    - from: "src/mcp_trino_optimizer/rules/engine.py"
      to: "src/mcp_trino_optimizer/rules/registry.py"
      via: "RuleEngine holds a RuleRegistry, calls all_rules() in run()"
    - from: "src/mcp_trino_optimizer/rules/engine.py"
      to: "src/mcp_trino_optimizer/ports/stats_source.py"
      via: "StatsSource | None constructor arg; prefetch calls fetch_table_stats()"
    - from: "src/mcp_trino_optimizer/rules/engine.py"
      to: "src/mcp_trino_optimizer/ports/catalog_source.py"
      via: "CatalogSource | None constructor arg; prefetch calls fetch_iceberg_metadata()"
---

<objective>
Build the complete rule engine infrastructure: fix the walk() O(n²) bug, implement the type system (findings, evidence, thresholds, registry, base class), and wire the RuleEngine execution loop. Create all test stubs for Wave 2–4 rule tests.

Purpose: Every subsequent plan (02–04) depends on this infrastructure. The walk() fix must land before any rule uses it. The type contracts (RuleFinding, EvidenceBundle, Rule ABC) are the integration surface for all 13 rules.

Output: `src/mcp_trino_optimizer/rules/` subpackage (8 files) + test infrastructure (6 files in tests/rules/ + 1 in tests/unit/).
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md
@.planning/phases/04-rule-engine-13-deterministic-rules/04-CONTEXT.md
@.planning/phases/04-rule-engine-13-deterministic-rules/04-RESEARCH.md
@.planning/phases/04-rule-engine-13-deterministic-rules/04-VALIDATION.md

@src/mcp_trino_optimizer/parser/models.py
@src/mcp_trino_optimizer/ports/stats_source.py
@src/mcp_trino_optimizer/ports/catalog_source.py
@src/mcp_trino_optimizer/settings.py

<interfaces>
<!-- Key types the executor needs. Extracted from codebase. -->

From src/mcp_trino_optimizer/parser/models.py:
```python
class PlanNode(BaseModel):
    id: str
    name: str
    descriptor: dict[str, str]
    details: list[str]
    estimates: list[CostEstimate]
    children: list["PlanNode"]
    cpu_time_ms: float | None
    wall_time_ms: float | None
    input_rows: int | None
    input_bytes: int | None
    output_rows: int | None
    output_bytes: int | None
    peak_memory_bytes: int | None
    iceberg_split_count: int | None
    iceberg_file_count: int | None
    iceberg_partition_spec_id: int | None
    @property def operator_type(self) -> str: ...
    @property def raw(self) -> dict[str, Any]: ...

class BasePlan(BaseModel):
    root: PlanNode
    schema_drift_warnings: list[SchemaDriftWarning]
    source_trino_version: str | None
    def walk(self) -> Iterator[PlanNode]: ...  # WR-01: currently uses pop(0) — MUST fix
    def find_nodes_by_type(self, operator_type: str) -> list[PlanNode]: ...

class EstimatedPlan(BasePlan):
    plan_type: Literal["estimated"] = "estimated"

class ExecutedPlan(BasePlan):
    plan_type: Literal["executed"] = "executed"

class CostEstimate(BaseModel):
    output_row_count: float | None = Field(default=None, alias="outputRowCount")
    output_size_in_bytes: float | None = Field(default=None, alias="outputSizeInBytes")
    cpu_cost: float | None = Field(default=None, alias="cpuCost")
```

From src/mcp_trino_optimizer/ports/stats_source.py:
```python
class StatsSource(Protocol):
    async def fetch_table_stats(self, catalog: str, schema: str, table: str) -> dict[str, Any]: ...
    async def fetch_system_runtime(self, query: str) -> list[dict[str, Any]]: ...
```

From src/mcp_trino_optimizer/ports/catalog_source.py:
```python
class CatalogSource(Protocol):
    async def fetch_iceberg_metadata(self, catalog: str, schema: str, table: str, suffix: str) -> list[dict[str, Any]]: ...
    async def fetch_catalogs(self) -> list[str]: ...
    async def fetch_schemas(self, catalog: str) -> list[str]: ...
```

From src/mcp_trino_optimizer/settings.py (pattern to follow for RuleThresholds):
```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MCPTO_", env_file=".env", extra="forbid")
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Fix walk() WR-01 + create rule subpackage skeleton + all test stubs</name>
  <files>
    src/mcp_trino_optimizer/parser/models.py
    tests/unit/test_parser_walk.py
    tests/rules/__init__.py
    tests/rules/test_registry.py
    tests/rules/test_engine.py
    tests/rules/test_engine_isolation.py
    tests/rules/test_findings.py
    tests/rules/test_thresholds.py
    tests/rules/test_r1_missing_stats.py
    tests/rules/test_r2_partition_pruning.py
    tests/rules/test_r3_predicate_pushdown.py
    tests/rules/test_r4_dynamic_filtering.py
    tests/rules/test_r5_broadcast_join.py
    tests/rules/test_r6_join_order.py
    tests/rules/test_r7_skew.py
    tests/rules/test_r8_exchange.py
    tests/rules/test_r9_low_selectivity.py
    tests/rules/test_i1_small_files.py
    tests/rules/test_i3_delete_files.py
    tests/rules/test_i6_stale_snapshots.py
    tests/rules/test_i8_partition_transform.py
    tests/rules/test_d11_cost_vs_actual.py
  </files>
  <behavior>
    - test_parser_walk.py: Given a 4-node tree (root → [A, B], A → [C]), walk() yields root, A, C, B (DFS pre-order). Assert order is [root_id, A_id, C_id, B_id].
    - test_parser_walk.py: walk() on a tree with 1000 nodes completes without O(n²) slowness — assert len(list(plan.walk())) == 1000.
    - All tests/rules/test_r*.py, test_i*.py, test_d*.py: stub files with a single `pytest.mark.skip("Wave N stub — implement when rule lands")` test so pytest collection doesn't fail.
  </behavior>
  <action>
    1. Fix BasePlan.walk() in src/mcp_trino_optimizer/parser/models.py:
       - Change `node = stack.pop(0)` to `node = stack.pop()` (remove the 0 index)
       - The extend line `stack.extend(reversed(node.children))` is ALREADY correct — leave it unchanged
       - Add a comment: `# WR-01 fix: pop() from right end is O(1); pop(0) was O(n)`
       - Do NOT use `from __future__ import annotations` in this file (existing critical comment)

    2. Write tests/unit/test_parser_walk.py:
       - Build a minimal PlanNode tree inline (no fixtures needed)
       - Test DFS order is correct: root → left-child → left-grandchild → right-child
       - Test walk() on a flat 100-node chain completes and returns 100 nodes

    3. Create tests/rules/__init__.py (empty file)

    4. Create 18 stub rule test files (test_r1 through test_d11). Each stub file:
       ```python
       import pytest

       @pytest.mark.skip("Wave N stub — implement when rule lands")
       def test_stub() -> None:
           pass
       ```
       Use Wave 2 for R1–R4, Wave 3 for R5–R9+D11, Wave 4 for I1/I3/I6/I8.

    5. Create tests/rules/test_registry.py, test_engine.py, test_engine_isolation.py, test_findings.py, test_thresholds.py as skip stubs — these will be un-skipped in Task 2.
  </action>
  <verify>
    <automated>uv run pytest tests/unit/test_parser_walk.py -x -q</automated>
  </verify>
  <done>walk() DFS order test passes; 18 rule test stubs + 5 infra test stubs created; all are skip-decorated; `uv run pytest tests/rules/ -q` collects 23 tests, all skipped, 0 errors.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Implement rule infrastructure — findings, evidence, base, registry, thresholds, engine</name>
  <files>
    src/mcp_trino_optimizer/rules/__init__.py
    src/mcp_trino_optimizer/rules/findings.py
    src/mcp_trino_optimizer/rules/evidence.py
    src/mcp_trino_optimizer/rules/base.py
    src/mcp_trino_optimizer/rules/registry.py
    src/mcp_trino_optimizer/rules/thresholds.py
    src/mcp_trino_optimizer/rules/engine.py
    tests/rules/test_registry.py
    tests/rules/test_engine.py
    tests/rules/test_engine_isolation.py
    tests/rules/test_findings.py
    tests/rules/test_thresholds.py
  </files>
  <behavior>
    - test_findings.py: RuleFinding round-trips through JSON; `kind` field is "finding". RuleError has kind="error". RuleSkipped has kind="skipped". Annotated union via `Annotated[RuleFinding | RuleError | RuleSkipped, Field(discriminator="kind")]` deserializes correctly.
    - test_registry.py: Registering a Rule subclass via `registry.register(MyRule)` makes it appear in `registry.all_rules()`. Registering the same class twice does not duplicate. `register()` returns the class (usable as decorator).
    - test_engine.py: `RuleEngine.run(plan)` with `stats_source=None, catalog_source=None` emits `RuleSkipped` for any rule requiring TABLE_STATS or ICEBERG_METADATA. A rule requiring PLAN_ONLY runs and returns its findings.
    - test_engine.py: With a mock StatsSource, prefetch is called exactly once even when two rules both require TABLE_STATS.
    - test_engine_isolation.py: When a rule's `check()` raises `ValueError`, the engine emits `RuleError(rule_id=..., error_type="ValueError")` and continues running remaining rules.
    - test_engine_isolation.py: `RuleError.message` equals `str(the_exception)`.
    - test_thresholds.py: `RuleThresholds()` loads defaults without env vars. `TRINO_RULE_SKEW_RATIO=10.0` env var overrides `skew_ratio` to 10.0. Parameterized test: for each threshold, assert its default value matches documented citation (spot-check 3 thresholds).
  </behavior>
  <action>
    **rules/findings.py:**
    ```python
    from typing import Annotated, Any, Literal
    from pydantic import BaseModel, Field

    Severity = Literal["critical", "high", "medium", "low"]

    class RuleFinding(BaseModel):
        kind: Literal["finding"] = "finding"
        rule_id: str
        severity: Severity
        confidence: float  # 0.0–1.0; validated ge=0.0, le=1.0
        message: str
        evidence: dict[str, Any]
        operator_ids: list[str]

    class RuleError(BaseModel):
        kind: Literal["error"] = "error"
        rule_id: str
        error_type: str
        message: str

    class RuleSkipped(BaseModel):
        kind: Literal["skipped"] = "skipped"
        rule_id: str
        reason: str

    EngineResult = Annotated[
        RuleFinding | RuleError | RuleSkipped,
        Field(discriminator="kind"),
    ]
    ```
    Add a `confidence` field validator: `ge=0.0, le=1.0` using Pydantic `Field(ge=0.0, le=1.0)`.

    **rules/evidence.py:**
    ```python
    import math
    from dataclasses import dataclass, field
    from enum import Enum
    from typing import Any
    from mcp_trino_optimizer.parser.models import BasePlan

    class EvidenceRequirement(Enum):
        PLAN_ONLY = "plan_only"
        PLAN_WITH_METRICS = "plan_with_metrics"
        TABLE_STATS = "table_stats"
        ICEBERG_METADATA = "iceberg_metadata"

    @dataclass
    class EvidenceBundle:
        plan: BasePlan
        table_stats: dict[str, Any] | None = None
        iceberg_snapshots: list[dict[str, Any]] | None = None
        iceberg_files: list[dict[str, Any]] | None = None

    def safe_float(val: Any) -> float | None:
        """Return None if val is None or NaN; otherwise return float(val).
        Use this before numeric comparisons to avoid NaN-silently-False pitfall."""
        if val is None:
            return None
        f = float(val)
        return None if math.isnan(f) else f
    ```

    **rules/base.py:**
    ```python
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

    **rules/registry.py:**
    ```python
    from mcp_trino_optimizer.rules.base import Rule

    class RuleRegistry:
        def __init__(self) -> None:
            self._rules: dict[str, type[Rule]] = {}

        def register(self, rule_cls: type[Rule]) -> type[Rule]:
            """Register a Rule class. Returns class unchanged (usable as @decorator)."""
            self._rules[rule_cls.rule_id] = rule_cls
            return rule_cls

        def all_rules(self) -> list[type[Rule]]:
            return list(self._rules.values())

    registry = RuleRegistry()
    ```

    **rules/thresholds.py** — implement EXACTLY per CONTEXT.md D-04 with all citation comments. Include all fields from the RESEARCH.md code example:
    - stats_divergence_factor: float = 5.0
    - broadcast_max_bytes: int = 100 * 1024 * 1024
    - skew_ratio: float = 5.0
    - scan_selectivity_threshold: float = 0.10
    - small_file_bytes: int = 16 * 1024 * 1024
    - small_file_split_count_threshold: int = 10_000
    - delete_file_count_threshold: int = 100
    - delete_ratio_threshold: float = 0.10
    - max_snapshot_count: int = 50
    - snapshot_retention_days: int = 30
    - max_metadata_rows: int = 10_000  # cap $files response rows (Pitfall 7)
    Use `model_config = SettingsConfigDict(env_prefix='TRINO_RULE_')`.
    Do NOT use `extra="forbid"` (unlike main Settings) — pydantic-settings BaseSettings allows extra by default.

    **rules/engine.py:**
    ```python
    import re
    from mcp_trino_optimizer.rules.registry import RuleRegistry, registry as _default_registry
    from mcp_trino_optimizer.rules.findings import RuleError, RuleSkipped, EngineResult
    from mcp_trino_optimizer.rules.evidence import EvidenceRequirement, EvidenceBundle
    from mcp_trino_optimizer.rules.thresholds import RuleThresholds
    from mcp_trino_optimizer.parser.models import BasePlan, ExecutedPlan
    from mcp_trino_optimizer.ports.stats_source import StatsSource
    from mcp_trino_optimizer.ports.catalog_source import CatalogSource

    class RuleEngine:
        def __init__(
            self,
            stats_source: StatsSource | None,
            catalog_source: CatalogSource | None,
            thresholds: RuleThresholds | None = None,
            registry: RuleRegistry | None = None,
        ) -> None:
            self._stats_source = stats_source
            self._catalog_source = catalog_source
            self._thresholds = thresholds or RuleThresholds()
            self._registry = registry or _default_registry

        async def run(self, plan: BasePlan, table: str | None = None) -> list[EngineResult]:
            evidence = await self._prefetch_evidence(plan, table)
            results: list[EngineResult] = []
            for rule_cls in self._registry.all_rules():
                rule = rule_cls()
                req = rule.evidence_requirement
                # Skip if evidence source unavailable
                if req == EvidenceRequirement.TABLE_STATS and self._stats_source is None:
                    results.append(RuleSkipped(rule_id=rule.rule_id, reason="offline_mode_no_stats_source"))
                    continue
                if req == EvidenceRequirement.ICEBERG_METADATA and self._catalog_source is None:
                    results.append(RuleSkipped(rule_id=rule.rule_id, reason="offline_mode_no_catalog_source"))
                    continue
                # Skip if rule needs execution metrics but plan is estimated
                if req == EvidenceRequirement.PLAN_WITH_METRICS and not isinstance(plan, ExecutedPlan):
                    results.append(RuleSkipped(rule_id=rule.rule_id, reason="requires_executed_plan_estimated_provided"))
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

        async def _prefetch_evidence(self, plan: BasePlan, table: str | None) -> EvidenceBundle:
            bundle = EvidenceBundle(plan=plan)
            requirements = {rule_cls.evidence_requirement for rule_cls in self._registry.all_rules()}
            # Parse table reference from plan if not explicitly provided
            resolved_table = table or self._extract_table_from_plan(plan)
            if resolved_table and (
                EvidenceRequirement.TABLE_STATS in requirements and self._stats_source is not None
            ):
                catalog, schema, tbl = self._parse_table_ref(resolved_table)
                if catalog and schema and tbl:
                    bundle.table_stats = await self._stats_source.fetch_table_stats(catalog, schema, tbl)
            if resolved_table and (
                EvidenceRequirement.ICEBERG_METADATA in requirements and self._catalog_source is not None
            ):
                catalog, schema, tbl = self._parse_table_ref(resolved_table)
                if catalog and schema and tbl:
                    raw_files = await self._catalog_source.fetch_iceberg_metadata(catalog, schema, tbl, "files")
                    bundle.iceberg_files = raw_files[:self._thresholds.max_metadata_rows]
                    bundle.iceberg_snapshots = await self._catalog_source.fetch_iceberg_metadata(catalog, schema, tbl, "snapshots")
            return bundle

        def _extract_table_from_plan(self, plan: BasePlan) -> str | None:
            """Extract first scan node's table reference from plan descriptor."""
            for node in plan.walk():
                if node.operator_type in ("TableScan", "ScanFilter", "ScanFilterProject"):
                    table_str = node.descriptor.get("table", "")
                    if table_str:
                        return table_str
            return None

        def _parse_table_ref(self, table_str: str) -> tuple[str | None, str | None, str | None]:
            """Parse 'catalog:schema.table$data@snapshotId [constraint on [col]]' into components.
            Returns (catalog, schema, table) or (None, None, None) on parse failure."""
            # Strip constraint suffix if present
            table_str = re.sub(r"\s+constraint on \[.*", "", table_str).strip()
            # Strip $data@snapshotId suffix
            table_str = re.sub(r"\$[^@\s]+@\S+", "", table_str).strip()
            # Parse catalog:schema.table
            match = re.match(r"^([^:]+):([^.]+)\.(.+)$", table_str)
            if match:
                return match.group(1), match.group(2), match.group(3)
            return None, None, None
    ```

    **rules/__init__.py** — re-export public API:
    ```python
    from mcp_trino_optimizer.rules.findings import RuleFinding, RuleError, RuleSkipped, EngineResult, Severity
    from mcp_trino_optimizer.rules.evidence import EvidenceRequirement, EvidenceBundle, safe_float
    from mcp_trino_optimizer.rules.base import Rule
    from mcp_trino_optimizer.rules.registry import registry
    from mcp_trino_optimizer.rules.engine import RuleEngine
    from mcp_trino_optimizer.rules.thresholds import RuleThresholds

    __all__ = [
        "RuleFinding", "RuleError", "RuleSkipped", "EngineResult", "Severity",
        "EvidenceRequirement", "EvidenceBundle", "safe_float",
        "Rule", "registry", "RuleEngine", "RuleThresholds",
    ]
    ```

    Now un-skip and implement the 5 infrastructure test files:
    - test_findings.py: discriminated union serialize/deserialize round-trip via `json.loads` + pydantic validation; confidence 0.0 and 1.0 valid; 1.01 raises.
    - test_registry.py: register a minimal Rule subclass; all_rules() returns it; re-register same class → still one entry; can use as decorator.
    - test_engine.py: mock StatsSource (AsyncMock returning {}), test prefetch-once, test skip for None sources.
    - test_engine_isolation.py: Rule.check() that raises RuntimeError → engine emits RuleError, other rules complete.
    - test_thresholds.py: default values match documented defaults; env override via monkeypatch.setenv.
  </action>
  <verify>
    <automated>uv run pytest tests/rules/test_registry.py tests/rules/test_engine.py tests/rules/test_engine_isolation.py tests/rules/test_findings.py tests/rules/test_thresholds.py tests/unit/test_parser_walk.py -x -q</automated>
  </verify>
  <done>All 6 test files pass. `uv run mypy src/mcp_trino_optimizer/rules/ --strict` passes. `uv run ruff check src/mcp_trino_optimizer/rules/` passes. The 18 rule stubs remain skipped. No existing tests are broken.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| engine → rule.check() | Rule bodies receive EvidenceBundle data; must not treat evidence values as format strings |
| env vars → RuleThresholds | TRINO_RULE_* env vars control thresholds; must validate ranges |
| plan descriptor → table_ref parser | Table descriptor strings from Trino plan are semi-trusted; parser must not crash on unexpected formats |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-04-01 | Tampering | RuleThresholds env overrides | mitigate | Pydantic field validators enforce `ge=0` on int thresholds, `ge=0.0, le=1.0` on ratio thresholds; invalid value raises ValidationError at startup |
| T-04-02 | Information Disclosure | RuleError.message | accept | Error messages come from exception str(); no user-controlled input reaches rule bodies — EvidenceBundle contains typed data only |
| T-04-03 | Denial of Service | _parse_table_ref regex | mitigate | Regex patterns use `re.match()` with anchored patterns; no unbounded backtracking; add `re.DOTALL` guard and 1000-char table string cap before parsing |
| T-04-04 | Elevation of Privilege | rules package imports | mitigate | Rule bodies must not import from mcp_trino_optimizer.adapters; enforced by mypy + ruff via a pre-commit check that greps for adapter imports in rules/ |
| T-04-05 | Repudiation | engine.run() audit trail | accept | Low risk in Phase 4 (no MCP wiring yet); Phase 8 will add structured logging of rule findings with request_id |
</threat_model>

<verification>
```bash
# Full infrastructure check
uv run pytest tests/rules/ tests/unit/test_parser_walk.py -x -q

# Type check
uv run mypy src/mcp_trino_optimizer/rules/ --strict

# Lint
uv run ruff check src/mcp_trino_optimizer/rules/ src/mcp_trino_optimizer/parser/models.py

# Confirm walk() fix doesn't break existing parser tests
uv run pytest tests/ -k "parser" -x -q

# Confirm 18 rule stubs are present and skipped (not erroring)
uv run pytest tests/rules/ -v --collect-only 2>&1 | grep -c "SKIP\|skip"
```
</verification>

<success_criteria>
1. `uv run pytest tests/rules/ tests/unit/test_parser_walk.py -x -q` — all infrastructure tests pass, all rule stubs skipped, zero errors
2. `uv run mypy src/mcp_trino_optimizer/rules/ --strict` — zero type errors
3. `BasePlan.walk()` uses `stack.pop()` (not `pop(0)`) — verified by grep and by passing DFS-order test
4. All 8 `rules/*.py` files exist with correct exports
5. All 13 rule test stub files plus 5 infra test files exist in `tests/rules/`
6. `RuleThresholds().skew_ratio == 5.0` and `TRINO_RULE_SKEW_RATIO=10.0` env var overrides it to 10.0
</success_criteria>

<output>
After completion, create `.planning/phases/04-rule-engine-13-deterministic-rules/04-01-SUMMARY.md` with:
- Files created/modified
- Walk() WR-01 fix confirmed
- Infrastructure contract (RuleFinding fields, EvidenceBundle fields, RuleEngine constructor signature)
- Any deviations from this plan
</output>
