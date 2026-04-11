# mcp-trino-optimizer

## What This Is

A Model Context Protocol (MCP) server that helps Claude Code (and other MCP-compatible clients) optimize Trino SQL queries running against Iceberg data lakes. It analyzes queries using EXPLAIN / EXPLAIN ANALYZE evidence, applies a deterministic rule engine to diagnose performance issues, suggests prioritized optimizations with reasoning, and can safely rewrite SQL while preserving semantics. It is designed for data engineers, analytics engineers, and platform teams working with Trino + Iceberg.

## Core Value

Turn opaque Trino query performance problems into actionable, evidence-backed optimization reports that a user (or an LLM agent) can trust and apply safely.

## Requirements

### Validated

<!-- Shipped and confirmed valuable. -->

(None yet — ship to validate)

### Active

<!-- Current scope. Building toward these. -->

#### Table Stakes (Platform)

- [ ] MCP server skeleton with Python 3.11+, packaged via `uv` + `pyproject.toml`, installable via `pip`/`uvx`
- [ ] Both `stdio` and `HTTP/SSE` MCP transports from day one
- [ ] Docker image for containerized deploy, with docker-compose for local development
- [ ] Read-only safety mode by default — no destructive SQL ever issued
- [ ] Structured query logging for every executed Trino statement
- [ ] Configuration via environment variables and a config file (Trino URL, catalog, schema, auth)
- [ ] `$INSTRUCTION_FILE` (CLAUDE.md) describing coding rules, DoD, validation workflow, and safe-execution boundaries
- [ ] README with quickstart, tool reference, and Claude Code integration instructions

#### Trino Adapter

- [ ] HTTP REST client against Trino (no JDBC/JVM dependency)
- [ ] Auth: no-auth, basic auth, and JWT bearer tokens
- [ ] Support `EXPLAIN (FORMAT JSON)`, `EXPLAIN ANALYZE`, `EXPLAIN (TYPE DISTRIBUTED)`
- [ ] Query system tables (`system.runtime.*`, `system.metadata.*`)
- [ ] Query Iceberg metadata tables (`$snapshots`, `$files`, `$partitions`, `$manifests`)
- [ ] Cancel/timeout protection on every request

#### Dual Execution Modes

- [ ] **Live mode** — connects to a configured Trino cluster and runs read-only EXPLAIN/ANALYZE
- [ ] **Offline mode** — accepts pasted EXPLAIN JSON + optional stats as tool input; no cluster needed

#### Plan Parser

- [ ] Parse Trino `EXPLAIN (FORMAT JSON)` output into a typed stage/operator tree
- [ ] Extract per-operator CPU time, wall time, input/output rows, peak memory, exchange patterns
- [ ] Normalize differences between EXPLAIN and EXPLAIN ANALYZE shapes
- [ ] Handle Iceberg-specific operators (IcebergTableScan, split info, manifest reads)

#### Rule Engine (minimum 10 rules)

- [ ] Missing / stale table statistics
- [ ] Join order issues (large build side, missing stats-driven reorder)
- [ ] Partition pruning failure
- [ ] Predicate pushdown failure
- [ ] Dynamic filtering not applied
- [ ] Data skew across workers
- [ ] Excessive exchange volume / wrong distribution type
- [ ] Large scan with low selectivity (poor filter ratio)
- [ ] Iceberg file scan explosion (too many small files / high split count)
- [ ] Iceberg small-files / stale snapshot / compaction needed
- [ ] Each rule is deterministic, testable in isolation, and produces structured findings with severity + evidence

#### Recommendation Engine

- [ ] Convert rule findings into prioritized suggestions (severity × impact × confidence)
- [ ] Each suggestion includes: reasoning, expected impact, risk analysis, validation steps
- [ ] Structured output schema (JSON) usable by both humans and LLM clients

#### SQL Rewrite Engine (safe mode only)

