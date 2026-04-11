# Architecture Research

**Domain:** Python MCP server — Trino/Iceberg query analyzer & optimizer
**Researched:** 2026-04-11
**Confidence:** HIGH (stack & patterns well-established; HIGH on MCP SDK + Trino REST, MEDIUM on rule engine internals which are project-specific)

## 1. Guiding Principles

1. **Deterministic core, thin edges.** The rule engine is a pure function of `(ExplainPlan, Stats, Catalog)` → `list[RuleFinding]`. Everything above it (MCP tool wiring, transport) and below it (HTTP client, SQL parsing) is a replaceable adapter.
2. **Ports and adapters (hexagonal).** Live mode and offline mode differ only in which adapter implements the `PlanSource` / `StatsSource` / `CatalogSource` protocols. The pipeline never knows or cares.
3. **Safety by construction, not convention.** A single `SqlClassifier` with an allowlist sits between the pipeline and the Trino adapter. It is impossible to reach the HTTP client without passing the classifier.
4. **Tools are thin.** Every MCP tool is ~30 lines: parse args → call a service → serialize result. All logic lives in services, not in tool handlers.
5. **Everything is serializable.** Every domain type is a Pydantic model with a JSON schema. This powers both MCP tool I/O and on-disk fixtures for testing.

## 2. System Overview

```
┌────────────────────────────────────────────────────────────────────────┐
│                         MCP Transport Layer                            │
│   ┌─────────────────┐                        ┌──────────────────────┐  │
│   │  stdio server   │                        │   HTTP/SSE server    │  │
│   │ (Claude Code)   │                        │   (hosted, remote)   │  │
│   └────────┬────────┘                        └──────────┬───────────┘  │
│            │         shared ASGI/MCP app object         │              │
└────────────┼─────────────────────────────────────────────┼──────────────┘
             │                                             │
┌────────────▼─────────────────────────────────────────────▼──────────────┐
│                     MCP Interface (tools/resources/prompts)             │
│  ┌───────────────────┐  ┌───────────────────┐  ┌────────────────────┐   │
│  │ 8 Tool Handlers   │  │ 4 Resources       │  │ 3 Prompts          │   │
│  │ (thin adapters)   │  │ (playbooks .md)   │  │ (jinja templates)  │   │
│  └─────────┬─────────┘  └───────────────────┘  └────────────────────┘   │
└────────────┼────────────────────────────────────────────────────────────┘
             │                (calls into services)
┌────────────▼────────────────────────────────────────────────────────────┐
│                            Service Layer                                │
│  ┌──────────────┐ ┌─────────────┐ ┌──────────────┐ ┌─────────────────┐  │
│  │ AnalysisSvc  │ │ RewriteSvc  │ │ CompareSvc   │ │ MetadataSvc     │  │
│  │ (pipeline)   │ │             │ │              │ │ (stats/plan)    │  │
│  └──────┬───────┘ └──────┬──────┘ └──────┬───────┘ └────────┬────────┘  │
└─────────┼────────────────┼───────────────┼──────────────────┼───────────┘
          │                │               │                  │
┌─────────▼────────────────▼───────────────▼──────────────────▼───────────┐
│                           Domain Core                                   │
│  ┌────────────┐  ┌──────────────┐  ┌──────────────┐ ┌────────────────┐  │
│  │ Plan Parser│  │ Rule Engine  │  │Recommendation│ │ SQL Rewriter   │  │
│  │ (JSON→AST) │  │ (registry)   │  │ Engine       │ │ (sqlglot)      │  │
│  └────────────┘  └──────────────┘  └──────────────┘ └────────────────┘  │
│                           Domain Models                                 │
│  TrinoQuery · ExplainPlan · PlanNode · RuleFinding · Recommendation     │
│  RewriteResult · ComparisonReport  (all Pydantic BaseModels)            │
└─────────┬───────────────────────────────────────────────────────────────┘
          │         (ports — protocols only, no impls)
┌─────────▼───────────────────────────────────────────────────────────────┐
│              Ports: PlanSource · StatsSource · CatalogSource            │
└─────────┬───────────────────────────────────────────────────────────────┘
          │
┌─────────▼───────────────────────────────────────────────────────────────┐
│                            Adapters                                     │
│  ┌────────────────────┐  ┌─────────────────┐  ┌─────────────────────┐   │
│  │ LiveTrinoAdapter   │  │ OfflineAdapter  │  │ IcebergMetaAdapter  │   │
│  │ (httpx REST)       │  │ (from JSON arg) │  │ ($snapshots, etc.)  │   │
│  └─────────┬──────────┘  └─────────────────┘  └─────────────────────┘   │
│            │                                                            │
│  ┌─────────▼──────────┐  ┌─────────────────┐                            │
│  │ SqlClassifier      │  │ Query Logger    │                            │
│  │ (allowlist gate)   │  │ (structured)    │                            │
│  └────────────────────┘  └─────────────────┘                            │
└─────────────────────────────────────────────────────────────────────────┘
```

