---
phase: "02"
status: complete
reviewed_at: "2026-04-12"
findings_critical: 1
findings_high: 4
findings_medium: 5
findings_low: 3
---

# Phase 02: Code Review Report

**Reviewed:** 2026-04-12
**Depth:** standard
**Files Reviewed:** 21
**Status:** issues_found

## Summary

Phase 02 delivers the Trino adapter stack: auth, SQL classifier, connection pooling, async/sync bridging, capabilities probing, and live/offline port implementations. The overall architecture is sound — the hexagonal port/adapter separation is clean, the classifier uses AST-based analysis (sqlglot) rather than regex, and the logging contract is correctly security-conscious (SHA-256 hash of SQL, never raw SQL). However, several correctness bugs and one critical security issue were found.

The critical issue is an identifier injection vector in `fetch_iceberg_metadata` inside `TrinoClient`: the `suffix` parameter is appended directly into the SQL string without any validation at that layer, meaning the `_ALLOWED_SUFFIXES` allowlist in `LiveCatalogSource` is the only guard — and it is not enforced on the public `TrinoClient.fetch_iceberg_metadata` method itself.

The high-severity issues are: (1) the semaphore leak when `asyncio.wait_for` cancels the underlying `acquire()` coroutine, (2) using the deprecated `asyncio.get_event_loop()` inside `TrinoThreadPool.run`, (3) `SHOW CATALOGS` routed through `fetch_system_runtime` which applies the classifier — `SHOW CATALOGS` is an `exp.Command`, so it passes, but the intent (stats/system path vs. catalog path) creates a confusing and fragile invariant, and (4) the `cancel_query` method uses HTTP vs HTTPS based on `trino_auth_mode != "none"` rather than `trino_verify_ssl`, which will send plaintext cancel requests against a cluster configured with `basic` auth over HTTPS.

---

## Critical Issues

### CR-01: SQL Injection via unvalidated `suffix` in `TrinoClient.fetch_iceberg_metadata`

**File:** `src/mcp_trino_optimizer/adapters/trino/client.py:145`

**Issue:** `TrinoClient.fetch_iceberg_metadata` constructs the SQL string by directly interpolating the `suffix` parameter into a `SELECT *` query with no validation:

```python
sql = f'SELECT * FROM "{catalog}"."{schema}"."{table}${suffix}"'
```

The suffix allowlist (`_ALLOWED_SUFFIXES`) lives only in `LiveCatalogSource.fetch_iceberg_metadata` (line 64 of `live_catalog_source.py`). Any caller that bypasses `LiveCatalogSource` and calls `TrinoClient.fetch_iceberg_metadata` directly — including future tools, tests, or internal code — can inject arbitrary SQL text after the `$` character in the table reference. For example, suffix `snapshots" UNION SELECT password FROM system.users --` would produce syntactically valid SQL, and the SqlClassifier (`assert_read_only`) would pass it because the top-level statement is still a `SELECT`.

**Fix:** Move the allowlist check into `TrinoClient.fetch_iceberg_metadata` so the public method on the lowest-level class is hardened, regardless of which higher-level adapter calls it:

```python
# In client.py, at the top of the module:
_ALLOWED_ICEBERG_SUFFIXES: frozenset[str] = frozenset(
    {"snapshots", "files", "manifests", "partitions", "history", "refs"}
)

# In TrinoClient.fetch_iceberg_metadata:
async def fetch_iceberg_metadata(self, catalog, schema, table, suffix, *, timeout=None):
    if suffix not in _ALLOWED_ICEBERG_SUFFIXES:
        raise TrinoClassifierRejected(
            f"Unknown Iceberg metadata suffix {suffix!r}. "
            f"Allowed: {sorted(_ALLOWED_ICEBERG_SUFFIXES)}"
        )
    sql = f'SELECT * FROM "{catalog}"."{schema}"."{table}${suffix}"'
    self._classifier.assert_read_only(sql)
    return await self._execute_query(sql, timeout=timeout)
```

The allowlist in `LiveCatalogSource` can remain as a fast-fail for the port layer, but the authoritative gate must be at the lowest abstraction level.

---

## High Severity

### HI-01: Semaphore leak on `asyncio.wait_for` cancellation in `TrinoThreadPool.run`

**File:** `src/mcp_trino_optimizer/adapters/trino/pool.py:64-73`

