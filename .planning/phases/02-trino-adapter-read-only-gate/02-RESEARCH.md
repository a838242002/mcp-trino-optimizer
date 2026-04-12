# Phase 2: Trino Adapter & Read-Only Gate - Research

**Researched:** 2026-04-12
**Domain:** Trino HTTP REST client, SQL classification, async concurrency, query cancellation, Iceberg metadata access, integration test harness
**Confidence:** HIGH

## Summary

Phase 2 delivers the Trino adapter layer (HTTP REST client wrapped in async), the `SqlClassifier` read-only gate, hexagonal ports (`PlanSource`/`StatsSource`/`CatalogSource`), offline plan ingress, query cancellation with confirmation, capability probing, and the docker-compose integration test harness. This is the most complex phase so far -- it touches networking, concurrency, security classification, and multi-service Docker orchestration.

The critical technical finding is that `sqlglot` parses Trino's `EXPLAIN`, `SHOW`, and `CALL` statements as `Command` fallback nodes (not typed AST classes), so the classifier must handle both typed expression nodes (Select, Insert, Delete, etc.) and `Command` nodes with keyword inspection. The `trino-python-client` exposes `cursor.query_id` immediately after `execute()` returns its first response, and `cursor.cancel()` sends a `DELETE` to the Trino `nextUri` -- but for the D-08 await-confirmed cancellation pattern, we need a separate `httpx` client hitting `/v1/query/{queryId}` directly. JWT per-request refresh (D-12) requires a custom authentication wrapper since `JWTAuthentication` only accepts a static string.

**Primary recommendation:** Build the classifier as a typed-allowlist over sqlglot AST node types (Select, Describe, Use, Values) plus keyword-based allowlist for Command nodes (EXPLAIN, SHOW). Use a dedicated async httpx client for cancel confirmation. Create a custom `PerCallJWTAuthentication` that re-reads `os.environ` on every `set_http_session` invocation.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01**: Hexagonal layout with ports/ and adapters/trino/ + adapters/offline/ structure
- **D-02**: Single TrinoClient class, every public method with `sql` param calls `assert_read_only(sql)` as first line
- **D-03**: Architectural test (TRN-05) introspects TrinoClient only, not OfflinePlanSource
- **D-04**: Bounded `asyncio.to_thread` + semaphore via `TrinoThreadPool` in pool.py
- **D-05**: Event-loop-lag probe in integration tests (never blocked > 100ms)
- **D-06**: QueryHandle dataclass with QueryIdCell thread-safe single-slot holder
- **D-07**: Cancel on timeout/tool-cancel is structural via `__aexit__`
- **D-08**: Cancel is await-confirmed with bounded exponential backoff (100ms -> 300ms -> 900ms -> 2700ms, cap ~4s)
- **D-09**: Timeout from settings + per-call override (default 60s, bounded 1-1800)
- **D-10**: Timeout UX returns `TimeoutResult[T]` instead of raising
- **D-11**: Auth mode selector with MCPTO_TRINO_* settings fields and fail-fast validator
- **D-12**: JWT is per-call re-read from env, no caching
- **D-13**: 401 retry-once policy
- **D-14**: Mutually exclusive auth modes, no fallback chains
- **D-15**: Classifier is live-adapter scoped; OfflinePlanSource is exempt
- **D-16**: Classifier allowlist baseline (SELECT, WITH/CTE, EXPLAIN, EXPLAIN ANALYZE, SHOW variants, DESCRIBE, USE, VALUES)
- **D-17**: Classifier unit test corpus locked in Phase 2
- **D-18**: Capability probe scope (lazy init, not at process start)
- **D-19**: CapabilityMatrix frozen dataclass shape
- **D-20**: OfflinePlanSource takes raw JSON text only, bounded 1MB
- **D-21**: Live + offline share one ExplainPlan dataclass (placeholder for Phase 3)
- **D-22**: testcontainers + minimal Iceberg stack in .testing/docker-compose.yml
- **D-23**: Integration mark + CI wiring (push-to-main only)
- **D-24**: Integration test coverage targets (6 minimum areas)
- **D-25**: Fixture setup bypass for DDL via separate test helper
- **D-26**: Structured error taxonomy (6 exception classes)
- **D-27**: Trino-side request context propagation (X-Trino-Source, X-Trino-Client-Tags, X-Trino-Client-Info)
- **D-28**: Query log entry per TRN-11 (statement hash, never raw SQL)