## 3. Component Boundaries & Module Layout

### Module decisions

| Question | Answer | Rationale |
|----------|--------|-----------|
| Plan parser vs rule engine — one package or two? | **Two.** `plan/` owns parsing & the typed tree. `rules/` depends on `plan/` but not vice versa. | Parser has zero domain opinions. Rules can evolve independently. Other tools (`get_explain_json`) need parser without rules. |
| Where does "analysis pipeline" live? | **`services/analysis.py`** — not in `rules/`. | The pipeline orchestrates parser → rules → recommender → optional rewriter. It is transport-agnostic and reusable by multiple MCP tools. |
| Recommendation engine vs rule engine? | **Separate.** Rules produce `RuleFinding` (observation). Recommender produces `Recommendation` (action + prioritization). | Priority/impact scoring is a second-pass concern; mixing them bloats rule code. |
| SQL rewriter — package or module? | **Package** (`rewrite/`) with one sub-module per transform. | Each rewrite (projection pruning, EXISTS→JOIN, etc.) is independently testable and can be enabled/disabled. |

### Concrete directory layout

```
mcp-trino-optimizer/
├── pyproject.toml
├── README.md
├── CLAUDE.md
├── Dockerfile
├── docker-compose.yml                   # Trino + Iceberg REST + MinIO for dev/CI
├── src/
│   └── mcp_trino_optimizer/
│       ├── __init__.py
│       ├── __main__.py                  # `python -m mcp_trino_optimizer`
│       ├── app.py                       # builds the MCP app object (shared by both transports)
│       │
│       ├── config/
│       │   ├── __init__.py
│       │   ├── settings.py              # pydantic-settings: env vars + config file
│       │   └── secrets.py               # JWT/basic auth resolution, never logged
│       │
│       ├── transport/
│       │   ├── __init__.py
│       │   ├── stdio.py                 # stdio entry point
│       │   └── http_sse.py              # HTTP/SSE entry point (Starlette/FastAPI)
│       │
│       ├── mcp/
│       │   ├── __init__.py
│       │   ├── server.py                # registers tools/resources/prompts on FastMCP
│       │   ├── tools/
│       │   │   ├── __init__.py
│       │   │   ├── analyze_trino_query.py
│       │   │   ├── get_explain_json.py
│       │   │   ├── get_explain_analyze.py
│       │   │   ├── get_table_statistics.py
│       │   │   ├── detect_optimization_issues.py
│       │   │   ├── suggest_optimizations.py
│       │   │   ├── rewrite_sql.py
│       │   │   └── compare_query_runs.py
│       │   ├── resources/
│       │   │   ├── __init__.py
│       │   │   ├── loader.py            # serves .md from package data dir
│       │   │   └── content/             # packaged markdown playbooks
│       │   │       ├── trino_optimization_playbook.md
│       │   │       ├── iceberg_best_practices.md
│       │   │       ├── trino_session_properties.md
│       │   │       └── query_anti_patterns.md
│       │   └── prompts/
│       │       ├── __init__.py
│       │       ├── loader.py            # jinja2 env pointed at content/
│       │       └── content/
│       │           ├── optimize_trino_query.jinja
│       │           ├── iceberg_query_review.jinja
│       │           └── generate_optimization_report.jinja
│       │
│       ├── services/                    # transport-agnostic business logic
│       │   ├── __init__.py
│       │   ├── analysis.py              # AnalysisService (the pipeline)
│       │   ├── rewrite.py               # RewriteService
│       │   ├── compare.py               # CompareService
│       │   └── metadata.py              # fetch stats / catalog info
│       │
│       ├── domain/                      # pure data types, no I/O
│       │   ├── __init__.py
│       │   ├── query.py                 # TrinoQuery
│       │   ├── plan.py                  # ExplainPlan, PlanNode, Stage, Operator, Metrics
│       │   ├── findings.py              # RuleFinding, Severity, Evidence
│       │   ├── recommendations.py       # Recommendation, RiskLevel
│       │   ├── rewrite.py               # RewriteResult, SqlDiff
│       │   └── comparison.py            # ComparisonReport
│       │
│       ├── ports/                       # protocols (interfaces) only
│       │   ├── __init__.py
│       │   ├── plan_source.py           # PlanSource protocol
│       │   ├── stats_source.py
│       │   └── catalog_source.py
│       │
│       ├── adapters/
│       │   ├── __init__.py
│       │   ├── trino/
│       │   │   ├── __init__.py
│       │   │   ├── client.py            # httpx-based REST client
│       │   │   ├── auth.py              # no-auth / basic / JWT
│       │   │   ├── live_plan_source.py  # implements PlanSource via client
│       │   │   ├── live_stats_source.py
│       │   │   └── live_catalog_source.py
│       │   ├── offline/
│       │   │   ├── __init__.py
│       │   │   └── json_plan_source.py  # implements PlanSource from pasted JSON
│       │   └── iceberg/
│       │       ├── __init__.py
│       │       └── metadata_reader.py   # $snapshots, $files, $partitions via Trino
│       │
│       ├── plan/                        # parser (no rule opinions)
│       │   ├── __init__.py
│       │   ├── parser.py                # JSON → ExplainPlan tree
│       │   ├── normalizer.py            # reconcile EXPLAIN vs EXPLAIN ANALYZE shapes
│       │   ├── metrics.py               # extract cpu/wall/rows/bytes/memory
│       │   └── iceberg_ops.py           # recognize IcebergTableScan, split info
│       │
│       ├── rules/
│       │   ├── __init__.py
│       │   ├── base.py                  # Rule ABC, Evidence requirements, decorators
│       │   ├── registry.py              # auto-discovery + ordering
│       │   ├── engine.py                # multi-pass orchestration
│       │   ├── stats/
│       │   │   ├── missing_stats.py
│       │   │   └── stale_stats.py
│       │   ├── joins/
│       │   │   ├── join_order.py
│       │   │   └── dynamic_filter.py
│       │   ├── pushdown/
│       │   │   ├── partition_pruning.py
│       │   │   └── predicate_pushdown.py
│       │   ├── distribution/
│       │   │   ├── data_skew.py
│       │   │   └── exchange_volume.py
│       │   ├── scans/
│       │   │   └── low_selectivity.py
│       │   └── iceberg/
│       │       ├── small_files.py
│       │       └── stale_snapshots.py
│       │
│       ├── recommend/
│       │   ├── __init__.py
│       │   ├── scorer.py                # severity × impact × confidence
│       │   ├── prioritizer.py
│       │   └── builder.py               # RuleFinding → Recommendation
│       │
│       ├── rewrite/
│       │   ├── __init__.py
│       │   ├── engine.py                # runs enabled transforms, preserves semantics
│       │   ├── sql_parser.py            # thin wrapper around sqlglot
│       │   ├── diff.py                  # human-readable unified diff
│       │   └── transforms/
│       │       ├── projection_pruning.py
│       │       ├── filter_pushdown.py
│       │       ├── exists_vs_join.py
│       │       └── early_aggregation.py
│       │
│       ├── compare/
│       │   ├── __init__.py
│       │   └── engine.py                # before/after metric deltas
│       │
│       ├── safety/
│       │   ├── __init__.py
│       │   ├── classifier.py            # SqlClassifier (allowlist gate)
│       │   └── allowlist.py             # SELECT/EXPLAIN/SHOW/DESCRIBE rules
│       │
│       └── observability/
│           ├── __init__.py
│           ├── logging.py               # structlog setup, request_id context var
│           └── query_log.py             # every SQL statement, params, timing, caller
│
└── tests/
    ├── unit/
    │   ├── plan/
    │   ├── rules/                       # one test file per rule, fixture-driven
    │   ├── rewrite/
    │   ├── safety/
    │   └── services/
    ├── fixtures/
    │   ├── plans/                       # hand-crafted EXPLAIN JSON per rule
    │   ├── queries/                     # golden SQL samples
    │   └── stats/
    ├── integration/                     # docker-compose driven; opt-in via marker
    │   ├── test_live_pipeline.py
    │   └── test_iceberg_metadata.py
    └── conftest.py
```

