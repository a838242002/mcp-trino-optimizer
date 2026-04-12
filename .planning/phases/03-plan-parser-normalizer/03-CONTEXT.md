# Phase 3: Plan Parser & Normalizer - Context

**Gathered:** 2026-04-12
**Status:** Ready for planning

<domain>
## Phase Boundary

Convert raw Trino `EXPLAIN (FORMAT JSON)` and `EXPLAIN ANALYZE (FORMAT JSON)` output into two fully typed plan classes — `EstimatedPlan` and `ExecutedPlan` — that:

1. **Replace** the Phase 2 placeholder `ExplainPlan` dataclass entirely
2. Expose a typed tree of `PlanNode` objects with per-operator metrics, Iceberg details, and version-drift tolerance via `model_extra` raw dict bags
3. **Normalize** common operator variants (`ScanFilterProject` → `TableScan + filter + projection`, `Project` wrapper walk-through) in-place before any consumer sees the tree
4. **Extract** Iceberg-specific operator details (split count, file count, partition spec ID) as first-class typed fields on `PlanNode`
5. Ship a **multi-version fixture corpus** (3 Trino versions: 429, middle LTS, 480+) gated by syrupy snapshot tests in CI

**Covers:** PLN-01 through PLN-07.

**Not in this phase (belongs elsewhere):**
- Rule engine and any rules — Phase 4
- Recommendation engine — Phase 5
- Rewrite engine — Phase 6
- MCP tools that consume the parser — Phase 8
- Additional fixture versions beyond the initial 3 — added when real drift is discovered
- Exchange normalization or other operator normalizations beyond ScanFilterProject/Project — handled per-rule in Phase 4 if needed

</domain>

<decisions>
## Implementation Decisions

### Parser Output Hierarchy

- **D-01 (replace ExplainPlan entirely):** Phase 3 removes the `ExplainPlan` dataclass from `ports/plan_source.py` and introduces `EstimatedPlan` and `ExecutedPlan` as the new domain types. `PlanSource.fetch_plan()` returns `EstimatedPlan`; `PlanSource.fetch_analyze_plan()` returns `ExecutedPlan`. The `OfflinePlanSource` and `LivePlanSource` adapters update their return types accordingly. Clean break — no inheritance from the old placeholder.

- **D-02 (new parser/ subpackage):** The typed plan models and parsing logic live in a new `src/mcp_trino_optimizer/parser/` subpackage:
  ```
  src/mcp_trino_optimizer/parser/
  ├── __init__.py         # public API: parse_estimated, parse_executed
  ├── models.py           # PlanNode, EstimatedPlan, ExecutedPlan, SchemaDriftWarning
  ├── parser.py           # JSON-to-typed-tree parsing logic
  └── normalizer.py       # ScanFilterProject collapse, Project walk-through
  ```
  Keeps parsing concerns separate from ports and adapters.

- **D-03 (generic PlanNode with operator_type field):** One `PlanNode` pydantic model with `operator_type: str` and typed common fields (estimated costs, children, filters, table references). No subclasses per operator type. Rules match on `operator_type` string patterns (e.g., `"IcebergTableScan"`, `"InnerJoin"`). Unknown operators are first-class — they just have fewer typed fields and more in `model_extra`.

- **D-04 (pydantic model_extra for raw dict bag):** `PlanNode` uses `model_config = ConfigDict(extra='allow')`. Known Trino fields are typed attributes; unknown or version-specific fields land in `model_extra` automatically. This satisfies PLN-02's "every node preserves its original fields inside a `raw` dict" without duplication — `model_extra` IS the raw bag.

### Version-Drift Tolerance

- **D-05 (schema_drift_warnings on plan result):** `EstimatedPlan` and `ExecutedPlan` carry a `schema_drift_warnings: list[SchemaDriftWarning]` field. Each `SchemaDriftWarning` has `node_path: str` (location in tree), `field_name: str | None`, `description: str`, and `severity: Literal["info", "warning"]`. Also logged via structlog. Rules and consumers can inspect warnings programmatically.

- **D-06 (lenient parsing — never raise on unexpected structure):** The parser is maximally lenient. Unknown node types, unexpected nesting, missing optional sections, renamed fields — all produce `SchemaDriftWarning` entries, never exceptions. A plan with zero successfully parsed nodes still returns an empty tree with warnings. Only truly unparseable input (invalid JSON, completely wrong top-level structure) raises `ParseError`.

- **D-07 (3 Trino versions for fixtures):** The fixture corpus starts with exactly 3 versions: Trino 429 (minimum supported), a middle version (~450–460 LTS), and 480+ (current). Additional versions are added only when real drift is discovered. Keeps the corpus manageable.

### Fixture Capture Strategy