- [ ] Projection pruning
- [ ] Filter pushdown-friendly rewrites
- [ ] `EXISTS` vs `JOIN` conversion where semantically equivalent
- [ ] Early aggregation / partial aggregation hints
- [ ] Semantic-preservation guarantees — never changes result set
- [ ] Returns both rewritten SQL and a human-readable diff + justification

#### Comparison Engine

- [ ] Compare before/after EXPLAIN ANALYZE runs
- [ ] Metrics: wall time, CPU time, scanned bytes, peak memory, stage distribution
- [ ] Structured comparison report with delta and % change

#### MCP Tools (all must have strict JSON schemas)

- [ ] `analyze_trino_query` — end-to-end analysis pipeline
- [ ] `get_explain_json` — fetch EXPLAIN (FORMAT JSON)
- [ ] `get_explain_analyze` — fetch EXPLAIN ANALYZE
- [ ] `get_table_statistics` — fetch table/column stats including Iceberg metadata
- [ ] `detect_optimization_issues` — run rule engine, return findings
- [ ] `suggest_optimizations` — return prioritized recommendations
- [ ] `rewrite_sql` — apply safe rewrites
- [ ] `compare_query_runs` — compare two EXPLAIN ANALYZE runs

#### MCP Resources

- [ ] `trino_optimization_playbook`
- [ ] `iceberg_best_practices`
- [ ] `trino_session_properties`
- [ ] `query_anti_patterns`

#### MCP Prompts

- [ ] `optimize_trino_query`
- [ ] `iceberg_query_review`
- [ ] `generate_optimization_report`

#### Iceberg Catalog Support

- [ ] Hive Metastore catalog
- [ ] REST catalog (Tabular / Polaris / Nessie / Lakekeeper)

#### Testing & Validation

- [ ] Unit tests for every rule with hand-crafted plan fixtures
- [ ] Integration tests against local docker-compose (Trino + Iceberg REST catalog + MinIO)
- [ ] Sample query suite covering each rule as a golden-path regression
- [ ] CI-friendly fast path that uses fixture JSON only (no Trino required)

### Out of Scope

<!-- Explicit boundaries. Includes reasoning to prevent re-adding. -->

- **Destructive or write SQL execution** — the server never issues `INSERT`, `UPDATE`, `DELETE`, `MERGE`, `DROP`, `CREATE`, `ALTER`, `TRUNCATE`, `CALL`, or DDL/DML of any kind. Read-only by construction; this is a safety guarantee.
- **JDBC driver support** — HTTP REST only for v1. JDBC pulls in JVM dependency and duplicates client code. Revisit only if users need Kerberos or complex auth.
- **Kerberos and mTLS authentication** — deferred; basic + JWT covers dev and most managed Trino (Starburst Galaxy, Ahana). Revisit per user request.
- **AWS Glue and Nessie (versioned) Iceberg catalogs** — deferred. Hive + REST covers the majority of deployments. Add when a user needs them.
- **Aggressive SQL rewrites that change semantics** — e.g., converting correlated subqueries to joins that alter null handling. Risk of silent correctness bugs is too high for an automated tool.
- **Cost-based optimizer replacement** — we advise and rewrite, we do not reimplement Trino's CBO.
- **Query editor / UI** — server only. Clients (Claude Code, Claude Desktop, custom) provide the interface.
- **Query execution beyond EXPLAIN / EXPLAIN ANALYZE / metadata reads** — no running of arbitrary user SELECTs for "preview" or result fetching.
- **Other query engines (Spark, Presto OSS, DuckDB, Snowflake)** — Trino + Iceberg is the focus. Code structure should make additional engines possible later but not this milestone.
- **Non-Iceberg table format rules** — Hive, Delta, Hudi rules are out of scope for v1. The rule engine architecture should allow them later.

## Context

