---
phase: 02-trino-adapter-read-only-gate
plan: 02
type: execute
wave: 1
depends_on: []
files_modified:
  - src/mcp_trino_optimizer/ports/__init__.py
  - src/mcp_trino_optimizer/ports/plan_source.py
  - src/mcp_trino_optimizer/ports/stats_source.py
  - src/mcp_trino_optimizer/ports/catalog_source.py
  - src/mcp_trino_optimizer/adapters/offline/__init__.py
  - src/mcp_trino_optimizer/adapters/offline/json_plan_source.py
  - tests/adapters/test_offline_plan_source.py
  - tests/adapters/test_port_conformance.py
autonomous: true
requirements:
  - TRN-12
  - TRN-13

must_haves:
  truths:
    - "PlanSource, StatsSource, CatalogSource are Protocol definitions with no adapter imports"
    - "OfflinePlanSource accepts raw JSON text and returns ExplainPlan"
    - "OfflinePlanSource does NOT call SqlClassifier (D-15)"
    - "Live and offline plan sources share the same PlanSource protocol"
  artifacts:
    - path: "src/mcp_trino_optimizer/ports/plan_source.py"
      provides: "PlanSource Protocol and ExplainPlan domain type"
      exports: ["PlanSource", "ExplainPlan"]
    - path: "src/mcp_trino_optimizer/ports/stats_source.py"
      provides: "StatsSource Protocol"
      exports: ["StatsSource"]
    - path: "src/mcp_trino_optimizer/ports/catalog_source.py"
      provides: "CatalogSource Protocol"
      exports: ["CatalogSource"]
    - path: "src/mcp_trino_optimizer/adapters/offline/json_plan_source.py"
      provides: "OfflinePlanSource implementing PlanSource from raw JSON"
      exports: ["OfflinePlanSource"]
  key_links:
    - from: "src/mcp_trino_optimizer/adapters/offline/json_plan_source.py"
      to: "src/mcp_trino_optimizer/ports/plan_source.py"
      via: "implements PlanSource protocol"
      pattern: "PlanSource"
---

<objective>
Define the hexagonal ports (PlanSource, StatsSource, CatalogSource) and the OfflinePlanSource adapter that accepts pasted EXPLAIN JSON.