- **D-08 (live capture from docker-compose):** Fixtures are captured by running real queries against the Phase 2 docker-compose Trino stack and saving the EXPLAIN JSON output. For multi-version capture, swap the Trino image tag and re-capture. Authentic real-world output — no synthetic JSON.

- **D-09 (fixtures at tests/fixtures/explain/):** Fixture files live at `tests/fixtures/explain/{version}/{query_name}.json`. Example: `tests/fixtures/explain/480/simple_select.json`, `tests/fixtures/explain/480/simple_select_analyze.json`. Clear naming convention, co-located with tests.

- **D-10 (snapshot parsed output):** Syrupy snapshot tests parse each fixture JSON through the parser and snapshot the resulting `EstimatedPlan` / `ExecutedPlan`. When Trino adds a field, the snapshot diff shows exactly what changed in the parsed output. Tests verify parsing correctness + detect drift in a single assertion.

### Normalization Scope

- **D-11 (in-place normalization):** The parser normalizes as it builds the tree. Consumers always see the canonical form. `ScanFilterProject` is never visible to rules — they only see the equivalent `TableScan + filter + projection` structure. One tree, one API, no confusion about which form to inspect.

- **D-12 (Iceberg extraction = PLN-04 minimum):** Extract exactly split count, file count, and partition spec identifier from `IcebergTableScan` operator details. These are the fields rules need for small-files detection (I1), partition pruning (R2), and partition transform mismatch (I8). Additional Iceberg details added in Phase 4 when rules need them.

- **D-13 (normalization scope = PLN-05 only):** Phase 3 normalizes only `ScanFilterProject` collapse and `Project` wrapper walk-through. Other operator quirks (Exchange variants, FilterNode attachment patterns) are handled per-rule in Phase 4 if needed. Keeps Phase 3 focused on exactly what the requirements specify.

### Claude's Discretion

The planner may make concrete choices on the following without re-asking:
- Exact pydantic model field names and types for `PlanNode` common fields (estimated row count, cost, output columns, etc.) — must be informed by actual Trino EXPLAIN JSON structure.
- Whether `EstimatedPlan` and `ExecutedPlan` share a common base class (`BasePlan`) or are fully separate — pick whichever produces the cleanest API for Phase 4's rule engine.
- How the parser detects plan_type from JSON content (heuristic-based vs explicit parameter from caller).
- Exact `SchemaDriftWarning` structure beyond the mandatory fields listed in D-05.
- How `IcebergTableScan` detail strings are parsed (regex vs structured parsing) — must be testable.
- Which queries to run for fixture capture (must cover at minimum: simple SELECT, JOIN, aggregate, Iceberg table scan).
- Exact syrupy snapshot configuration (serializer, update policy).
- How the `PlanSource` protocol signature changes are coordinated with `OfflinePlanSource` and `LivePlanSource` updates.
- Tree-walking utility methods on `EstimatedPlan` / `ExecutedPlan` (e.g., `find_nodes_by_type()`, `walk()`) — must exist, shape is planner's choice.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project Truth
- `CLAUDE.md` — project instructions, tech stack (load-bearing, contains prescriptive version pins including `pydantic>=2.9,<3`, `syrupy>=5.1.0`)
- `.planning/PROJECT.md` — vision, core value, determinism constraint
- `.planning/REQUIREMENTS.md` §PLN-01..PLN-07 — the 7 requirements this phase must deliver
- `.planning/ROADMAP.md` — Phase 3 section (Success Criteria 1–5 are the verification spine)
- `.planning/STATE.md` — Key Decisions 1–16; especially #4 (sqlglot for SQL, not plan parsing), #12 (Trino ≥ 429)

### Prior Phase Context
- `.planning/phases/01-skeleton-safety-foundation/01-CONTEXT.md` — Phase 1 decisions; D-01 src-layout, D-04 tool auto-registration
- `.planning/phases/02-trino-adapter-read-only-gate/02-CONTEXT.md` — Phase 2 decisions; D-01 hexagonal layout (ports/adapters structure), D-20 OfflinePlanSource, D-21 ExplainPlan placeholder (replaced by this phase), D-22 docker-compose stack, D-25 fixture setup bypass

### Research Corpus (load-bearing)
- `.planning/research/SUMMARY.md` §4.3 — Plan parser stack, pydantic models for plan tree
- `.planning/research/ARCHITECTURE.md` — hexagonal ports overview, PlanSource protocol shape
- `.planning/research/PITFALLS.md` — plan JSON schema drift across Trino versions, version-tolerance strategy
- `.planning/research/FEATURES.md` — EstimatedPlan/ExecutedPlan requirements, Iceberg operator details

### Existing Code (Phase 2 delivered)
- `src/mcp_trino_optimizer/ports/plan_source.py` — current `ExplainPlan` + `PlanSource` Protocol (REPLACED by this phase)
- `src/mcp_trino_optimizer/adapters/offline/json_plan_source.py` — `OfflinePlanSource` (UPDATED by this phase)
- `src/mcp_trino_optimizer/adapters/trino/live_plan_source.py` — `LivePlanSource` (UPDATED by this phase)
- `.testing/docker-compose.yml` — Trino 480 + Lakekeeper + MinIO + Postgres (used for fixture capture)

