# Phase 2: Trino Adapter & Read-Only Gate - Context

**Gathered:** 2026-04-12
**Status:** Ready for planning

<domain>
## Phase Boundary

Deliver the full Trino adapter layer plus the read-only safety gate:

1. **`trino-python-client` HTTP REST client** wrapped in `asyncio.to_thread` with a
   bounded pool (default 4 workers). Supports no-auth, Basic, and JWT bearer auth.
2. **`SqlClassifier`** — a single `sqlglot`-AST-based allowlist gate at the adapter
   boundary. Every live-adapter method calls `assert_read_only(sql)` as its first
   line. Rejects writes, multi-statement, comment-wrapped DDL, Unicode escape
   tricks; recursively validates `EXPLAIN ANALYZE <inner>`.
3. **Hexagonal ports** — `PlanSource`, `StatsSource`, `CatalogSource` protocols
   and their live Trino adapters plus `OfflinePlanSource`. Both modes share the
   same ports so rules/recommenders/rewrites (future phases) stay mode-agnostic.
4. **Cancellation + timeout** — every query returns a `QueryHandle` that carries
   the Trino `query_id`. On timeout or client cancel, the adapter issues
   `DELETE /v1/query/{queryId}` and awaits confirmation via bounded exponential
   backoff. Partial-results-on-timeout UX is required (K-Decision #13).
5. **Capability probes** — on adapter init, detect Trino version (refuse < 429),
   Iceberg catalog type, and Iceberg metadata-table availability; store a
   capability matrix that downstream rules can gate on.
6. **Integration test harness** — ship `.testing/docker-compose.yml` (Trino 480
   + Lakekeeper + Postgres + MinIO), wire testcontainers-python into a new
   `integration` pytest mark, flip the CI integration job on for push-to-main.

**Covers:** TRN-01 through TRN-15.

**Not in this phase (belongs elsewhere):**
- Plan parsing (typed `EstimatedPlan` / `ExecutedPlan` from EXPLAIN JSON) — Phase 3
- Rule engine and any rules — Phase 4
- Recommendation engine — Phase 5
- Rewrite engine — Phase 6
- Comparison engine — Phase 7
- MCP tools that consume the adapter (`analyze_query`, `offline_analyze`, etc.) — Phase 8
- Productized docker-compose with production hardening — Phase 9 refines the
  `.testing/docker-compose.yml` we ship here
- Kerberos or certificate-based Trino auth — out of scope per PROJECT.md

</domain>

<decisions>
## Implementation Decisions

### Adapter Topology & Module Layout

- **D-01 (hexagonal layout lands now):** Create the ports + adapters structure
  referenced in ARCHITECTURE.md §7:
  ```
  src/mcp_trino_optimizer/
  ├── ports/
  │   ├── __init__.py
  │   ├── plan_source.py          # PlanSource Protocol
  │   ├── stats_source.py         # StatsSource Protocol
  │   └── catalog_source.py       # CatalogSource Protocol
  └── adapters/
      ├── __init__.py
      ├── trino/
      │   ├── __init__.py
      │   ├── client.py           # TrinoClient — sync wrapper + async facade
      │   ├── auth.py             # none / basic / JWT authentication
      │   ├── classifier.py       # SqlClassifier (AST-based allowlist)
      │   ├── handle.py           # QueryHandle dataclass + thread-safe query_id cell
      │   ├── pool.py             # bounded to_thread pool + semaphore
      │   ├── capabilities.py     # version probe + capability matrix
      │   ├── live_plan_source.py # implements PlanSource via TrinoClient
      │   ├── live_stats_source.py
      │   └── live_catalog_source.py
      └── offline/
          ├── __init__.py
          └── json_plan_source.py # implements PlanSource from raw JSON text
  ```
  All live adapter modules live under `adapters/trino/`; offline lives under
  `adapters/offline/`. Ports are pure Protocol definitions — no imports from
  adapters.

- **D-02 (single live TrinoClient, method-level classifier calls):** One
  `TrinoClient` class in `adapters/trino/client.py` owns the sync `trino.dbapi`
  cursor lifecycle. Every public method (`fetch_plan`, `fetch_analyze_plan`,
  `fetch_distributed_plan`, `fetch_stats`, `fetch_iceberg_metadata`,
  `cancel_query`, `probe_capabilities`, …) calls
  `self._classifier.assert_read_only(sql)` **as its first executable line**
  when it takes a `sql` argument. `cancel_query(query_id)` and
  `probe_capabilities()` are the only public methods exempt — no SQL input.

- **D-03 (architectural test is adapter-scoped):** The TRN-05 invariant test
  introspects the public method signatures of `TrinoClient` only. If a method
  takes a `sql: str` parameter, its AST must start with a call to
  `self._classifier.assert_read_only`. The test does NOT introspect
  `OfflinePlanSource` — offline mode is classifier-exempt (see D-15).

### Concurrency & Async Wrapper

- **D-04 (bounded `asyncio.to_thread` + semaphore):** A single
  `TrinoThreadPool` in `adapters/trino/pool.py` exposes
  `async def run(fn, *args, **kwargs) -> T`. Internally:
  - `ThreadPoolExecutor(max_workers=max_concurrent_queries, thread_name_prefix="trino-")`
  - `asyncio.Semaphore(max_concurrent_queries)` bounds concurrent submission
  - `asyncio.to_thread(...)` via `loop.run_in_executor(pool, ...)` binds the pool
  - Reject with backpressure (not queue) when the semaphore is full — surface as
    `TrinoPoolBusyError` so tool handlers can return a structured error.
  - `max_concurrent_queries` comes from Settings (default 4, K-Decision #15).

- **D-05 (event-loop-lag probe in tests):** An integration test asserts the
  asyncio event loop is never blocked > 100ms while 4 concurrent `fetch_plan`
  calls run. Uses `loop.call_later` + `time.perf_counter` ticker pattern. Also
  `uvloop` is NOT used — stdio transport must stay on the default selector loop
  for MCP SDK compatibility.

### QueryHandle & Cancellation Protocol

- **D-06 (QueryHandle pattern):** Every adapter method that executes SQL
  against Trino returns — or yields through an async context manager — a
  `QueryHandle` dataclass:
  ```python
  @dataclass
  class QueryHandle:
      request_id: str           # bound via contextvars on creation
      query_id_cell: QueryIdCell  # thread-safe single-slot holder
      started_at: datetime
      wall_clock_deadline: datetime
      # methods: .query_id (blocking, bounded wait); .cancel() (idempotent)
  ```
  `QueryIdCell` is a small threading primitive: `set_once(query_id)` from the
  worker thread after Trino's first response, `wait_for(timeout)` from async
  land. This gives us reliable query-id capture the moment Trino returns it.

- **D-07 (cancel on timeout/tool-cancel is structural):** The TrinoClient uses
  an `async with QueryHandle(...)` pattern. The `__aexit__` path unconditionally
  calls `handle.cancel()` if the handle's `query_id` is set and the query hasn't
  completed. Cancellation is triggered by:
  1. `asyncio.CancelledError` propagating into the handle's context (MCP tool
     cancellation from the transport layer)
  2. Wall-clock deadline expiry (monitored by a background asyncio task)
  3. Explicit `handle.cancel()` call from the caller

- **D-08 (cancel is await-confirmed with bounded backoff):** `QueryHandle.cancel()`:
  1. Fires `DELETE /v1/query/{queryId}` via a separate httpx client (does NOT
     go through the sync trino-python-client)
  2. Polls `GET /v1/query/{queryId}/info` (or equivalent) at 100ms → 300ms → 900ms
     → 2700ms intervals (cap ~4s total wall-clock) until the query leaves the
     active set
  3. Logs `query_canceled` structured event with `{query_id, request_id,
     elapsed_ms, attempts}`
  4. On failure to confirm cancellation within the budget, logs
     `cancel_unconfirmed` (WARN level) with the same fields — does NOT raise
  5. Subsequent calls to `.cancel()` are idempotent no-ops.

- **D-09 (timeout source: settings + per-call override):**
  `MCPTO_TRINO_QUERY_TIMEOUT_SEC` Settings field (default **60s**, SecretStr no,
  bounded 1–1800). Every TrinoClient method accepts an optional
  `timeout: float | None = None` kwarg that overrides the default. Tool layer
  (Phase 8) will expose this bounded by the setting when calling adapter methods.

- **D-10 (timeout UX: partial results + structured note):** On wall-clock
  timeout — per K-Decision #13 — the adapter:
  1. Captures whatever statement output has been received so far (empty dict/list
     if nothing arrived)
  2. Calls `handle.cancel()` (see D-08)
  3. Wraps the payload in a `TimeoutResult` dataclass:
     ```python
     @dataclass
     class TimeoutResult(Generic[T]):
         partial: T
         timed_out: bool = True
         elapsed_ms: int
         query_id: str
         reason: Literal["wall_clock_deadline"] = "wall_clock_deadline"
     ```
  4. Returns `TimeoutResult[T]` instead of raising. Tool handlers (Phase 8) are
     responsible for rendering the partial + note. Adapter methods document
     their return type as `T | TimeoutResult[T]`.

### Authentication

- **D-11 (auth mode selector):** New Settings fields in Phase 2:
  - `MCPTO_TRINO_AUTH_MODE: Literal['none', 'basic', 'jwt']`, default `'none'`
  - `MCPTO_TRINO_USER: str | None`, default None (required if `auth_mode='basic'`)
  - `MCPTO_TRINO_PASSWORD: SecretStr | None`, default None (required if
    `auth_mode='basic'`)
  - `MCPTO_TRINO_JWT: SecretStr | None`, default None (required if
    `auth_mode='jwt'`)
  - `MCPTO_TRINO_HOST: str`, required (no default — fail fast if unset)
  - `MCPTO_TRINO_PORT: int`, default `8080`
  - `MCPTO_TRINO_CATALOG: str`, default `iceberg`
  - `MCPTO_TRINO_SCHEMA: str | None`, default None
  - `MCPTO_TRINO_VERIFY_SSL: bool`, default `True` (carried from Phase 1 deferred)
  - `MCPTO_TRINO_CA_BUNDLE: Path | None`, default None (carried from Phase 1 deferred)

  A `@model_validator(mode='after')` in Settings fails fast when the selected
  `auth_mode` is missing its required fields (e.g., `auth_mode='basic'` but
  `user` or `password` is None). Error surface matches Phase 1 D-08: one
  structured JSON line on stderr, non-zero exit, before any transport binds.

- **D-12 (JWT is per-call re-read from env):** `adapters/trino/auth.py`
  exposes `build_authentication(settings) -> trino.auth.Authentication | None`.
  For `auth_mode='jwt'`, returns a callable-backed authentication that re-reads
  `os.environ['MCPTO_TRINO_JWT']` on **every** invocation. No in-process caching.
  If the env var is updated (e.g., by a sidecar refresher), the next call picks
  up the fresh token. The JWT value is a `SecretStr` at the Settings layer and
  renders as `[REDACTED]` via Phase 1 D-09. The denylist already covers
  `authorization`, `bearer`, `token`, `credential.*`.

- **D-13 (401 retry-once policy):** On HTTP 401 from Trino during a Trino
  client call, the adapter:
  1. Re-reads the JWT (or Basic creds) via `build_authentication()`
  2. Retries the same request EXACTLY ONCE
  3. If the second attempt also 401s, raises `TrinoAuthError(query_id=...)`
     that propagates to the caller
  4. Emits a `trino_auth_retry` structured log event with
     `{request_id, query_id, attempt, auth_mode}` — **never the token value**

- **D-14 (mutually exclusive auth modes):** Phase 2 does not attempt fallback
  chains (e.g., "try JWT, fall back to Basic"). The selected `auth_mode` is
  authoritative. This matches PROJECT.md's PITFALLS-driven "config is explicit
  or it fails fast" posture.

### SqlClassifier

- **D-15 (classifier is live-adapter scoped):** `OfflinePlanSource` does NOT
  call the classifier. Its input is a pre-materialized EXPLAIN JSON — there is
  no SQL to classify and no network call to gate. This keeps the architectural
  test (D-03) targeted at the live client only and avoids dead code paths in
  offline mode. When Phase 8 ships an offline-analyze tool, the tool schema
  will NOT accept a `sql` parameter alongside the plan JSON in v1.

- **D-16 (classifier allowlist baseline):** The planner ships at least the
  following statement types on the allowlist, per TRN-04:
  - `SELECT` (and `WITH` / CTE wrapping a SELECT)
  - `EXPLAIN <inner>` where `<inner>` is recursively validated
  - `EXPLAIN ANALYZE <inner>` where `<inner>` is recursively validated
  - `SHOW CATALOGS`, `SHOW SCHEMAS`, `SHOW TABLES`, `SHOW COLUMNS`,
    `SHOW CREATE TABLE`, `SHOW CREATE SCHEMA`, `SHOW SESSION`
  - `DESCRIBE` / `DESC`
  - `USE` (catalog/schema switching — no side effects on Trino beyond session state)
  - `VALUES` (read-only literal rows, supports tests and probes)

  Rejects: `INSERT`, `UPDATE`, `DELETE`, `MERGE`, `CREATE`, `DROP`, `ALTER`,
  `TRUNCATE`, `CALL`, `GRANT`, `REVOKE`, `REFRESH`, any `EXECUTE` statement,
  `SET SESSION AUTHORIZATION`, multi-statement blocks (rejected via the
  sqlglot `parse(sql)` returning more than one statement), comment-wrapped DDL
  (`parse` strips comments before classification).

  Unicode/escape tricks: classifier only accepts the sqlglot-parsed AST root
  type — raw text inspection is forbidden. This is why `sqlparse` is not used
  (PROJECT.md constraint).

- **D-17 (classifier unit test corpus is locked in Phase 2):** A
  `tests/safety/test_sql_classifier.py` ships in Phase 2 with parameterized
  cases for every rejected statement type plus the Unicode-escape tricks
  (`SELECT\u002A1`, `/* DROP TABLE x */ SELECT 1`, backslash-unicode hidden
  `DELETE`), empty strings, whitespace-only, and the recursive
  `EXPLAIN ANALYZE INSERT INTO x VALUES (1)` case. Planner decides exact test
  fixture count; must cover every rejected keyword.

### Capability Matrix

- **D-18 (capability probe scope):** On first adapter use (lazy init, NOT at
  process start — K-Decision #8 "fail fast on invalid config" applies to
  settings, not to runtime Trino reachability), the adapter probes:
  1. `SELECT node_version FROM system.runtime.nodes LIMIT 1` → parse version,
     refuse if < 429 with structured `TrinoVersionUnsupported` error
  2. `SHOW CATALOGS` → detect which catalogs are present
  3. `SHOW SCHEMAS IN <iceberg_catalog>` → confirm iceberg catalog is reachable
  4. `SELECT * FROM system.metadata.table_properties LIMIT 0` → confirm the
     metadata catalog responds
  5. Attempt `SELECT * FROM "<catalog>"."information_schema"."tables" LIMIT 0`
     → confirms Iceberg metadata-table availability (probe will be refined
     against the real Iceberg REST catalog during integration tests)

- **D-19 (capability matrix shape):** A frozen dataclass stored on the client:
  ```python
  @dataclass(frozen=True)
  class CapabilityMatrix:
      trino_version: str              # "480"
      trino_version_major: int         # 480
      catalogs: frozenset[str]         # {"iceberg", "memory", ...}
      iceberg_catalog_name: str | None
      iceberg_metadata_tables_available: bool
      probed_at: datetime
      # Future fields appended; dataclass versioning via a field `version: int = 1`
  ```
  Rules that need a newer Trino (Phase 4+) gate on `matrix.trino_version_major >= X`
  and emit `rule_skipped: requires_trino >= X` findings instead of raising.

### Offline Mode

- **D-20 (`OfflinePlanSource` takes raw JSON text only):**
  ```python
  class OfflinePlanSource:
      def fetch(self, plan_json: str) -> ExplainPlan: ...
  ```
  - `plan_json` is a raw JSON string bounded by a `maxLength` (default
    1_000_000 bytes — distinct from the 100KB SQL cap). The bound lives in
    `safety/schema_lint.py` constants and is applied to any tool parameter
    typed as "plan JSON" via the Phase 8 schema-lint rules.
  - No filesystem path, no URI support, no generating-SQL parameter.
  - When Phase 8 ships `offline_analyze`, the tool wraps the raw plan JSON via
    `wrap_untrusted()` before any log emits the payload. Phase 2 does NOT ship
    any tool that exposes this port — the port + implementation ship here; the
    tool lands in Phase 8.

- **D-21 (live + offline share one ExplainPlan dataclass):** Phase 2 ships a
  minimum-viable `ExplainPlan` domain dataclass that both live and offline
  `PlanSource.fetch()` return. It wraps the raw JSON in a `plan_json: dict`
  field plus a few typed fields that Phase 3's parser will refine
  (`plan_type: Literal['estimated', 'executed', 'distributed']`,
  `source_trino_version: str | None`). Phase 3 replaces the typed surface with
  the full `EstimatedPlan` / `ExecutedPlan` hierarchy — Phase 2's minimal shape
  is a placeholder that Phase 3 inherits from or replaces outright.

### Integration Test Harness

- **D-22 (testcontainers + minimal Iceberg stack):** Phase 2 ships
  `.testing/docker-compose.yml` with:
  - `trinodb/trino:480` (pinned by tag + digest)
  - `quay.io/lakekeeper/catalog:latest-main` (pinned by digest)
  - `postgres:16-alpine` (Lakekeeper metadata)
  - `minio/minio:latest` (pinned by digest, single-node)
  - `minio/mc:latest` init job to create the bucket
  Plus a `trino/etc/catalog/iceberg.properties` that points Trino at Lakekeeper.
  `testcontainers-python`'s `DockerCompose` wrapper drives lifecycle from
  `tests/integration/conftest.py`. Session-scoped fixture; warm up on first use.

- **D-23 (integration mark + CI wiring):** Tests that touch the real stack are
  marked `@pytest.mark.integration`. The Phase 1 `unit-smoke` job keeps its
  `pytest -m "not integration"` filter unchanged. The Phase 1 `integration`
  job stub (which has `if: false`) flips to run on push-to-main only:
  ```yaml
  if: github.event_name == 'push' && github.ref == 'refs/heads/main'
  ```
  ubuntu-latest only (testcontainers needs Docker daemon). macOS/Windows
  matrix cells continue skipping. Developers run `pytest -m integration`
  locally when modifying adapter code. Planner may also add a nightly
  `schedule: cron` trigger — acceptable, not required.

- **D-24 (integration test coverage targets):** Phase 2's integration suite
  must cover at minimum:
  1. `fetch_plan` / `fetch_analyze_plan` / `fetch_distributed_plan` against a
     simple `SELECT 1` and a real Iceberg table (`CREATE TABLE` via Trino
     during test setup; classifier must let `CREATE TABLE` through as a
     fixture-only backdoor — see D-25).
  2. Cancellation via `QueryHandle.cancel()` during an intentionally slow
     query; verify `query_id` left `system.runtime.queries`.
  3. Wall-clock timeout → `TimeoutResult` shape.
  4. JWT + Basic auth (bring up a second Trino container with Basic enabled,
     OR configure Basic on the main container — planner's choice).
  5. `capability_matrix` probe against Trino 480 — assert version detection
     and Iceberg-catalog presence.
  6. `system.runtime.*` / `system.metadata.*` / Iceberg metadata tables
     (`$snapshots`, `$files`, `$manifests`, `$partitions`, `$history`, `$refs`)
     read paths.

- **D-25 (fixture setup bypass for DDL):** Integration tests need to
  `CREATE TABLE` / `INSERT` data to seed fixtures. These are done via a
  **separate** helper in `tests/integration/fixtures.py` that calls the raw
  `trino-python-client` cursor directly — **NOT** through `TrinoClient`.
  This keeps the classifier invariant intact: the production adapter still
  never executes DDL. The helper is test-only, lives outside
  `src/mcp_trino_optimizer/`, and has a comment citing this decision.

### Logging, Errors, and Observability

- **D-26 (structured error taxonomy):** New exceptions in
  `adapters/trino/errors.py`:
  - `TrinoAdapterError(Exception)` — root
  - `TrinoAuthError` — 401 after retry
  - `TrinoVersionUnsupported` — version < 429
  - `TrinoPoolBusyError` — semaphore full (backpressure surface)
  - `TrinoTimeoutError` — wall-clock deadline hit (raised ONLY if timeout
     happens before any partial results; normal timeout returns `TimeoutResult`)
  - `TrinoClassifierRejected` — SqlClassifier rejected the statement
  - `TrinoConnectionError` — network-level failure; retryable per tool
  Each exception's `__init__` takes `request_id`, `query_id` (if known), and a
  user-facing message. All fields render via structlog without re-binding.

- **D-27 (trino-side request context propagation):** Every HTTP request to
  Trino sets these headers (PITFALLS 18):
  - `X-Trino-Source: mcp-trino-optimizer/{package_version}`
  - `X-Trino-Client-Tags: mcp_request_id={request_id}`
  - `X-Trino-Client-Info: git_sha={git_sha}`
  This lets Trino cluster admins correlate slow queries back to MCP requests
  via `system.runtime.queries.client_tags`.

- **D-28 (query log entry per TRN-11):** After every executed Trino statement,
  emit a `trino_query_executed` structured log event with:
  `{event, request_id, query_id, statement_hash (SHA-256 of the SQL string),
  duration_ms, result_row_count, result_byte_count, trino_state, auth_mode}`.
  The raw SQL is NEVER logged — only the hash. The caller identity field
  (`mcp_client_name`) is populated from the MCP `clientInfo` when available,
  NULL otherwise.

### Claude's Discretion

The planner may make concrete choices on the following without re-asking:
- Exact signature of the `QueryHandle` context manager (sync vs async context
  manager, generator-based vs class-based) — must honor D-06 through D-08.
- Whether `DELETE /v1/query/{queryId}` goes through the same `httpx.Client`
  used for auth or a dedicated session — must honor D-08 and not go through
  the sync trino-python-client.
- Exact shape of the `ExplainPlan` placeholder dataclass (D-21) — Phase 3
  will replace or inherit from it anyway.
- Exact set of integration-test fixtures seeded in D-24 — minimum coverage
  listed is a floor, not a ceiling.
- Lakekeeper + MinIO compose file details (env vars, wait conditions,
  healthchecks) — planner chooses whatever produces a reliable session-scoped
  fixture in testcontainers-python.
- The `TrinoPoolBusyError` backpressure surface — whether it's a top-level
  exception or a structured `RejectedResult` dataclass like `TimeoutResult`.
  Planner picks the cleanest API.
- Pre-commit hook additions for Phase 2 (if any) — must not weaken Phase 1's
  hooks.
- Whether the Phase 2 pre-commit config also greps for `subprocess.*trino`
  shell-outs or other anti-patterns (PITFALLS 22 / 25).
- Schema-lint additions: `plan_json` max_length constant (default 1_000_000),
  any new identifier `pattern` regexes needed for Trino catalog/schema/table
  names. Constants live in `safety/schema_lint.py`.
- How the integration test's `TrinoThreadPool` lag probe is implemented
  (`loop.call_later` ticker vs explicit monotonic clock thread).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents (researcher, planner, executor, checker) MUST read these before acting.**

### Project Truth
- `CLAUDE.md` — project instructions, tech stack (load-bearing, contains prescriptive version pins including `trino>=0.337.0`, `sqlglot>=30.4.2`, `testcontainers[trino,minio]>=4.14.2`)
- `.planning/PROJECT.md` — vision, core value, HTTP REST only / no JVM constraint, safety posture
- `.planning/REQUIREMENTS.md` §TRN-01..TRN-15 — the 15 requirements this phase must deliver
- `.planning/ROADMAP.md` — Phase 2 section (Success Criteria 1–5 are the verification spine)
- `.planning/STATE.md` — Key Decisions 1–16 (non-negotiable); especially #5 (ports), #6 (classifier), #7 (both transports), #12 (Trino ≥ 429), #13 (partial + cancel), #15 (max 4 concurrent)

### Prior Phase Context
- `.planning/phases/01-skeleton-safety-foundation/01-CONTEXT.md` — Phase 1 decisions D-01..D-15; D-03 explicitly defers ports to Phase 2; D-09 redaction denylist (extended, not replaced); D-11 schema_lint (extended); D-12 stdout discipline (unchanged); D-14 CI matrix (Phase 2 flips the integration job)

### Research Corpus (load-bearing)
- `.planning/research/SUMMARY.md` §4.2 — Trino adapter stack, JWT per-request semantics, testcontainers approach
- `.planning/research/SUMMARY.md` §6.2 — Phase 2 safety spine: AST-based SQL gate, cancel propagation, thread-pool discipline
- `.planning/research/SUMMARY.md` §9 — Open research questions; specifically "Trino cancellation semantics via trino-python-client" is the research unknown Phase 2 research must resolve
- `.planning/research/STACK.md` — version pins (`trino>=0.337.0`, `sqlglot>=30.4.2`, `testcontainers[trino,minio]>=4.14.2`), alternatives rejected, "What NOT to Use" (no JDBC, no PyHive, no sqlparse for classification)
- `.planning/research/ARCHITECTURE.md` §7-§10 — hexagonal layout, SqlClassifier placement at adapter boundary, `PlanSource`/`StatsSource`/`CatalogSource` protocol shape
- `.planning/research/PITFALLS.md` §9 — read-only invariant via AST-based gate
- `.planning/research/PITFALLS.md` §11 — sync Trino client in async handler trap + bounded threadpool mitigation
- `.planning/research/PITFALLS.md` §18 — structured logging spine + `X-Trino-Source` / `X-Trino-Client-Tags` propagation
- `.planning/research/PITFALLS.md` §22 — cancellation semantics (DELETE + await confirmation)
- `.planning/research/PITFALLS.md` §24 — max_concurrent_queries semaphore
- `.planning/research/PITFALLS.md` §25 — test isolation from production classifier
- `.planning/research/FEATURES.md` — Phase 8 will add `analyze_query`, `analyze_running_query`, `offline_analyze` tools that consume this adapter; Phase 2 only ships the adapter

### External Specs Touched by Phase 2
- [trino-python-client docs](https://trino.io/docs/current/client/python.html) — DBAPI cursor lifecycle, `JWTAuthentication`, `BasicAuthentication`
- [Trino REST API — Statement Resource](https://trino.io/docs/current/develop/client-protocol.html) — `POST /v1/statement`, `nextUri` polling, `DELETE /v1/query/{queryId}`, `GET /v1/query/{queryId}/info`
- [Trino 480 — system.runtime.queries](https://trino.io/docs/current/connector/system.html#runtime-queries-table) — state field semantics for cancel confirmation
- [sqlglot Trino dialect docs](https://sqlglot.com/sqlglot/dialects/trino.html) — statement types, parser AST nodes
- [testcontainers-python Trino module](https://testcontainers.com/modules/trino/) — container lifecycle, wait strategies
- [testcontainers-python DockerCompose wrapper](https://testcontainers-python.readthedocs.io/en/latest/core/README.html#docker-compose-support) — compose lifecycle from pytest
- [Lakekeeper getting-started compose](https://docs.lakekeeper.io/getting-started/) — Trino + Lakekeeper + MinIO + Postgres integration
- [Iceberg metadata tables](https://iceberg.apache.org/docs/latest/spark-queries/#metadata-tables) — `$snapshots`, `$files`, `$manifests`, `$partitions`, `$history`, `$refs` spec

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets (from Phase 1)
- **`src/mcp_trino_optimizer/settings.py`** — existing `Settings(BaseSettings)` with
  `env_prefix="MCPTO_"`, `extra='forbid'`, `model_validator(mode='after')`. Phase 2
  adds `trino_*` fields here; validator logic for auth-mode fail-fast lands in
  the same class. `load_settings_or_die()` is already wired.
- **`src/mcp_trino_optimizer/logging_setup.py`** — structlog pipeline already
  redacts `authorization`, `bearer`, `token`, `credential.*` (D-09). Phase 2
  does NOT extend the denylist — existing coverage is sufficient for Trino
  auth headers. The `merge_contextvars` processor handles `request_id` and
  `tool_name`; Phase 2 adds `query_id` via the same mechanism inside QueryHandle.
- **`src/mcp_trino_optimizer/_context.py`** — `new_request_id()` contextvar
  helper. Phase 2 also binds `trino_query_id` into contextvars inside the
  QueryHandle lifecycle so every log line during a Trino call carries it.
- **`src/mcp_trino_optimizer/safety/envelope.py`** — `wrap_untrusted()` exists
  and is tested. Phase 2's `OfflinePlanSource` does NOT yet call it (the plan
  JSON is structured, not free-form text) — but Phase 8's future
  `offline_analyze` tool will wrap the plan summary before echoing.
- **`src/mcp_trino_optimizer/safety/schema_lint.py`** — `MAX_STRING_LEN=100_000`,
  `MAX_PROSE_LEN=4_096`, `MAX_ARRAY_LEN=1_000`. Phase 2 adds a new constant
  `MAX_PLAN_JSON_LEN = 1_000_000` for the offline plan ingress.
- **`src/mcp_trino_optimizer/tools/_middleware.py`** — `tool_envelope()` decorator
  emits `tool_invoked` log line with contextvars-bound `request_id`. Phase 2
  adapter methods are NOT tools themselves — but any future Phase 8 tool
  wrapping these adapter methods will inherit this middleware for free.

### Established Patterns
- **Settings fail-fast with structured stderr error** (Phase 1 D-08) — new
  Phase 2 auth_mode validator matches this pattern exactly.
- **Module-level BaseModel definitions** — Python 3.12+ PEP 563 + FastMCP
  eval_str requires all Pydantic models used in tool signatures to live at
  module scope, not inside functions (Phase 1 UAT issue). Phase 2 must follow
  the same convention for any Settings/adapter DTOs used downstream.
- **pytest conftest auto-configures structlog per test** — `tests/conftest.py`
  has `_configure_structlog_for_tests` autouse fixture. Phase 2 integration
  tests inherit this; no new logging plumbing needed.
- **Commit conventions** — `feat(02): ...` for code, `docs(02): ...` for docs,
  `test(02): ...` for test-only commits. Phase 2 commits use `02`.

### Integration Points
- **`pyproject.toml`** — Phase 2 adds: `trino>=0.337.0`, `sqlglot>=30.4.2`,
  `httpx>=0.28.1` (already indirectly via FastMCP; verify), `anyio>=4.4`
  (already in), `testcontainers[trino,minio]>=4.14.2` (dev-only), `tenacity>=9.0`
  (for cancel confirmation backoff — planner may skip if simple `anyio.sleep`
  loop suffices).
- **`.github/workflows/ci.yml`** — flip the `if: false` on the `integration`
  job to `if: github.event_name == 'push' && github.ref == 'refs/heads/main'`
  (D-23). Add a step that runs `docker compose -f .testing/docker-compose.yml up -d`
  (or delegates to testcontainers), then `uv run pytest -m integration`.
- **`.env.example`** — extend with the new `MCPTO_TRINO_*` variables, all
  commented out by default. The existing comments-placeholder section from
  Phase 1 gets replaced with actual documented settings.
- **`CONTRIBUTING.md`** — Phase 1 shipped this file with four top-level
  sections including "Safe-execution boundaries". Phase 2 populates the Trino
  classifier invariants under that section, and extends Coding Rules with:
  "No raw trino-python-client access from any module outside `adapters/trino/`
  or `tests/integration/fixtures.py`."
- **`tests/conftest.py`** — Phase 2 extends with integration-specific fixtures
  (testcontainers session fixture, seed helpers). Must NOT change the existing
  `_configure_structlog_for_tests` autouse.

</code_context>

<specifics>
## Specific Ideas

- **Classifier invariant is the spine.** TRN-05's architectural test is the
  non-negotiable regression guard. Planner must write this test FIRST (TDD
  order) so the Trino client implementation naturally conforms. Any refactor
  that moves the classifier call out of the first line fails the test.
- **Cancellation is await-confirmed per D-08.** "Fire and forget" is explicitly
  rejected. Success Criterion 3 says "no query remains in system.runtime.queries
  after the cancel" — we verify this in the integration test via a follow-up
  query against `system.runtime.queries`.
- **Partial-results UX is structural, not per-tool opt-in.** Every adapter
  method has return type `T | TimeoutResult[T]` (D-10). This is enforced by
  mypy strict. Phase 8 tool handlers unwrap `TimeoutResult` uniformly.
- **JWT is re-read on every call, no caching.** The env-var-per-call pattern
  (D-12) is the user's explicit preference over file-watchers and callable
  hooks. External refresh machinery (sidecar, wrapper process) is the caller's
  responsibility.
- **The integration test harness is shipped now, refined later.** Phase 9
  productizes the compose file for human consumption; Phase 2's version is
  test-harness-shaped (session-scoped, fast teardown). Planner should leave
  comments in `.testing/docker-compose.yml` pointing at Phase 9's eventual
  home for each service.
- **No test runs the classifier AGAINST production data.** The integration
  fixture bypass (D-25) uses raw trino-python-client for seeding, outside the
  `src/` tree, documented as a test-only backdoor.
- **OfflinePlanSource does NOT wrap with `wrap_untrusted()` in Phase 2.** That's
  a Phase 8 tool-layer concern. Phase 2's offline source just parses and
  returns the typed plan; it never emits the raw JSON to a log or response.
- **The `trino_query_id` contextvar is bound from INSIDE the QueryHandle.**
  This means any log line emitted during a Trino call — from adapter code, from
  deeper utilities, from structlog processors — automatically carries the
  query_id. No manual binding at call sites.

</specifics>

<deferred>
## Deferred Ideas

- **Prepared statements + parameter binding** (TRN-03 does not require them; Phase 2
  uses plain SQL strings for EXPLAIN/SELECT targets). Parameterized execution
  lands in Phase 8 or later if a tool needs it.
- **Connection pooling beyond the thread pool** — the `trino-python-client`
  establishes a new HTTP connection per statement via httpx. Phase 2 does not
  introduce a persistent connection pool. Revisit if profiling shows
  connection-setup latency dominates.
- **Kerberos / client-certificate auth** — out of scope per PROJECT.md. Not in
  Phase 2, not in any planned phase.
- **Trino catalog-specific auth overrides** (e.g., per-catalog credentials) —
  out of scope for v1. One auth mode per process.
- **Automatic JWT refresh via OIDC/JWKS fetch** — explicitly rejected in D-12.
  If needed, a user can run an external sidecar that writes to the env var or
  re-exec the process. Plugin callable hooks (rejected in this discussion) may
  come back in v2 if demand materializes.
- **Prometheus / OpenTelemetry metrics export** — Phase 2 ships structured log
  events (D-28). Metrics export (histograms, counters) deferred; logs can be
  scraped via Loki/Datadog for the same insights.
- **Query plan caching** — Phase 2 does NOT cache EXPLAIN results. Phase 4
  (rule engine) may introduce a bounded cache keyed on
  `(sql_hash, trino_query_id_of_last_run, iceberg_snapshot_id)` per PITFALLS 21.
- **Rate limiting / per-user quotas** — semaphore-bounded concurrency only
  (D-04). Per-client quotas are a future phase if needed.
- **Streaming result consumption** — Phase 2 materializes the full statement
  response before returning. Streaming support (`AsyncIterator[Row]`) is not
  needed for EXPLAIN-centric workflows and can come later if a Phase 8 tool
  needs it.
- **Retries beyond the single 401 retry** (D-13) — no retry on 5xx, no retry
  on connection errors. Tenacity may be used for the D-08 cancel confirmation
  backoff, but regular query execution is retry-free.
- **Productized docker-compose with full hardening** — Phase 9. Phase 2's
  compose file is intentionally test-shaped (minimal volumes, fast teardown,
  session-scoped).
- **Prompt-injection adversarial corpus for MCP tool inputs** — Phase 9.
- **SqlClassifier allowlist for `CREATE TABLE AS SELECT` / `INSERT INTO SELECT` in
  offline-only mode** — rejected. If a future phase wants to analyze these,
  they go through a separate port, not the live adapter.

</deferred>

---

*Phase: 02-trino-adapter-read-only-gate*
*Context gathered: 2026-04-12 via /gsd-discuss-phase*
