"""Untrusted-content envelope for tool responses (PLAT-11, D-10).

Every tool response that embeds a user-origin string (SQL, pasted
EXPLAIN JSON, Trino error messages, remote metadata) MUST route that
string through wrap_untrusted() before putting it into a response.

The envelope is a pure JSON shape — no delimiters, no escaping, no
nested markers. The MCP client is responsible for rendering the
envelope safely for LLM consumption.

See PLAT-11, PITFALLS.md §Pitfall 8 (indirect prompt injection),
CONTEXT.md D-10, RESEARCH.md §10.
"""

from __future__ import annotations

from typing import Literal, TypedDict


class UntrustedEnvelope(TypedDict):
    source: Literal["untrusted"]
    content: str


def wrap_untrusted(content: str) -> UntrustedEnvelope:
    """Wrap a user-origin string in the untrusted-content envelope.

    Args:
        content: Any user-origin string. Preserved verbatim.

    Returns:
        Exactly ``{"source": "untrusted", "content": content}``.
        No transformation. The MCP client distinguishes untrusted
        content by checking the ``source`` field.
    """
    return {"source": "untrusted", "content": content}


__all__ = ["UntrustedEnvelope", "wrap_untrusted"]
