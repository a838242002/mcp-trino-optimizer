# Phase 2: Trino Adapter & Read-Only Gate - Research

**Researched:** 2026-04-12
**Domain:** Trino HTTP REST adapter, SQL classification, async concurrency, Docker integration testing
**Confidence:** HIGH

## Summary

Phase 2 builds the full Trino adapter layer: a `trino-python-client`-based HTTP REST client wrapped in `asyncio.to_thread`, a `sqlglot`-AST-based SQL classifier gate, hexagonal ports (`PlanSource`, `StatsSource`, `CatalogSource`), query cancellation via `DELETE nextUri`, and an integration test harness using testcontainers-python with a Trino 480 + Lakekeeper + MinIO + Postgres docker-compose stack.

The primary research risk was cancellation mechanics. The trino-python-client's `Cursor.cancel()` sends `DELETE` to `nextUri` (the dynamic URL from the last query response), NOT to a fixed `/v1/query/{queryId}` endpoint. The CONTEXT.md D-08 references `DELETE /v1/query/{queryId}` but this is not a documented Trino client protocol endpoint -- the correct mechanism is `DELETE nextUri`. The implementation must either (a) use the cursor's built-in `cancel()` which handles this, or (b) capture `nextUri` from the cursor internals and issue the DELETE via httpx. Option (b) aligns with D-08's requirement to use a separate httpx client, but must target `nextUri`, not a fabricated `/v1/query/{queryId}` path.

A second critical finding: sqlglot's Trino dialect parses `EXPLAIN`, `SHOW`, and `CALL` statements as `Command` (a catch-all type), not as typed AST nodes. The classifier must handle this by inspecting `Command.this` (which holds the keyword string like `"EXPLAIN"`, `"SHOW"`, `"CALL"`) and parsing the remainder from `Command.expression.this`. For `EXPLAIN ANALYZE <inner>`, recursive validation requires extracting the inner SQL text from the `Command.expression` literal and re-parsing it.

**Primary recommendation:** Build the classifier with a two-tier dispatch: typed expression nodes (`Select`, `Insert`, `Delete`, etc.) for DML/DDL, plus `Command.this` keyword inspection for `EXPLAIN`/`SHOW`/`CALL`. Use the trino-python-client cursor's `_next_uri` for cancellation via a separate httpx client, with confirmation polling via `system.runtime.queries`.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- D-01: Hexagonal layout with ports/ and adapters/trino/ and adapters/offline/ module structure
- D-02: Single TrinoClient class, every public method with sql param calls assert_read_only(sql) as first line
- D-03: TRN-05 architectural test scoped to TrinoClient only, not OfflinePlanSource
- D-04: Bounded asyncio.to_thread + semaphore in TrinoThreadPool, backpressure via TrinoPoolBusyError
- D-05: Event-loop-lag probe test asserting < 100ms lag with 4 concurrent fetch_plan calls
- D-06: QueryHandle dataclass with QueryIdCell thread-safe single-slot holder
- D-07: Cancel on timeout/tool-cancel via async context manager __aexit__
- D-08: Cancel is await-confirmed with bounded exponential backoff (100ms->300ms->900ms->2700ms, cap ~4s)
- D-09: Timeout from settings (default 60s, bounded 1-1800) with per-call override
- D-10: TimeoutResult[T] return type for partial results
- D-11: Auth mode selector with MCPTO_TRINO_* settings fields, model_validator fail-fast
- D-12: JWT re-read from env on every call, no caching
- D-13: 401 retry-once policy
- D-14: Mutually exclusive auth modes, no fallback chains
- D-15: OfflinePlanSource does NOT call classifier
- D-16: Classifier allowlist: SELECT, WITH/CTE, EXPLAIN, EXPLAIN ANALYZE, SHOW *, DESCRIBE, USE, VALUES
- D-17: Classifier unit test corpus locked in Phase 2
- D-18: Capability probe scope: version, catalogs, iceberg metadata availability (lazy init)
- D-19: CapabilityMatrix frozen dataclass shape
- D-20: OfflinePlanSource takes raw JSON text only, maxLength 1_000_000
- D-21: Live + offline share one ExplainPlan dataclass (placeholder for Phase 3)
- D-22: testcontainers + docker-compose with Trino 480, Lakekeeper, Postgres 16, MinIO
- D-23: Integration mark + CI wiring (push-to-main only)
- D-24: Integration test coverage targets (6 areas)
- D-25: Fixture setup bypass using raw trino-python-client outside TrinoClient
- D-26: Structured error taxonomy (6 exception classes)
- D-27: Trino-side request context propagation (X-Trino-Source, X-Trino-Client-Tags, X-Trino-Client-Info)
- D-28: Query log entry with statement_hash, never raw SQL

### Claude's Discretion
- Exact QueryHandle context manager signature (sync vs async, generator vs class)
- Whether DELETE cancel goes through same httpx client or dedicated session
- Exact ExplainPlan placeholder dataclass shape
- Integration test fixture set (minimum is floor, not ceiling)
- Lakekeeper + MinIO compose file details (env vars, healthchecks, wait conditions)
- TrinoPoolBusyError surface (exception vs structured dataclass)
- Pre-commit hook additions
- Schema-lint additions
- Event-loop lag probe implementation approach