- **Ecosystem**: Trino is the de facto query engine for open data lakes; Iceberg is the dominant open table format. Operators using Trino + Iceberg at scale frequently hit performance cliffs driven by missing stats, partition pruning failures, small-file explosions, and suboptimal join orders. Diagnosing these today requires deep expertise with EXPLAIN ANALYZE output.
- **MCP**: The Model Context Protocol is the emerging standard for giving LLM clients typed tools, resources, and prompts. Claude Code is a primary consumer. Building this as an MCP server (rather than a CLI) means the same capabilities are immediately available inside an agent loop.
- **Why now**: LLMs are credible at explaining plans and proposing rewrites, but they hallucinate without grounded evidence. This server provides the deterministic rule engine and real EXPLAIN output the LLM needs to be trustworthy.
- **Primary users**: Data engineers, analytics engineers, and platform teams already running Trino + Iceberg. Secondary: anyone using Claude Code who wants query-level optimization help without leaving their editor.
- **Design principle**: Deterministic rules first, LLM-assisted narrative second. The rule engine is the source of truth; prompts/resources shape how an LLM client presents the findings.

## Constraints

- **Tech stack**: Python 3.11+ with `uv` package manager, `pyproject.toml`, official `mcp` Python SDK, HTTP REST Trino client. No JVM dependency — Why: single-language simplicity, fast cold start, rich data tooling, and the strongest Python MCP ecosystem for this problem domain.
- **MCP transports**: Both `stdio` (for Claude Code / Desktop) and `HTTP/SSE` (for remote / hosted deployments) must work from day one — Why: user explicitly needs both local and remote workflows.
- **Trino client**: HTTP REST only — Why: avoids JVM, keeps the server pure Python, works across all Trino versions.
- **Auth scope**: Basic + JWT bearer only — Why: covers open-source Trino and managed offerings without pulling in Kerberos/cert complexity.
- **Safety**: Read-only by default, no destructive SQL allowed, all executed queries logged — Why: the server is designed to be handed to an LLM agent; any hole becomes an exploit.
- **Packaging**: `uv` + `pyproject.toml` + Docker image — Why: reproducible dev, easy `pip install`, container-friendly deploy.
- **Testing**: Local docker-compose with Trino + Iceberg (REST catalog via Nessie or Lakekeeper) + MinIO — Why: real integration coverage without external dependencies; CI can run it.
- **Determinism**: Rule engine output must be deterministic given identical input — Why: reproducibility and auditability are non-negotiable for a tool LLMs will invoke.
- **Iceberg focus**: Rules and rewrites specifically target Iceberg semantics and metadata — Why: that is the target data platform; other formats are deferred.

## Key Decisions

<!-- Decisions that constrain future work. Add throughout project lifecycle. -->

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Python 3.11+ as the implementation language | Official MCP Python SDK maturity, mature `trino-python-client`, strong data tooling, avoids JVM | — Pending |
| HTTP REST Trino client (no JDBC) | Keeps the server pure Python, no JVM, works across Trino versions | — Pending |
| Dual execution mode: live + offline | Live gives grounded EXPLAIN evidence; offline lets users/LLMs analyze pasted plans without a cluster | — Pending |
| Basic + JWT auth only for v1 | Covers OSS Trino and major managed offerings without Kerberos/cert complexity | — Pending |
| `uv` + `pyproject.toml` + Docker packaging | Reproducible dev, easy install via `pip`/`uvx`, containerized deploy path | — Pending |
| Both `stdio` and `HTTP/SSE` MCP transports | User needs local (Claude Code) and remote/hosted use cases from day one | — Pending |
| Hive + REST Iceberg catalogs first | Covers the dominant deployments; Glue/Nessie deferred | — Pending |
| Local docker-compose (Trino + Iceberg + MinIO) for integration tests | Real coverage in CI without external dependencies | — Pending |
| Deterministic rule engine as source of truth; LLM prompts shape narrative only | Prevents hallucination; rules are auditable and testable | — Pending |
| Safe-only SQL rewrites; never change semantics | Correctness is non-negotiable; an unsafe rewrite destroys trust | — Pending |
| Read-only by construction — no DDL/DML ever issued | Server will be invoked by LLM agents; blast radius must be bounded | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-04-11 after initialization*