**Issue:** When `asyncio.wait_for(self._semaphore.acquire(), timeout=_ACQUIRE_TIMEOUT)` raises `asyncio.TimeoutError`, the implementation correctly re-raises as `TrinoPoolBusyError`. However, in Python 3.11+ the cancellation of the wrapped `acquire()` coroutine by `wait_for` can (depending on asyncio scheduler timing) cause the semaphore's internal counter to decrement without a corresponding release. This is a known Python issue (bpo-45584) — the `acquire()` coroutine can complete between the `TimeoutError` being raised and the `wait_for` cleanup running.

The result is that under sustained load the effective semaphore capacity silently shrinks below `max_workers`, causing `TrinoPoolBusyError` to be raised even when worker threads are idle.

**Fix:** Use `asyncio.wait_for` with a cancellation shield or restructure using `asyncio.Semaphore` with `acquire()` wrapped in a `try/except`:

```python
try:
    await asyncio.wait_for(
        asyncio.shield(self._semaphore.acquire()),
        timeout=_ACQUIRE_TIMEOUT,
    )
except asyncio.TimeoutError:
    # asyncio.shield ensures the acquire() coroutine is not cancelled;
    # the semaphore counter is not decremented on timeout.
    raise TrinoPoolBusyError(...)
```

Alternatively, use `asyncio.Semaphore.acquire()` directly with a manual `asyncio.wait_for` loop and explicit release-on-cancel pattern.

### HI-02: Deprecated `asyncio.get_event_loop()` in `TrinoThreadPool.run`

**File:** `src/mcp_trino_optimizer/adapters/trino/pool.py:75`

**Issue:** `loop = asyncio.get_event_loop()` is deprecated as of Python 3.10 and will emit a `DeprecationWarning` (or raise `RuntimeError`) when called from a coroutine context without a running loop, or when called from a thread. Since `run()` is an `async` method, the correct API is `asyncio.get_running_loop()`, which is guaranteed to return the loop for the currently executing coroutine.

**Fix:**
```python
loop = asyncio.get_running_loop()
```

### HI-03: Wrong scheme selection in `cancel_query` — plaintext cancel over HTTPS-configured clusters

**File:** `src/mcp_trino_optimizer/adapters/trino/client.py:168-170`

**Issue:** The scheme for the cancel URL is chosen as:

```python
f"{'https' if self._settings.trino_auth_mode != 'none' else 'http'}"
```

This logic is wrong in two ways:
1. A cluster configured with `trino_auth_mode="basic"` but `trino_verify_ssl=False` (e.g., a dev cluster with self-signed certs) will get `https://` but the cancel request will fail TLS verification.
2. More importantly, `_execute_query` (line 292-294) also constructs the cancel URL with the same flawed logic — neither path uses `trino_verify_ssl` or the CA bundle when constructing the `httpx.AsyncClient`.

The httpx client in `QueryHandle.cancel` is created with no `verify=` argument, defaulting to `True`. If the cluster uses self-signed certs and `trino_verify_ssl=False`, the cancel HTTP call will fail with an SSL error, leaving the query running on the server.

**Fix:** Pass the SSL configuration from settings into the cancel call. Either thread `settings` into `QueryHandle.cancel`, or pass the resolved `verify` value:

```python
# In TrinoClient.cancel_query and _execute_query timeout handler:
http_scheme = "https" if self._settings.trino_verify_ssl else "http"
verify: bool | str = (
    self._settings.trino_ca_bundle or self._settings.trino_verify_ssl
)
# Pass verify into QueryHandle.cancel(base_url=..., ssl_verify=verify)
```

And update `QueryHandle.cancel` to accept and use `ssl_verify`:

```python
async with httpx.AsyncClient(base_url=base_url, headers=headers, verify=ssl_verify) as client:
```

### HI-04: Race condition in `QueryIdCell.set_once` — non-atomic check-then-set

**File:** `src/mcp_trino_optimizer/adapters/trino/handle.py:47-51`

**Issue:** `set_once` checks `self._value is not None` and then writes `self._value = query_id` without a lock. The `threading.Event` is thread-safe, but the `_value` attribute is not protected by any lock. If two threads simultaneously call `set_once` with different values, both could pass the `is not None` check before either has written, resulting in a race between two writes. In practice this is unlikely (cursor.execute is called once per connection), but the abstraction advertises thread-safety and does not deliver it.

**Fix:** Add a `threading.Lock` to protect the check-then-set:

```python
class QueryIdCell:
    def __init__(self) -> None:
        self._event = threading.Event()
        self._value: str | None = None
        self._lock = threading.Lock()

    def set_once(self, query_id: str) -> None:
        with self._lock:
            if self._value is not None:
                return
            self._value = query_id
        self._event.set()
```

