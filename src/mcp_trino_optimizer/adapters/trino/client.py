"""TrinoClient — sync wrapper + async facade (D-02, D-27, D-28).

Every public method that takes a ``sql: str`` parameter calls
``self._classifier.assert_read_only(sql)`` as its **first executable line**
(TRN-05 invariant, enforced by tests/adapters/test_trino_client_invariant.py).

Thread-safety:
- Trino cursor operations run in a bounded ThreadPoolExecutor via TrinoThreadPool.
- query_id flows from the worker thread to the event loop via QueryIdCell.
- Auth refresh on 401 mutates ``self._auth`` — this is safe because:
  a) The new value is always equivalent or fresher (same env-var read),
  b) In the extreme case where two threads race on 401, both rebuild auth
     identically, so the last write wins without data loss.

Logging contract (D-28, T-02-10, T-02-11):
- Every executed statement emits ``trino_query_executed`` with:
    request_id, query_id, statement_hash (SHA-256), duration_ms,
    result_row_count, trino_state, auth_mode.
- Raw SQL is NEVER logged. Only the SHA-256 hex digest is recorded.
"""

from __future__ import annotations

import contextlib
import hashlib
import time
from datetime import UTC, datetime
from typing import Any

import trino.dbapi
import trino.exceptions

from mcp_trino_optimizer._context import (
    bind_trino_query_id,
    current_request_id,
)
from mcp_trino_optimizer.adapters.trino.auth import build_authentication
from mcp_trino_optimizer.adapters.trino.classifier import SqlClassifier
from mcp_trino_optimizer.adapters.trino.errors import TrinoAuthError, TrinoClassifierRejected
from mcp_trino_optimizer.adapters.trino.handle import (
    QueryHandle,
    QueryIdCell,
    TimeoutResult,
)
from mcp_trino_optimizer.adapters.trino.pool import TrinoThreadPool
from mcp_trino_optimizer.logging_setup import get_logger
from mcp_trino_optimizer.ports.plan_source import ExplainPlan
from mcp_trino_optimizer.settings import Settings

__all__ = ["TrinoClient"]

# Authoritative allowlist of Iceberg metadata table suffixes (CR-01 / T-02-13).
# LiveCatalogSource may apply its own fast-fail, but this is the definitive gate
# at the lowest abstraction level — regardless of which caller invokes the method.
_ALLOWED_ICEBERG_SUFFIXES: frozenset[str] = frozenset(
    {"snapshots", "files", "manifests", "partitions", "history", "refs"}
)


def _get_version() -> str:
    try:
        from importlib.metadata import version

        return version("mcp-trino-optimizer")
    except Exception:
        return "dev"


def _statement_hash(sql: str) -> str:
    return hashlib.sha256(sql.encode()).hexdigest()


def _is_401_error(exc: Exception) -> bool:
    """Return True if *exc* looks like a Trino HTTP 401 auth failure."""
    msg = str(exc).lower()
    return "401" in msg or "authentication" in msg or "unauthorized" in msg