### Structure rationale

- **`domain/` has zero I/O** — pure Pydantic models. This is the stable core.
- **`ports/` are protocols only** — lets `services/` and `rules/` stay mode-agnostic.
- **`adapters/` are the only place that touches the network** — single blast radius for auth, retries, timeouts.
- **`rules/` is sub-packaged by concern** — 10+ rules flat becomes unreadable; grouping by theme mirrors how users think ("my joins are slow" → look in `rules/joins/`).
- **`mcp/tools/` — one file per tool** — forces each tool to stay thin and makes discovery trivial for new contributors.
- **`safety/` is a top-level package** — signals that it is load-bearing for read-only guarantees.

## 4. Data Model

All types are `pydantic.BaseModel` subclasses. They are the wire format for MCP tool I/O **and** the internal representation.

### Core types

```python
# domain/query.py
class TrinoQuery(BaseModel):
    sql: str                                   # original, unmodified
    catalog: str | None
    schema: str | None
    session_properties: dict[str, str] = {}
    caller_context: CallerContext | None       # who/why, for audit logs

# domain/plan.py
class Metrics(BaseModel):
    cpu_time_ms: int | None
    wall_time_ms: int | None
    input_rows: int | None
    output_rows: int | None
    input_bytes: int | None
    output_bytes: int | None
    peak_memory_bytes: int | None

class Operator(BaseModel):
    id: str
    kind: str                                  # "IcebergTableScan", "HashJoin", ...
    details: dict[str, Any]                    # raw operator props
    metrics: Metrics
    children: list["Operator"] = []

class Stage(BaseModel):
    id: str
    operators: list[Operator]
    distribution: str | None                   # SINGLE, HASH, BROADCAST, ...

class ExplainPlan(BaseModel):
    source: Literal["explain", "explain_analyze", "offline"]
    root_stage: Stage
    all_stages: list[Stage]                    # flat index for O(1) traversal
    raw_json: dict[str, Any]                   # original for debugging

# domain/findings.py
class Severity(StrEnum): CRITICAL = "critical"; HIGH = "high"; MEDIUM = "medium"; LOW = "low"; INFO = "info"

class EvidenceRef(BaseModel):
    kind: Literal["operator", "stage", "stat", "metadata_row"]
    id: str                                    # stable pointer into ExplainPlan
    extract: dict[str, Any]                    # snapshot of the evidence value

class RuleFinding(BaseModel):
    rule_id: str                               # "rules.stats.missing_stats"
    severity: Severity
    confidence: float                          # 0.0–1.0
    message: str                               # short human summary
    details: str                               # long-form explanation
    evidence: list[EvidenceRef]
    tags: list[str] = []

# domain/recommendations.py
class RiskLevel(StrEnum): SAFE = "safe"; MODERATE = "moderate"; RISKY = "risky"

class Recommendation(BaseModel):
    rule_id: str
    title: str
    reasoning: str
    expected_impact: str
    risk: RiskLevel
    validation_steps: list[str]
    priority_score: float                      # severity × impact × confidence
    suggested_actions: list[SuggestedAction]   # session prop, rewrite, stats refresh, etc.

# domain/rewrite.py
class RewriteResult(BaseModel):
    original_sql: str
    rewritten_sql: str
    diff_unified: str
    transforms_applied: list[str]
    justification: list[str]
    semantics_preserved: Literal[True]         # type-level assertion; always True or reject

# domain/comparison.py
class ComparisonReport(BaseModel):
    before: ExplainPlan
    after: ExplainPlan
    deltas: dict[str, MetricDelta]             # wall_time, cpu, bytes, memory, ...
    stage_changes: list[StageDelta]
    verdict: Literal["improved", "neutral", "regressed"]
```