Purpose: The ports are the contracts that decouple the rule engine, recommender, and rewrite engine from the adapter layer (K-Decision #5). Defining them now — before the live adapters exist — ensures the interface is driven by consumer needs, not implementation convenience. OfflinePlanSource (TRN-12) proves the ports work without a Trino connection.

Output: `ports/` subpackage with three Protocol definitions, `adapters/offline/json_plan_source.py`, `ExplainPlan` domain dataclass, unit tests for offline mode and port conformance.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md
@.planning/phases/02-trino-adapter-read-only-gate/02-CONTEXT.md
@.planning/phases/02-trino-adapter-read-only-gate/02-RESEARCH.md

<interfaces>
<!-- Key types referenced by this plan -->

From CONTEXT.md D-21:
```python
# ExplainPlan is a minimum-viable domain dataclass that Phase 3 will replace/extend
@dataclass
class ExplainPlan:
    plan_json: dict  # raw parsed JSON from EXPLAIN
    plan_type: Literal["estimated", "executed", "distributed"]
    source_trino_version: str | None  # None for offline mode
```

From CONTEXT.md D-20:
```python
# OfflinePlanSource takes raw JSON text only, bounded 1MB
class OfflinePlanSource:
    def fetch(self, plan_json: str) -> ExplainPlan: ...
```

From CONTEXT.md D-01 (architecture):
```
ports/
├── plan_source.py    # PlanSource Protocol
├── stats_source.py   # StatsSource Protocol
└── catalog_source.py # CatalogSource Protocol
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Hexagonal ports + ExplainPlan domain type</name>
  <files>
    src/mcp_trino_optimizer/ports/__init__.py
    src/mcp_trino_optimizer/ports/plan_source.py
    src/mcp_trino_optimizer/ports/stats_source.py
    src/mcp_trino_optimizer/ports/catalog_source.py
  </files>
  <read_first>
    .planning/phases/02-trino-adapter-read-only-gate/02-CONTEXT.md
    .planning/phases/02-trino-adapter-read-only-gate/02-RESEARCH.md
  </read_first>
  <behavior>
    - Test: PlanSource is a Protocol with a `fetch` method
    - Test: StatsSource is a Protocol with methods for stats retrieval
    - Test: CatalogSource is a Protocol with methods for catalog/metadata queries
    - Test: ExplainPlan dataclass has plan_json, plan_type, source_trino_version fields
    - Test: ports module has no imports from adapters (no coupling)
  </behavior>
  <action>
    **Create `src/mcp_trino_optimizer/ports/__init__.py`** that re-exports PlanSource, StatsSource, CatalogSource, ExplainPlan.

    **Create `plan_source.py`** per D-21 and ARCHITECTURE.md:
    ```python
    from __future__ import annotations
    from dataclasses import dataclass, field
    from typing import Any, Literal, Protocol, runtime_checkable

    @dataclass
    class ExplainPlan:
        """Minimum-viable domain type. Phase 3 replaces with typed hierarchy."""
        plan_json: dict[str, Any]
        plan_type: Literal["estimated", "executed", "distributed"]
        source_trino_version: str | None = None
        raw_text: str = ""  # original JSON text for round-trip fidelity

    @runtime_checkable
    class PlanSource(Protocol):
        async def fetch_plan(self, sql: str) -> ExplainPlan: ...
        async def fetch_analyze_plan(self, sql: str) -> ExplainPlan: ...
        async def fetch_distributed_plan(self, sql: str) -> ExplainPlan: ...
    ```

    **Create `stats_source.py`**:
    ```python
    @runtime_checkable
    class StatsSource(Protocol):
        async def fetch_table_stats(self, catalog: str, schema: str, table: str) -> dict[str, Any]: ...
        async def fetch_system_runtime(self, query: str) -> list[dict[str, Any]]: ...
    ```

    **Create `catalog_source.py`**:
    ```python
    @runtime_checkable
    class CatalogSource(Protocol):
        async def fetch_iceberg_metadata(self, catalog: str, schema: str, table: str, suffix: str) -> list[dict[str, Any]]: ...
        async def fetch_catalogs(self) -> list[str]: ...
        async def fetch_schemas(self, catalog: str) -> list[str]: ...
    ```

    All ports are pure Protocol definitions. They MUST NOT import anything from `adapters/`. The `runtime_checkable` decorator enables `isinstance()` checks in tests and the port conformance test.
  </action>
  <verify>
    <automated>python -c "from mcp_trino_optimizer.ports import PlanSource, StatsSource, CatalogSource, ExplainPlan; print('OK')"</automated>
  </verify>
  <acceptance_criteria>
    - `src/mcp_trino_optimizer/ports/plan_source.py` contains `class PlanSource(Protocol)` and `class ExplainPlan`
    - `src/mcp_trino_optimizer/ports/stats_source.py` contains `class StatsSource(Protocol)`
    - `src/mcp_trino_optimizer/ports/catalog_source.py` contains `class CatalogSource(Protocol)`
    - `grep -r "from.*adapters" src/mcp_trino_optimizer/ports/` returns no results (no coupling)
    - `ExplainPlan` has fields `plan_json`, `plan_type`, `source_trino_version`
  </acceptance_criteria>
  <done>Three port Protocols and ExplainPlan domain type defined with zero adapter coupling.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: OfflinePlanSource + port conformance tests</name>
  <files>
    src/mcp_trino_optimizer/adapters/offline/__init__.py
    src/mcp_trino_optimizer/adapters/offline/json_plan_source.py
    tests/adapters/test_offline_plan_source.py
    tests/adapters/test_port_conformance.py
  </files>
  <read_first>
    src/mcp_trino_optimizer/ports/plan_source.py
    src/mcp_trino_optimizer/ports/stats_source.py
    src/mcp_trino_optimizer/ports/catalog_source.py
    .planning/phases/02-trino-adapter-read-only-gate/02-CONTEXT.md
  </read_first>
  <behavior>
    - Test: OfflinePlanSource.fetch_plan(valid_json_str) returns ExplainPlan with plan_type="estimated"
    - Test: OfflinePlanSource.fetch_plan(invalid_json) raises ValueError
    - Test: OfflinePlanSource.fetch_plan(json > 1MB) raises ValueError with "exceeds maximum"
    - Test: OfflinePlanSource does NOT import or use SqlClassifier
    - Test: OfflinePlanSource satisfies isinstance(source, PlanSource) check
    - Test: ExplainPlan.source_trino_version is None for offline plans
  </behavior>
  <action>
    **Create `src/mcp_trino_optimizer/adapters/offline/__init__.py`** (empty).

    **Create `json_plan_source.py`** per D-15, D-20:
    ```python
    class OfflinePlanSource:
        """PlanSource from raw JSON text — no Trino connection needed."""

        MAX_BYTES = 1_000_000  # 1MB cap per D-20

        async def fetch_plan(self, sql: str) -> ExplainPlan:
            """sql parameter is actually the raw JSON text for offline mode."""
            self._validate_size(sql)
            plan_dict = self._parse_json(sql)
            return ExplainPlan(
                plan_json=plan_dict,
                plan_type=self._detect_plan_type(plan_dict),
                source_trino_version=None,
                raw_text=sql,
            )

        async def fetch_analyze_plan(self, sql: str) -> ExplainPlan:
            self._validate_size(sql)
            plan_dict = self._parse_json(sql)
            return ExplainPlan(plan_json=plan_dict, plan_type="executed", source_trino_version=None, raw_text=sql)

        async def fetch_distributed_plan(self, sql: str) -> ExplainPlan:
            self._validate_size(sql)
            plan_dict = self._parse_json(sql)
            return ExplainPlan(plan_json=plan_dict, plan_type="distributed", source_trino_version=None, raw_text=sql)
    ```

    The `_detect_plan_type` method inspects the JSON for presence of runtime metrics keys (e.g., `"cpuTimeMillis"`) to distinguish estimated vs executed. If unclear, defaults to `"estimated"`.

    The `_validate_size` method checks `len(sql.encode("utf-8")) <= MAX_BYTES` and raises `ValueError("Plan JSON exceeds maximum size of 1000000 bytes")` on violation.

    The `_parse_json` method calls `orjson.loads(sql)` and raises `ValueError("Invalid JSON: ...")` on parse error.

    **This class does NOT import `SqlClassifier`** — per D-15 it is classifier-exempt.

    **Create `tests/adapters/test_offline_plan_source.py`** with async tests for valid JSON, invalid JSON, size limit, plan type detection.

    **Create `tests/adapters/test_port_conformance.py`** that:
    - Asserts `isinstance(OfflinePlanSource(), PlanSource)` is True (runtime_checkable Protocol)
    - Imports ports and verifies they have no imports from `adapters` via `inspect.getfile` + source reading
  </action>
  <verify>
    <automated>uv run pytest tests/adapters/test_offline_plan_source.py tests/adapters/test_port_conformance.py -v -x</automated>
  </verify>
  <acceptance_criteria>
    - `src/mcp_trino_optimizer/adapters/offline/json_plan_source.py` contains `class OfflinePlanSource`
    - `grep -r "SqlClassifier\|classifier" src/mcp_trino_optimizer/adapters/offline/` returns no results
    - `tests/adapters/test_offline_plan_source.py` tests valid JSON, invalid JSON, size limit, and plan type
    - `tests/adapters/test_port_conformance.py` asserts OfflinePlanSource satisfies PlanSource protocol
    - `uv run pytest tests/adapters/test_offline_plan_source.py tests/adapters/test_port_conformance.py -v -x` exits 0
  </acceptance_criteria>
  <done>OfflinePlanSource accepts raw JSON, enforces 1MB limit, returns ExplainPlan, does not use classifier, satisfies PlanSource protocol. Port conformance test validates decoupling.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| User pasted JSON -> OfflinePlanSource | Untrusted JSON text from tool input (bounded by MAX_PLAN_JSON_LEN) |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-02-05 | Denial of Service | OfflinePlanSource | mitigate | 1MB size cap on raw JSON input; enforced before parsing |
| T-02-06 | Tampering | OfflinePlanSource | accept | Offline JSON is untrusted input but only parsed into a dict — no SQL execution, no network calls. Phase 8 tool layer wraps with wrap_untrusted() when echoing back. |
</threat_model>

<verification>
```bash
uv run pytest tests/adapters/test_offline_plan_source.py tests/adapters/test_port_conformance.py -v -x
uv run pytest -m "not integration" -x --tb=short -q
uv run mypy src/mcp_trino_optimizer/ports/ src/mcp_trino_optimizer/adapters/offline/ --strict
```
</verification>

<success_criteria>
- Three port Protocols are defined with proper async method signatures
- ExplainPlan domain type has all required fields
- OfflinePlanSource parses JSON, enforces size limit, returns ExplainPlan
- OfflinePlanSource is classifier-exempt (no classifier import)
- Port conformance test passes
- Ports have zero imports from adapters
</success_criteria>

<output>
After completion, create `.planning/phases/02-trino-adapter-read-only-gate/02-02-SUMMARY.md`
</output>