### Claude's Discretion
- QueryHandle context manager exact signature (sync vs async, generator vs class)
- Whether DELETE /v1/query/{queryId} uses same httpx client or dedicated session
- ExplainPlan placeholder dataclass shape
- Integration test fixture set (floor not ceiling)
- Lakekeeper + MinIO compose details (env vars, wait conditions, healthchecks)
- TrinoPoolBusyError surface (exception vs RejectedResult dataclass)
- Pre-commit hook additions
- Schema-lint additions (plan_json max_length, identifier patterns)
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
- Retries beyond single 401 retry
- Productized docker-compose (Phase 9)
- Prompt-injection adversarial corpus (Phase 9)
- CTAS / INSERT INTO SELECT in offline mode
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| TRN-01 | HTTP REST via trino-python-client, no JDBC | trino 0.337.0 verified on PyPI; DBAPI cursor lifecycle documented |
| TRN-02 | Every Trino call through asyncio.to_thread with bounded pool | anyio 4.4 to_thread + ThreadPoolExecutor pattern researched |
| TRN-03 | No-auth, Basic, JWT bearer; JWT per-request | JWTAuthentication is static-only; custom wrapper needed for per-call refresh |
| TRN-04 | SqlClassifier AST-based allowlist gate | sqlglot Trino dialect parsing verified; Command fallback for EXPLAIN/SHOW documented |
| TRN-05 | Architectural unit test asserting classifier-first | AST introspection approach validated via sqlglot parse behavior |
| TRN-06 | Cancel sends DELETE /v1/query/{queryId} | REST API DELETE to nextUri documented; separate httpx client for query-id-based cancel |
| TRN-07 | Version probe via system.runtime.nodes | node_version column confirmed in system.runtime.nodes table |
| TRN-08 | Iceberg catalog probe + capability matrix | system.metadata.table_properties and catalog probes documented |
| TRN-09 | Fetch EXPLAIN JSON, EXPLAIN ANALYZE JSON, EXPLAIN DISTRIBUTED | Trino EXPLAIN variants confirmed; adapter constructs SQL and classifies |
| TRN-10 | Read system.runtime.*, system.metadata.*, Iceberg metadata tables | All metadata tables ($snapshots, $files, $manifests, $partitions, $history, $refs) documented with access patterns |
| TRN-11 | Statement logging with hash, duration, request_id | structlog pipeline from Phase 1 supports this; SHA-256 hash of SQL, never raw |
| TRN-12 | OfflinePlanSource accepts pasted EXPLAIN JSON | Simple JSON parse + ExplainPlan construction; no network call |
| TRN-13 | Live + offline share PlanSource/StatsSource/CatalogSource ports | Protocol-based ports; hexagonal architecture from ARCHITECTURE.md |
| TRN-14 | Refuse Trino < 429 | Version string parsing from system.runtime.nodes probe |
| TRN-15 | Max-concurrent-queries semaphore (default 4) | asyncio.Semaphore + ThreadPoolExecutor bounded pool pattern |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `trino` | `>=0.337.0` (latest: 0.337.0) | HTTP REST client for Trino DBAPI | Official trinodb client; exposes cursor.query_id, cancel(), auth classes [VERIFIED: PyPI] |
| `sqlglot` | `>=30.4.2` (latest: 30.4.2) | SQL parsing for classifier + future rewrites | Trino dialect, AST-based classification, zero deps [VERIFIED: PyPI] |
| `httpx` | `>=0.28.1` | Async HTTP for cancel confirmation + REST catalog probes | Already a dependency; needed for async DELETE /v1/query/{queryId} [VERIFIED: pyproject.toml] |
| `anyio` | `>=4.4` | asyncio.to_thread bridge for sync Trino client | Already a dependency; MCP SDK is async-first [VERIFIED: pyproject.toml] |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `tenacity` | `>=9.1.4` (latest: 9.1.4) | Retry with backoff for cancel confirmation polling | Cancel confirmation exponential backoff (D-08); alternatively use simple asyncio.sleep loop [VERIFIED: PyPI] |
| `testcontainers[trino,minio]` | `>=4.14.2` (latest: 4.14.2) | Docker container lifecycle for integration tests | DockerCompose wrapper for Trino+Lakekeeper+MinIO+Postgres [VERIFIED: PyPI] |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `tenacity` for cancel backoff | Manual `asyncio.sleep` loop | tenacity adds a dep but is cleaner for bounded retry with backoff; manual loop is ~15 lines and avoids the dep |
| Separate `httpx` client for cancel | Trino client's built-in cancel | Built-in cancel sends DELETE to nextUri (may be gone); separate httpx client targets /v1/query/{queryId} reliably |

**Installation:**
```bash
uv add trino>=0.337.0 sqlglot>=30.4.2
uv add --dev testcontainers[trino,minio]>=4.14.2
# httpx and anyio already in dependencies
# tenacity is optional -- planner decides
```

## Architecture Patterns

### Recommended Project Structure (Phase 2 additions)
```
src/mcp_trino_optimizer/
├── ports/
│   ├── __init__.py
│   ├── plan_source.py          # PlanSource Protocol
│   ├── stats_source.py         # StatsSource Protocol
│   └── catalog_source.py       # CatalogSource Protocol
├── adapters/
│   ├── __init__.py
│   ├── trino/
│   │   ├── __init__.py
│   │   ├── client.py           # TrinoClient -- sync wrapper + async facade
│   │   ├── auth.py             # none / basic / JWT per-call
│   │   ├── classifier.py       # SqlClassifier (AST-based allowlist)
│   │   ├── handle.py           # QueryHandle + QueryIdCell
│   │   ├── pool.py             # TrinoThreadPool (bounded to_thread + semaphore)
│   │   ├── capabilities.py     # Version probe + CapabilityMatrix
│   │   ├── errors.py           # Exception taxonomy
│   │   ├── live_plan_source.py # PlanSource via TrinoClient
│   │   ├── live_stats_source.py
│   │   └── live_catalog_source.py
│   └── offline/
│       ├── __init__.py
│       └── json_plan_source.py # PlanSource from raw JSON text
├── safety/
│   └── schema_lint.py          # + MAX_PLAN_JSON_LEN = 1_000_000
└── settings.py                 # + MCPTO_TRINO_* fields

tests/
├── safety/
│   └── test_sql_classifier.py  # Locked classifier corpus (D-17)
├── adapters/
│   └── test_trino_client_invariant.py  # TRN-05 architectural test
├── integration/
│   ├── conftest.py             # testcontainers session fixture
│   ├── fixtures.py             # DDL bypass helper (D-25)
│   ├── test_fetch_plans.py
│   ├── test_cancellation.py
│   ├── test_auth.py
│   ├── test_capabilities.py
│   ├── test_metadata_tables.py
│   └── test_event_loop_lag.py

.testing/
└── docker-compose.yml          # Trino 480 + Lakekeeper + Postgres + MinIO
```

### Pattern 1: SqlClassifier -- AST-Based Allowlist

**What:** Parse SQL via `sqlglot.parse(sql, dialect="trino")`, inspect the root AST node type, and allow/reject based on a typed allowlist.