### Pipeline dataflow

```
TrinoQuery
   │
   ▼ (PlanSource.fetch or parse)
ExplainPlan
   │
   ▼ (plan.parser + plan.normalizer)
ExplainPlan (typed, metrics populated)
   │
   ├──► rules.engine.run(plan, stats, catalog)
   │        │
   │        ▼
   │    list[RuleFinding]
   │        │
   │        ▼ (recommend.builder + scorer)
   │    list[Recommendation]
   │
   └──► (optional) rewrite.engine.apply(query, findings)
            │
            ▼
        RewriteResult
```

## 5. Rule Engine Design

### Base class & registry

```python
# rules/base.py
class EvidenceRequirement(StrEnum):
    PLAN_ONLY = "plan_only"                    # raw EXPLAIN is enough
    PLAN_WITH_METRICS = "plan_with_metrics"    # needs EXPLAIN ANALYZE
    TABLE_STATS = "table_stats"                # needs SHOW STATS FOR
    ICEBERG_METADATA = "iceberg_metadata"      # needs $files/$partitions

class Rule(ABC):
    id: ClassVar[str]                          # "rules.stats.missing_stats"
    severity_default: ClassVar[Severity]
    requires: ClassVar[frozenset[EvidenceRequirement]]
    tags: ClassVar[frozenset[str]] = frozenset()

    @abstractmethod
    def check(self, ctx: RuleContext) -> list[RuleFinding]: ...

# rules/registry.py
RULES: list[type[Rule]] = []

def register(cls: type[Rule]) -> type[Rule]:
    RULES.append(cls)
    return cls
```

Rules self-register via `@register` decorator. `RuleContext` bundles `ExplainPlan`, `StatsSource`, `CatalogSource`, plus a memoized helper for common lookups ("find all table scans," "total exchange bytes").

### Multi-pass orchestration

```python
# rules/engine.py
def run(plan: ExplainPlan, stats: StatsSource, catalog: CatalogSource) -> list[RuleFinding]:
    ctx = RuleContext(plan=plan, stats=stats, catalog=catalog)
    ctx.prefetch(_required_evidence(plan))      # batch all stats/metadata lookups once
    findings = []
    for rule_cls in RULES:
        if not ctx.has_evidence_for(rule_cls.requires):
            findings.append(_skipped(rule_cls, "missing evidence"))
            continue
        try:
            findings.extend(rule_cls().check(ctx))
        except Exception as e:
            findings.append(_errored(rule_cls, e))
            logger.exception("rule_failed", rule_id=rule_cls.id)
    return findings
```

