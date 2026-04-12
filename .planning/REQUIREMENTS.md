# Requirements: mcp-trino-optimizer

**Defined:** 2026-04-11
**Core Value:** Turn opaque Trino query performance problems into actionable, evidence-backed optimization reports that a user (or an LLM agent) can trust and apply safely.

**Source documents:**

- `.planning/PROJECT.md` (project context)
- `.planning/research/SUMMARY.md` (synthesized research; canonical for categorization)
- `.planning/research/STACK.md`, `FEATURES.md`, `ARCHITECTURE.md`, `PITFALLS.md` (depth)

**Note:** Wherever PROJECT.md originally said "HTTP/SSE", the requirement is Streamable HTTP — legacy SSE was deprecated in MCP spec revision 2025-03-26. Intent (local + remote transport from day one) is preserved.

## v1 Requirements

Requirements for the initial v1 release. Each maps to exactly one roadmap phase. Every v1 requirement is testable, user-centric, and atomic.

### Platform (PLAT) — Skeleton, Safety Foundation, Packaging

- [x] **PLAT-01**: Developer can install the server via `uv tool install mcp-trino-optimizer`, `uvx mcp-trino-optimizer`, and `pip install mcp-trino-optimizer` on macOS, Linux, and Windows
- [x] **PLAT-02**: Developer can start the server on the `stdio` transport (default) and have Claude Code discover and connect to it via a documented `mcpServers` config
- [x] **PLAT-03**: Developer can start the server on the Streamable HTTP transport (`/mcp` endpoint) bound to `127.0.0.1` by default with a static bearer token
- [x] **PLAT-04**: Developer can run the server from the published Docker image (`python:3.12-slim-bookworm` base) with stdio by default and Streamable HTTP via a flag
- [x] **PLAT-05**: Every log line is written to stderr only, never stdout, so the stdio JSON-RPC channel is never corrupted (enforced by startup guard + CI test that asserts stdout contains only valid JSON-RPC after `initialize`)
- [x] **PLAT-06**: Every log line is structured JSON (via `structlog`) with `request_id`, `tool_name`, `git_sha`, `package_version`, and ISO8601 UTC timestamp
- [x] **PLAT-07**: Any dict containing `Authorization`, `X-Trino-Extra-Credentials`, `credential.*`, or configured secret keys is hard-redacted to `[REDACTED]` before being logged (unit-tested)
- [x] **PLAT-08**: Developer can configure the server via environment variables, a config file, and per-tool-call overrides (env > file > default) using `pydantic-settings`, with secrets held as `SecretStr`
- [x] **PLAT-09**: The server exposes an `mcp_selftest` tool that returns server version, transport, enabled capabilities, and a round-trip payload echo — usable as a protocol health probe from Claude Code
- [x] **PLAT-10**: Every MCP tool has a strict JSON Schema: `additionalProperties: false`, bounded string `maxLength` (SQL ≤ 100KB), identifier `pattern`, bounded arrays
- [x] **PLAT-11**: Every tool output that contains a user-origin string (SQL, pasted EXPLAIN, Trino error message) wraps that string in an `untrusted_content` envelope (`{ "source": "untrusted", "content": "..." }`) so LLM callers cannot be indirectly prompt-injected via tool results
- [x] **PLAT-12**: README includes copy-pasteable Claude Code `mcpServers` JSON for each install path and a "CLAUDE.md" defining coding rules, DoD, validation workflow, and safe-execution boundaries
- [x] **PLAT-13**: The CI install-matrix verifies successful install and `initialize` round-trip on Python 3.11, 3.12, 3.13 × macOS, Linux, Windows

### Trino Adapter (TRN) — HTTP REST, Auth, Safety Gate, Dual Mode

