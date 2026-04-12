---
phase: "02"
fixed_at: "2026-04-12T00:00:00Z"
review_path: .planning/phases/02-trino-adapter-read-only-gate/02-REVIEW.md
iteration: 1
findings_in_scope: 5
fixed: 5
skipped: 0
status: all_fixed
---

# Phase 02: Code Review Fix Report

**Fixed at:** 2026-04-12
**Source review:** .planning/phases/02-trino-adapter-read-only-gate/02-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 5 (1 Critical, 4 High)
- Fixed: 5
- Skipped: 0

## Fixed Issues

### CR-01: SQL Injection via unvalidated `suffix` in `TrinoClient.fetch_iceberg_metadata`

**Files modified:** `src/mcp_trino_optimizer/adapters/trino/client.py`
**Commit:** 65926e2
**Applied fix:** Added module-level `_ALLOWED_ICEBERG_SUFFIXES: frozenset[str]` constant and a guard at the top of `fetch_iceberg_metadata` that raises `TrinoClassifierRejected` if the suffix is not in the allowlist. Also imported `TrinoClassifierRejected` in the imports. The `LiveCatalogSource` allowlist is preserved as a fast-fail at the port layer; the new check is the authoritative gate at the lowest level.

### HI-01: Semaphore leak on `asyncio.wait_for` cancellation in `TrinoThreadPool.run`

**Files modified:** `src/mcp_trino_optimizer/adapters/trino/pool.py`
**Commit:** 65926e2
**Applied fix:** Wrapped `self._semaphore.acquire()` with `asyncio.shield()` before passing to `asyncio.wait_for`. This prevents `wait_for` from cancelling the acquire coroutine on timeout, closing the bpo-45584 race where the semaphore counter could be decremented without a corresponding release. Added an explanatory comment referencing the bug report.

### HI-02: Deprecated `asyncio.get_event_loop()` in `TrinoThreadPool.run`

**Files modified:** `src/mcp_trino_optimizer/adapters/trino/pool.py`
**Commit:** 65926e2
**Applied fix:** Replaced `asyncio.get_event_loop()` with `asyncio.get_running_loop()` at pool.py:79. Since `run()` is an `async` method, `get_running_loop()` is correct and guaranteed to return the current event loop without DeprecationWarning.

### HI-03: Wrong scheme selection in `cancel_query` — plaintext cancel over HTTPS-configured clusters

**Files modified:** `src/mcp_trino_optimizer/adapters/trino/client.py`, `src/mcp_trino_optimizer/adapters/trino/handle.py`
**Commit:** 65926e2
**Applied fix:** Both `cancel_query` and the `asyncio.TimeoutError` handler in `_execute_query` now derive `http_scheme` from `trino_verify_ssl` (not `trino_auth_mode`) and compute `ssl_verify = trino_ca_bundle or trino_verify_ssl`. Both call `handle.cancel(base_url=..., ssl_verify=ssl_verify)`. `QueryHandle.cancel` was updated to accept `ssl_verify: bool | str = True` and pass it as `verify=ssl_verify` to `httpx.AsyncClient`.

### HI-04: Race condition in `QueryIdCell.set_once` — non-atomic check-then-set

**Files modified:** `src/mcp_trino_optimizer/adapters/trino/handle.py`
**Commit:** 65926e2
**Applied fix:** Added `self._lock = threading.Lock()` to `QueryIdCell.__init__` and wrapped the check-then-set in `set_once` with `with self._lock:`. The `self._event.set()` call is intentionally placed after the lock is released to avoid holding the lock during the event notification.

---

_Fixed: 2026-04-12_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
