---
phase: 02-trino-adapter-read-only-gate
plan: 03
type: execute
wave: 2
depends_on: ["02-01", "02-02"]
files_modified:
  - src/mcp_trino_optimizer/adapters/trino/handle.py
  - src/mcp_trino_optimizer/adapters/trino/pool.py
  - src/mcp_trino_optimizer/adapters/trino/client.py
  - src/mcp_trino_optimizer/_context.py
  - tests/adapters/test_pool.py
  - tests/adapters/test_query_logging.py
  - tests/adapters/test_trino_client_invariant.py
  - tests/adapters/test_auth_retry.py
autonomous: true
requirements:
  - TRN-01
  - TRN-02
  - TRN-05
  - TRN-06
  - TRN-11
  - TRN-15

must_haves:
  truths:
    - "Every public TrinoClient method with sql param calls assert_read_only(sql) as first line"
    - "All Trino calls go through asyncio.to_thread with bounded thread pool (default 4)"
    - "QueryHandle captures query_id from worker thread via QueryIdCell"
    - "Cancel sends DELETE /v1/query/{queryId} via httpx and awaits confirmation"
    - "Timeout returns TimeoutResult[T] instead of raising"
    - "Every executed statement is logged with request_id, statement hash, duration — never raw SQL"
    - "Semaphore rejects with TrinoPoolBusyError when full"
    - "On HTTP 401, TrinoClient retries once with refreshed auth; double-401 raises TrinoAuthError; trino_auth_retry log emitted"
  artifacts:
    - path: "src/mcp_trino_optimizer/adapters/trino/handle.py"
      provides: "QueryHandle + QueryIdCell + TimeoutResult"
      exports: ["QueryHandle", "QueryIdCell", "TimeoutResult"]
    - path: "src/mcp_trino_optimizer/adapters/trino/pool.py"
      provides: "TrinoThreadPool with bounded executor + semaphore"
      exports: ["TrinoThreadPool"]
    - path: "src/mcp_trino_optimizer/adapters/trino/client.py"
      provides: "TrinoClient — sync wrapper + async facade"
      exports: ["TrinoClient"]
    - path: "tests/adapters/test_trino_client_invariant.py"
      provides: "TRN-05 architectural test"
      min_lines: 30
  key_links:
    - from: "src/mcp_trino_optimizer/adapters/trino/client.py"
      to: "src/mcp_trino_optimizer/adapters/trino/classifier.py"
      via: "self._classifier.assert_read_only(sql) as first line of every sql-taking method"
      pattern: "assert_read_only"
    - from: "src/mcp_trino_optimizer/adapters/trino/client.py"
      to: "src/mcp_trino_optimizer/adapters/trino/pool.py"
      via: "self._pool.run(fn, *args) for all Trino calls"
      pattern: "_pool\\.run"
    - from: "src/mcp_trino_optimizer/adapters/trino/handle.py"
      to: "httpx"
      via: "httpx.AsyncClient for DELETE /v1/query/{queryId} cancel"
      pattern: "httpx\\.AsyncClient"
---

<objective>
Build the TrinoClient (sync wrapper + async facade), QueryHandle with confirmed cancellation, TrinoThreadPool with semaphore, and the TRN-05 architectural invariant test.

Purpose: This is the core adapter that all live data access flows through. The classifier-first invariant (TRN-05), bounded concurrency (TRN-02, TRN-15), confirmed cancellation (TRN-06), and statement logging (TRN-11) are all enforced here. The architectural test is the non-negotiable regression guard that prevents any refactor from bypassing the read-only gate.

Output: `handle.py`, `pool.py`, `client.py` under `adapters/trino/`, architectural invariant test, pool unit tests, query logging tests.
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

<interfaces>
<!-- From Plan 01 outputs -->

From src/mcp_trino_optimizer/adapters/trino/classifier.py:
```python
class SqlClassifier:
    def assert_read_only(self, sql: str) -> None: ...  # raises TrinoClassifierRejected
```