### Deferred Ideas (OUT OF SCOPE)
- Prepared statements + parameter binding
- Connection pooling beyond thread pool
- Kerberos / client-certificate auth
- Per-catalog auth overrides
- Automatic JWT refresh via OIDC/JWKS
- Prometheus / OpenTelemetry metrics
- Query plan caching
- Rate limiting / per-user quotas
- Streaming result consumption
- Retries beyond 401 retry-once
- Productized docker-compose (Phase 9)
- Prompt-injection adversarial corpus (Phase 9)
- CTAS/INSERT classifier exemptions
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| TRN-01 | HTTP REST via trino-python-client, no JDBC | trino 0.337.0 verified on PyPI; uses requests internally; DBAPI cursor pattern documented |
| TRN-02 | asyncio.to_thread with bounded thread pool | anyio 4.13.0 available; ThreadPoolExecutor + Semaphore pattern well-established |
| TRN-03 | No-auth, Basic, JWT bearer auth | JWTAuthentication takes static str; custom Authentication subclass needed for per-call JWT re-read |
| TRN-04 | SqlClassifier gate via sqlglot AST | sqlglot 30.4.2 Trino dialect verified; Command catch-all for EXPLAIN/SHOW/CALL requires two-tier dispatch |
| TRN-05 | Architectural unit test for classifier invariant | AST inspection of method bodies feasible via inspect module |
| TRN-06 | Timeout + cancel with DELETE nextUri | Trino protocol uses DELETE to nextUri, not /v1/query/{queryId}; cursor exposes query_id; confirmation via system.runtime.queries |
| TRN-07 | Version probe on init, capability matrix | SELECT node_version FROM system.runtime.nodes; parse version string |
| TRN-08 | Iceberg catalog probe | SHOW CATALOGS + SHOW SCHEMAS + metadata table probe pattern documented |
| TRN-09 | Fetch EXPLAIN JSON, ANALYZE JSON, DISTRIBUTED | These are adapter methods that compose SQL and delegate to TrinoClient |
| TRN-10 | Read system.runtime.*, system.metadata.*, Iceberg metadata tables | Iceberg metadata tables use "table$snapshots" double-quoted syntax |
| TRN-11 | Structured query logging with statement_hash | structlog contextvars pattern from Phase 1; SHA-256 of SQL string |
| TRN-12 | OfflinePlanSource for pasted EXPLAIN JSON | Pure JSON parsing, no network; shares ExplainPlan return type |
| TRN-13 | PlanSource/StatsSource/CatalogSource ports | Python Protocol classes; live and offline adapters implement same interface |
| TRN-14 | Minimum Trino version 429, refuse older | Version string parsing from system.runtime.nodes |
| TRN-15 | Max concurrent queries semaphore (default 4) | asyncio.Semaphore + ThreadPoolExecutor(max_workers=4) |
</phase_requirements>

## Standard Stack

### Core (Phase 2 additions to pyproject.toml)