- [x] **TRN-01**: The server talks to Trino via HTTP REST using `trino-python-client` (no JDBC, no JVM dependency)
- [x] **TRN-02**: Every Trino call runs through `asyncio.to_thread` with a bounded thread pool (default 4, configurable) so the MCP event loop never blocks
- [x] **TRN-03**: The server supports no-auth, Basic auth, and JWT bearer auth, with the JWT token read per-request (never cached in logs)
- [x] **TRN-04**: Every SQL statement sent to Trino passes through a single `SqlClassifier` gate (at the adapter boundary) that uses `sqlglot` AST inspection; any statement not on the allowlist of `SELECT` / `EXPLAIN` / `EXPLAIN ANALYZE` / `SHOW` / `DESCRIBE` / Iceberg metadata queries is rejected before any network call. Multi-statement is rejected. `EXPLAIN ANALYZE <inner>` recursively validates the inner statement.
- [x] **TRN-05**: The classifier invariant is enforced by an architectural unit test that asserts every public method of the Trino client calls `assert_read_only(sql)` as its first line
- [x] **TRN-06**: Every Trino request has a wall-clock budget; on timeout or cancel, the adapter sends `DELETE /v1/query/{queryId}` to Trino and awaits confirmation, leaving no orphaned query on the cluster
- [x] **TRN-07**: On adapter init, the server probes the Trino version (`SELECT node_version FROM system.runtime.nodes`) and builds a capability matrix; rules that require a newer Trino report "skipped — requires Trino ≥ Y" as a structured finding, never an exception
- [x] **TRN-08**: On adapter init, the server probes the Iceberg catalog type, Iceberg format version, and metadata-table availability; results are recorded in the capability matrix
- [x] **TRN-09**: The adapter can fetch `EXPLAIN (FORMAT JSON)`, `EXPLAIN ANALYZE (FORMAT JSON)`, and `EXPLAIN (TYPE DISTRIBUTED)` for a user-supplied query
- [x] **TRN-10**: The adapter can read from `system.runtime.*`, `system.metadata.*`, and Iceberg metadata tables (`$snapshots`, `$files`, `$manifests`, `$partitions`, `$history`, `$refs`) for a user-supplied table
- [x] **TRN-11**: Every executed statement is logged with `request_id`, statement hash, duration, caller identity, and Trino `X-Trino-Source` + `X-Trino-Client-Tags` propagation
- [x] **TRN-12**: The analysis pipeline supports **offline mode** — an `OfflinePlanSource` accepts pasted `EXPLAIN (FORMAT JSON)` text as tool input and produces the same typed plan used by live mode, with no network call
- [x] **TRN-13**: Live mode and offline mode share one pipeline via `PlanSource` / `StatsSource` / `CatalogSource` ports — adding a new mode does not touch rules, recommenders, or rewrites
- [x] **TRN-14**: Minimum supported Trino version is **429**; the server refuses to initialize against older clusters with a structured error
- [x] **TRN-15**: The max-concurrent-queries semaphore is enforced per MCP process (default 4)

### Plan Parser (PLN) — Typed Tolerant Tree

- [x] **PLN-01**: The parser produces two distinct typed plan classes: `EstimatedPlan` (from `EXPLAIN (FORMAT JSON)`) and `ExecutedPlan` (from `EXPLAIN ANALYZE`); rules declare which they support and the engine filters by availability
- [x] **PLN-02**: Every parsed node preserves a `raw: dict[str, Any]` bag alongside typed fields so unknown or renamed Trino-version fields survive without a parse error
- [x] **PLN-03**: The parser extracts per-operator CPU time, wall time, input/output rows, input/output bytes, peak memory, and exchange metadata
- [x] **PLN-04**: The parser recognizes Iceberg-specific operators (`IcebergTableScan`, split info, manifest reads) and exposes their split count, file count, and partition spec identifier
- [x] **PLN-05**: The parser normalizes plan shape before rules see it — collapses `ScanFilterProject` into `TableScan + filter + projection` and walks transparently through `Project` nodes when searching for scans
- [x] **PLN-06**: A multi-version fixture corpus from at least 3 Trino versions (Trino 429, a middle LTS, and 480+) is captured from the docker-compose stack; every fixture must parse without error and produces a syrupy snapshot that is gated in CI
- [x] **PLN-07**: When the parser encounters an unknown node type or schema drift, it records a structured `schema_drift_warning` in the plan result rather than raising

