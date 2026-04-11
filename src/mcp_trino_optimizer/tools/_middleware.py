"""Tool decorator middleware: request_id + tool_name contextvars binding.

Every tool's entry point is wrapped with tool_envelope(tool_name) so every
log call inside the handler inherits request_id and tool_name via structlog
contextvars. This satisfies PLAT-06's mandatory fields for log lines
emitted during tool execution.

Phase 1 ships only a sync decorator (selftest is sync). Phase 2 will add
an async variant when Trino-touching tools land.
"""

from __future__ import annotations

import functools
from collections.abc import Callable
from typing import Any, TypeVar

import structlog

from mcp_trino_optimizer._context import new_request_id
from mcp_trino_optimizer.logging_setup import get_logger

F = TypeVar("F", bound=Callable[..., Any])


def tool_envelope(tool_name: str) -> Callable[[F], F]:
    """Bind request_id + tool_name contextvars around a sync tool handler.

    Also emits a single ``tool_invoked`` log line on entry so PLAT-06's
    mandatory binding (request_id + tool_name on every log line) has at
    least one observable event per call, even when the tool body itself
    emits no logs.
    """

    def deco(fn: F) -> F:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            structlog.contextvars.clear_contextvars()
            rid = new_request_id()
            structlog.contextvars.bind_contextvars(
                request_id=rid,
                tool_name=tool_name,
            )
            get_logger(__name__).info("tool_invoked")
            return fn(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return deco


__all__ = ["tool_envelope"]