Key properties:
- **Single pass over the rule list**, but `RuleContext` caches traversals so rules share work.
- **Prefetch step** — the engine inspects `Rule.requires` for all registered rules, computes the union, and fetches stats/metadata **once** before any rule runs. Avoids N×M round trips.
- **Rule failures are isolated** — one broken rule does not kill the report; it is recorded as an errored finding.
- **Deterministic ordering** — `RULES` list order is stable, rule output is sorted by `(severity, rule_id, evidence_id)` before return.

### How rules are tested

- **Fixture-driven.** One `tests/fixtures/plans/<rule_id>_positive.json` (should fire) and `<rule_id>_negative.json` (should not fire) per rule.
- **No Trino needed.** Tests use `OfflinePlanSource` + `FakeStatsSource` + `FakeCatalogSource`.
- **Golden assertions on `RuleFinding`** — severity, evidence IDs, rendered message (snapshot).

## 6. Dual-Mode Execution (Live + Offline)

The port-adapter split handles this cleanly. `services.analysis.AnalysisService` depends only on `PlanSource`, `StatsSource`, `CatalogSource`. The transport picks which adapter to wire in:

```python
# services/analysis.py
class AnalysisService:
    def __init__(self, plan_source: PlanSource, stats: StatsSource, catalog: CatalogSource): ...

    def analyze(self, query: TrinoQuery, *, use_analyze: bool) -> AnalysisReport:
        plan = self.plan_source.fetch(query, with_metrics=use_analyze)
        findings = rules.engine.run(plan, self.stats, self.catalog)
        recs = recommend.builder.build(findings)
        return AnalysisReport(plan=plan, findings=findings, recommendations=recs)
```

**Live mode** (default when `TRINO_URL` is set):
```python
AnalysisService(
    plan_source=LiveTrinoPlanSource(client),
    stats=LiveTrinoStatsSource(client),
    catalog=LiveIcebergCatalog(client),
)
```

**Offline mode** (when the tool call includes `explain_json` argument):
```python
AnalysisService(
    plan_source=OfflinePlanSource(pasted_json),
    stats=InlineStatsSource(pasted_stats or {}),
    catalog=NullCatalog(),                  # rules requiring catalog evidence are skipped
)
```

A single factory `build_analysis_service(tool_args, settings)` decides which wiring to use based on `tool_args.explain_json`. The pipeline body never branches on mode.

## 7. MCP Interface Wiring

### Tools

Each tool file is ~30 lines and looks the same:

```python
# mcp/tools/analyze_trino_query.py
async def handler(args: AnalyzeArgs, ctx: MCPContext) -> AnalyzeResult:
    with observability.request_scope(tool="analyze_trino_query", caller=ctx.caller):
        svc = build_analysis_service(args, settings)
        report = svc.analyze(args.to_query(), use_analyze=args.use_analyze)
        return AnalyzeResult.from_report(report)

tool = Tool(
    name="analyze_trino_query",
    description="…",
    input_schema=AnalyzeArgs.model_json_schema(),
    handler=handler,
)
```

`mcp/server.py` registers all tools on a `FastMCP` instance. The same app object is then handed to either the stdio or HTTP/SSE runner in `transport/`.

### Resources (playbooks)

**Decision: package as package data.** Playbooks live in `src/mcp_trino_optimizer/mcp/resources/content/*.md` and are shipped inside the wheel. A loader reads them via `importlib.resources` and serves them over MCP. Rationale: reproducible across install methods (pip/uvx/Docker), versioned with the code, no external dependency, no drift.

### Prompts

Jinja2 templates in `mcp/prompts/content/*.jinja`. The loader renders with the tool arguments + (optionally) the analysis report. Keeps narrative shaping out of Python code.

## 8. Configuration & Secrets

- **`pydantic-settings`** in `config/settings.py` reads env vars first, then an optional TOML/YAML config file, then allows per-tool-call overrides (`args.trino_url`, `args.catalog`).
- **Precedence:** tool-call arg > env var > config file > default.
- **Secrets** (`TRINO_PASSWORD`, `TRINO_JWT`) go through `config/secrets.py` which returns a `SecretStr`. The structured logger has a filter that redacts any `SecretStr` field and any header starting with `authorization`.
- **JWT flow:** the adapter reads the token from settings at request time (not at startup), allowing token rotation without restart. The token is never logged, never included in tool results, never written to disk.

## 9. Transport Handling

