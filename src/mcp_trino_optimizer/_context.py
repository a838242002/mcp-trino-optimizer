"""Request-ID contextvars for structlog binding (RESEARCH.md §5.2).

FastMCP's async tool dispatch uses anyio, which propagates Python
contextvars natively. Binding request_id at tool entry ensures every
log call inside the tool handler inherits it without manual plumbing.
"""

from __future__ import annotations

import contextvars
import uuid

import structlog

_request_id: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="")
_trino_query_id: contextvars.ContextVar[str] = contextvars.ContextVar("trino_query_id", default="")


def new_request_id() -> str:
    """Generate + bind a new request_id; returns it for caller use."""
    rid = uuid.uuid4().hex[:16]
    _request_id.set(rid)
    structlog.contextvars.bind_contextvars(request_id=rid)
    return rid


def current_request_id() -> str:
    return _request_id.get()


def bind_trino_query_id(query_id: str) -> None:
    """Bind a Trino query_id to the current context for structured logging."""
    _trino_query_id.set(query_id)
    structlog.contextvars.bind_contextvars(trino_query_id=query_id)


def current_trino_query_id() -> str:
    return _trino_query_id.get()


__all__ = [
    "bind_trino_query_id",
    "current_request_id",
    "current_trino_query_id",
    "new_request_id",
]
