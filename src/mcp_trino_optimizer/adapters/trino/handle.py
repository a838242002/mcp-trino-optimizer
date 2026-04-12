"""QueryHandle, QueryIdCell, and TimeoutResult — D-06, D-07, D-08, D-10.

QueryIdCell: thread-safe holder for the Trino query_id that is only known
after cursor.execute() returns inside the worker thread.

QueryHandle: per-request state object carrying the cell + wall-clock deadline.
Cancel sends DELETE /v1/query/{queryId} and polls for confirmation (D-08).

TimeoutResult: returned instead of raising when the wall-clock deadline is
exceeded; carries whatever partial data was collected before timeout (D-10).
"""

from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Generic, Literal, TypeVar

import httpx
import structlog

__all__ = ["QueryHandle", "QueryIdCell", "TimeoutResult"]

T = TypeVar("T")

_log = structlog.get_logger("trino.handle")

# Exponential-backoff poll intervals for cancel confirmation (cap ~4 s).
_CANCEL_POLL_INTERVALS: tuple[float, ...] = (0.1, 0.3, 0.9, 2.7)
_TERMINAL_STATES: frozenset[str] = frozenset({"FINISHED", "FAILED", "CANCELED"})


class QueryIdCell:
    """Thread-safe, write-once holder for a Trino query_id string.

    The query_id is assigned by the Trino server after cursor.execute()
    runs in the worker thread. This cell lets the async event-loop read
    the id as soon as it becomes available, without busy-waiting.
    """

    def __init__(self) -> None:
        self._event = threading.Event()
        self._value: str | None = None

    def set_once(self, query_id: str) -> None:
        """Store *query_id* and fire the event. Idempotent — no-op if already set."""
        if self._value is not None:
            return
        self._value = query_id
        self._event.set()

    def wait_for(self, timeout: float) -> str | None:
        """Block up to *timeout* seconds; return value or None on timeout."""
        self._event.wait(timeout=timeout)
        return self._value

    @property
    def value(self) -> str | None:
        """Return the current value without blocking."""
        return self._value


@dataclass
class TimeoutResult(Generic[T]):
    """Returned instead of raising when the wall-clock deadline is exceeded.

    Carries whatever partial data was available at timeout, plus metadata for
    structured logging and retry decisions.
    """

    partial: T
    timed_out: bool = True
    elapsed_ms: int = 0
    query_id: str = ""
    reason: Literal["wall_clock_deadline"] = "wall_clock_deadline"


@dataclass
class QueryHandle:
    """Per-request state object: query_id cell + wall-clock deadline + cancel.

    Created at the start of every TrinoClient method call that executes SQL.
    """

    request_id: str
    query_id_cell: QueryIdCell = field(default_factory=QueryIdCell)
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    wall_clock_deadline: datetime = field(default_factory=lambda: datetime.now(UTC))

    # Internal cancel-idempotency flag
    _cancelled: bool = field(default=False, init=False, repr=False)

    @property
    def query_id(self) -> str | None:
        """Non-blocking read of the Trino query_id (may be None before execute)."""
        return self.query_id_cell.value

    async def cancel(
        self,
        base_url: str,
        auth_headers: dict[str, str] | None = None,
    ) -> bool:
        """Send DELETE /v1/query/{queryId} and poll for confirmation.

        Implements D-08 / RESEARCH.md Pattern 4:
        1. If query_id is unknown, return False (nothing to cancel).
        2. DELETE /v1/query/{query_id} — expect 204.
        3. Poll GET /v1/query/{query_id} with exponential backoff intervals.
        4. Terminal state (FINISHED/FAILED/CANCELED) or 404 → return True.
        5. Budget exhausted → log cancel_unconfirmed at WARN, return False.
        6. Idempotent: subsequent calls are no-ops returning True.

        Args:
            base_url: Trino coordinator base URL, e.g. "http://localhost:8080".
            auth_headers: Optional dict of HTTP headers for auth (Bearer / Basic).

        Returns:
            True if cancellation confirmed, False if unconfirmed within budget.
        """
        if self._cancelled:
            return True

        qid = self.query_id
        if qid is None:
            # query_id not yet assigned — nothing to cancel
            return False

        headers = dict(auth_headers or {})

        async with httpx.AsyncClient(base_url=base_url, headers=headers) as client:
            # Step 1: fire the DELETE
            try:
                resp = await client.delete(f"/v1/query/{qid}")
                if resp.status_code == 204:
                    self._cancelled = True
                    return True
            except httpx.HTTPError:
                pass  # Network blip — fall through to polling

            # Step 2: poll for terminal state
            for interval in _CANCEL_POLL_INTERVALS:
                await asyncio.sleep(interval)
                try:
                    poll = await client.get(f"/v1/query/{qid}")
                    if poll.status_code == 404:
                        self._cancelled = True
                        return True
                    body = poll.json()
                    state: str = body.get("state", "")
                    if state in _TERMINAL_STATES:
                        self._cancelled = True
                        return True
                except (httpx.HTTPError, ValueError):
                    pass  # Continue polling

        # Budget exhausted
        _log.warning(
            "cancel_unconfirmed",
            query_id=qid,
            request_id=self.request_id,
        )
        return False
