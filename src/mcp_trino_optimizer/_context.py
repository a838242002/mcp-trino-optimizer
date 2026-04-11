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


def new_request_id() -> str:
    """Generate + bind a new request_id; returns it for caller use."""
    rid = uuid.uuid4().hex[:16]
    _request_id.set(rid)
    structlog.contextvars.bind_contextvars(request_id=rid)
    return rid


def current_request_id() -> str:
    return _request_id.get()


__all__ = ["current_request_id", "new_request_id"]