| Library | Version | Purpose | Why Standard | Confidence |
|---------|---------|---------|--------------|------------|
| `trino` | `>=0.337.0` | Trino HTTP REST client, DBAPI cursor, auth classes | Official trinodb client; HTTP-only, no JVM; verified on PyPI 2026-03-06 | HIGH [VERIFIED: PyPI] |
| `sqlglot` | `>=30.4.2` | SQL parsing for classifier gate; Trino dialect | Already in venv; verified AST types for classifier via local testing | HIGH [VERIFIED: local test + PyPI] |
| `httpx` | `>=0.28.1` | Async HTTP for cancel DELETE calls (separate from trino client's requests) | Already a dependency; needed for cancellation outside the sync trino client | HIGH [VERIFIED: installed 0.28.1] |
| `anyio` | `>=4.4` | asyncio.to_thread bridge, concurrency primitives | Already a dependency at 4.13.0 | HIGH [VERIFIED: installed 4.13.0] |

### Supporting (dev-only)

| Library | Version | Purpose | When to Use | Confidence |
|---------|---------|---------|-------------|------------|
| `testcontainers` | `>=4.14.2` | DockerCompose wrapper for integration tests | Integration tests only; session-scoped pytest fixture | HIGH [VERIFIED: PyPI 4.14.2] |
| `pytest-cov` | `>=5` | Coverage reporting | Already in CLAUDE.md stack | HIGH [ASSUMED] |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Separate httpx cancel client | Cursor.cancel() built-in | Built-in cancel uses next_uri internally but goes through sync requests lib; D-08 requires async cancel via httpx |
| Custom JWT auth class | Static JWTAuthentication | Static class caches token at init; per-call re-read requires custom Authentication subclass |
| testcontainers DockerCompose | Raw subprocess docker compose | DockerCompose handles teardown, port discovery, wait strategies automatically |

**Installation (Phase 2 additions):**
```bash
uv add trino>=0.337.0 sqlglot>=30.4.2
uv add --dev "testcontainers[compose]>=4.14.2"
```

Note: `httpx>=0.28.1` and `anyio>=4.4` are already dependencies. `sqlglot` was installed manually but needs to be added to pyproject.toml `dependencies`.

## Architecture Patterns

### Phase 2 Module Structure (from D-01)

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
    │   ├── handle.py           # QueryHandle + QueryIdCell
    │   ├── pool.py             # TrinoThreadPool (bounded to_thread)
    │   ├── capabilities.py     # Version probe + CapabilityMatrix
    │   ├── errors.py           # TrinoAdapterError hierarchy
    │   ├── live_plan_source.py
    │   ├── live_stats_source.py
    │   └── live_catalog_source.py
    └── offline/
        ├── __init__.py
        └── json_plan_source.py
```

### Pattern 1: SqlClassifier Two-Tier Dispatch

**What:** sqlglot's Trino dialect parses DML/DDL into typed nodes (`Select`, `Insert`, `Delete`, `Create`, `Drop`, etc.) but parses `EXPLAIN`, `SHOW`, `CALL` as generic `Command` nodes.

**When to use:** Every call to `assert_read_only(sql)`.

**Implementation strategy:**
```python
# Source: verified via local sqlglot 30.4.2 testing
import sqlglot
from sqlglot import exp

def classify(sql: str) -> str:
    """Returns classification: 'allowed', 'rejected', or raises."""
    stmts = sqlglot.parse(sql, dialect="trino")

    # Reject empty/whitespace
    if not stmts or all(s is None for s in stmts):
        raise TrinoClassifierRejected("Empty statement")

    # Reject multi-statement
    non_none = [s for s in stmts if s is not None]
    if len(non_none) != 1:
        raise TrinoClassifierRejected("Multi-statement blocks rejected")

    stmt = non_none[0]

    # Tier 1: Typed AST nodes
    if isinstance(stmt, exp.Select):
        return "allowed"
    if isinstance(stmt, (exp.Insert, exp.Delete, exp.Update, exp.Merge,
                          exp.Create, exp.Drop, exp.Alter, exp.TruncateTable,
                          exp.Grant, exp.Set)):
        raise TrinoClassifierRejected(f"Statement type {type(stmt).__name__} rejected")
    if isinstance(stmt, exp.Describe):
        return "allowed"
    if isinstance(stmt, exp.Use):
        return "allowed"
    if isinstance(stmt, exp.Values):
        return "allowed"

    # Tier 2: Command catch-all (EXPLAIN, SHOW, CALL, etc.)
    if isinstance(stmt, exp.Command):
        keyword = stmt.this.upper()  # "EXPLAIN", "SHOW", "CALL", etc.
        if keyword == "EXPLAIN":
            # Recursive validation of inner statement
            inner_text = stmt.expression.this if stmt.expression else ""
            # Strip ANALYZE, FORMAT JSON, TYPE DISTRIBUTED prefixes
            _validate_explain_inner(inner_text)
            return "allowed"
        if keyword == "SHOW":
            return "allowed"
        if keyword in ("CALL", "EXECUTE", "REFRESH"):
            raise TrinoClassifierRejected(f"Command '{keyword}' rejected")
        raise TrinoClassifierRejected(f"Unknown command '{keyword}' rejected")

    raise TrinoClassifierRejected(f"Unknown statement type {type(stmt).__name__}")
```

**Critical detail for EXPLAIN inner validation:** The expression text for `EXPLAIN ANALYZE INSERT INTO t VALUES(1)` is `"ANALYZE INSERT INTO t VALUES(1)"`. The classifier must strip the `ANALYZE` prefix, then any `(FORMAT JSON)` or `(TYPE DISTRIBUTED)` options, then re-parse the remaining SQL to validate the inner statement is on the allowlist.

[VERIFIED: local sqlglot 30.4.2 testing]

### Pattern 2: sqlglot AST Types Reference

Verified via local testing with sqlglot 30.4.2, Trino dialect:

| SQL | AST Type | Notes |
|-----|----------|-------|
| `SELECT 1` | `Select` | Typed node |
| `INSERT INTO t VALUES (1)` | `Insert` | Typed node |
| `DELETE FROM t` | `Delete` | Typed node |
| `UPDATE t SET x=1` | `Update` | Typed node |
| `CREATE TABLE t (id INT)` | `Create` | Typed node |
| `DROP TABLE t` | `Drop` | Typed node |
| `ALTER TABLE t ADD COLUMN x INT` | `Alter` | Typed node |
| `TRUNCATE TABLE t` | `TruncateTable` | Typed node |
| `MERGE INTO t USING s...` | `Merge` | Typed node |
| `GRANT SELECT ON t TO u` | `Grant` | Typed node |
| `SET SESSION x = y` | `Set` | Typed node |
| `DESCRIBE t` | `Describe` | Typed node |
| `USE catalog` | `Use` | Typed node |
| `VALUES (1,2)` | `Values` | Typed node |
| `EXPLAIN SELECT 1` | `Command(this='EXPLAIN')` | Command catch-all |
| `EXPLAIN ANALYZE SELECT 1` | `Command(this='EXPLAIN')` | `.expression.this='ANALYZE SELECT 1'` |
| `EXPLAIN (FORMAT JSON) SELECT 1` | `Command(this='EXPLAIN')` | `.expression.this='(FORMAT JSON) SELECT 1'` |
| `SHOW CATALOGS` | `Command(this='SHOW')` | Command catch-all |
| `SHOW TABLES` | `Command(this='SHOW')` | `.expression.this='TABLES'` |
| `SHOW CREATE TABLE t` | `Command(this='SHOW')` | `.expression.this='CREATE TABLE t'` |
| `CALL system.sync()` | `Command(this='CALL')` | Command catch-all |
| `SET SESSION AUTHORIZATION admin` | `Command(this='SET')` | Command (not Set node) |
| `REFRESH MATERIALIZED VIEW v` | `Refresh` | Typed node |
| `/* comment */ SELECT 1` | `Select` | Comments stripped by parser |
| `''` (empty) | `None` | Returns [None] |
| `'   '` (whitespace) | `None` | Returns [None] |
| `SELECT 1; DROP TABLE t` | `[Select, Drop]` | Multi-statement: len > 1 |

[VERIFIED: local sqlglot 30.4.2 testing on this codebase]

### Pattern 3: QueryHandle Cancellation Protocol

**What:** Trino cancellation uses `DELETE nextUri`, NOT `DELETE /v1/query/{queryId}`.

**Key findings:**
1. The trino-python-client `Cursor` exposes `.query_id` as a property, populated after the first HTTP response from Trino [VERIFIED: GitHub source review]
2. `Cursor.cancel()` sends `DELETE` to `self._next_uri` (the dynamic URL from the last Trino response), NOT to a fixed `/v1/query/{queryId}` path [VERIFIED: GitHub source review]
3. The Trino REST API protocol documents only `DELETE nextUri` for cancellation -- there is no `/v1/query/{queryId}` endpoint in the client protocol [VERIFIED: Trino 480 docs]
4. `cursor._query.query_id` is available after the first response
5. `cursor._query._next_uri` holds the cancellation target URL

**Implementation approach (honoring D-08's intent while using correct Trino protocol):**
```python
# D-08 says use separate httpx client, not sync trino-python-client
# The correct target is nextUri, not /v1/query/{queryId}
# Capture both query_id (for logging/confirmation) and next_uri (for cancellation)

@dataclass
class QueryIdCell:
    """Thread-safe single-slot holder for query metadata from worker thread."""
    _query_id: str | None = field(default=None, init=False)
    _next_uri: str | None = field(default=None, init=False)
    _event: threading.Event = field(default_factory=threading.Event, init=False)

    def set_once(self, query_id: str, next_uri: str) -> None:
        self._query_id = query_id
        self._next_uri = next_uri
        self._event.set()

    def wait_for(self, timeout: float) -> tuple[str | None, str | None]:
        self._event.wait(timeout=timeout)
        return self._query_id, self._next_uri
```

**Cancel confirmation:** After issuing DELETE, poll `system.runtime.queries` WHERE `query_id = '{qid}'` to verify the query has left the active set or its state is `FAILED` (cancelled queries transition to FAILED state). [ASSUMED -- verification via integration test]

### Pattern 4: Custom JWT Authentication for Per-Call Re-Read

**What:** `trino.auth.JWTAuthentication` accepts a static `str` token, not a callable. Per D-12, JWT must be re-read from env on every call.

**Implementation:** Create a custom `Authentication` subclass:
```python
# Source: trino.auth.Authentication ABC has abstract method set_http_session
import os
from trino.auth import Authentication
from requests import Session

class PerCallJWTAuthentication(Authentication):
    """Re-reads JWT from env var on every HTTP session setup."""

    def __init__(self, env_var: str = "MCPTO_TRINO_JWT") -> None:
        self._env_var = env_var

    def set_http_session(self, http_session: Session) -> Session:
        token = os.environ.get(self._env_var, "")
        http_session.headers["Authorization"] = f"Bearer {token}"
        return http_session

    def get_exceptions(self) -> tuple:
        return ()
```

**Key detail:** `set_http_session` is called by the trino client before each HTTP request cycle. By reading from `os.environ` inside this method, the token is fresh on every call. [VERIFIED: trino.auth.Authentication ABC confirmed via GitHub source]

### Pattern 5: Trino Query States

Trino queries progress through these states (from `QueryStateMachine`):

| State | Meaning | Terminal? |
|-------|---------|-----------|
| QUEUED | Accepted, awaiting execution | No |
| DISPATCHING | Being dispatched to coordinator | No |
| PLANNING | Query plan being generated | No |
| STARTING | Execution starting | No |
| RUNNING | At least one task running | No |
| BLOCKED | Waiting for resources | No |
| FINISHING | Committing/finalizing | No |
| FINISHED | Completed successfully | Yes |
| FAILED | Execution failed (includes cancelled) | Yes |

Cancelled queries transition to `FAILED` state. To confirm cancellation, query `system.runtime.queries` and check `state = 'FAILED'` or absence from the table (queries age out). [CITED: GitHub issues #23759, #18467; Trino Web UI docs]

### Pattern 6: Iceberg Metadata Table Syntax

```sql
-- Syntax: "catalog"."schema"."table$metadata_type"
-- The $ metadata suffix must be inside double quotes

SELECT * FROM iceberg.myschema."orders$snapshots";
SELECT * FROM iceberg.myschema."orders$files";
SELECT * FROM iceberg.myschema."orders$manifests";
SELECT * FROM iceberg.myschema."orders$partitions";
SELECT * FROM iceberg.myschema."orders$history";
SELECT * FROM iceberg.myschema."orders$refs";
```

The double-quoting of `table$suffix` is required because `$` is not a valid unquoted identifier character. [CITED: Trino 480 Iceberg connector docs]

### Anti-Patterns to Avoid

- **Anti-pattern: Logging raw SQL.** D-28 requires only SHA-256 hash of SQL. Never log the SQL text itself -- it may contain sensitive data in WHERE clauses.
- **Anti-pattern: Blocking the event loop.** Every trino-python-client call MUST go through `asyncio.to_thread` / the bounded thread pool. The trino client is sync-only (uses `requests`). [VERIFIED: trino client uses requests, confirmed via PyPI dependency check]
- **Anti-pattern: Using cursor.cancel() directly from async code.** The cursor's cancel() uses the sync `requests` library. For async cancel, use httpx with the captured `next_uri`. This is why D-08 specifies a separate httpx client.
- **Anti-pattern: Fabricating /v1/query/{queryId} URL.** This endpoint is NOT part of the Trino client REST API. Cancel via `nextUri` as documented.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| SQL parsing for classification | Regex or string matching | `sqlglot.parse(sql, dialect="trino")` | AST-based classification handles comments, Unicode, CTEs, subqueries correctly |
| HTTP Trino polling | Custom HTTP + nextUri loop | `trino.dbapi.Cursor` | Cursor handles statement lifecycle, nextUri chaining, error mapping |
| Thread pool management | Custom threading.Thread spawner | `ThreadPoolExecutor` + `asyncio.to_thread` | Standard library; proper shutdown semantics |
| JWT bearer header injection | Manual requests.Session header setting | Custom `Authentication` subclass | Integrates with trino client's session lifecycle |
| Docker compose lifecycle in tests | subprocess.Popen + manual cleanup | `testcontainers.compose.DockerCompose` | Handles teardown, port discovery, wait strategies |

## Common Pitfalls

### Pitfall 1: sqlglot Command Catch-All
**What goes wrong:** EXPLAIN, SHOW, and CALL all parse as `Command` in the Trino dialect. A classifier that only checks typed nodes (`Select`, `Insert`, etc.) will miss these entirely, either allowing `CALL` (security hole) or rejecting `EXPLAIN` (broken functionality).
**Why it happens:** sqlglot's Trino dialect does not have first-class AST types for EXPLAIN/SHOW/CALL.
**How to avoid:** Two-tier dispatch: typed nodes first, then `Command.this` keyword inspection.
**Warning signs:** Tests pass for SELECT/INSERT but fail for EXPLAIN/SHOW queries.

### Pitfall 2: EXPLAIN Inner Statement Extraction
**What goes wrong:** `EXPLAIN ANALYZE (FORMAT JSON) INSERT INTO t VALUES(1)` produces `Command(this='EXPLAIN', expression=Literal('ANALYZE (FORMAT JSON) INSERT INTO t VALUES(1)'))`. The inner text must be stripped of `ANALYZE`, format options, and type options before re-parsing.
**Why it happens:** sqlglot treats everything after `EXPLAIN` as a raw literal string.
**How to avoid:** Regex-based prefix stripping of `ANALYZE`, `(FORMAT ...)`, `(TYPE ...)` before re-parsing the inner statement.
**Warning signs:** `EXPLAIN ANALYZE INSERT INTO t` passes the classifier (security hole).

### Pitfall 3: SET vs SET SESSION AUTHORIZATION
**What goes wrong:** `SET SESSION query_max_memory = '1GB'` parses as `exp.Set` (typed node), but `SET SESSION AUTHORIZATION admin` parses as `Command(this='SET')`. The classifier must reject the latter (privilege escalation) while potentially handling the former.
**Why it happens:** sqlglot only has a typed node for regular SET, not for SET SESSION AUTHORIZATION.
**How to avoid:** For `Command(this='SET')`, always reject. The classifier allowlist (D-16) does not include `SET SESSION`.
**Warning signs:** Authorization escalation via SET SESSION AUTHORIZATION.

### Pitfall 4: Cancel Target is nextUri, Not /v1/query/{queryId}
**What goes wrong:** Code sends `DELETE /v1/query/{queryId}` and gets 404 from Trino.
**Why it happens:** CONTEXT.md D-08 references `/v1/query/{queryId}` but this is not a documented Trino client protocol endpoint. The correct cancellation target is the `nextUri` from the last query response.
**How to avoid:** Capture `next_uri` from the cursor internals (`cursor._query._next_uri`) alongside `query_id`.
**Warning signs:** Cancel always "fails" but queries actually do stop (because the client disconnects).

### Pitfall 5: trino-python-client Uses requests, Not httpx
**What goes wrong:** Calling `cursor.cancel()` from async code blocks the event loop because it uses the sync `requests` library internally.
**Why it happens:** The trino-python-client has not migrated to httpx.
**How to avoid:** Perform cancellation via a separate `httpx.AsyncClient` call to the captured `next_uri`, as D-08 requires.
**Warning signs:** Event-loop-lag probe test fails when cancel is invoked concurrently.

### Pitfall 6: Lakekeeper Warehouse Registration
**What goes wrong:** Trino starts but cannot see any Iceberg tables; metadata queries fail.
**Why it happens:** Lakekeeper requires explicit warehouse registration via HTTP POST before Trino can access it. The docker-compose must include a bootstrap/init service.
**How to avoid:** Include a curl-based init container that registers the warehouse and accepts terms of use.
**Warning signs:** `SHOW SCHEMAS IN iceberg` returns empty or errors.

### Pitfall 7: Python Version Mismatch
**What goes wrong:** Code runs on Python 3.14 locally (current venv) but CI targets 3.11.
**Why it happens:** The local venv was created with Python 3.14 (visible in pip output paths).
**How to avoid:** Test with `python_version = "3.11"` in mypy; avoid 3.12+ only features unless guarded.
**Warning signs:** Type annotations using `X | Y` syntax work in 3.14 but `from __future__ import annotations` is needed for 3.11. The project already uses `from __future__ import annotations` (confirmed in Phase 1 code).

## Code Examples

### Trino DBAPI Cursor Lifecycle
```python
# Source: trino-python-client docs + GitHub source
import trino

conn = trino.dbapi.connect(
    host="localhost",
    port=8080,
    user="trino",
    catalog="iceberg",
    schema="default",
    http_scheme="http",
    # auth=trino.auth.BasicAuthentication("user", "pass"),
)
cursor = conn.cursor()
cursor.execute("SELECT 1")
# cursor.query_id is available after execute()
rows = cursor.fetchall()  # blocks until complete

# Cancel:
cursor.cancel()  # sends DELETE to next_uri internally
```

[VERIFIED: trino-python-client GitHub source + DBAPI docs]

### Custom Authentication Subclass
```python
# Source: trino.auth module (GitHub)
import abc
from requests import Session

class Authentication(metaclass=abc.ABCMeta):
    @abc.abstractmethod
    def set_http_session(self, http_session: Session) -> Session:
        ...

    def get_exceptions(self) -> tuple:
        return ()
```

[VERIFIED: trino-python-client GitHub auth.py]

### testcontainers DockerCompose Pattern
```python
# Source: testcontainers docs + GitHub examples
from testcontainers.compose import DockerCompose
import pytest

@pytest.fixture(scope="session")
def compose_stack():
    compose = DockerCompose(
        filepath=".testing",
        compose_file_name="docker-compose.yml",
    )
    compose.start()
    compose.wait_for(
        "http://localhost:8080/v1/info",
        timeout=120,
    )
    yield compose
    compose.stop()
```

[ASSUMED -- API details based on testcontainers docs; exact method signatures need verification during implementation]

### asyncio.to_thread with Bounded Pool
```python
# Source: Python stdlib + anyio docs
import asyncio
from concurrent.futures import ThreadPoolExecutor

class TrinoThreadPool:
    def __init__(self, max_workers: int = 4) -> None:
        self._pool = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="trino-",
        )
        self._semaphore = asyncio.Semaphore(max_workers)

    async def run(self, fn, *args, **kwargs):
        if not self._semaphore.locked():
            # Semaphore has capacity
            pass
        else:
            raise TrinoPoolBusyError("All Trino worker threads busy")

        async with self._semaphore:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(self._pool, lambda: fn(*args, **kwargs))