**Critical finding:** sqlglot's Trino dialect parses `EXPLAIN`, `SHOW`, and `CALL` as `Command` fallback nodes, not typed expression classes. The classifier must handle both cases. [VERIFIED: local sqlglot 30.4.2 testing]

**When to use:** Every SQL string before it reaches the Trino HTTP client.

**Example:**
```python
# Source: verified via local sqlglot testing 2026-04-12
import sqlglot
from sqlglot import expressions as exp

# Typed AST nodes (direct allowlist)
ALLOWED_TYPED = (exp.Select, exp.Describe, exp.Use, exp.Values)

# Command-type keywords (EXPLAIN, SHOW fall back to Command)
ALLOWED_COMMAND_KEYWORDS = frozenset({"EXPLAIN", "SHOW", "DESCRIBE"})
REJECTED_COMMAND_KEYWORDS = frozenset({"CALL", "EXECUTE", "REFRESH"})

def classify(sql: str) -> bool:
    stmts = sqlglot.parse(sql, dialect="trino")

    # Reject empty, whitespace-only, multi-statement
    valid = [s for s in stmts if s is not None]
    if len(valid) != 1:
        return False  # empty or multi-statement

    root = valid[0]

    # Typed expression allowlist
    if isinstance(root, ALLOWED_TYPED):
        return True

    # Command fallback -- inspect keyword
    if isinstance(root, exp.Command):
        keyword = str(root.this).upper()
        if keyword in ALLOWED_COMMAND_KEYWORDS:
            # For EXPLAIN, recursively validate inner statement
            if keyword == "EXPLAIN":
                return _validate_explain_inner(root)
            return True
        if keyword in REJECTED_COMMAND_KEYWORDS:
            return False
        return False  # unknown Command = reject

    # Everything else (Insert, Update, Delete, Merge, Create, Drop,
    # Alter, TruncateTable, Grant, Revoke, Set) = reject
    return False
```

**EXPLAIN inner validation (critical for TRN-04):**
```python
# Source: verified via local sqlglot testing 2026-04-12
def _validate_explain_inner(cmd: exp.Command) -> bool:
    """Recursively validate the inner statement of EXPLAIN/EXPLAIN ANALYZE."""
    expr = cmd.args.get("expression")
    if expr is None:
        return True  # bare EXPLAIN with no inner = safe

    inner_text = expr.this if hasattr(expr, "this") else str(expr)

    # EXPLAIN ANALYZE -> expression.this = "ANALYZE <inner_sql>"
    # EXPLAIN (FORMAT JSON) -> expression.this = "(FORMAT JSON) <inner_sql>"
    # Strip ANALYZE prefix and (FORMAT ...) / (TYPE ...) options
    text = str(inner_text)
    if text.upper().startswith("ANALYZE "):
        text = text[len("ANALYZE "):]

    # Strip parenthesized options like (FORMAT JSON), (TYPE DISTRIBUTED)
    import re
    text = re.sub(r'^\(.*?\)\s*', '', text).strip()

    if not text:
        return True

    # Re-parse the inner SQL and classify recursively
    inner_stmts = sqlglot.parse(text, dialect="trino")
    valid_inner = [s for s in inner_stmts if s is not None]
    if len(valid_inner) != 1:
        return False
    return classify_single(valid_inner[0])  # must be SELECT/SHOW/DESCRIBE/VALUES
```

### Pattern 2: QueryHandle with QueryIdCell

**What:** Thread-safe single-slot holder for Trino query_id, enabling cancel from async land while the sync cursor runs in a thread.

**Example:**
```python
# Source: D-06 from CONTEXT.md + trino-python-client cursor.query_id behavior
import threading
from dataclasses import dataclass, field

class QueryIdCell:
    """Thread-safe single-write, multi-read cell for Trino query_id."""
    def __init__(self) -> None:
        self._value: str | None = None
        self._event = threading.Event()

    def set_once(self, query_id: str) -> None:
        if self._value is not None:
            return  # idempotent
        self._value = query_id
        self._event.set()

    def wait_for(self, timeout: float) -> str | None:
        self._event.wait(timeout=timeout)
        return self._value

    @property
    def value(self) -> str | None:
        return self._value
```

### Pattern 3: Per-Call JWT Authentication

**What:** Custom authentication class that re-reads the JWT from `os.environ` on every call, since trino-python-client's `JWTAuthentication` only accepts a static string. [VERIFIED: trino auth.py source on GitHub]

**Example:**
```python
# Source: trino auth.py (GitHub master) + D-12
import os
from trino.auth import Authentication

class PerCallJWTAuthentication(Authentication):
    """Re-reads JWT from environment on every set_http_session call."""

    def __init__(self, env_var: str = "MCPTO_TRINO_JWT") -> None:
        self._env_var = env_var

    def set_http_session(self, http_session):
        token = os.environ.get(self._env_var, "")
        http_session.headers["Authorization"] = f"Bearer {token}"
        return http_session

    def get_exceptions(self):
        return ()
```

**Implementation note:** The `trino-python-client` calls `set_http_session` when creating the HTTP session for each request. For the per-call pattern to work, we need to verify whether `set_http_session` is called once per connection or once per request. If it is per-connection, we may need to create a new connection per request or use a different hook point. [ASSUMED -- needs integration test verification]

**Alternative approach (safer):** Create a new `trino.dbapi.connect()` for each request, passing a freshly-read JWT. This is heavier but guarantees the token is always current. Given that Phase 2 does not implement connection pooling (deferred), this is the recommended approach.

### Pattern 4: Cancel via Separate httpx Client