---

## Medium Severity

### ME-01: `SHOW CATALOGS` routed through `fetch_system_runtime` bypasses intent separation

**File:** `src/mcp_trino_optimizer/adapters/trino/live_catalog_source.py:82` and `src/mcp_trino_optimizer/adapters/trino/capabilities.py:127`

**Issue:** `SHOW CATALOGS` and `SHOW SCHEMAS IN ...` are issued via `client.fetch_system_runtime()`, a method documented in the port as "query against `system.runtime.*`". These are not system.runtime queries — they are DDL commands. This works because the SqlClassifier allows `exp.Command` nodes with the `SHOW` prefix, but it violates the method's documented contract, making the code harder to reason about and test. A future refactor that adds system.runtime-specific validation to `fetch_system_runtime` would silently break catalog probing.

**Fix:** Add a dedicated `fetch_command(sql)` method to `TrinoClient` (or route these through `_execute_query` directly), and expose it with appropriate classifier gating. Alternatively, rename `fetch_system_runtime` to `fetch_read_only_query` to match its actual semantics.

### ME-02: `_is_401_error` heuristic is fragile and produces false positives

**File:** `src/mcp_trino_optimizer/adapters/trino/client.py:66-69`

**Issue:** The 401 detection matches any exception whose string representation contains "401", "authentication", or "unauthorized" (case-insensitive). A Trino query that returns a legitimate error message such as `"Query failed: authentication step count exceeded 401 retries"` or a table named `authentication_log` in the error context would trigger an unintended retry. The retry-once-on-401 behavior is correct, but the detection should be more precise.

**Fix:** Check the `trino.exceptions.TrinoExternalError` error code field rather than string-matching:

```python
def _is_401_error(exc: trino.exceptions.TrinoExternalError) -> bool:
    # TrinoExternalError carries error_code and status_code from the server
    return getattr(exc, "status_code", None) == 401
```

Verify the exact attribute name from the trino-python-client source (`error_code`, `status_code`, or HTTP status via the underlying requests.Response).

### ME-03: `OfflinePlanSource._validate_size` encodes full string to bytes unnecessarily

**File:** `src/mcp_trino_optimizer/adapters/offline/json_plan_source.py:139`

**Issue:** `len(text.encode("utf-8"))` allocates a full copy of the input string as bytes just to measure its length. For inputs near the 1MB limit this doubles peak memory usage momentarily. Given that this is called at tool entry with potentially large EXPLAIN outputs, this is a needless spike.

**Fix:**
```python
# Use sys.getsizeof approximation or codec-based length without copy:
import codecs
byte_len = codecs.encode(text, "utf-8").find  # No — use the proper approach:

# Actually, for correctness without full copy (Python 3.11+):
byte_len = len(text.encode("utf-8", errors="surrogatepass"))
# This still copies. Best approach: use len() with a streaming encoder or
# accept a small (necessary) memory spike and document it as a known tradeoff.
# If the spike is unacceptable: reject based on len(text) * 4 as a fast upper bound.
```

For now, document the allocation behavior in a comment. Alternatively, use `len(text) * 4 > MAX_PLAN_BYTES` as a fast-path rejection before the precise measurement.

### ME-04: `probe_capabilities` issues `SELECT *` from a non-existent dummy table through `fetch_system_runtime`

**File:** `src/mcp_trino_optimizer/adapters/trino/capabilities.py:159-163`

**Issue:**

```python
await client.fetch_system_runtime(
    f'SELECT * FROM "{iceberg_catalog_name}"."{first_schema}"."__dummy_probe__$snapshots" LIMIT 1'
)
```

This probes Iceberg metadata availability by querying a table named `__dummy_probe__` that is guaranteed to not exist. The logic then catches the exception and sets `iceberg_metadata_available = True` on the assumption that a table-not-found error means the metadata table feature itself works. This is unreliable: Trino can raise table-not-found for many reasons unrelated to metadata table support (permission denied, catalog not ready, network blip). The heuristic will incorrectly report `iceberg_metadata_tables_available=True` even when the cluster cannot actually serve metadata queries.

**Fix:** Instead of probing a non-existent table, probe a known metadata table on the first real table found in `first_schema`:

```python
table_rows = await client.fetch_system_runtime(
    f'SHOW TABLES IN "{iceberg_catalog_name}"."{first_schema}" LIMIT 1'
)
if table_rows and isinstance(table_rows, list):
    first_table = str(table_rows[0].get("Table", table_rows[0].get("table", "")))
    if first_table:
        meta_rows = await client.fetch_iceberg_metadata(
            iceberg_catalog_name, first_schema, first_table, "snapshots"
        )
        iceberg_metadata_available = isinstance(meta_rows, list)
```