From src/mcp_trino_optimizer/adapters/trino/errors.py:
```python
class TrinoAdapterError(Exception): ...
class TrinoAuthError(TrinoAdapterError): ...
class TrinoVersionUnsupported(TrinoAdapterError): ...
class TrinoPoolBusyError(TrinoAdapterError): ...
class TrinoTimeoutError(TrinoAdapterError): ...
class TrinoClassifierRejected(TrinoAdapterError): ...
class TrinoConnectionError(TrinoAdapterError): ...
```

From src/mcp_trino_optimizer/adapters/trino/auth.py:
```python
def build_authentication(settings: Settings) -> Authentication | None: ...
class PerCallJWTAuthentication(Authentication): ...
```

From src/mcp_trino_optimizer/settings.py:
```python
class Settings(BaseSettings):
    trino_host: str | None
    trino_port: int = 8080
    trino_catalog: str = "iceberg"
    trino_schema: str | None
    trino_auth_mode: Literal["none", "basic", "jwt"]
    trino_query_timeout_sec: int = 60
    max_concurrent_queries: int = 4
    trino_verify_ssl: bool = True
    trino_ca_bundle: str | None
```

From src/mcp_trino_optimizer/ports/plan_source.py:
```python
class ExplainPlan:
    plan_json: dict[str, Any]
    plan_type: Literal["estimated", "executed", "distributed"]
    source_trino_version: str | None
    raw_text: str
```