| Aspect | stdio | HTTP/SSE |
|---|---|---|
| Entry point | `transport/stdio.py` | `transport/http_sse.py` |
| Process model | One process per client (spawned by Claude Code) | Long-running server, many clients |
| Auth | None (local trust) | Bearer token required, configurable via settings |
| CORS | N/A | Allowlist origins from settings; default closed |
| Lifecycle | Stateless; each call independent | Session-scoped trace context |
| What's shared | `app.py` builds the exact same `FastMCP` app object | same |

Both transports produce a `FastMCP` app object from `app.build_app(settings)` and then start the appropriate runner. **No tool code is transport-aware.**

## 10. Safety Enforcement

**One central gate.** `safety/classifier.py` exposes:

```python
class SqlClassifier:
    def classify(self, sql: str) -> SqlKind: ...          # SELECT / EXPLAIN / SHOW / DESCRIBE / FORBIDDEN
    def assert_read_only(self, sql: str) -> None:         # raises ForbiddenSqlError
```

Classification uses `sqlglot.parse` to get an AST, walks the top-level statements, and matches against an **explicit allowlist**:
- `EXPLAIN` (any sub-form)
- `SELECT` (with constraint: no CTAS, no INSERT INTO SELECT)
- `SHOW …`
- `DESCRIBE …`
- Metadata table queries (`system.*`, `$snapshots`, `$files`, etc. — already `SELECT`)

**Anything else → `ForbiddenSqlError`.** String matching is a secondary sanity check (reject DDL/DML keywords anywhere in the tokenized statement), but the AST check is authoritative.

**Enforcement location.** `adapters/trino/client.py` calls `SqlClassifier.assert_read_only(sql)` as its first line in every query method. **There is no code path to the Trino HTTP endpoint that does not pass through this check.** Unit tests assert this invariant by importing the client and asserting the first line of every public method.

## 11. Observability

- **`structlog`** bound with `request_id`, `tool_name`, `caller`, `trino_url` (not auth), `catalog`, `schema`.
- **Query log.** `observability/query_log.py` emits a `trino.query.executed` event for every statement with fields `(request_id, statement_preview, statement_hash, duration_ms, rows_returned, bytes_scanned, status, error)`. This is the audit trail promised in PROJECT.md.
- **Request scope.** A context manager that sets a `contextvars.ContextVar` for `request_id`, so every log line inside a tool call is correlated without threading the ID through every function.
- **Timings.** The service layer emits `service.<name>.completed` with total time and per-phase timings (fetch_plan, run_rules, build_recs, rewrite).

## 12. Testability — Seams & Strategy

| Component | Seam | Mocks/fakes needed | Difficulty |
|---|---|---|---|
| `plan/parser.py` | Pure function `json → ExplainPlan` | None (fixture JSON) | Easy |
| `rules/*` | `RuleContext` | `FakeStatsSource`, `FakeCatalogSource`, fixture plans | Easy |
| `rules/engine.py` | Registry can be swapped | Register a single test rule | Easy |
| `recommend/scorer.py` | Pure function | None | Easy |
| `rewrite/transforms/*` | `sql → sql` functions + semantic assertions | sqlglot test harness | Medium |
| `services/analysis.py` | Depends on 3 ports | Provide fakes for all three | Easy |
| `adapters/trino/client.py` | `httpx.AsyncClient` | `respx` for HTTP mocking | Medium |
| `safety/classifier.py` | Pure | None | Easy |
| `mcp/tools/*` | Call into services | Fake services | Easy |
| `transport/http_sse.py` | Starlette TestClient | None | Medium |
| End-to-end with Trino | docker-compose | Real Trino + Iceberg + MinIO | Hard (marked `@pytest.mark.integration`) |

**Testing layers:**
1. **Unit (fast, no network, CI default)** — `tests/unit/`, uses only fixtures.
2. **Contract** — adapters validated against `respx`-mocked HTTP responses recorded from real Trino.
3. **Integration (opt-in)** — `tests/integration/` requires `docker-compose up`. Gated by `@pytest.mark.integration` and `TRINO_URL` env.
4. **Golden regression** — sample query suite produces snapshotted `AnalysisReport` JSON; diffs are reviewed.

## 13. Build Order (Topological)

