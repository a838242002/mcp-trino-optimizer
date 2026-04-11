"""structlog pipeline: stderr-only JSON with redaction (PLAT-06, PLAT-07, D-09, D-12 layer 1).

Processor order is LOAD-BEARING:
  1. merge_contextvars (request_id, tool_name from contextvars)
  2. add_log_level + add_logger_name
  3. TimeStamper ISO8601 UTC
  4. Static fields lambda (package_version, git_sha)
  5. REDACTION — must run BEFORE serialization
  6. StackInfoRenderer + format_exc_info (exceptions)
  7. _orjson_renderer — final JSON on stderr

Never writes to the stdout stream. The stdout-discipline guarantee depends
on this module never installing a handler bound to the standard-output
file descriptor (D-12 layer 1 of 3).
"""

from __future__ import annotations

import logging
import re
import sys
from collections.abc import MutableMapping
from typing import Any

import orjson
import structlog
from pydantic import SecretStr

REDACTION_DENYLIST: frozenset[str] = frozenset(
    {
        "authorization",
        "x-trino-extra-credentials",
        "cookie",
        "token",
        "password",
        "api_key",
        "apikey",
        "bearer",
        "secret",
        "ssl_password",
    }
)

_CREDENTIAL_PATTERN = re.compile(r"^credential\.", re.IGNORECASE)


def _redact_processor(
    logger: Any,
    method_name: str,
    event_dict: MutableMapping[str, Any],
) -> MutableMapping[str, Any]:
    """Recursively redact secret-shaped keys and SecretStr values.

    - Any dict key matching REDACTION_DENYLIST (case-insensitive) → [REDACTED]
    - Any dict key matching r"^credential\\." → [REDACTED]
    - Any value of type pydantic.SecretStr → [REDACTED]
    - Recurses into nested dicts, lists, tuples at any depth
    """

    def _walk(obj: Any) -> Any:
        if isinstance(obj, SecretStr):
            return "[REDACTED]"
        if isinstance(obj, dict):
            return {
                k: (
                    "[REDACTED]"
                    if (
                        isinstance(k, str)
                        and (
                            k.lower() in REDACTION_DENYLIST
                            or _CREDENTIAL_PATTERN.match(k)
                        )
                    )
                    else _walk(v)
                )
                for k, v in obj.items()
            }
        if isinstance(obj, (list, tuple)):
            return type(obj)(_walk(x) for x in obj)
        return obj

    return _walk(event_dict)  # type: ignore[no-any-return]


def _add_logger_name(
    logger: Any,
    method_name: str,
    event_dict: MutableMapping[str, Any],
) -> MutableMapping[str, Any]:
    """Inject `logger` name field without relying on structlog.stdlib.add_logger_name.

    The stdlib processor expects a stdlib logging.Logger instance, but we use
    structlog.PrintLoggerFactory which yields a PrintLogger without a `name`
    attribute. This fallback gracefully pulls a name off whichever logger type
    is in use and is a no-op otherwise.
    """
    name = getattr(logger, "name", None)
    if name:
        event_dict.setdefault("logger", name)
    return event_dict


def _orjson_renderer(
    logger: Any,
    method_name: str,
    event_dict: MutableMapping[str, Any],
) -> str:
    return orjson.dumps(dict(event_dict)).decode("utf-8")


def configure_logging(
    level: str = "INFO",
    *,
    package_version: str,
    git_sha: str,
) -> None:
    """Configure structlog for stderr-only JSON output with redaction.

    Must be called exactly once at process startup, BEFORE any log calls.
    """
    numeric_level = getattr(logging, level.upper())

    # Force stdlib logging to stderr (belt-and-suspenders; any library
    # using stdlib logging won't leak to stdout).
    logging.basicConfig(
        stream=sys.stderr,
        level=numeric_level,
        format="%(message)s",
        force=True,
    )
    logging.captureWarnings(True)

    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(numeric_level),
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            _add_logger_name,
            structlog.processors.TimeStamper(fmt="iso", utc=True, key="timestamp"),
            # Inject static process-wide fields (PLAT-06).
            lambda _l, _m, ev: {
                **ev,
                "package_version": package_version,
                "git_sha": git_sha,
            },
            # REDACTION — must run before any serialization processor.
            _redact_processor,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            # Final JSON render via orjson.
            _orjson_renderer,
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = "") -> Any:
    """Return a bound structlog logger."""
    return structlog.get_logger(name)


__all__ = [
    "REDACTION_DENYLIST",
    "configure_logging",
    "get_logger",
]