```

[VERIFIED: Python stdlib ThreadPoolExecutor + asyncio.Semaphore API]

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| HTTP+SSE transport | Streamable HTTP | MCP spec 2025-03-26 | Phase 1 already handles this |
| `requests` in trino client | Still `requests` (not migrated) | N/A | Must use asyncio.to_thread; cancel via httpx |
| `/v1/query/{queryId}` cancel | `DELETE nextUri` | Always was nextUri in protocol | D-08 references must target nextUri |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Cancelled queries transition to FAILED state in system.runtime.queries | Trino Query States | Cancel confirmation logic would need different state check; LOW risk -- verifiable via integration test |
| A2 | testcontainers DockerCompose has wait_for() method with URL parameter | Code Examples | May need different wait strategy API; LOW risk -- fallback to manual healthcheck polling |
| A3 | Lakekeeper requires explicit warehouse registration POST before Trino can use it | Pitfall 6 | Init container may not be needed if auto-registration exists; LOW risk -- verifiable during compose setup |
| A4 | TrinoPoolBusyError should be raised before acquiring semaphore (backpressure) | Code Examples | Could alternatively queue with timeout; MEDIUM risk -- D-04 says "reject with backpressure" |

## Open Questions

1. **nextUri vs /v1/query/{queryId} for cancellation**
   - What we know: The Trino client protocol documents only `DELETE nextUri`. CONTEXT.md D-08 references `/v1/query/{queryId}`.
   - What's unclear: Whether the CONTEXT.md reference was aspirational or reflects an undocumented internal API.
   - Recommendation: Use `DELETE nextUri` via httpx (correct protocol), capture `query_id` for logging/confirmation only. The D-08 intent (async cancel via httpx, not sync trino client) is honored; only the URL target changes.

2. **QueryIdCell.next_uri capture timing**
   - What we know: `cursor._query._next_uri` is set after the first response and changes with each poll. Cancel needs the current `next_uri`, not the initial one.
   - What's unclear: Whether capturing `next_uri` from a different thread while the cursor is polling is thread-safe.
   - Recommendation: The worker thread should update `QueryIdCell.next_uri` on each poll cycle, or the cancel path should call `cursor.cancel()` in the worker thread via a threading.Event signal rather than issuing DELETE from async land.

3. **testcontainers DockerCompose exact API**
   - What we know: DockerCompose exists in `testcontainers.compose`, has start/stop lifecycle.
   - What's unclear: Exact constructor parameters, wait strategy API, port mapping discovery.
   - Recommendation: Verify API during implementation; fall back to raw `subprocess` + `docker compose` if needed.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Docker Engine | Integration tests | Yes | 29.3.1 | Skip integration tests |
| Docker Compose v2 | Integration tests | Yes | 5.1.1 | -- |
| Python 3.11+ | Runtime | Yes (3.14) | 3.14.3 | Need 3.11 in CI matrix |
| trino (PyPI) | Trino adapter | No (not installed) | 0.337.0 available | Install via uv add |
| sqlglot (PyPI) | SqlClassifier | Yes (manual install) | 30.4.2 | Add to pyproject.toml |
| testcontainers (PyPI) | Integration tests | No (not installed) | 4.14.2 available | Install via uv add --dev |
| httpx | Cancel client | Yes | 0.28.1 | Already a dependency |
| anyio | Thread pool bridge | Yes | 4.13.0 | Already a dependency |

**Missing dependencies with no fallback:** None -- all are installable.

**Missing dependencies with fallback:** None -- all are available.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.3+ with pytest-asyncio 1.3.0 |
| Config file | `pyproject.toml` [tool.pytest.ini_options] |
| Quick run command | `uv run pytest -m "not integration" -x` |
| Full suite command | `uv run pytest -x` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| TRN-04 | SqlClassifier rejects DML/DDL, allows SELECT/EXPLAIN/SHOW | unit | `uv run pytest tests/safety/test_sql_classifier.py -x` | Wave 0 |
| TRN-05 | Architectural test: every TrinoClient method with sql param calls assert_read_only first | unit | `uv run pytest tests/safety/test_classifier_invariant.py -x` | Wave 0 |
| TRN-02/15 | ThreadPool bounded, semaphore enforced, event loop not blocked | unit+integration | `uv run pytest tests/test_trino_pool.py -x` | Wave 0 |
| TRN-01/09 | fetch_plan, fetch_analyze_plan, fetch_distributed_plan work | integration | `uv run pytest tests/integration/test_trino_adapter.py -x -m integration` | Wave 0 |
| TRN-03 | No-auth, Basic, JWT all work | integration | `uv run pytest tests/integration/test_trino_auth.py -x -m integration` | Wave 0 |
| TRN-06 | Cancel via DELETE nextUri, query leaves runtime.queries | integration | `uv run pytest tests/integration/test_trino_cancel.py -x -m integration` | Wave 0 |
| TRN-07/08/14 | Capability probe: version, catalog, refuse < 429 | unit+integration | `uv run pytest tests/test_capabilities.py -x` | Wave 0 |
| TRN-10 | system.runtime.*, Iceberg metadata tables read | integration | `uv run pytest tests/integration/test_metadata_tables.py -x -m integration` | Wave 0 |
| TRN-11 | Structured query log with statement_hash | unit | `uv run pytest tests/test_query_logging.py -x` | Wave 0 |
| TRN-12/13 | OfflinePlanSource parses JSON, returns same type as live | unit | `uv run pytest tests/test_offline_plan_source.py -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest -m "not integration" -x`
- **Per wave merge:** `uv run pytest -x` (full suite including integration if Docker available)
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/safety/test_sql_classifier.py` -- covers TRN-04
- [ ] `tests/safety/test_classifier_invariant.py` -- covers TRN-05
- [ ] `tests/test_trino_pool.py` -- covers TRN-02, TRN-15
- [ ] `tests/test_capabilities.py` -- covers TRN-07, TRN-08, TRN-14
- [ ] `tests/test_query_logging.py` -- covers TRN-11
- [ ] `tests/test_offline_plan_source.py` -- covers TRN-12, TRN-13
- [ ] `tests/integration/conftest.py` -- session-scoped compose fixture
- [ ] `tests/integration/fixtures.py` -- DDL bypass helper (D-25)
- [ ] `tests/integration/test_trino_adapter.py` -- covers TRN-01, TRN-09
- [ ] `tests/integration/test_trino_auth.py` -- covers TRN-03
- [ ] `tests/integration/test_trino_cancel.py` -- covers TRN-06
- [ ] `tests/integration/test_metadata_tables.py` -- covers TRN-10
- [ ] `.testing/docker-compose.yml` -- Trino 480 + Lakekeeper + MinIO + Postgres

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | Yes | Custom `PerCallJWTAuthentication`; `BasicAuthentication` from trino client; `SecretStr` for credentials |
| V3 Session Management | No | No HTTP sessions -- each Trino statement is independent |
| V4 Access Control | Yes | SqlClassifier allowlist gate -- defense in depth against SQL injection |
| V5 Input Validation | Yes | sqlglot AST parsing (not regex); schema_lint maxLength bounds |
| V6 Cryptography | No | TLS termination delegated to reverse proxy |