class TrinoClient:
    """Async facade over the synchronous trino-python-client.

    All Trino HTTP calls are executed in a bounded thread pool via
    ``TrinoThreadPool``. The event loop is never blocked.

    Args:
        settings: Validated Settings instance.
        pool: TrinoThreadPool to execute synchronous Trino calls in.
    """

    def __init__(self, settings: Settings, pool: TrinoThreadPool) -> None:
        self._settings = settings
        self._pool = pool
        self._classifier = SqlClassifier()
        self._auth = build_authentication(settings)
        self._log = get_logger("trino.client")

    # ------------------------------------------------------------------
    # Public API — sql-taking methods (every one starts with classifier call)
    # ------------------------------------------------------------------

    async def fetch_plan(
        self,
        sql: str,
        *,
        timeout: float | None = None,
    ) -> ExplainPlan | TimeoutResult[ExplainPlan]:
        self._classifier.assert_read_only(sql)
        explain_sql = f"EXPLAIN (FORMAT JSON) {sql}"
        return await self._execute_explain(explain_sql, "estimated", timeout=timeout)

    async def fetch_analyze_plan(
        self,
        sql: str,
        *,
        timeout: float | None = None,
    ) -> ExplainPlan | TimeoutResult[ExplainPlan]:
        self._classifier.assert_read_only(sql)
        explain_sql = f"EXPLAIN ANALYZE {sql}"
        return await self._execute_explain(explain_sql, "executed", timeout=timeout)

    async def fetch_distributed_plan(
        self,
        sql: str,
        *,
        timeout: float | None = None,
    ) -> ExplainPlan | TimeoutResult[ExplainPlan]:
        self._classifier.assert_read_only(sql)
        explain_sql = f"EXPLAIN (TYPE DISTRIBUTED) {sql}"
        return await self._execute_explain(explain_sql, "distributed", timeout=timeout)

    async def fetch_stats(
        self,
        catalog: str,
        schema: str,
        table: str,
        *,
        timeout: float | None = None,
    ) -> list[dict[str, Any]] | TimeoutResult[list[dict[str, Any]]]:
        sql = f'SHOW STATS FOR "{catalog}"."{schema}"."{table}"'
        self._classifier.assert_read_only(sql)
        return await self._execute_query(sql, timeout=timeout)

    async def fetch_iceberg_metadata(
        self,
        catalog: str,
        schema: str,
        table: str,
        suffix: str,
        *,
        timeout: float | None = None,
    ) -> list[dict[str, Any]] | TimeoutResult[list[dict[str, Any]]]:
        if suffix not in _ALLOWED_ICEBERG_SUFFIXES:
            raise TrinoClassifierRejected(
                f"Unknown Iceberg metadata suffix {suffix!r}. Allowed: {sorted(_ALLOWED_ICEBERG_SUFFIXES)}"
            )
        sql = f'SELECT * FROM "{catalog}"."{schema}"."{table}${suffix}"'
        self._classifier.assert_read_only(sql)
        return await self._execute_query(sql, timeout=timeout)

    async def fetch_system_runtime(
        self,
        sql: str,
        *,
        timeout: float | None = None,
    ) -> list[dict[str, Any]] | TimeoutResult[list[dict[str, Any]]]:
        self._classifier.assert_read_only(sql)
        return await self._execute_query(sql, timeout=timeout)

    # ------------------------------------------------------------------
    # Public API — classifier-exempt (no sql parameter)
    # ------------------------------------------------------------------

    async def cancel_query(self, query_id: str) -> bool:
        """Cancel a running Trino query by query_id.

        Sends DELETE /v1/query/{queryId} and awaits confirmation.
        Returns True if confirmed, False if unconfirmed within budget.
        """
        http_scheme = "https" if self._settings.trino_verify_ssl else "http"
        ssl_verify: bool | str = self._settings.trino_ca_bundle or self._settings.trino_verify_ssl
        base_url = f"{http_scheme}://{self._settings.trino_host}:{self._settings.trino_port}"
        handle = QueryHandle(
            request_id=current_request_id(),
            query_id_cell=QueryIdCell(),
        )
        handle.query_id_cell.set_once(query_id)
        return await handle.cancel(base_url=base_url, ssl_verify=ssl_verify)

    async def probe_capabilities(self) -> dict[str, Any]:
        """Probe Trino version and capabilities.

        Implemented in Plan 04. Returns an empty dict until then.
        """
        return {}

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _make_connection(self) -> Any:  # trino.dbapi is untyped
        """Create a new Trino connection per request (ensures fresh JWT per D-12)."""
        http_scheme = "https" if self._settings.trino_verify_ssl else "http"
        return trino.dbapi.connect(  # type: ignore[no-untyped-call]
            host=self._settings.trino_host or "localhost",
            port=self._settings.trino_port,
            user=getattr(self._settings, "trino_user", None) or "mcp-trino-optimizer",
            catalog=self._settings.trino_catalog,
            schema=self._settings.trino_schema,
            auth=self._auth,
            http_scheme=http_scheme,
            verify=self._settings.trino_verify_ssl,
            source=f"mcp-trino-optimizer/{_get_version()}",
            client_tags=[f"mcp_request_id={current_request_id()}"],
        )

    def _run_in_thread(
        self,
        sql: str,
        handle: QueryHandle,
    ) -> list[dict[str, Any]]:
        """Synchronous Trino cursor execution (runs in thread pool).

        1. Create a fresh connection (ensures latest auth).
        2. Execute the SQL.
        3. Capture query_id into handle.query_id_cell.
        4. Fetch all rows.
        5. Close cursor + connection in finally block.

        Returns a list of row dicts.
        """
        conn = self._make_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(sql)
            qid: str = getattr(cursor, "query_id", "") or ""
            if qid:
                handle.query_id_cell.set_once(qid)
            rows = cursor.fetchall()
            description = cursor.description or []
            if description:
                col_names = [col[0] for col in description]
                return [dict(zip(col_names, row, strict=False)) for row in rows]
            return list(rows) if rows else []
        finally:
            with contextlib.suppress(Exception):
                cursor.close()
            with contextlib.suppress(Exception):
                conn.close()

    async def _execute_query(
        self,
        sql: str,
        *,
        timeout: float | None = None,
    ) -> list[dict[str, Any]] | TimeoutResult[list[dict[str, Any]]]:
        """Execute a generic query and return a list of row dicts.

        Implements D-13 retry-once on 401 and D-28 statement logging.
        """
        timeout_secs = timeout if timeout is not None else self._settings.trino_query_timeout_sec
        deadline = datetime.now(UTC).timestamp() + timeout_secs
        handle = QueryHandle(
            request_id=current_request_id(),
            wall_clock_deadline=datetime.fromtimestamp(deadline, tz=UTC),
        )

        start_ms = time.monotonic()
        result: list[dict[str, Any]] = []

        try:
            result = await self._pool.run(self._run_in_thread, sql, handle)
        except trino.exceptions.HttpError as exc:
            # Trino raises HttpError (not TrinoExternalError) for protocol-level
            # 401s such as "Password not allowed for insecure authentication".
            raise TrinoAuthError(
                f"Authentication failed: {exc}",
                request_id=handle.request_id,
                query_id=handle.query_id or "",
            ) from exc
        except trino.exceptions.TrinoExternalError as exc:
            if not _is_401_error(exc):
                raise
            # D-13: retry once with refreshed auth
            self._log.warning(
                "trino_auth_retry",
                request_id=handle.request_id,
                query_id=handle.query_id or "",
                attempt=1,
                auth_mode=self._settings.trino_auth_mode,
            )
            self._auth = build_authentication(self._settings)
            try:
                result = await self._pool.run(self._run_in_thread, sql, handle)
            except trino.exceptions.TrinoExternalError as exc2:
                if _is_401_error(exc2):
                    raise TrinoAuthError(
                        "Authentication failed after retry",
                        request_id=handle.request_id,
                        query_id=handle.query_id or "",
                    ) from exc2
                raise
        except TimeoutError:
            elapsed = int((time.monotonic() - start_ms) * 1000)
            http_scheme = "https" if self._settings.trino_verify_ssl else "http"
            ssl_verify: bool | str = self._settings.trino_ca_bundle or self._settings.trino_verify_ssl
            base_url = f"{http_scheme}://{self._settings.trino_host}:{self._settings.trino_port}"
            await handle.cancel(base_url=base_url, ssl_verify=ssl_verify)
            return TimeoutResult(
                partial=result,
                elapsed_ms=elapsed,
                query_id=handle.query_id or "",
            )

        elapsed_ms = int((time.monotonic() - start_ms) * 1000)
        if handle.query_id:
            bind_trino_query_id(handle.query_id)

        self._log.info(
            "trino_query_executed",
            request_id=handle.request_id,
            query_id=handle.query_id or "",
            statement_hash=_statement_hash(sql),
            duration_ms=elapsed_ms,
            result_row_count=len(result),
            trino_state="FINISHED",
            auth_mode=self._settings.trino_auth_mode,
        )
        return result

    async def _execute_explain(
        self,
        explain_sql: str,
        plan_type: str,
        *,
        timeout: float | None = None,
    ) -> ExplainPlan | TimeoutResult[ExplainPlan]:
        """Execute an EXPLAIN query and parse the JSON plan."""
        import json as _json

        raw = await self._execute_query(explain_sql, timeout=timeout)
        if isinstance(raw, TimeoutResult):
            empty_plan = ExplainPlan(
                plan_json={},
                plan_type=plan_type,  # type: ignore[arg-type]
                raw_text="",
            )
            return TimeoutResult(
                partial=empty_plan,
                timed_out=raw.timed_out,
                elapsed_ms=raw.elapsed_ms,
                query_id=raw.query_id,
            )

        # EXPLAIN returns one row with one column containing the JSON string
        plan_text = ""
        if raw:
            row = raw[0]
            # row is dict[str, Any] — get the single column value
            plan_text = str(next(iter(row.values()), ""))

        try:
            plan_json = _json.loads(plan_text) if plan_text else {}
        except _json.JSONDecodeError:
            plan_json = {"raw": plan_text}

        return ExplainPlan(
            plan_json=plan_json,
            plan_type=plan_type,  # type: ignore[arg-type]
            raw_text=plan_text,
        )