**What:** The trino-python-client's `cursor.cancel()` sends `DELETE` to `nextUri`, which may no longer be valid if the cursor has been partially consumed or the statement has progressed. For reliable cancellation per D-08, use a separate `httpx.AsyncClient` to hit the Trino REST API directly. [VERIFIED: trino client.py source on GitHub]

**Example:**
```python
# Source: Trino REST API docs + D-08
import httpx

async def cancel_query(
    base_url: str,
    query_id: str,
    auth_headers: dict[str, str],
) -> bool:
    """Send DELETE /v1/query/{queryId} and poll for confirmation."""
    async with httpx.AsyncClient(base_url=base_url) as client:
        # Step 1: DELETE the query
        resp = await client.delete(
            f"/v1/query/{query_id}",
            headers=auth_headers,
        )
        if resp.status_code == 204:
            return True  # Trino acknowledged

        # Step 2: Poll for state change (bounded backoff)
        delays = [0.1, 0.3, 0.9, 2.7]  # ~4s total budget
        for delay in delays:
            await asyncio.sleep(delay)
            info = await client.get(f"/v1/query/{query_id}")
            if info.status_code == 200:
                state = info.json().get("state", "")
                if state in ("FINISHED", "FAILED"):
                    return True
            elif info.status_code == 404:
                return True  # query already gone
        return False  # cancel unconfirmed
```