From src/mcp_trino_optimizer/_context.py:
```python
def new_request_id() -> str: ...
def current_request_id() -> str: ...
```
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: QueryHandle + QueryIdCell + TimeoutResult + TrinoThreadPool</name>
  <files>
    src/mcp_trino_optimizer/adapters/trino/handle.py
    src/mcp_trino_optimizer/adapters/trino/pool.py
    src/mcp_trino_optimizer/_context.py
    tests/adapters/test_pool.py
  </files>
  <read_first>
    src/mcp_trino_optimizer/_context.py
    src/mcp_trino_optimizer/adapters/trino/errors.py
    src/mcp_trino_optimizer/settings.py
    .planning/phases/02-trino-adapter-read-only-gate/02-CONTEXT.md
    .planning/phases/02-trino-adapter-read-only-gate/02-RESEARCH.md
  </read_first>
  <action>
    **Create `handle.py`** at `src/mcp_trino_optimizer/adapters/trino/handle.py` per D-06, D-07, D-08, D-10:

    `QueryIdCell` class:
    - `__init__`: creates `threading.Event()` and `_value: str | None = None`
    - `set_once(query_id: str)`: sets value + event (idempotent — no-op if already set)
    - `wait_for(timeout: float) -> str | None`: waits on event, returns value
    - `value` property: returns current value (non-blocking)

    `TimeoutResult` generic dataclass per D-10:
    ```python
    @dataclass
    class TimeoutResult(Generic[T]):
        partial: T
        timed_out: bool = True
        elapsed_ms: int = 0
        query_id: str = ""
        reason: Literal["wall_clock_deadline"] = "wall_clock_deadline"
    ```

    `QueryHandle` dataclass per D-06:
    ```python
    @dataclass
    class QueryHandle:
        request_id: str
        query_id_cell: QueryIdCell = field(default_factory=QueryIdCell)
        started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
        wall_clock_deadline: datetime = field(default_factory=lambda: datetime.now(UTC))

        @property
        def query_id(self) -> str | None:
            return self.query_id_cell.value

        async def cancel(self, base_url: str, auth_headers: dict[str, str]) -> bool:
            """Send DELETE /v1/query/{queryId} and poll for confirmation per D-08."""
    ```

    Cancel implementation per D-08 and RESEARCH.md Pattern 4:
    1. If `query_id` is None, return False (nothing to cancel)
    2. Fire `DELETE /v1/query/{query_id}` via `httpx.AsyncClient`
    3. If 204: return True
    4. Poll `GET /v1/query/{query_id}` at intervals [0.1, 0.3, 0.9, 2.7] seconds (cap ~4s)
    5. If state in ("FINISHED", "FAILED") or 404: return True
    6. If budget exhausted: log `cancel_unconfirmed` at WARN level, return False
    7. Idempotent: track `_cancelled: bool` flag, subsequent calls are no-ops

    **Create `pool.py`** at `src/mcp_trino_optimizer/adapters/trino/pool.py` per D-04:
    ```python
    class TrinoThreadPool:
        def __init__(self, max_workers: int = 4) -> None:
            self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="trino-")
            self._semaphore = asyncio.Semaphore(max_workers)

        async def run(self, fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
            if self._semaphore.locked():
                # All slots busy — check if we can acquire immediately
                acquired = self._semaphore._value == 0  # noqa: SLF001
            acquired = self._semaphore.acquire_nowait()  # non-blocking
            # If acquire_nowait raises, raise TrinoPoolBusyError
            ...
    ```

    The pool rejects with `TrinoPoolBusyError` when the semaphore is full (backpressure, not queue). Use `semaphore.acquire()` with a short timeout (0.1s) and raise `TrinoPoolBusyError` if not acquired.

    **Extend `_context.py`** to add `trino_query_id` contextvar per the specifics section:
    ```python
    _trino_query_id: contextvars.ContextVar[str] = contextvars.ContextVar("trino_query_id", default="")

    def bind_trino_query_id(query_id: str) -> None:
        _trino_query_id.set(query_id)
        structlog.contextvars.bind_contextvars(trino_query_id=query_id)
    ```

    **Create `tests/adapters/test_pool.py`** with:
    - Test: TrinoThreadPool.run() executes a callable in a thread (returns result)
    - Test: TrinoThreadPool rejects when all slots are busy (raises TrinoPoolBusyError)
    - Test: TrinoThreadPool with max_workers=1 allows sequential execution
    - Test: QueryIdCell.set_once sets value and triggers event
    - Test: QueryIdCell.set_once is idempotent (second call is no-op)
    - Test: QueryIdCell.wait_for returns value after set_once from another thread
    - Test: TimeoutResult dataclass has correct fields and defaults
  </action>
  <verify>
    <automated>uv run pytest tests/adapters/test_pool.py -v -x</automated>
  </verify>
  <acceptance_criteria>
    - `src/mcp_trino_optimizer/adapters/trino/handle.py` contains `class QueryHandle`, `class QueryIdCell`, `class TimeoutResult`
    - `src/mcp_trino_optimizer/adapters/trino/handle.py` contains `httpx.AsyncClient` for cancel
    - `src/mcp_trino_optimizer/adapters/trino/pool.py` contains `class TrinoThreadPool` with `ThreadPoolExecutor` and `asyncio.Semaphore`
    - `src/mcp_trino_optimizer/_context.py` contains `bind_trino_query_id`
    - `tests/adapters/test_pool.py` exits 0 with at least 7 test cases
  </acceptance_criteria>
  <done>QueryHandle with confirmed cancel, QueryIdCell thread-safe holder, TimeoutResult, TrinoThreadPool with semaphore backpressure — all tested.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: TrinoClient + architectural invariant test + query logging</name>
  <files>
    src/mcp_trino_optimizer/adapters/trino/client.py
    tests/adapters/test_trino_client_invariant.py
    tests/adapters/test_query_logging.py
    tests/adapters/test_auth_retry.py
  </files>
  <read_first>
    src/mcp_trino_optimizer/adapters/trino/classifier.py
    src/mcp_trino_optimizer/adapters/trino/errors.py
    src/mcp_trino_optimizer/adapters/trino/auth.py
    src/mcp_trino_optimizer/adapters/trino/handle.py
    src/mcp_trino_optimizer/adapters/trino/pool.py
    src/mcp_trino_optimizer/ports/plan_source.py
    src/mcp_trino_optimizer/settings.py
    src/mcp_trino_optimizer/_context.py
    src/mcp_trino_optimizer/logging_setup.py
    .planning/phases/02-trino-adapter-read-only-gate/02-CONTEXT.md
  </read_first>
  <behavior>
    - Test (invariant): Every public method of TrinoClient that takes a `sql: str` parameter has `self._classifier.assert_read_only(sql)` as its first executable line (AST introspection)
    - Test (invariant): `cancel_query` and `probe_capabilities` are exempt (no sql parameter)
    - Test (logging): After a query execution, a `trino_query_executed` log event is emitted with `request_id`, `statement_hash`, `duration_ms`, `auth_mode` — never raw SQL
    - Test (logging): statement_hash is SHA-256 of the SQL string
    - Test (D-13 retry): On first HTTP 401 from Trino, _execute_query re-reads auth via build_authentication(), retries EXACTLY ONCE, and succeeds if retry works
    - Test (D-13 retry): On two consecutive HTTP 401s, _execute_query raises TrinoAuthError with query_id
    - Test (D-13 retry): On 401 retry, a `trino_auth_retry` log event is emitted with {request_id, query_id, attempt, auth_mode} and no token value
  </behavior>
  <action>
    **Create `client.py`** at `src/mcp_trino_optimizer/adapters/trino/client.py` per D-02, D-27, D-28:

    ```python
    class TrinoClient:
        def __init__(self, settings: Settings, pool: TrinoThreadPool) -> None:
            self._settings = settings
            self._pool = pool
            self._classifier = SqlClassifier()
            self._auth = build_authentication(settings)
            self._capabilities: CapabilityMatrix | None = None
            self._log = get_logger("trino.client")

        def _make_connection(self) -> trino.dbapi.Connection:
            """Create a new trino connection per request (ensures fresh JWT per D-12)."""
            return trino.dbapi.connect(
                host=self._settings.trino_host,
                port=self._settings.trino_port,
                user=self._settings.trino_user or "mcp-trino-optimizer",
                catalog=self._settings.trino_catalog,
                schema=self._settings.trino_schema,
                auth=self._auth,
                http_scheme="https" if self._settings.trino_auth_mode != "none" else "http",
                verify=self._settings.trino_verify_ssl,
                source=f"mcp-trino-optimizer/{_get_version()}",
                client_tags=[f"mcp_request_id={current_request_id()}"],
            )

        async def fetch_plan(self, sql: str, *, timeout: float | None = None) -> ExplainPlan | TimeoutResult[ExplainPlan]:
            self._classifier.assert_read_only(sql)  # FIRST LINE per D-02/TRN-05
            explain_sql = f"EXPLAIN (FORMAT JSON) {sql}"
            self._classifier.assert_read_only(explain_sql)
            return await self._execute_explain(explain_sql, "estimated", timeout=timeout)

        async def fetch_analyze_plan(self, sql: str, *, timeout: float | None = None) -> ExplainPlan | TimeoutResult[ExplainPlan]:
            self._classifier.assert_read_only(sql)  # FIRST LINE
            explain_sql = f"EXPLAIN ANALYZE (FORMAT JSON) {sql}"
            self._classifier.assert_read_only(explain_sql)
            return await self._execute_explain(explain_sql, "executed", timeout=timeout)

        async def fetch_distributed_plan(self, sql: str, *, timeout: float | None = None) -> ExplainPlan | TimeoutResult[ExplainPlan]:
            self._classifier.assert_read_only(sql)  # FIRST LINE
            explain_sql = f"EXPLAIN (TYPE DISTRIBUTED) {sql}"
            self._classifier.assert_read_only(explain_sql)
            return await self._execute_explain(explain_sql, "distributed", timeout=timeout)

        async def fetch_stats(self, catalog: str, schema: str, table: str, *, timeout: float | None = None) -> dict[str, Any] | TimeoutResult[dict[str, Any]]:
            sql = f'SHOW STATS FOR "{catalog}"."{schema}"."{table}"'
            self._classifier.assert_read_only(sql)  # FIRST LINE
            return await self._execute_query(sql, timeout=timeout)

        async def fetch_iceberg_metadata(self, catalog: str, schema: str, table: str, suffix: str, *, timeout: float | None = None) -> list[dict[str, Any]] | TimeoutResult[list[dict[str, Any]]]:
            sql = f'SELECT * FROM "{catalog}"."{schema}"."{table}${suffix}"'
            self._classifier.assert_read_only(sql)  # FIRST LINE
            return await self._execute_query(sql, timeout=timeout)

        async def fetch_system_runtime(self, query_sql: str, *, timeout: float | None = None) -> list[dict[str, Any]] | TimeoutResult[list[dict[str, Any]]]:
            self._classifier.assert_read_only(query_sql)  # FIRST LINE
            return await self._execute_query(query_sql, timeout=timeout)

        async def cancel_query(self, query_id: str) -> bool:
            """Cancel a running query — no sql parameter, classifier-exempt."""
            ...

        async def probe_capabilities(self) -> CapabilityMatrix:
            """Probe Trino version + catalog — no sql parameter, classifier-exempt."""
            ...  # Implemented in Plan 04
    ```

    Every public method that takes `sql: str` calls `self._classifier.assert_read_only(sql)` **as its very first executable line** — this is the TRN-05 invariant.

    `_execute_query` and `_execute_explain` are private methods that:
    1. Create a `QueryHandle` with wall-clock deadline from `timeout or self._settings.trino_query_timeout_sec`
    2. Bind `trino_query_id` to contextvars once captured
    3. Run the sync cursor operation via `self._pool.run(self._run_in_thread, ...)`
    4. **D-13 retry-once on 401:** If the Trino client raises an auth-related error (check for `trino.exceptions.TrinoExternalError` with HTTP 401, or the error message containing "401" / "Authentication"):
       a. Emit a `trino_auth_retry` structured log event with `{request_id, query_id, attempt=1, auth_mode}` — **never the token value**
       b. Re-read credentials: `self._auth = build_authentication(self._settings)` (picks up rotated JWT/password from env)
       c. Retry the same `self._pool.run(self._run_in_thread, ...)` call EXACTLY ONCE with a fresh connection (which uses the new `self._auth`)
       d. If the retry also raises a 401-class error, raise `TrinoAuthError(message, request_id=handle.request_id, query_id=handle.query_id or "")` — do NOT retry again
    5. On timeout: capture partial results, call `handle.cancel()`, return `TimeoutResult`
    6. Log `trino_query_executed` per D-28: `{event, request_id, query_id, statement_hash, duration_ms, result_row_count, trino_state, auth_mode}` — statement_hash is `hashlib.sha256(sql.encode()).hexdigest()`, raw SQL is NEVER logged

    `_run_in_thread` is the sync function per RESEARCH.md Pattern (Query ID Capture):
    1. Create connection via `self._make_connection()`
    2. `cursor.execute(sql)`
    3. Capture `cursor.query_id` into `handle.query_id_cell.set_once()`
    4. `cursor.fetchall()` or `cursor.fetchone()` depending on query type
    5. Close cursor + connection in finally block

    Set Trino request headers per D-27:
    - `X-Trino-Source: mcp-trino-optimizer/{version}`
    - `X-Trino-Client-Tags: mcp_request_id={request_id}`
    - `X-Trino-Client-Info: git_sha={git_sha}`
    (These are passed via `trino.dbapi.connect()` kwargs `source=`, `client_tags=`)

    **Create `tests/adapters/test_trino_client_invariant.py`** per D-03 and TRN-05:
    - Use `ast` module to parse `client.py` source
    - Find all public method definitions (not starting with `_`)
    - For each method that has a parameter named `sql` with type annotation `str`:
      - Get the first statement in the method body
      - Assert it is a call to `self._classifier.assert_read_only(sql)`
    - Explicitly verify `cancel_query` and `probe_capabilities` do NOT have `sql` parameter

    **Create `tests/adapters/test_query_logging.py`**:
    - Mock the Trino connection to avoid network calls
    - Execute a query via TrinoClient
    - Capture structlog output
    - Assert `trino_query_executed` event is present with `statement_hash`, `duration_ms`, `request_id`
    - Assert the raw SQL string does NOT appear in any log line
    - Assert `statement_hash` is `hashlib.sha256(sql.encode()).hexdigest()`

    **Create `tests/adapters/test_auth_retry.py`** per D-13:
    - Mock `_run_in_thread` to raise a `trino.exceptions.TrinoExternalError` with HTTP 401 on first call, then succeed on second call
    - Assert TrinoClient retries exactly once and returns the successful result
    - Mock `_run_in_thread` to raise 401 on both calls
    - Assert TrinoClient raises `TrinoAuthError` with `query_id` set
    - Capture structlog output and assert `trino_auth_retry` event is present with `{request_id, query_id, attempt, auth_mode}`
    - Assert no token/password/jwt value appears in the log event
    - Mock `_run_in_thread` to raise a non-401 error (e.g., 500)
    - Assert TrinoClient does NOT retry (raises immediately, no `trino_auth_retry` event)
  </action>
  <verify>
    <automated>uv run pytest tests/adapters/test_trino_client_invariant.py tests/adapters/test_query_logging.py tests/adapters/test_auth_retry.py -v -x</automated>
  </verify>
  <acceptance_criteria>
    - `src/mcp_trino_optimizer/adapters/trino/client.py` contains `class TrinoClient` with methods `fetch_plan`, `fetch_analyze_plan`, `fetch_distributed_plan`, `fetch_stats`, `fetch_iceberg_metadata`, `fetch_system_runtime`, `cancel_query`, `probe_capabilities`
    - Every public method with `sql` parameter has `self._classifier.assert_read_only(sql)` as first line — verified by `test_trino_client_invariant.py`
    - `tests/adapters/test_trino_client_invariant.py` exits 0
    - `tests/adapters/test_query_logging.py` asserts `trino_query_executed` log event with `statement_hash` and absence of raw SQL
    - `tests/adapters/test_auth_retry.py` verifies D-13 retry-once on 401, raises TrinoAuthError on double-401, emits trino_auth_retry log event
    - `uv run pytest -m "not integration" -x --tb=short -q` exits 0
  </acceptance_criteria>
  <done>TrinoClient with classifier-first invariant, bounded thread pool, confirmed cancellation, timeout result, and statement hash logging. Architectural test and query logging test pass.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| MCP tool input -> TrinoClient.fetch_* | Untrusted SQL crosses into Trino adapter |