### External Specs Touched by Phase 3
- [Trino EXPLAIN JSON format](https://trino.io/docs/current/sql/explain.html) — EXPLAIN (FORMAT JSON) output structure
- [Trino EXPLAIN ANALYZE](https://trino.io/docs/current/sql/explain-analyze.html) — per-operator runtime metrics fields
- [Pydantic model_config extra='allow'](https://docs.pydantic.dev/latest/concepts/config/#extra-attributes) — model_extra for raw dict bag
- [syrupy snapshot testing](https://github.com/toptal/syrupy) — snapshot assertion patterns

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets (from Phase 1 & 2)
- **`src/mcp_trino_optimizer/ports/plan_source.py`** — existing `ExplainPlan` dataclass and `PlanSource` Protocol. Phase 3 replaces `ExplainPlan` with `EstimatedPlan`/`ExecutedPlan` and updates `PlanSource` method signatures.
- **`src/mcp_trino_optimizer/adapters/offline/json_plan_source.py`** — `OfflinePlanSource` currently returns `ExplainPlan`. Phase 3 updates it to parse through the new parser and return `EstimatedPlan`/`ExecutedPlan`.
- **`src/mcp_trino_optimizer/adapters/trino/live_plan_source.py`** — `LivePlanSource` currently returns `ExplainPlan`. Same update needed.
- **`.testing/docker-compose.yml`** — Trino 480 + Lakekeeper stack. Used to capture real EXPLAIN JSON fixtures.
- **`tests/integration/conftest.py`** — integration test fixtures with docker-compose lifecycle. Fixture capture scripts extend this.

### Established Patterns
- **Pydantic models at module scope** — Phase 1 UAT learned that FastMCP + PEP 563 requires Pydantic models at module scope, not inside functions. Parser models must follow this pattern.
- **Settings fail-fast** — model_validator pattern from Phase 1 D-08 / Phase 2 D-11. Parser should fail fast on invalid input with structured errors.
- **Commit conventions** — `feat(03): ...` for code, `docs(03): ...` for docs, `test(03): ...` for test-only commits.

### Integration Points
- **`pyproject.toml`** — Phase 3 adds `syrupy>=5.1.0` as a dev dependency.
- **`ports/plan_source.py`** — PlanSource protocol signature changes affect all adapters.
- **`ports/__init__.py`** — public API exports change: `ExplainPlan` → `EstimatedPlan`, `ExecutedPlan`.
- **Phase 4 (rule engine)** — rules consume `EstimatedPlan`/`ExecutedPlan` and `PlanNode` tree. The parser's output shape directly determines the rule engine's input API.

</code_context>

<specifics>
## Specific Ideas

- **ExplainPlan replacement is a clean break.** No compatibility shims, no re-exports of the old type. Phase 2 adapters are updated to use the new types. Any code importing `ExplainPlan` is updated or removed.
- **`model_extra` IS the raw bag.** PLN-02 says "every node preserves its original fields inside a `raw` dict" — `model_extra` achieves this without duplicating data. Document this clearly so rule authors know to check `model_extra` for version-specific fields.
- **In-place normalization means ScanFilterProject never exists in the parsed tree.** Rules that need to find "scans under this subtree" can use a simple tree walk without special-casing. This is the whole point of PLN-05.
- **Fixture capture requires running the docker-compose stack.** The fixture capture process should be scripted so it can be re-run when a new Trino version is added. Consider a `scripts/capture_fixtures.py` or similar.
- **Snapshot tests are the drift alarm.** When Trino 490 adds a new field to EXPLAIN JSON, the snapshot test fails with a clean diff showing exactly what changed. The developer then updates the snapshot and optionally adds typed fields for the new data.

</specifics>

<deferred>
## Deferred Ideas

- **Exchange normalization** (LocalExchange, RemoteStreamingExchange variants) — handled per-rule in Phase 4 if needed.
- **Additional Iceberg metadata extraction** beyond split count, file count, partition spec ID — added when Phase 4 rules need them.
- **Additional Trino fixture versions** beyond the initial 3 — added when real drift is discovered.
- **Plan caching** — Phase 4 may introduce a bounded cache keyed on SQL hash + snapshot ID.
- **Distributed plan parsing** — `EXPLAIN (TYPE DISTRIBUTED)` is fetched by the adapter but typed parsing of stage/fragment layout is deferred unless Phase 4 rules need it. Phase 3 parses it into a generic PlanNode tree.

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 03-plan-parser-normalizer*
*Context gathered: 2026-04-12 via /gsd-discuss-phase*