### Anti-Patterns to Avoid
- **Using cursor.cancel() for confirmed cancellation:** The trino-python-client cancel sends DELETE to nextUri which is ephemeral. Use a direct HTTP DELETE to /v1/query/{queryId} for reliability. [VERIFIED: trino client.py source]
- **Blocking the event loop with sync Trino calls:** Every Trino operation must go through `asyncio.to_thread` / `loop.run_in_executor`. The MCP SDK is async; blocking will stall all concurrent tool calls. [CITED: PITFALLS.md #11]
- **Logging raw SQL or JWT tokens:** SQL is logged as SHA-256 hash only (D-28). JWT values are `SecretStr` and redacted by the structlog pipeline (Phase 1 D-09). [CITED: CONTEXT.md D-28]
- **Regex-based SQL classification:** sqlglot AST is the only safe approach. Regex cannot handle comments, Unicode escapes, or nested EXPLAIN correctly. [CITED: CLAUDE.md "What NOT to Use"]
- **Using trino-python-client for the cancel HTTP call:** The cancel must go through httpx (async), not the sync trino client, per D-08. [CITED: CONTEXT.md D-08]

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| SQL parsing for classification | Regex classifier, token scanner | `sqlglot.parse(sql, dialect="trino")` | Comments, Unicode, nested EXPLAIN, CTE wrapping are all handled by the parser |
| Trino HTTP REST protocol | Raw httpx against /v1/statement | `trino.dbapi.connect()` + cursor | Statement polling, nextUri chaining, error mapping, auth session setup |
| Retry with backoff | Manual sleep loop with counter | `tenacity` (optional) or simple bounded loop | tenacity handles jitter, max attempts, timeout budget cleanly |
| Thread pool management | Raw threading.Thread creation | `concurrent.futures.ThreadPoolExecutor` + `asyncio.to_thread` | Proper lifecycle, naming, bounded concurrency |

**Key insight:** The trino-python-client handles the complex Trino statement lifecycle (POST -> poll nextUri -> collect results), but its cancel mechanism is insufficient for confirmed cancellation. Layer httpx on top for the cancel path only.

## Common Pitfalls

### Pitfall 1: sqlglot Command Fallback for EXPLAIN and SHOW
**What goes wrong:** sqlglot's Trino dialect parses `EXPLAIN`, `SHOW CATALOGS`, `SHOW TABLES`, `SHOW SCHEMAS`, `SHOW SESSION`, and `CALL` as `Command` nodes rather than typed expression classes. If the classifier only checks typed AST nodes, it will reject all EXPLAIN and SHOW statements.
**Why it happens:** sqlglot's Trino dialect does not have first-class support for all Trino-specific statement types; unsupported syntax falls back to `Command(this=keyword, expression=Literal(rest))`.
**How to avoid:** The classifier must handle `isinstance(root, exp.Command)` as a separate branch and inspect `root.this` (the leading keyword string) against an allowlist.
**Warning signs:** All EXPLAIN and SHOW queries being rejected by the classifier during testing.
[VERIFIED: local sqlglot 30.4.2 testing on 2026-04-12]

### Pitfall 2: EXPLAIN ANALYZE Inner Statement Extraction
**What goes wrong:** For `EXPLAIN ANALYZE SELECT 1`, sqlglot produces `Command(this="EXPLAIN", expression=Literal(this="ANALYZE SELECT 1"))`. The inner SQL is embedded as a string literal, prefixed with "ANALYZE ". For `EXPLAIN (FORMAT JSON) SELECT 1`, the prefix is "(FORMAT JSON) ".
**Why it happens:** The Command fallback treats everything after the keyword as a raw string.
**How to avoid:** Strip the "ANALYZE " prefix and any parenthesized options before re-parsing the inner SQL for recursive classification.
**Warning signs:** `EXPLAIN ANALYZE INSERT INTO t VALUES (1)` passing the classifier because only the outer EXPLAIN is checked.
[VERIFIED: local sqlglot 30.4.2 testing on 2026-04-12]

### Pitfall 3: trino-python-client JWTAuthentication is Static
**What goes wrong:** `JWTAuthentication(token="...")` stores the token as a string and sets it once on the HTTP session. If the JWT expires mid-session, all subsequent requests fail with 401.
**Why it happens:** The client was designed for short-lived connections, not long-running servers that need per-request token refresh.
**How to avoid:** Either (a) create a custom auth class that re-reads from env on every session setup, or (b) create a new connection for each request.
**Warning signs:** 401 errors after token rotation when using a long-lived connection.
[VERIFIED: trino auth.py source on GitHub]

### Pitfall 4: cursor.cancel() vs DELETE /v1/query/{queryId}
**What goes wrong:** The trino-python-client's `cancel()` sends DELETE to `nextUri`, which is a transient URL that changes with each polling response. If the cursor has already consumed some results or the nextUri has expired, cancel is silently a no-op (nextUri is None).
**Why it happens:** The cancel mechanism was designed for DBAPI cursor lifecycle, not for external cancel-on-timeout from a different thread/task.
**How to avoid:** Capture the query_id from `cursor.query_id` immediately after execute, then use a separate httpx client to DELETE `/v1/query/{queryId}`.
**Warning signs:** Orphaned queries in `system.runtime.queries` after timeout.
[VERIFIED: trino client.py source on GitHub -- cancel() checks `if self._next_uri is None: return`]

### Pitfall 5: Multi-Statement Blocks
**What goes wrong:** `sqlglot.parse("SELECT 1; DROP TABLE t", dialect="trino")` returns a list of 2 statements. If the classifier only checks the first, the DROP passes through.
**Why it happens:** sqlglot splits on semicolons and returns multiple AST roots.
**How to avoid:** Reject any input where `parse()` returns more than one non-None statement.
**Warning signs:** Multi-statement SQL bypassing the classifier.
[VERIFIED: local sqlglot testing -- returns [Select, Drop] for "SELECT 1; DROP TABLE t"]

### Pitfall 6: Empty/Whitespace SQL Input
**What goes wrong:** `parse("", dialect="trino")` returns `[None]`. `parse("   ")` returns `[None]` (falsy). The classifier must handle these edge cases.
**Why it happens:** sqlglot returns a list with a None entry for empty input.
**How to avoid:** Filter None values from parse results; reject if no valid statements remain.
[VERIFIED: local sqlglot testing]

### Pitfall 7: Trino Version String Parsing
**What goes wrong:** `SELECT node_version FROM system.runtime.nodes` returns a string like "480" or "480-e" (enterprise). Simple integer parsing may fail on suffixed versions.
**Why it happens:** Trino versioning varies between OSS and commercial distributions.
**How to avoid:** Parse the leading numeric portion only. Use regex `r"^(\d+)"` to extract the major version.
[ASSUMED -- based on Trino documentation patterns]

### Pitfall 8: testcontainers DockerCompose Session Scope
**What goes wrong:** Using `module` scope and `function` scope in the same file causes Docker Compose to try spinning up containers twice, which fails.
**Why it happens:** Docker Compose doesn't allow duplicate container starts.
**How to avoid:** Use `session` scope for the compose fixture. All integration tests share one compose stack. Individual tests create/drop their own tables via the D-25 fixture bypass.
[CITED: testcontainers-python documentation]

## Code Examples

### Trino Connection with Auth Modes
```python
# Source: trino-python-client docs + D-11
import trino
from trino.auth import BasicAuthentication

# No auth
conn = trino.dbapi.connect(
    host=settings.trino_host,
    port=settings.trino_port,
    user="mcp-trino-optimizer",
    catalog=settings.trino_catalog,
    schema=settings.trino_schema,
    source=f"mcp-trino-optimizer/{version}",
    client_tags=[f"mcp_request_id={request_id}"],
)

# Basic auth
conn = trino.dbapi.connect(
    host=settings.trino_host,
    port=settings.trino_port,
    user=settings.trino_user,
    auth=BasicAuthentication(settings.trino_user, settings.trino_password.get_secret_value()),
    http_scheme="https",
    verify=settings.trino_verify_ssl,
)

# JWT auth (per-call refresh)
conn = trino.dbapi.connect(
    host=settings.trino_host,
    port=settings.trino_port,
    user="mcp-trino-optimizer",
    auth=PerCallJWTAuthentication(env_var="MCPTO_TRINO_JWT"),
    http_scheme="https",
)
```

### Query ID Capture in Thread
```python
# Source: trino dbapi.py + D-06
def _execute_in_thread(conn_factory, sql: str, handle: QueryHandle) -> list[dict]:
    """Runs in ThreadPoolExecutor; captures query_id into handle."""
    conn = conn_factory()
    cursor = conn.cursor()
    try:
        cursor.execute(sql)
        # query_id available immediately after execute returns
        if cursor.query_id:
            handle.query_id_cell.set_once(cursor.query_id)
        return cursor.fetchall()
    except Exception:
        if cursor.query_id:
            handle.query_id_cell.set_once(cursor.query_id)
        raise
    finally:
        cursor.close()
        conn.close()
```

### Iceberg Metadata Table Access
```python
# Source: Trino 480 Iceberg connector docs
# Access pattern: "catalog.schema"."table_name$metadata_suffix"

# Snapshots
SELECT committed_at, snapshot_id, parent_id, operation, summary
FROM "iceberg"."myschema"."mytable$snapshots"
ORDER BY committed_at DESC;

# Files (current snapshot)
SELECT content, file_path, record_count, file_size_in_bytes, file_format
FROM "iceberg"."myschema"."mytable$files";

# Manifests
SELECT content, path, length, partition_spec_id, added_snapshot_id
FROM "iceberg"."myschema"."mytable$manifests";

# Partitions
SELECT partition, record_count, file_count, total_size
FROM "iceberg"."myschema"."mytable$partitions";

# History
SELECT made_current_at, snapshot_id, parent_id, is_current_ancestor
FROM "iceberg"."myschema"."mytable$history";

# Refs (branches + tags)
SELECT * FROM "iceberg"."myschema"."mytable$refs";
```

### Docker Compose for Integration Tests
```yaml
# Source: Lakekeeper examples/minimal + customization for testing
# .testing/docker-compose.yml
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: lakekeeper
      POSTGRES_PASSWORD: lakekeeper
      POSTGRES_DB: lakekeeper
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U lakekeeper"]
      interval: 2s
      timeout: 5s
      retries: 5
    ports:
      - "127.0.0.1:5432:5432"

  minio:
    image: minio/minio:RELEASE.2025-07-23T15-54-02Z
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: minioadmin
    healthcheck:
      test: ["CMD", "mc", "ready", "local"]
      interval: 5s
      timeout: 5s
      retries: 5
    ports:
      - "127.0.0.1:9000:9000"
      - "127.0.0.1:9001:9001"

  createbuckets:
    image: minio/mc
    depends_on:
      minio:
        condition: service_healthy
    entrypoint: >
      /bin/sh -c "
      mc alias set myminio http://minio:9000 minioadmin minioadmin;
      mc mb myminio/warehouse;
      mc anonymous set public myminio/warehouse;
      exit 0;
      "

  lakekeeper:
    image: quay.io/lakekeeper/catalog:latest-main
    depends_on:
      postgres:
        condition: service_healthy
      createbuckets:
        condition: service_completed_successfully
    environment:
      LAKEKEEPER__BASE_URI: http://lakekeeper:8181
      LAKEKEEPER__LISTEN_PORT: "8181"
      LAKEKEEPER__PG__DATABASE_URL: postgres://lakekeeper:lakekeeper@postgres:5432/lakekeeper
      LAKEKEEPER__PG__ENCRYPTION_KEY: deadbeefdeadbeefdeadbeefdeadbeef
    healthcheck:
      test: ["CMD", "/home/nonroot/lakekeeper", "healthcheck"]
      interval: 2s
      timeout: 5s
      retries: 10
    ports:
      - "127.0.0.1:8181:8181"

  # Lakekeeper needs migration + bootstrap
  migrate:
    image: quay.io/lakekeeper/catalog:latest-main
    depends_on:
      postgres:
        condition: service_healthy
    command: migrate
    environment:
      LAKEKEEPER__PG__DATABASE_URL: postgres://lakekeeper:lakekeeper@postgres:5432/lakekeeper
      LAKEKEEPER__PG__ENCRYPTION_KEY: deadbeefdeadbeefdeadbeefdeadbeef

  bootstrap:
    image: curlimages/curl
    depends_on:
      lakekeeper:
        condition: service_healthy
    command: >
      -X POST http://lakekeeper:8181/management/v1/bootstrap
      -H "Content-Type: application/json"
      -d '{"accept-terms": true}'

  initwarehouse:
    image: curlimages/curl
    depends_on:
      bootstrap:
        condition: service_completed_successfully
    command: >
      -X POST http://lakekeeper:8181/management/v1/warehouse
      -H "Content-Type: application/json"
      -d '{"warehouse-name":"test","project-id":"00000000-0000-0000-0000-000000000000","storage-profile":{"type":"s3","bucket":"warehouse","endpoint":"http://minio:9000","region":"us-east-1","path-style-access":true,"flavor":"minio","sts-enabled":false},"storage-credential":{"type":"s3","credential-type":"access-key","aws-access-key-id":"minioadmin","aws-secret-access-key":"minioadmin"}}'

  trino:
    image: trinodb/trino:480
    depends_on:
      initwarehouse:
        condition: service_completed_successfully
    ports:
      - "127.0.0.1:8080:8080"
    healthcheck:
      test: ["CMD-SHELL", "curl -f http://localhost:8080/v1/info | grep -q '\"starting\":false'"]
      interval: 5s
      timeout: 10s
      retries: 30
    volumes:
      - ./trino/etc/catalog/iceberg.properties:/etc/trino/catalog/iceberg.properties:ro

networks:
  default:
    name: mcp-trino-test
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `JWTAuthentication(static_token)` | Custom per-call auth or new connection per request | Current | Required for D-12 per-request JWT refresh |
| `cursor.cancel()` for query termination | Direct `DELETE /v1/query/{queryId}` via httpx | Current | Reliable confirmed cancellation per D-08 |
| `pytest-docker-compose` | `testcontainers[compose]` DockerCompose | 2024+ | `pytest-docker-compose` is stale; testcontainers actively maintained |
| `docker-compose` (v1 binary) | `docker compose` (v2 plugin) | 2023+ | testcontainers uses Compose v2; ensure `docker compose` (space) works |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `set_http_session` is called per-connection, not per-request, in trino-python-client | Pattern 3 (Per-Call JWT) | If per-connection, the custom auth class won't refresh per-call; would need new connection per request instead |
| A2 | Trino version string from `system.runtime.nodes` is always numeric-prefixed (e.g., "480", "480-e") | Pitfall 7 | Version parsing regex may fail on unexpected formats |
| A3 | Lakekeeper bootstrap API at `/management/v1/bootstrap` + `/management/v1/warehouse` | Docker Compose example | If API paths changed, init containers fail; verify against actual Lakekeeper version |
| A4 | `DELETE /v1/query/{queryId}` returns 204 on success | Cancel pattern | If Trino returns different status codes, cancel confirmation logic needs adjustment |
| A5 | `GET /v1/query/{queryId}` returns query info with state field | Cancel polling | If endpoint doesn't exist or returns different shape, polling fails |

## Open Questions (RESOLVED)

1. **set_http_session call frequency in trino-python-client** -- RESOLVED
   - What we know: JWTAuthentication.set_http_session sets auth on the HTTP session
   - What's unclear: Is this called once per connection or once per request?
   - Recommendation: Integration test with a short-lived JWT token to verify; fallback to new-connection-per-request if needed
   - **Resolution:** Plans use new-connection-per-request pattern (TrinoClient._make_connection() creates a fresh trino.dbapi.Connection for every query execution). This sidesteps the ambiguity entirely -- each connection gets a fresh set_http_session call, so PerCallJWTAuthentication re-reads the env var on every query. Additionally, the D-13 retry-once logic calls build_authentication() to get a fresh auth object before the retry attempt, ensuring rotated credentials are picked up even within a single request cycle.

2. **Trino 480 DELETE /v1/query/{queryId} exact behavior** -- RESOLVED
   - What we know: REST docs say "DELETE to nextUri terminates a running query"
   - What's unclear: Whether DELETE to /v1/query/{queryId} (not nextUri) also works
   - Recommendation: Test in integration against Trino 480; if /v1/query/{queryId} doesn't work, fall back to storing and deleting the last-known nextUri
   - **Resolution:** Plans implement DELETE /v1/query/{queryId} as the primary path with a polling confirmation loop (D-08). Integration test test_cancellation.py will verify the exact behavior against Trino 480. If /v1/query/{queryId} DELETE does not work, the cancel implementation falls back to storing the last-known nextUri during cursor iteration.

3. **Lakekeeper healthcheck binary path** -- RESOLVED
   - What we know: Lakekeeper docs show a healthcheck command
   - What's unclear: Exact binary path inside the container image
   - Recommendation: Verify with `docker run --rm quay.io/lakekeeper/catalog:latest-main ls /home/nonroot/`
   - **Resolution:** docker-compose.yml uses `/home/nonroot/lakekeeper healthcheck` as documented. Integration test stack boot (Plan 05 Task 1) will validate this during the first docker-compose up. If the path differs, the healthcheck command in docker-compose.yml is the single place to update.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Docker Engine | Integration tests | Yes | 29.3.1 | -- |
| Docker Compose v2 | Integration tests | Yes | 5.1.1 | -- |
| Python 3.11+ | Runtime | Yes (3.14.3 via uv) | 3.14.3 | -- |
| uv | Package management | Yes | 0.11.6 | -- |
| Trino 480 (via Docker) | Integration tests | Pullable | -- | -- |
| Lakekeeper (via Docker) | Integration tests | Pullable | -- | -- |
| MinIO (via Docker) | Integration tests | Pullable | -- | -- |
| PostgreSQL 16 (via Docker) | Lakekeeper backend | Pullable | -- | -- |

**Missing dependencies with no fallback:** None.

**Missing dependencies with fallback:** None.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio 1.3.x |
| Config file | pyproject.toml `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest -m "not integration" -x` |
| Full suite command | `uv run pytest -x` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| TRN-01 | HTTP REST via trino-python-client | integration | `uv run pytest tests/integration/test_fetch_plans.py -x` | No -- Wave 0 |
| TRN-02 | asyncio.to_thread bounded pool | unit + integration | `uv run pytest tests/adapters/test_pool.py tests/integration/test_event_loop_lag.py -x` | No -- Wave 0 |
| TRN-03 | No-auth, Basic, JWT auth | unit + integration | `uv run pytest tests/adapters/test_auth.py tests/integration/test_auth.py -x` | No -- Wave 0 |
| TRN-04 | SqlClassifier AST allowlist | unit | `uv run pytest tests/safety/test_sql_classifier.py -x` | No -- Wave 0 |
| TRN-05 | Architectural invariant test | unit | `uv run pytest tests/adapters/test_trino_client_invariant.py -x` | No -- Wave 0 |
| TRN-06 | Cancel sends DELETE + confirms | integration | `uv run pytest tests/integration/test_cancellation.py -x` | No -- Wave 0 |
| TRN-07 | Version probe + refuse < 429 | unit + integration | `uv run pytest tests/adapters/test_capabilities.py tests/integration/test_capabilities.py -x` | No -- Wave 0 |
| TRN-08 | Iceberg catalog probe | integration | `uv run pytest tests/integration/test_capabilities.py -x` | No -- Wave 0 |
| TRN-09 | Fetch EXPLAIN variants | integration | `uv run pytest tests/integration/test_fetch_plans.py -x` | No -- Wave 0 |
| TRN-10 | system.runtime.* + Iceberg metadata | integration | `uv run pytest tests/integration/test_metadata_tables.py -x` | No -- Wave 0 |
| TRN-11 | Statement logging with hash | unit | `uv run pytest tests/adapters/test_query_logging.py -x` | No -- Wave 0 |
| TRN-12 | OfflinePlanSource | unit | `uv run pytest tests/adapters/test_offline_plan_source.py -x` | No -- Wave 0 |
| TRN-13 | Live + offline share ports | unit | `uv run pytest tests/adapters/test_port_conformance.py -x` | No -- Wave 0 |
| TRN-14 | Refuse Trino < 429 | unit | `uv run pytest tests/adapters/test_capabilities.py -x` | No -- Wave 0 |
| TRN-15 | Semaphore (max 4 concurrent) | unit | `uv run pytest tests/adapters/test_pool.py -x` | No -- Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest -m "not integration" -x`
- **Per wave merge:** `uv run pytest -x` (includes integration if Docker available)
- **Phase gate:** Full suite green before /gsd-verify-work

### Wave 0 Gaps
- [ ] `tests/safety/test_sql_classifier.py` -- TRN-04, TRN-05 classifier corpus
- [ ] `tests/adapters/test_trino_client_invariant.py` -- TRN-05 architectural invariant
- [ ] `tests/adapters/test_pool.py` -- TRN-02, TRN-15 thread pool + semaphore
- [ ] `tests/adapters/test_auth.py` -- TRN-03 auth mode construction
- [ ] `tests/adapters/test_capabilities.py` -- TRN-07, TRN-14 version parsing
- [ ] `tests/adapters/test_query_logging.py` -- TRN-11 statement logging
- [ ] `tests/adapters/test_offline_plan_source.py` -- TRN-12 offline mode
- [ ] `tests/adapters/test_port_conformance.py` -- TRN-13 port protocol check
- [ ] `tests/integration/conftest.py` -- session-scoped compose fixture
- [ ] `tests/integration/fixtures.py` -- DDL bypass helper
- [ ] `tests/integration/test_fetch_plans.py` -- TRN-01, TRN-09
- [ ] `tests/integration/test_cancellation.py` -- TRN-06
- [ ] `tests/integration/test_auth.py` -- TRN-03 live auth
- [ ] `tests/integration/test_capabilities.py` -- TRN-07, TRN-08
- [ ] `tests/integration/test_metadata_tables.py` -- TRN-10
- [ ] `tests/integration/test_event_loop_lag.py` -- TRN-02 event loop probe
- [ ] `.testing/docker-compose.yml` -- integration stack
- [ ] `.testing/trino/etc/catalog/iceberg.properties` -- Trino catalog config

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | Yes | `trino.auth.BasicAuthentication` / custom JWT; `SecretStr` for sensitive fields |
| V3 Session Management | No | No web sessions; stateless per-request |
| V4 Access Control | Yes | `SqlClassifier` read-only gate; bounded thread pool prevents resource exhaustion |
| V5 Input Validation | Yes | `sqlglot.parse` for SQL; `pydantic` for all Settings; `MAX_PLAN_JSON_LEN` for offline input |
| V6 Cryptography | No | No custom crypto; TLS handled by httpx/trino client `verify=True` |

### Known Threat Patterns for Trino Adapter

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| SQL injection via classifier bypass | Tampering | AST-based allowlist (not regex); reject multi-statement; reject Command nodes not in allowlist |
| Comment-wrapped DDL (`/* DROP */ SELECT 1`) | Tampering | sqlglot strips comments during parsing; AST contains only semantic content |
| Unicode escape tricks (`SELECT\u002A`) | Tampering | sqlglot normalizes Unicode during tokenization; classifier sees AST, not raw text |
| EXPLAIN ANALYZE wrapping dangerous SQL | Tampering | Recursive validation of inner statement extracted from Command expression |
| JWT token leakage via logs | Information Disclosure | `SecretStr`, structlog redaction denylist, statement hash instead of raw SQL |
| Orphaned queries on Trino cluster | Denial of Service | Confirmed cancellation via DELETE + polling; bounded timeout; semaphore limits concurrency |
| Thread pool exhaustion | Denial of Service | Bounded `ThreadPoolExecutor(max_workers=4)` + `asyncio.Semaphore(4)` + `TrinoPoolBusyError` |

## Sources

### Primary (HIGH confidence)
- [trino 0.337.0 on PyPI](https://pypi.org/project/trino/) -- version verified 2026-04-12
- [sqlglot 30.4.2 on PyPI](https://pypi.org/project/sqlglot/) -- version verified 2026-04-12
- [testcontainers 4.14.2 on PyPI](https://pypi.org/project/testcontainers/) -- version verified 2026-04-12
- [tenacity 9.1.4 on PyPI](https://pypi.org/project/tenacity/) -- version verified 2026-04-12
- Local sqlglot 30.4.2 testing -- Command fallback, EXPLAIN parsing, multi-statement behavior verified
- [trino-python-client dbapi.py on GitHub](https://github.com/trinodb/trino-python-client/blob/master/trino/dbapi.py) -- cursor.query_id, cancel(), close()
- [trino-python-client client.py on GitHub](https://github.com/trinodb/trino-python-client/blob/master/trino/client.py) -- TrinoQuery.cancel() sends DELETE to nextUri
- [trino-python-client auth.py on GitHub](https://github.com/trinodb/trino-python-client/blob/master/trino/auth.py) -- JWTAuthentication is static string only
- [Trino 480 REST API docs](https://trino.io/docs/current/develop/client-protocol.html) -- DELETE to nextUri terminates query
- [Trino 480 Iceberg connector docs](https://trino.io/docs/current/connector/iceberg.html) -- metadata tables ($snapshots, $files, etc.)
- [Trino 480 System connector docs](https://trino.io/docs/current/connector/system.html) -- system.runtime.* and system.metadata.* tables
- [trino-python-client Issue #84](https://github.com/trinodb/trino-python-client/issues/84) -- cursor close cancellation fix (resolved via PR #195)

### Secondary (MEDIUM confidence)
- [Lakekeeper minimal docker-compose example](https://github.com/lakekeeper/lakekeeper/tree/main/examples/minimal) -- service topology and bootstrap pattern
- [Lakekeeper getting-started docs](https://docs.lakekeeper.io/getting-started/) -- deployment overview
- [testcontainers-python DockerCompose docs](https://testcontainers-python.readthedocs.io/en/latest/core/README.html) -- session scope guidance

### Tertiary (LOW confidence)
- Trino query state values (QUEUED, PLANNING, STARTING, RUNNING, BLOCKED, FINISHING, FINISHED, FAILED) -- from web search, not directly from official schema docs
- DELETE /v1/query/{queryId} endpoint behavior -- inferred from REST API docs mentioning nextUri DELETE; direct query-id-based DELETE needs integration verification

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all versions verified on PyPI, trino-python-client source inspected
- Architecture: HIGH -- patterns verified via local sqlglot testing and GitHub source review
- Pitfalls: HIGH -- all critical pitfalls verified empirically (sqlglot Command fallback, multi-statement, cancel mechanics)
- Integration test harness: MEDIUM -- Lakekeeper compose topology from examples, exact API paths assumed
- Cancel confirmation protocol: MEDIUM -- DELETE /v1/query/{queryId} behavior inferred, needs integration verification

**Research date:** 2026-04-12
**Valid until:** 2026-05-12 (stable domain -- trino-python-client and sqlglot release cadence is ~monthly)