| TrinoClient -> Trino cluster | Classified SQL sent over HTTP REST |
| Worker thread -> async event loop | query_id flows back via QueryIdCell |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-02-07 | Tampering | TrinoClient | mitigate | assert_read_only(sql) as first line of every sql-taking method; TRN-05 architectural test enforces at CI time |
| T-02-08 | Denial of Service | TrinoThreadPool | mitigate | Bounded ThreadPoolExecutor(max_workers=4) + asyncio.Semaphore(4); TrinoPoolBusyError on overflow |
| T-02-09 | Denial of Service | Trino cluster | mitigate | Confirmed cancellation via DELETE /v1/query/{queryId} + polling; wall-clock timeout + TimeoutResult |
| T-02-10 | Information Disclosure | Query logging | mitigate | SQL logged as SHA-256 hash only (D-28); raw SQL never appears in any log line |
| T-02-11 | Repudiation | Query execution | mitigate | Every query logged with request_id, query_id, statement_hash, duration_ms, auth_mode; X-Trino-Client-Tags propagation for cluster-side correlation |
</threat_model>

<verification>
```bash
uv run pytest tests/adapters/test_trino_client_invariant.py -v -x
uv run pytest tests/adapters/test_query_logging.py -v -x
uv run pytest tests/adapters/test_pool.py -v -x
uv run pytest -m "not integration" -x --tb=short -q
uv run mypy src/mcp_trino_optimizer/adapters/trino/ --strict
```
</verification>

<success_criteria>
- TrinoClient has all 8 public methods with correct signatures
- Architectural invariant test passes (every sql-taking method has classifier call first)
- TrinoThreadPool rejects when all slots busy
- QueryHandle cancel sends DELETE and polls for confirmation
- TimeoutResult returned on wall-clock deadline
- Statement logging uses SHA-256 hash, never raw SQL
- Full non-integration test suite passes
</success_criteria>

<output>
After completion, create `.planning/phases/02-trino-adapter-read-only-gate/02-03-SUMMARY.md`
</output>