If no tables exist in any schema, leave `iceberg_metadata_available=False` (conservative).

### ME-05: `_execute_query` deadline is computed from wall clock but never enforced against the thread execution

**File:** `src/mcp_trino_optimizer/adapters/trino/client.py:254-265`

**Issue:** A `wall_clock_deadline` is set on the `QueryHandle`, but it is never used to actually enforce the timeout on the thread execution. `TrinoThreadPool.run()` does not accept a `timeout` parameter — it runs the thread to completion. The `asyncio.TimeoutError` caught at line 288 would only fire if `TrinoPool.run()` itself raised it, which it does not: `asyncio.wait_for` wraps only the semaphore acquisition (0.1s), not the thread execution. Therefore the `trino_query_timeout_sec` setting has **no effect** on long-running queries. The `asyncio.TimeoutError` branch in `_execute_query` is dead code.

**Fix:** Wrap the `pool.run()` call with `asyncio.wait_for`:

```python
try:
    result = await asyncio.wait_for(
        self._pool.run(self._run_in_thread, sql, handle),
        timeout=timeout_secs,
    )
except asyncio.TimeoutError:
    # cancel and return TimeoutResult as currently implemented
    ...
```

Note that `asyncio.wait_for` cancels the coroutine wrapper but the thread itself will continue running until the Trino cursor completes or the connection is dropped. Combine with the `handle.cancel()` call (already in the timeout handler) to send the server-side cancellation signal.

---

## Low Severity

### LO-01: Redundant `.get("node_version", ...)` with the same key in `probe_capabilities`

**File:** `src/mcp_trino_optimizer/adapters/trino/capabilities.py:110-113`

**Issue:** The version extraction reads:

```python
version_rows[0].get("node_version", version_rows[0].get("node_version", ""))
```

The fallback key is identical to the primary key — this is almost certainly a copy-paste artifact and the intent was to try a differently-cased column name (e.g., `"Node Version"` as Trino might return it).

**Fix:**
```python
version_str: str = str(
    version_rows[0].get("node_version", version_rows[0].get("Node Version", ""))
    if isinstance(version_rows[0], dict)
    else version_rows[0]
)
```

### LO-02: `assert` used for invariant enforcement in production code path (`auth.py`)

**File:** `src/mcp_trino_optimizer/adapters/trino/auth.py:85-86`

**Issue:**

```python
assert settings.trino_user is not None, "trino_user must be set for basic auth"
assert settings.trino_password is not None, "trino_password must be set for basic auth"
```

`assert` statements are stripped by Python's optimizer when run with `-O` (optimize flag). Docker images commonly set `PYTHONOPTIMIZE=1` or use `-O` for production deployments. If the Settings validator were somehow bypassed (e.g., directly constructing a Settings object in a test), the assertion would silently not fire, and `trino_password.get_secret_value()` on a `None` object would raise an `AttributeError` with a confusing message.

**Fix:** Replace with explicit `if` checks raising `TrinoAuthError` or `ValueError`:

```python
if settings.trino_user is None:
    raise ValueError("trino_user must be set for basic auth (internal invariant violation)")
if settings.trino_password is None:
    raise ValueError("trino_password must be set for basic auth (internal invariant violation)")
```

### LO-03: `PerCallJWTAuthentication` silently sends an empty bearer token if env var is unset

**File:** `src/mcp_trino_optimizer/adapters/trino/auth.py:57-58`

**Issue:**

```python
token = os.environ.get(self._env_var, "")
http_session.headers["Authorization"] = f"Bearer {token}"
```

If `MCPTO_TRINO_JWT` is absent from the environment at call time (e.g., after a rotation that removed the old variable before setting the new one), the authorization header becomes `"Bearer "` — an invalid but non-empty header. Trino will reject this with a 401, triggering the retry logic in `_execute_query`, which will also fail. The error message from Trino ("invalid bearer token") will be less clear than a proactive check.

**Fix:** Raise `TrinoAuthError` rather than silently sending an empty token:

```python
token = os.environ.get(self._env_var, "")
if not token:
    raise TrinoAuthError(
        f"JWT token env var {self._env_var!r} is empty or unset at call time. "
        "Ensure the token rotation completed before the next request."
    )
http_session.headers["Authorization"] = f"Bearer {token}"
```

---

_Reviewed: 2026-04-12_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
