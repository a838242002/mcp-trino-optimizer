---
phase: 02-trino-adapter-read-only-gate
plan: "03"
subsystem: trino-adapter
tags: [trino, adapter, concurrency, safety, logging, cancellation, tdd]
dependency_graph:
  requires:
    - 02-01-classifier-auth-settings
    - 02-02-hexagonal-ports-offline
  provides:
    - TrinoClient (fetch_plan, fetch_analyze_plan, fetch_distributed_plan, fetch_stats, fetch_iceberg_metadata, fetch_system_runtime, cancel_query, probe_capabilities)
    - TrinoThreadPool (bounded concurrency + semaphore backpressure)
    - QueryHandle + QueryIdCell + TimeoutResult
    - TRN-05 architectural invariant test (AST-based)
  affects:
    - All future plans that perform live Trino queries
    - Plan 04 (capability probing) builds on TrinoClient.probe_capabilities stub
tech_stack:
  added:
    - httpx.AsyncClient for DELETE /v1/query/{queryId} confirmed cancel
    - threading.Event for thread-safe QueryIdCell
    - asyncio.Semaphore(max_workers) for pool backpressure
    - hashlib.sha256 for statement logging (never raw SQL)
    - ast module for TRN-05 compile-time invariant check
  patterns:
    - Thread-safe write-once cell pattern (QueryIdCell) for cross-thread id propagation
    - Generic TimeoutResult[T] for partial-results-on-timeout (K-Decision 13)
    - Retry-once on 401 with log event (D-13)
    - AST introspection test as architectural regression guard (D-03)
key_files:
  created:
    - src/mcp_trino_optimizer/adapters/trino/handle.py
    - src/mcp_trino_optimizer/adapters/trino/pool.py
    - src/mcp_trino_optimizer/adapters/trino/client.py
    - tests/adapters/test_pool.py
    - tests/adapters/test_trino_client_invariant.py
    - tests/adapters/test_query_logging.py
    - tests/adapters/test_auth_retry.py
  modified:
    - src/mcp_trino_optimizer/_context.py (added bind_trino_query_id + current_trino_query_id)
decisions:
  - fetch_system_runtime parameter renamed from query_sql to sql for consistency with TRN-05 invariant pattern
  - fetch_stats and fetch_iceberg_metadata build SQL internally (catalog/schema/table params) — they call assert_read_only on the constructed SQL but are not in the sql: str param category tested by the AST invariant
  - TrinoClient._make_connection return type annotated as Any due to trino.dbapi being untyped (type: ignore[no-untyped-call] on connect call)
metrics:
  duration_seconds: 496
  completed_date: "2026-04-12"
  tasks_completed: 2
  files_created: 7
  files_modified: 1
  tests_added: 31
  tests_passing: 189
---

# Phase 02 Plan 03: Trino Client Pool Cancel Summary

**One-liner:** TrinoClient with classifier-first invariant (TRN-05), bounded ThreadPoolExecutor + semaphore backpressure, confirmed httpx cancel, SHA-256 statement logging, and retry-once on 401.

## What Was Built

### Task 1: QueryHandle + QueryIdCell + TimeoutResult + TrinoThreadPool

**`handle.py`** — three complementary types for per-request lifecycle management:

