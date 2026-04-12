"""Exception taxonomy for the Trino adapter layer — D-26.

All adapter exceptions inherit from TrinoAdapterError so callers can
catch the base class for broad handling or subclasses for specific recovery.
"""

from __future__ import annotations

__all__ = [
    "TrinoAdapterError",
    "TrinoAuthError",
    "TrinoClassifierRejected",
    "TrinoConnectionError",
    "TrinoPoolBusyError",
    "TrinoTimeoutError",
    "TrinoVersionUnsupported",
]


class TrinoAdapterError(Exception):
    """Base class for all Trino adapter errors.

    Carries optional ``request_id`` (MCP request correlation) and
    ``query_id`` (Trino server-assigned query ID) for structured logging.
    """

    def __init__(
        self,
        message: str,
        *,
        request_id: str = "",
        query_id: str = "",
    ) -> None:
        self.request_id = request_id
        self.query_id = query_id
        super().__init__(message)


class TrinoAuthError(TrinoAdapterError):
    """Authentication or authorization failure against the Trino cluster."""


class TrinoVersionUnsupported(TrinoAdapterError):
    """Trino server version is below the minimum supported (429)."""


class TrinoPoolBusyError(TrinoAdapterError):
    """All concurrent query slots are occupied; caller should retry later."""


class TrinoTimeoutError(TrinoAdapterError):
    """Query exceeded the configured wall-clock timeout."""


class TrinoClassifierRejected(TrinoAdapterError):
    """SQL was rejected by the read-only gate (SqlClassifier).

    Raised before any network call is made. The ``message`` always
    includes the reason for rejection (statement type, multi-statement,
    empty input, etc.).
    """


class TrinoConnectionError(TrinoAdapterError):
    """Network-level failure reaching the Trino coordinator."""