```
Layer 0 — Foundation (no deps)
  1. config/settings.py
  2. observability/logging.py
  3. domain/*  (Pydantic models)
  4. safety/classifier.py + safety/allowlist.py

Layer 1 — Ports & parser
  5. ports/*  (protocols)
  6. plan/parser.py + plan/normalizer.py + plan/metrics.py
  7. plan/iceberg_ops.py

Layer 2 — Adapters (live)
  8. adapters/trino/client.py  (uses safety.classifier)
  9. adapters/trino/auth.py
 10. adapters/trino/live_plan_source.py + live_stats_source.py + live_catalog_source.py
 11. adapters/offline/json_plan_source.py
 12. adapters/iceberg/metadata_reader.py

Layer 3 — Rules
 13. rules/base.py + rules/registry.py + rules/engine.py
 14. rules/stats/*  → rules/pushdown/* → rules/joins/* → rules/distribution/* → rules/scans/* → rules/iceberg/*
     (order within this step is flexible; each rule is independent)

Layer 4 — Higher-level engines
 15. recommend/scorer.py + prioritizer.py + builder.py
 16. rewrite/sql_parser.py + diff.py + engine.py
 17. rewrite/transforms/*
 18. compare/engine.py

Layer 5 — Services
 19. services/metadata.py
 20. services/analysis.py
 21. services/rewrite.py
 22. services/compare.py

Layer 6 — MCP interface
 23. mcp/resources/loader.py + content/*.md
 24. mcp/prompts/loader.py + content/*.jinja
 25. mcp/tools/*  (8 handlers)
 26. mcp/server.py (wires tools/resources/prompts onto FastMCP)

Layer 7 — Transport
 27. app.py (builds shared FastMCP app object)
 28. transport/stdio.py
 29. transport/http_sse.py
 30. __main__.py + docker-compose + Dockerfile
```

### Phase implications for the roadmap

This topology suggests roughly five roadmap phases:

1. **Foundation** (Layers 0-1) — config, logging, domain models, safety, plan parser. No Trino yet. End state: can parse a pasted EXPLAIN JSON into typed form, tested against fixtures.
2. **Trino adapter + offline mode** (Layer 2) — HTTP client, auth, classifier integration, offline adapter. End state: can fetch and parse plans in both modes.
3. **Rule engine core + first 3 rules** (Layer 3 partial) — base class, registry, engine, plus stats/pushdown/join rules with fixtures. End state: rule engine runs end-to-end on offline plans.
4. **Remaining rules + recommender + rewriter + comparator** (Layers 3-4 rest) — complete the ruleset, build recommendation engine, implement safe rewrites, comparison.
5. **MCP surface + transports + packaging** (Layers 5-7) — services, 8 tools, resources, prompts, stdio + HTTP/SSE, Docker, README, integration tests.

## 14. Dataflow: `analyze_trino_query` Happy Path

```
Claude Code
    │  MCP tool call
    ▼
transport/stdio.py (or http_sse.py)
    │  JSON-RPC message
    ▼
FastMCP dispatcher
    │  resolves tool name → handler
    ▼
mcp/tools/analyze_trino_query.py::handler(args, ctx)
    │  enters observability.request_scope(request_id=…, tool=…)
    │  builds TrinoQuery from args
    ▼
app.build_analysis_service(args, settings)
    │  picks LiveTrinoPlanSource or OfflinePlanSource
    │  constructs AnalysisService with the three ports
    ▼
services/analysis.py::AnalysisService.analyze(query, use_analyze=True)
    │
    ├──▶ plan_source.fetch(query, with_metrics=True)
    │       │
    │       ▼ (live mode)
    │    adapters/trino/live_plan_source.py
    │       │ builds "EXPLAIN ANALYZE " + query.sql
    │       ▼
    │    adapters/trino/client.py::execute()
    │       │ safety.classifier.assert_read_only(sql)  ← GATE
    │       │ httpx POST /v1/statement
    │       │ observability.query_log emits trino.query.executed
    │       │ polls nextUri until FINISHED
    │       ▼
    │    raw JSON rows → extract explain text → json.loads
    │       │
    │       ▼
    │    plan/parser.py::parse_explain_json(raw)
    │    plan/normalizer.py::normalize(plan)
    │    plan/metrics.py::populate(plan)
    │       │
    │       ▼
    │    ExplainPlan (typed)
    │
    ├──▶ rules/engine.py::run(plan, stats, catalog)
    │       │ ctx.prefetch(required_evidence)  ← one batch of metadata lookups
    │       │ for rule in RULES:
    │       │     rule.check(ctx) → RuleFinding(s)
    │       ▼
    │    list[RuleFinding]  (sorted, deterministic)
    │
    └──▶ recommend/builder.py::build(findings)
            │ recommend/scorer.py scores each
            │ recommend/prioritizer.py sorts
            ▼
         list[Recommendation]

    │
    ▼
AnalysisReport(plan, findings, recommendations)
    │
    ▼
AnalyzeResult.from_report(report)  (MCP-facing Pydantic model)
    │
    ▼
FastMCP serializes → JSON-RPC response
    │
    ▼
transport returns to Claude Code
```

**Logging trail for the above call:**
- `request.started` (tool, request_id, caller)
- `service.analysis.phase_completed` (phase="fetch_plan", duration_ms)
- `trino.query.executed` (statement_hash, duration_ms, rows, bytes, status)
- `service.analysis.phase_completed` (phase="run_rules", rule_count, findings_count)
- `service.analysis.phase_completed` (phase="build_recs", rec_count)
- `request.completed` (total_duration_ms, status)

## 15. Scaling Considerations

