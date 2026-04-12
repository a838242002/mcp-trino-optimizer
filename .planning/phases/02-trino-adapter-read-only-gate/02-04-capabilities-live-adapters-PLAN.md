---
phase: 02-trino-adapter-read-only-gate
plan: 04
type: execute
wave: 3
depends_on: ["02-01", "02-02", "02-03"]
files_modified:
  - src/mcp_trino_optimizer/adapters/trino/capabilities.py
  - src/mcp_trino_optimizer/adapters/trino/live_plan_source.py
  - src/mcp_trino_optimizer/adapters/trino/live_stats_source.py
  - src/mcp_trino_optimizer/adapters/trino/live_catalog_source.py
  - tests/adapters/test_capabilities.py
autonomous: true
requirements:
  - TRN-07
  - TRN-08
  - TRN-09
  - TRN-10
  - TRN-14

must_haves:
  truths:
    - "Capability probe detects Trino version and refuses < 429"
    - "CapabilityMatrix records catalogs, Iceberg catalog name, metadata table availability"
    - "LivePlanSource implements PlanSource protocol via TrinoClient"
    - "LiveStatsSource implements StatsSource protocol via TrinoClient"
    - "LiveCatalogSource implements CatalogSource protocol via TrinoClient"
    - "Version probe parses leading numeric portion from version strings like '480' or '480-e'"
  artifacts:
    - path: "src/mcp_trino_optimizer/adapters/trino/capabilities.py"
      provides: "CapabilityMatrix + probe logic"
      exports: ["CapabilityMatrix", "probe_capabilities"]
    - path: "src/mcp_trino_optimizer/adapters/trino/live_plan_source.py"
      provides: "LivePlanSource implementing PlanSource"
      exports: ["LivePlanSource"]
    - path: "src/mcp_trino_optimizer/adapters/trino/live_stats_source.py"
      provides: "LiveStatsSource implementing StatsSource"
      exports: ["LiveStatsSource"]
    - path: "src/mcp_trino_optimizer/adapters/trino/live_catalog_source.py"
      provides: "LiveCatalogSource implementing CatalogSource"
      exports: ["LiveCatalogSource"]
  key_links:
    - from: "src/mcp_trino_optimizer/adapters/trino/capabilities.py"
      to: "src/mcp_trino_optimizer/adapters/trino/client.py"
      via: "Uses TrinoClient to execute probe queries"
      pattern: "TrinoClient"
    - from: "src/mcp_trino_optimizer/adapters/trino/live_plan_source.py"
      to: "src/mcp_trino_optimizer/ports/plan_source.py"
      via: "Implements PlanSource protocol"
      pattern: "PlanSource"
---

<objective>
Build the capability probing system (version detection, Iceberg catalog detection, refuse Trino < 429) and the live port adapter implementations (LivePlanSource, LiveStatsSource, LiveCatalogSource).

Purpose: The capability matrix enables rules (Phase 4+) to gate on Trino version and available features without exceptions. The live adapters implement the same PlanSource/StatsSource/CatalogSource protocols as OfflinePlanSource, completing the hexagonal architecture where all downstream consumers are adapter-agnostic.

Output: `capabilities.py`, `live_plan_source.py`, `live_stats_source.py`, `live_catalog_source.py` under `adapters/trino/`, capability probe unit tests.
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
@.planning/phases/02-trino-adapter-read-only-gate/02-01-SUMMARY.md
@.planning/phases/02-trino-adapter-read-only-gate/02-02-SUMMARY.md

<interfaces>
<!-- From Plan 01 + 02 outputs -->

From src/mcp_trino_optimizer/adapters/trino/client.py (Plan 03 creates this, but Plan 04 runs in same wave — see note):
```python
class TrinoClient:
    async def fetch_plan(self, sql: str, *, timeout: float | None = None) -> ExplainPlan | TimeoutResult[ExplainPlan]: ...
    async def fetch_analyze_plan(self, sql: str, *, timeout: float | None = None) -> ExplainPlan | TimeoutResult[ExplainPlan]: ...
    async def fetch_distributed_plan(self, sql: str, *, timeout: float | None = None) -> ExplainPlan | TimeoutResult[ExplainPlan]: ...
    async def fetch_stats(self, catalog: str, schema: str, table: str, *, timeout: float | None = None) -> ...: ...
    async def fetch_iceberg_metadata(self, catalog: str, schema: str, table: str, suffix: str, *, timeout: float | None = None) -> ...: ...
    async def fetch_system_runtime(self, query_sql: str, *, timeout: float | None = None) -> ...: ...
```