- `QueryIdCell`: thread-safe write-once holder using `threading.Event`. The worker thread calls `set_once(query_id)` after `cursor.execute()`; the async event loop reads via `wait_for(timeout)` or the non-blocking `value` property.
- `TimeoutResult[T]`: generic dataclass returned instead of raising when the wall-clock deadline is exceeded. Carries `partial`, `elapsed_ms`, `query_id`, and a fixed `reason="wall_clock_deadline"` literal (K-Decision #13).
- `QueryHandle`: per-request state object with `request_id`, `query_id_cell`, `started_at`, and `wall_clock_deadline`. The `cancel()` async method sends `DELETE /v1/query/{queryId}` via `httpx.AsyncClient` and polls with exponential backoff [0.1, 0.3, 0.9, 2.7] seconds, returning True on confirmation or False with a `cancel_unconfirmed` WARN log if the budget is exhausted.

**`pool.py`** — `TrinoThreadPool`:
- Wraps `concurrent.futures.ThreadPoolExecutor(max_workers=N, thread_name_prefix="trino-")`
- Paired `asyncio.Semaphore(N)` provides backpressure: `acquire()` with a 0.1 s timeout; raises `TrinoPoolBusyError` immediately if all slots are occupied (T-02-08 mitigation)
- `run(fn, *args, **kwargs)` offloads to the executor via `loop.run_in_executor()` and releases the semaphore in a `finally` block

**`_context.py` extension:**
- Added `bind_trino_query_id(query_id)` and `current_trino_query_id()` using a `contextvars.ContextVar` + `structlog.contextvars.bind_contextvars` for structured log correlation

**`test_pool.py`** — 11 unit tests covering:
- Pool run with args / kwargs
- TrinoPoolBusyError when slot is held
- Sequential execution with max_workers=1
- QueryIdCell set_once idempotency and cross-thread wait_for
- TimeoutResult default fields and custom values

### Task 2: TrinoClient + Architectural Invariant Test + Query Logging

**`client.py`** — `TrinoClient` with 8 public methods:

| Method | sql: str param? | Classifier call |
|--------|-----------------|-----------------|
| `fetch_plan(sql)` | yes | `assert_read_only(sql)` first line |
| `fetch_analyze_plan(sql)` | yes | `assert_read_only(sql)` first line |
| `fetch_distributed_plan(sql)` | yes | `assert_read_only(sql)` first line |
| `fetch_system_runtime(sql)` | yes | `assert_read_only(sql)` first line |
| `fetch_stats(catalog, schema, table)` | no (builds SQL internally) | `assert_read_only(built_sql)` after construction |
| `fetch_iceberg_metadata(catalog, schema, table, suffix)` | no (builds SQL internally) | `assert_read_only(built_sql)` after construction |
| `cancel_query(query_id)` | no | classifier-exempt |
| `probe_capabilities()` | no | classifier-exempt |

Key behaviors:
- `_run_in_thread`: creates fresh connection, executes SQL, captures `cursor.query_id` into `QueryIdCell`, fetches all rows, closes cursor + connection in finally
- `_execute_query`: D-13 retry-once on 401 (checks `TrinoExternalError` message for "401"/"authentication"/"unauthorized"), emits `trino_auth_retry` log event with `{request_id, query_id, attempt, auth_mode}` (no token value)
- `_execute_query`: emits `trino_query_executed` log event with `{request_id, query_id, statement_hash, duration_ms, result_row_count, trino_state, auth_mode}` — raw SQL is NEVER logged
- `_execute_explain`: wraps `_execute_query` with EXPLAIN prefix, parses JSON plan

**`test_trino_client_invariant.py`** — 10 AST-based tests:
- Parses client.py at test time using `ast.AsyncFunctionDef`
- Verifies `_is_assert_read_only_call()` on the first executable statement of each sql-taking method
- Explicitly checks cancel_query and probe_capabilities have no sql param
- `test_all_required_methods_present` enumerates all 8 methods
- `test_sql_str_param_methods_enumerated` locks down the exact set of sql: str methods

**`test_query_logging.py`** — 4 tests:
- `trino_query_executed` event emitted after execution
- Raw SQL never appears in any log line
- `statement_hash = SHA-256(sql).hexdigest()`
- `request_id` present in log event

**`test_auth_retry.py`** — 6 tests:
- Retry once on 401, return result
- Double-401 raises `TrinoAuthError`
- `trino_auth_retry` event emitted with correct fields
- No JWT token in retry log event
- Non-401 errors not retried
- No `trino_auth_retry` event for non-401 errors

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] fetch_system_runtime parameter renamed from query_sql to sql**
- **Found during:** Task 2 (TRN-05 invariant test failure)
- **Issue:** Plan interface spec used `query_sql` as the parameter name, but the TRN-05 invariant test specifically looks for parameters named `sql`. The AST check `_has_sql_str_param` returned False for `query_sql`.
- **Fix:** Renamed `query_sql: str` to `sql: str` in `fetch_system_runtime`. Consistent with all other sql-taking methods.
- **Files modified:** `src/mcp_trino_optimizer/adapters/trino/client.py`
- **Commit:** af79646

**2. [Rule 2 - Missing critical functionality] fetch_stats / fetch_iceberg_metadata not in sql: str invariant test**
- **Found during:** Task 2 (test parametrize list initially included them)
- **Issue:** These methods take `catalog/schema/table` params and build SQL internally, so `_has_sql_str_param()` correctly returns False for them. The parametrize list was wrong.
- **Fix:** Removed from parametrize list; added `test_all_required_methods_present` to verify all 8 methods exist, and `test_sql_str_param_methods_enumerated` to lock down the exact set.
- **Files modified:** `tests/adapters/test_trino_client_invariant.py`
- **Commit:** af79646

**3. [Rule 1 - Bug] mypy unreachable branch in _execute_explain**
- **Found during:** Task 2 post-implementation mypy check
- **Issue:** `raw` is typed as `list[dict[str, Any]]` after the `TimeoutResult` check, so `row` is always `dict` — the `elif isinstance(row, (list, tuple))` branch was unreachable.
- **Fix:** Simplified to direct dict access: `str(next(iter(row.values()), ""))`.
- **Files modified:** `src/mcp_trino_optimizer/adapters/trino/client.py`
- **Commit:** af79646

### Pre-existing Issues (Deferred)

- `auth.py:24`: `types-requests` stubs not installed — pre-existing from Plan 01, not introduced by this plan. Tracked in deferred-items.

## Known Stubs

- `probe_capabilities()` returns `{}` — stub implementation. Full capability probing (Trino version check, Iceberg catalog detection) is the responsibility of Plan 04.

## Threat Flags

None — all threat register mitigations (T-02-07 through T-02-11) from the plan's threat model are implemented:

| Threat | Mitigation Implemented |
|--------|----------------------|
| T-02-07 (Tampering) | assert_read_only(sql) as first line; TRN-05 AST test in CI |
| T-02-08 (DoS - pool) | asyncio.Semaphore(max_workers) + 0.1s acquire timeout → TrinoPoolBusyError |
| T-02-09 (DoS - cluster) | DELETE /v1/query/{queryId} + exponential backoff polling in QueryHandle.cancel() |
| T-02-10 (Info Disclosure) | SHA-256 hash only; raw SQL never logged; verified by test_raw_sql_never_in_log |
| T-02-11 (Repudiation) | Every query logged with request_id, query_id, statement_hash, duration_ms, auth_mode; X-Trino-Client-Tags propagation |

## Self-Check


## Self-Check: PASSED

All 7 created files verified on disk. All 3 task commits verified in git history:
- 40d0ae0: feat(02-03): QueryHandle + QueryIdCell + TimeoutResult + TrinoThreadPool
- 95914d2: test(02-03): add failing tests for TrinoClient invariant, logging, auth retry
- af79646: feat(02-03): TrinoClient + TRN-05 architectural invariant test + logging + auth retry

Full non-integration test suite: 189 passed in 1.52s