### Known Threat Patterns for Trino Adapter

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| SQL injection via tool input | Tampering | SqlClassifier AST-based allowlist; reject anything not SELECT/EXPLAIN/SHOW |
| DDL/DML bypass via comments | Tampering | sqlglot parser strips comments before AST classification |
| DDL/DML bypass via Unicode escapes | Tampering | sqlglot normalizes Unicode during tokenization |
| Multi-statement injection | Tampering | Reject when `sqlglot.parse()` returns > 1 statement |
| EXPLAIN ANALYZE wrapping DML | Tampering | Recursive inner-statement validation |
| Credential leak in logs | Info Disclosure | structlog redaction denylist; JWT as SecretStr; SQL logged as hash only |
| Orphaned long-running queries | Denial of Service | Cancel-on-timeout with confirmed deletion; bounded concurrency semaphore |
| Token replay via log scraping | Info Disclosure | JWT never cached in memory beyond single call; never logged |

## Sources

### Primary (HIGH confidence)
- sqlglot 30.4.2 local testing -- AST types for all SQL statement categories [VERIFIED: local Python execution]
- [trino-python-client GitHub source (client.py)](https://github.com/trinodb/trino-python-client/blob/master/trino/client.py) -- cancel(), query_id, next_uri mechanics [VERIFIED: WebFetch]
- [trino-python-client GitHub source (auth.py)](https://github.com/trinodb/trino-python-client/blob/master/trino/auth.py) -- Authentication ABC, JWTAuthentication(token: str) [VERIFIED: WebFetch]
- [trino-python-client GitHub source (dbapi.py)](https://github.com/trinodb/trino-python-client/blob/master/trino/dbapi.py) -- Cursor.cancel(), Cursor.query_id [VERIFIED: WebFetch]
- [Trino 480 client REST API docs](https://trino.io/docs/current/develop/client-protocol.html) -- DELETE nextUri for cancellation [VERIFIED: WebFetch]
- [Trino 480 Iceberg connector docs](https://trino.io/docs/current/connector/iceberg.html) -- metadata table syntax [CITED]
- [trino PyPI 0.337.0](https://pypi.org/project/trino/) -- latest version [VERIFIED: PyPI API]
- [testcontainers PyPI 4.14.2](https://pypi.org/project/testcontainers/) -- latest version [VERIFIED: PyPI API]
- [sqlglot PyPI 30.4.2](https://pypi.org/project/sqlglot/) -- installed and tested [VERIFIED: local install]

### Secondary (MEDIUM confidence)
- [Trino query states](https://github.com/trinodb/trino/issues/23759) -- QUEUED/RUNNING/FINISHING/FINISHED/FAILED lifecycle [CITED: GitHub issues]
- [Lakekeeper minimal docker-compose](https://github.com/lakekeeper/lakekeeper/blob/main/examples/minimal/docker-compose.yaml) -- compose structure with Trino + Lakekeeper + MinIO + Postgres [CITED: GitHub]
- [testcontainers-python docs](https://testcontainers-python.readthedocs.io/) -- DockerCompose API [CITED: ReadTheDocs]

### Tertiary (LOW confidence)
- testcontainers DockerCompose exact API (wait_for, get_service_port) -- needs implementation-time verification [ASSUMED]

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all packages verified on PyPI with correct versions
- Architecture: HIGH -- sqlglot AST types verified via local execution; cancel mechanics verified via source review
- Pitfalls: HIGH -- critical pitfalls (Command catch-all, nextUri vs query_id) verified by testing
- Integration testing: MEDIUM -- testcontainers API details need implementation-time verification

**Research date:** 2026-04-12
**Valid until:** 2026-05-12 (30 days -- stable ecosystem, pinned versions)