### Rule Engine (RUL) — Deterministic Core

- [x] **RUL-01**: Rules are registered via a plugin registry; each rule is a class inheriting a shared `Rule` base with a deterministic `check(plan, evidence)` method
- [x] **RUL-02**: Each rule declares its evidence requirement via an enum (`PLAN_ONLY`, `PLAN_WITH_METRICS`, `TABLE_STATS`, `ICEBERG_METADATA`); the engine prefetches the union of all required evidence once per analysis
- [x] **RUL-03**: Rules that require unavailable evidence (e.g., ICEBERG_METADATA in offline mode) are skipped with a structured `rule_skipped` finding, not an exception
- [x] **RUL-04**: A rule failure is isolated — one crashing rule never aborts the whole analysis; the engine reports `rule_error` and continues
- [x] **RUL-05**: Every rule produces `RuleFinding` objects with `rule_id`, `severity`, `confidence`, human message, and a machine-readable evidence payload referencing specific plan operator IDs
- [x] **RUL-06**: Each rule ships with three fixture classes: synthetic-minimum (pure unit), realistic-from-compose (captured from docker-compose), and negative-control (a plan that must NOT trigger)
- [x] **RUL-07**: **R1 — missing or stale table statistics**: detects tables with no stats, or estimates vs ANALYZE actuals divergent by > 5×, by cross-referencing `SHOW STATS`, Iceberg `$snapshots`/`$files`, and executed operator metrics
- [x] **RUL-08**: **R2 — partition pruning failure**: detects scans where `physicalInputRows` ≈ total table rows despite a partition predicate (the #1 real-world cliff), using actual-bytes comparison, not predicate text
- [x] **RUL-09**: **R3 — predicate pushdown failure**: detects function-wrapped column predicates (e.g., `DATE(ts) = X`) that prevent pushdown, including timezone and timestamp-cast patterns
- [x] **RUL-10**: **R4 — dynamic filtering not applied**: detects joins where dynamic filtering was eligible but the collected filter was not propagated to the probe side (the #2 real-world cliff)
- [x] **RUL-11**: **R5 — large build side / broadcast too big**: detects `BROADCAST` joins where the build side exceeds configured threshold, recommending `PARTITIONED` distribution
- [x] **RUL-12**: **R6 — join order inversion**: detects joins where the CBO-selected order leaves a very large probe side due to missing stats
- [x] **RUL-13**: **R7 — CPU / wall-time skew**: detects stages where p99/p50 worker metric ratio exceeds 5×
- [x] **RUL-14**: **R8 — excessive exchange volume**: detects exchanges where bytes shuffled exceed scanned bytes
- [x] **RUL-15**: **R9 — low-selectivity scan**: detects scans where selected bytes / scanned bytes < configured threshold (default 0.10)
- [x] **RUL-16**: **I1 — Iceberg small-files explosion**: detects tables with p50 file size < 16MB or split count > 10k on the scan
- [x] **RUL-17**: **I3 — Iceberg delete-file accumulation**: detects tables where position-delete + equality-delete file count exceeds thresholds, using the `$files`-cross-reference workaround for Trino issue #28910 (since `$partitions` does not expose delete metrics)
- [x] **RUL-18**: **I6 — stale snapshot accumulation**: detects tables with too many retained snapshots or snapshots older than the configured retention window
- [x] **RUL-19**: **I8 — partition transform mismatch**: detects predicates that don't align with the Iceberg partition transform (e.g., `ts = '2025-01-01'` on a `day(ts)` partitioned table) and feeds the Phase 6 rewrite engine
- [x] **RUL-20**: **D11 — cost-vs-actual divergence**: detects operators where CBO estimate vs `EXPLAIN ANALYZE` actuals diverge by > 5× (smoking gun for stale stats)
- [x] **RUL-21**: Rule thresholds are data-driven with sourced rationale (each threshold carries a citation and is overridable via config, not a magic number)

### Recommendation Engine (REC) — Scoring, Prioritization, Narrative

- [ ] **REC-01**: The recommender converts a set of `RuleFinding` objects into a prioritized list of `Recommendation` objects; priority = severity × impact × confidence
- [ ] **REC-02**: Each `Recommendation` includes: reasoning, expected impact, risk level, validation steps the user can run, and confidence level
- [ ] **REC-03**: Recommendation narrative is produced from audited templates keyed by `rule_id`; free-form user-origin text never flows through to recommendation body
- [ ] **REC-04**: When two rules attach to the same operator with conflicting recommendations, the higher-confidence one wins and the other is demoted to "considered but rejected" with explicit reasoning
- [ ] **REC-05**: When a rule's fix is a Trino session property, the recommendation includes the exact `SET SESSION` statement using the session-property name from the `trino_session_properties` resource (no hallucinated property names) (D2)
- [ ] **REC-06**: The recommender produces an **Iceberg table health summary** per scanned table: snapshot count, small-file ratio, delete-file ratio, partition spec evolution state, last compaction reference (D5)
- [ ] **REC-07**: The recommender produces an **operator-level bottleneck ranking** with a grounded natural-language narrative per top-N operator, referencing plan evidence (D8)

### Rewrite Engine (RWR) — Safe Transforms Only

- [ ] **RWR-01**: The rewrite engine uses `sqlglot` (Trino dialect) for parsing and regeneration; regex-based rewrites are forbidden
- [ ] **RWR-02**: Only whitelisted transforms are available. v1 ships with: (a) projection pruning (`SELECT *` → enumerated used columns), (b) function-wrapped predicate unwrapping (`DATE(ts) = X` → half-open timestamp range), (c) partition-transform-aligned predicate rewrite (feeds from rule I8, differentiator D1)
- [ ] **RWR-03**: Every rewrite declares its preconditions explicitly; a rewrite is refused if any precondition fails, with a structured reason
- [ ] **RWR-04**: Every rewrite output includes the original SQL, the rewritten SQL, a unified diff, a list of checked preconditions, a justification, and a "not-verified-equivalent" disclaimer when live validation is not run
- [ ] **RWR-05**: `dangerous_rewrites: false` is the default; anything touching `NOT IN` ↔ `NOT EXISTS`, `LEFT JOIN` predicate motion, correlated subquery unwrap, window frame mutation, `CASE` restructuring, `UNNEST`, UDFs, or `WITH RECURSIVE` is advisory-only (never emitted as a rewrite)
- [ ] **RWR-06**: When live mode is available, the engine runs a round-trip validation: `SELECT COUNT(*), SUM(HASH(...))` on both original and rewritten against sample data; any delta marks the rewrite "failed validation" regardless of what the transform logic says
- [ ] **RWR-07**: `EXISTS ↔ JOIN` transforms only run when join keys are provably `NOT NULL` from catalog introspection — and are still off by default in v1 unless the user flips `dangerous_rewrites: true`

### Comparison Engine (CMP) — Honest Before/After

- [ ] **CMP-01**: The comparison tool accepts two `EXPLAIN ANALYZE` runs (or two SQL statements + live Trino) and returns a structured `ComparisonReport`
- [ ] **CMP-02**: The primary metric is **CPU time**; wall time is reported but labeled "volatile — do not use for go/no-go"; other metrics are scanned bytes, peak memory, shuffle bytes, stage count, and output row count
- [ ] **CMP-03**: In live mode, the comparison runner executes **N=5 paired-alternation runs** (A, B, A, B, ...), discards the first run as warm-up, computes CPU-time deltas and median absolute deviation (MAD), and pins the Iceberg table snapshot so both runs see identical data
- [ ] **CMP-04**: The comparator refuses to compare across an Iceberg snapshot boundary (returns a structured `snapshot_boundary_error`)
- [ ] **CMP-05**: The comparator asserts that output row counts are identical between the two runs; any divergence is surfaced as a potential correctness bug, not a win
- [ ] **CMP-06**: The comparator emits a HIGH / MEDIUM / LOW confidence classification based on CPU-time delta vs MAD and reports it alongside raw numbers

### MCP Surface (MCP) — Tools, Resources, Prompts

- [ ] **MCP-01**: Tool **`analyze_trino_query`** — end-to-end pipeline: takes SQL (or pasted plan), runs plan fetch → rules → recommender → report. Supports long-running work via partial-results-on-timeout in v1 (job-pattern deferred to v1.1).
- [ ] **MCP-02**: Tool **`get_explain_json`** — returns raw `EXPLAIN (FORMAT JSON)` for a given query
- [ ] **MCP-03**: Tool **`get_explain_analyze`** — returns raw `EXPLAIN ANALYZE (FORMAT JSON)` for a given query, gated by a pre-flight CBO cost check that refuses execution if estimated `cpuCost` or `outputBytes` exceeds the configured budget
- [ ] **MCP-04**: Tool **`get_table_statistics`** — returns `SHOW STATS` + Iceberg metadata-table summary for a given table
- [ ] **MCP-05**: Tool **`detect_optimization_issues`** — runs the rule engine over a plan (live or offline) and returns structured `RuleFinding` objects
- [ ] **MCP-06**: Tool **`suggest_optimizations`** — runs the recommender over findings and returns prioritized `Recommendation` objects
- [ ] **MCP-07**: Tool **`rewrite_sql`** — runs the safe rewrite engine on a given SQL statement and returns whitelisted rewrites with diffs and preconditions
- [ ] **MCP-08**: Tool **`compare_query_runs`** — runs the comparison engine on two plans (or two SQLs in live mode) and returns a structured `ComparisonReport`
- [ ] **MCP-09**: Resource **`trino_optimization_playbook`** — curated markdown shipped in package data
- [ ] **MCP-10**: Resource **`iceberg_best_practices`** — curated markdown shipped in package data
- [ ] **MCP-11**: Resource **`trino_session_properties`** — curated list of Trino session properties with descriptions, defaults, valid ranges, Trino version gates; this is the single source of truth for property names in recommendations (prevents LLM hallucination)
- [ ] **MCP-12**: Resource **`query_anti_patterns`** — curated markdown shipped in package data
- [ ] **MCP-13**: Prompt **`optimize_trino_query`** — jinja template that takes a query and asks for optimization analysis via the server's tools
- [ ] **MCP-14**: Prompt **`iceberg_query_review`** — jinja template that reviews a query through the Iceberg lens
- [ ] **MCP-15**: Prompt **`generate_optimization_report`** — jinja template that produces a formatted final report from tool results
- [ ] **MCP-16**: Tool handlers are thin (~30 lines); all business logic lives in the service layer, so stdio and Streamable HTTP share the same `FastMCP` app object with zero transport-aware code in tools
- [ ] **MCP-17**: Tool descriptions are static and loaded at server startup (no dynamic strings from user input in tool descriptions — prevents tool-description prompt injection)
- [ ] **MCP-18**: The resource and prompt content is loaded via `importlib.resources` from the installed package (no filesystem assumptions)

### Testing & Integration (TST) — Docker Compose, Fixtures, CI

- [ ] **TST-01**: A docker-compose stack (`Trino 480` + `Lakekeeper` Iceberg REST catalog + `PostgreSQL` + `MinIO`) boots with `docker compose up` and the server's integration tests pass against it
- [ ] **TST-02**: Integration tests use `testcontainers[trino,minio]` and the `DockerCompose` fixture class; they are gated behind `@pytest.mark.integration` and opt-in in CI
- [ ] **TST-03**: Every rule has unit tests driven by the three fixture classes (synthetic, realistic, negative-control) and every negative-control test is a regression guard against false positives
- [ ] **TST-04**: Snapshot tests via `syrupy` cover the full `AnalysisReport` JSON output for a canonical set of queries
- [ ] **TST-05**: A stdio-cleanliness test boots the server, sends a JSON-RPC `initialize`, and asserts stdout contains only valid JSON-RPC frames (bytes between frames must be empty)
- [ ] **TST-06**: A prompt-injection adversarial test corpus is run against every tool and asserts that (a) the server never passes untrusted content outside a typed envelope and (b) the classifier gate rejects injected DDL/DML wrapped in comments, Unicode tricks, and multi-statement blocks
- [ ] **TST-07**: `.env.example` provides randomized MinIO credentials; compose binds services to `127.0.0.1` only; `gitleaks` runs in CI
- [ ] **TST-08**: The install-matrix CI builds and runs the basic smoke test (stdio `initialize` + `mcp_selftest` round trip) on `{3.11, 3.12, 3.13} × {macOS, Linux, Windows}`

## v2 Requirements

Deferred beyond v1. Tracked but not in current roadmap. Promote to v1 only with explicit user decision and a roadmap update.

### Additional Differentiators

- **V2-D7**: `iceberg_query_review` "audit every touched table" prompt orchestrating multiple tools in one workflow
- **V2-D10**: Bloom filter / sort order / file-level stats advisory rules
- **V2-D14**: Partition spec evolution awareness in file-level analysis
- **V2-D15**: Dedicated manifest fragmentation rule (beyond the base manifest count check in I2)

### Additional Rewrites

- **V2-RWR-01**: Safe `DISTINCT` removal under provable uniqueness
- **V2-RWR-02**: Early / partial aggregation session-property hints emitted as an advisory-only rewrite
- **V2-RWR-03**: `EXISTS ↔ JOIN` enabled by default once schema introspection for `NOT NULL` is universally available across supported catalogs

### Long-Running Job Pattern

- **V2-JOB-01**: `start_analyze_job` / `poll_analyze_job` / `get_analyze_result` tools for analyses that exceed MCP client timeouts (v1 ships partial-results-on-timeout + cancel)

### Additional Iceberg Catalogs

- **V2-CAT-01**: AWS Glue catalog support
- **V2-CAT-02**: Nessie (versioned) catalog support with branch/tag awareness
- **V2-CAT-03**: Polaris catalog as a second integration-test profile

### Additional Auth

- **V2-AUTH-01**: Kerberos authentication
- **V2-AUTH-02**: mTLS / client certificate authentication

### Additional Resources

- **V2-RES-01**: `iceberg_metadata_tables_reference` resource
- **V2-RES-02**: `trino_explain_format_reference` resource

## Out of Scope

Explicitly excluded. Documented to prevent scope creep and to prevent someone asking "why didn't you include X?" three milestones in.

| Feature | Reason |
|---------|--------|
| Destructive SQL (INSERT/UPDATE/DELETE/MERGE/DROP/CREATE/ALTER/TRUNCATE/CALL, any DDL/DML) | Constitutional — read-only by construction is the safety contract the server makes with LLM callers |
| Unsafe semantic-changing rewrites (NOT IN↔NOT EXISTS, correlated subquery unwrap, LEFT JOIN predicate motion, window frame mutation, CASE restructuring) | Three-valued-logic / NULL / ordering correctness is non-negotiable; LLM trust collapses on a single silent wrong answer |
| JDBC driver support | HTTP REST is sufficient; JDBC pulls in JVM and duplicates the client surface. Revisit only if Kerberos/mTLS demand |
| Arbitrary `SELECT` execution for result preview | Out-of-scope by product intent; the server is an analyzer, not a query runner |
| Compaction / snapshot-expiration execution | We *recommend* `OPTIMIZE` and `expire_snapshots`; we never *run* them |
| Query editor / UI | Server only; Claude Code and other MCP clients provide the interface |
| Non-Iceberg table formats (Hive, Delta, Hudi) | Iceberg is the focus; the architecture allows format expansion later but not this milestone |
| Other query engines (Spark, Presto OSS, DuckDB, Snowflake) | Trino is the focus; architecture allows engine expansion later |
| CBO replacement | We advise and rewrite; we do not reimplement Trino's cost-based optimizer |
| Background scheduling / watch mode / cron-like features | Scope creep; users can drive scheduled analysis externally |
| Cross-session caching of user queries or plans | Privacy + safety; plans and SQL never persist beyond the current session |
| LLM-authored rewrites (free-form SQL generation by an LLM) | Defeats the purpose of deterministic rules; the LLM *narrates*, it does not *author* rewrites |
| Trino event-listener plugin | Server-side Java plugin is out of this project's Python scope |
| Generic "SQL advisor" framing (non-Trino-specific) | The value is in the depth of Trino+Iceberg specifics; breadth dilutes that |
| Kerberos / mTLS auth | Deferred to v2; Basic + JWT covers OSS + managed Trino |
| AWS Glue / Nessie / Polaris Iceberg catalogs as default | Deferred to v2; Hive Metastore + REST (Lakekeeper) cover the dominant deployments |
| Legacy MCP HTTP+SSE transport | Deprecated in MCP spec 2025-03-26; Streamable HTTP is the correct replacement and covers the same "local + remote from day one" intent |
| Mobile / Desktop app | Not applicable — this is a stdio/HTTP server |

## Traceability

Populated by the roadmapper on 2026-04-11. Every v1 REQ-ID maps to exactly one phase in `.planning/ROADMAP.md`.

| Requirement | Phase | Status |
|-------------|-------|--------|
| PLAT-01 | Phase 1 | Complete |
| PLAT-02 | Phase 1 | Complete |
| PLAT-03 | Phase 1 | Complete |
| PLAT-04 | Phase 1 | Complete |
| PLAT-05 | Phase 1 | Complete |
| PLAT-06 | Phase 1 | Complete |
| PLAT-07 | Phase 1 | Complete |
| PLAT-08 | Phase 1 | Complete |
| PLAT-09 | Phase 1 | Complete |
| PLAT-10 | Phase 1 | Complete |
| PLAT-11 | Phase 1 | Complete |
| PLAT-12 | Phase 1 | Complete |
| PLAT-13 | Phase 1 | Complete |
| TRN-01 | Phase 2 | Complete |
| TRN-02 | Phase 2 | Complete |
| TRN-03 | Phase 2 | Complete |
| TRN-04 | Phase 2 | Complete |
| TRN-05 | Phase 2 | Complete |
| TRN-06 | Phase 2 | Complete |
| TRN-07 | Phase 2 | Complete |
| TRN-08 | Phase 2 | Complete |
| TRN-09 | Phase 2 | Complete |
| TRN-10 | Phase 2 | Complete |
| TRN-11 | Phase 2 | Complete |
| TRN-12 | Phase 2 | Complete |
| TRN-13 | Phase 2 | Complete |
| TRN-14 | Phase 2 | Complete |
| TRN-15 | Phase 2 | Complete |
| PLN-01 | Phase 3 | Complete |
| PLN-02 | Phase 3 | Complete |
| PLN-03 | Phase 3 | Complete |
| PLN-04 | Phase 3 | Complete |
| PLN-05 | Phase 3 | Complete |
| PLN-06 | Phase 3 | Complete |
| PLN-07 | Phase 3 | Complete |
| RUL-01 | Phase 4 | Complete |
| RUL-02 | Phase 4 | Complete |
| RUL-03 | Phase 4 | Complete |
| RUL-04 | Phase 4 | Complete |
| RUL-05 | Phase 4 | Complete |
| RUL-06 | Phase 4 | Complete |
| RUL-07 | Phase 4 | Complete |
| RUL-08 | Phase 4 | Complete |
| RUL-09 | Phase 4 | Complete |
| RUL-10 | Phase 4 | Complete |
| RUL-11 | Phase 4 | Complete |
| RUL-12 | Phase 4 | Complete |
| RUL-13 | Phase 4 | Complete |
| RUL-14 | Phase 4 | Complete |
| RUL-15 | Phase 4 | Complete |
| RUL-16 | Phase 4 | Complete |
| RUL-17 | Phase 4 | Complete |
| RUL-18 | Phase 4 | Complete |
| RUL-19 | Phase 4 | Complete |
| RUL-20 | Phase 4 | Complete |
| RUL-21 | Phase 4 | Complete |
| REC-01 | Phase 5 | Pending |
| REC-02 | Phase 5 | Pending |
| REC-03 | Phase 5 | Pending |
| REC-04 | Phase 5 | Pending |
| REC-05 | Phase 5 | Pending |
| REC-06 | Phase 5 | Pending |
| REC-07 | Phase 5 | Pending |
| RWR-01 | Phase 6 | Pending |
| RWR-02 | Phase 6 | Pending |
| RWR-03 | Phase 6 | Pending |
| RWR-04 | Phase 6 | Pending |
| RWR-05 | Phase 6 | Pending |
| RWR-06 | Phase 6 | Pending |
| RWR-07 | Phase 6 | Pending |
| CMP-01 | Phase 7 | Pending |
| CMP-02 | Phase 7 | Pending |
| CMP-03 | Phase 7 | Pending |
| CMP-04 | Phase 7 | Pending |
| CMP-05 | Phase 7 | Pending |
| CMP-06 | Phase 7 | Pending |
| MCP-01 | Phase 8 | Pending |
| MCP-02 | Phase 8 | Pending |
| MCP-03 | Phase 8 | Pending |
| MCP-04 | Phase 8 | Pending |
| MCP-05 | Phase 8 | Pending |
| MCP-06 | Phase 8 | Pending |
| MCP-07 | Phase 8 | Pending |
| MCP-08 | Phase 8 | Pending |
| MCP-09 | Phase 8 | Pending |
| MCP-10 | Phase 8 | Pending |
| MCP-11 | Phase 8 | Pending |
| MCP-12 | Phase 8 | Pending |
| MCP-13 | Phase 8 | Pending |
| MCP-14 | Phase 8 | Pending |
| MCP-15 | Phase 8 | Pending |
| MCP-16 | Phase 8 | Pending |
| MCP-17 | Phase 8 | Pending |
| MCP-18 | Phase 8 | Pending |
| TST-01 | Phase 9 | Pending |
| TST-02 | Phase 9 | Pending |
| TST-03 | Phase 9 | Pending |
| TST-04 | Phase 9 | Pending |
| TST-05 | Phase 9 | Pending |
| TST-06 | Phase 9 | Pending |
| TST-07 | Phase 9 | Pending |
| TST-08 | Phase 9 | Pending |

**Coverage:**

- v1 requirements: 102 total (PLAT 13, TRN 15, PLN 7, RUL 21, REC 7, RWR 7, CMP 6, MCP 18, TST 8)
- Mapped to phases: 102
- Unmapped: 0 ✓

---
*Requirements defined: 2026-04-11*
*Last updated: 2026-04-12 — PLAT-01..13, TRN-01..15, PLN-01..07 marked complete (Phases 1–3 shipped)*