From src/mcp_trino_optimizer/ports/plan_source.py:
```python
class PlanSource(Protocol):
    async def fetch_plan(self, sql: str) -> ExplainPlan: ...
    async def fetch_analyze_plan(self, sql: str) -> ExplainPlan: ...
    async def fetch_distributed_plan(self, sql: str) -> ExplainPlan: ...

class ExplainPlan:
    plan_json: dict[str, Any]
    plan_type: Literal["estimated", "executed", "distributed"]
    source_trino_version: str | None
    raw_text: str
```

From src/mcp_trino_optimizer/adapters/trino/errors.py:
```python
class TrinoVersionUnsupported(TrinoAdapterError): ...
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: CapabilityMatrix + version probe + refuse Trino < 429</name>
  <files>
    src/mcp_trino_optimizer/adapters/trino/capabilities.py
    tests/adapters/test_capabilities.py
  </files>
  <read_first>
    src/mcp_trino_optimizer/adapters/trino/errors.py
    src/mcp_trino_optimizer/ports/plan_source.py
    .planning/phases/02-trino-adapter-read-only-gate/02-CONTEXT.md
    .planning/phases/02-trino-adapter-read-only-gate/02-RESEARCH.md
  </read_first>
  <behavior>
    - Test: parse_trino_version("480") returns 480
    - Test: parse_trino_version("480-e") returns 480
    - Test: parse_trino_version("429") returns 429
    - Test: parse_trino_version("abc") raises ValueError
    - Test: CapabilityMatrix is frozen dataclass with trino_version, trino_version_major, catalogs, iceberg_catalog_name, iceberg_metadata_tables_available, probed_at
    - Test: probe raises TrinoVersionUnsupported for version "428"
    - Test: probe succeeds for version "429" and "480"
  </behavior>
  <action>
    **Create `capabilities.py`** at `src/mcp_trino_optimizer/adapters/trino/capabilities.py` per D-18, D-19:

    ```python
    import re
    from dataclasses import dataclass
    from datetime import UTC, datetime

    MINIMUM_TRINO_VERSION = 429

    _VERSION_RE = re.compile(r"^(\d+)")

    def parse_trino_version(version_str: str) -> int:
        """Extract leading numeric portion from version string like '480' or '480-e'."""
        m = _VERSION_RE.match(version_str.strip())
        if not m:
            raise ValueError(f"Cannot parse Trino version from: {version_str!r}")
        return int(m.group(1))

    @dataclass(frozen=True)
    class CapabilityMatrix:
        trino_version: str              # "480"
        trino_version_major: int         # 480
        catalogs: frozenset[str]         # {"iceberg", "memory", ...}
        iceberg_catalog_name: str | None
        iceberg_metadata_tables_available: bool
        probed_at: datetime
        version: int = 1  # dataclass versioning

    async def probe_capabilities(client: "TrinoClient", settings: "Settings") -> CapabilityMatrix:
        """Probe Trino version and Iceberg catalog per D-18. Lazy init."""
    ```

    The `probe_capabilities` function:
    1. Executes `SELECT node_version FROM system.runtime.nodes LIMIT 1` via client
    2. Parses version with `parse_trino_version()`
    3. If version < 429: raises `TrinoVersionUnsupported` with structured message
    4. Executes `SHOW CATALOGS` to enumerate catalogs
    5. Looks for `settings.trino_catalog` (default "iceberg") in the list
    6. If found, probes `SHOW SCHEMAS IN {catalog}` and attempts a metadata table probe
    7. Returns `CapabilityMatrix` with all fields populated

    All probe queries go through `TrinoClient` methods that call `assert_read_only()` — the probes are all read-only by construction.

    **Create `tests/adapters/test_capabilities.py`** with:
    - Unit tests for `parse_trino_version` with various version strings
    - Unit test for CapabilityMatrix frozen dataclass creation
    - Mock-based test for `probe_capabilities` that mocks TrinoClient responses:
      - Test version < 429 raises TrinoVersionUnsupported
      - Test version 480 succeeds and populates matrix
      - Test missing iceberg catalog sets `iceberg_catalog_name=None`
  </action>
  <verify>
    <automated>uv run pytest tests/adapters/test_capabilities.py -v -x</automated>
  </verify>
  <acceptance_criteria>
    - `src/mcp_trino_optimizer/adapters/trino/capabilities.py` contains `class CapabilityMatrix`, `def parse_trino_version`, `async def probe_capabilities`
    - `MINIMUM_TRINO_VERSION = 429` in capabilities.py
    - `parse_trino_version("480-e")` returns 480
    - `tests/adapters/test_capabilities.py` exits 0 with at least 7 test cases
  </acceptance_criteria>
  <done>CapabilityMatrix is a frozen dataclass. Version probe parses leading numeric portion. probe_capabilities refuses Trino < 429 with structured error. All tests pass.</done>
</task>

<task type="auto">
  <name>Task 2: Live port adapters (LivePlanSource, LiveStatsSource, LiveCatalogSource)</name>
  <files>
    src/mcp_trino_optimizer/adapters/trino/live_plan_source.py
    src/mcp_trino_optimizer/adapters/trino/live_stats_source.py
    src/mcp_trino_optimizer/adapters/trino/live_catalog_source.py
  </files>
  <read_first>
    src/mcp_trino_optimizer/ports/plan_source.py
    src/mcp_trino_optimizer/ports/stats_source.py
    src/mcp_trino_optimizer/ports/catalog_source.py
    src/mcp_trino_optimizer/adapters/trino/client.py
    src/mcp_trino_optimizer/adapters/trino/handle.py
    .planning/phases/02-trino-adapter-read-only-gate/02-CONTEXT.md
  </read_first>
  <action>
    **Create `live_plan_source.py`**:
    ```python
    class LivePlanSource:
        """PlanSource via live TrinoClient. Thin wrapper — delegates to client."""

        def __init__(self, client: TrinoClient) -> None:
            self._client = client

        async def fetch_plan(self, sql: str) -> ExplainPlan:
            result = await self._client.fetch_plan(sql)
            if isinstance(result, TimeoutResult):
                raise TrinoTimeoutError(f"EXPLAIN timed out after {result.elapsed_ms}ms", query_id=result.query_id)
            return result

        async def fetch_analyze_plan(self, sql: str) -> ExplainPlan:
            result = await self._client.fetch_analyze_plan(sql)
            if isinstance(result, TimeoutResult):
                raise TrinoTimeoutError(f"EXPLAIN ANALYZE timed out after {result.elapsed_ms}ms", query_id=result.query_id)
            return result

        async def fetch_distributed_plan(self, sql: str) -> ExplainPlan:
            result = await self._client.fetch_distributed_plan(sql)
            if isinstance(result, TimeoutResult):
                raise TrinoTimeoutError(f"EXPLAIN DISTRIBUTED timed out after {result.elapsed_ms}ms", query_id=result.query_id)
            return result
    ```

    **Create `live_stats_source.py`**:
    ```python
    class LiveStatsSource:
        """StatsSource via live TrinoClient."""

        def __init__(self, client: TrinoClient) -> None:
            self._client = client

        async def fetch_table_stats(self, catalog: str, schema: str, table: str) -> dict[str, Any]:
            result = await self._client.fetch_stats(catalog, schema, table)
            if isinstance(result, TimeoutResult):
                return result.partial  # best-effort on timeout
            return result

        async def fetch_system_runtime(self, query: str) -> list[dict[str, Any]]:
            result = await self._client.fetch_system_runtime(query)
            if isinstance(result, TimeoutResult):
                return result.partial
            return result
    ```

    **Create `live_catalog_source.py`**:
    ```python
    class LiveCatalogSource:
        """CatalogSource via live TrinoClient."""

        def __init__(self, client: TrinoClient) -> None:
            self._client = client

        async def fetch_iceberg_metadata(self, catalog: str, schema: str, table: str, suffix: str) -> list[dict[str, Any]]:
            """suffix is one of: snapshots, files, manifests, partitions, history, refs"""
            result = await self._client.fetch_iceberg_metadata(catalog, schema, table, suffix)
            if isinstance(result, TimeoutResult):
                return result.partial
            return result

        async def fetch_catalogs(self) -> list[str]:
            result = await self._client.fetch_system_runtime("SHOW CATALOGS")
            if isinstance(result, TimeoutResult):
                return [r.get("Catalog", "") for r in result.partial]
            return [r.get("Catalog", "") for r in result]

        async def fetch_schemas(self, catalog: str) -> list[str]:
            result = await self._client.fetch_system_runtime(f'SHOW SCHEMAS IN "{catalog}"')
            if isinstance(result, TimeoutResult):
                return [r.get("Schema", "") for r in result.partial]
            return [r.get("Schema", "") for r in result]
    ```

    Each live source is a thin wrapper that delegates to TrinoClient. The classifier call happens inside TrinoClient, not in the live source. This maintains the invariant.

    These live sources are integration-tested in Plan 05 against the real Trino stack. No unit test file is created here since the sources are pure delegation with no business logic beyond TimeoutResult unwrapping — they're covered by the architectural invariant test (ensuring TrinoClient classifier-first) and the integration tests.
  </action>
  <verify>
    <automated>uv run python -c "from mcp_trino_optimizer.adapters.trino.live_plan_source import LivePlanSource; from mcp_trino_optimizer.adapters.trino.live_stats_source import LiveStatsSource; from mcp_trino_optimizer.adapters.trino.live_catalog_source import LiveCatalogSource; print('OK')" && uv run mypy src/mcp_trino_optimizer/adapters/trino/live_plan_source.py src/mcp_trino_optimizer/adapters/trino/live_stats_source.py src/mcp_trino_optimizer/adapters/trino/live_catalog_source.py --strict</automated>
  </verify>
  <acceptance_criteria>
    - `src/mcp_trino_optimizer/adapters/trino/live_plan_source.py` contains `class LivePlanSource` with `fetch_plan`, `fetch_analyze_plan`, `fetch_distributed_plan`
    - `src/mcp_trino_optimizer/adapters/trino/live_stats_source.py` contains `class LiveStatsSource` with `fetch_table_stats`, `fetch_system_runtime`
    - `src/mcp_trino_optimizer/adapters/trino/live_catalog_source.py` contains `class LiveCatalogSource` with `fetch_iceberg_metadata`, `fetch_catalogs`, `fetch_schemas`
    - All three import from `adapters.trino.client` (not directly from `trino` package)
    - `uv run mypy` on all three files passes strict mode
  </acceptance_criteria>
  <done>Three live port adapters delegate to TrinoClient. LivePlanSource raises TrinoTimeoutError on timeout. LiveStatsSource and LiveCatalogSource return partial results on timeout. All pass mypy strict.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Trino cluster -> CapabilityMatrix | Trino version string from system table is semi-trusted (could be manipulated by a rogue cluster) |
| User table name -> fetch_iceberg_metadata | Table identifier components (catalog, schema, table) used in SQL construction |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-02-12 | Spoofing | capabilities.py | accept | Version string from system.runtime.nodes is trusted-within-network; a rogue Trino could lie but we're inside the user's deployment |
| T-02-13 | Tampering | live_catalog_source.py | mitigate | Table identifiers are quoted with double quotes in SQL construction; additionally, all constructed SQL goes through SqlClassifier before execution |
| T-02-14 | Elevation of Privilege | capabilities.py | mitigate | Refuse Trino < 429 with structured error; prevents running against unsupported clusters with unknown security posture |
</threat_model>

<verification>
```bash
uv run pytest tests/adapters/test_capabilities.py -v -x
uv run python -c "from mcp_trino_optimizer.adapters.trino import live_plan_source, live_stats_source, live_catalog_source; print('OK')"
uv run mypy src/mcp_trino_optimizer/adapters/trino/ --strict
uv run pytest -m "not integration" -x --tb=short -q
```
</verification>

<success_criteria>
- CapabilityMatrix frozen dataclass with all required fields
- Version probe refuses < 429 with TrinoVersionUnsupported
- Version parser handles "480", "480-e", and edge cases
- Three live sources implement their respective port protocols
- Live sources delegate to TrinoClient (no direct trino-python-client access)
- All non-integration tests pass, mypy strict passes
</success_criteria>

<output>
After completion, create `.planning/phases/02-trino-adapter-read-only-gate/02-04-SUMMARY.md`
</output>