This is not a user-facing SaaS; scaling concerns are operator-facing.

| Scale | Concern | Approach |
|---|---|---|
| 1 user (local) | Cold start | stdio, single process, no caching. |
| Team (10-50 users, shared HTTP server) | Concurrent tool calls | Async throughout (`httpx.AsyncClient`), one `FastMCP` app, Starlette workers. Bound by Trino concurrency, not by us. |
| Heavy usage | Repeated EXPLAIN for same query | Optional in-memory LRU cache keyed on `(sql_hash, catalog, schema)` with short TTL. Opt-in via config. |
| Very large plans | Parser memory | Stream parse is unnecessary — Trino plans are KB-MB, not GB. Hard-cap response size at the client and reject with a clear error. |

## 16. Anti-Patterns to Avoid

### Anti-Pattern 1: Tool handlers that contain business logic
**What people do:** Put rule execution, SQL fetching, and formatting directly in `mcp/tools/*.py`.
**Why wrong:** Duplication across tools, cannot reuse pipeline in tests, transport-coupled logic.
**Do instead:** Tools are ~30 lines: args → service → result. All logic in `services/`.

### Anti-Pattern 2: Rules that reach into Trino directly
**What people do:** A rule calls `trino_client.execute("SHOW STATS …")` from inside its `check` method.
**Why wrong:** Rules become stateful, untestable without a cluster, and cannot run in offline mode.
**Do instead:** Rules declare evidence via `requires`. The engine prefetches. Rules only touch `RuleContext`.

### Anti-Pattern 3: Scattered safety checks
**What people do:** Every tool validates SQL on its own with ad-hoc regex.
**Why wrong:** Easy to miss a path. One regex bug = destructive SQL reaches Trino.
**Do instead:** Single `SqlClassifier`, enforced at the adapter boundary, covered by an architectural test.

### Anti-Pattern 4: Mode-aware pipeline
**What people do:** `if offline: … else: …` branches inside `AnalysisService`.
**Why wrong:** Mode logic metastasizes; every future change must reason about both branches.
**Do instead:** Mode is chosen at construction time (`build_analysis_service`). The pipeline is mode-blind.

### Anti-Pattern 5: Logging secrets
**What people do:** `logger.info("connecting", settings=settings.dict())`.
**Why wrong:** JWT tokens end up in log aggregators.
**Do instead:** `SecretStr` everywhere for credentials + a structlog processor that drops any field whose value is a `SecretStr` or whose key matches `auth|token|password|secret`.

### Anti-Pattern 6: Rules that panic
**What people do:** A rule raises on unexpected plan shape, killing the whole analysis.
**Why wrong:** One bad rule kills all of the user's feedback.
**Do instead:** `rules/engine.py` catches per-rule exceptions, records an `errored` finding, continues.

## 17. Integration Points

| Integration | Pattern | Notes |
|---|---|---|
| Trino REST API | httpx async, bearer/basic auth, statement polling | Timeout every request; cancel on tool-call cancellation |
| Iceberg metadata tables | Via Trino (no direct catalog access) | Keeps the client Trino-only; Hive/REST catalog choice is Trino's problem |
| MCP clients (Claude Code, Desktop) | Official Python `mcp` SDK (`FastMCP`) | Both transports ship from day one |
| sqlglot | In-process library | Used by safety classifier **and** rewriter; one shared parser |
| Docker compose (dev/CI) | Trino + Iceberg REST catalog + MinIO | Integration tests only; unit tests must not require it |

## 18. Quality Gate Checklist

- [x] Components clearly defined with boundaries and interfaces (section 3, 4, 5)
- [x] Data flow explicit with named types (section 4, 14)
- [x] Build order implications noted — topological, five phases proposed (section 13)
- [x] Directory layout is concrete, not hand-wavy (section 3)
- [x] Safety-critical pieces (no-destructive-SQL, logging) have clear ownership (sections 10, 11)

## Sources

- MCP Python SDK `FastMCP` patterns — Anthropic MCP documentation (HIGH confidence)
- Trino REST statement protocol — trino.io/docs/current/develop/client-protocol.html (HIGH)
- Trino EXPLAIN output formats — trino.io/docs/current/sql/explain.html (HIGH)
- Iceberg metadata tables — iceberg.apache.org/docs/latest/spark-queries/#inspecting-tables (HIGH, Trino exposes equivalents)
- Hexagonal architecture / ports-and-adapters — Alistair Cockburn, widely adopted Python pattern (HIGH)
- Pydantic v2 + pydantic-settings — docs.pydantic.dev (HIGH)
- sqlglot AST-based SQL classification — github.com/tobymao/sqlglot (HIGH)
- structlog contextvar request scoping — www.structlog.org (HIGH)

---
*Architecture research for: Python MCP server — Trino/Iceberg query optimizer*
*Researched: 2026-04-11*
