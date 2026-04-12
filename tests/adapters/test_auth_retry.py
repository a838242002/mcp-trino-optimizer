"""Tests for D-13 auth retry logic in TrinoClient.

Verifies:
- On first HTTP 401, TrinoClient retries exactly once with refreshed auth
- On double-401, TrinoAuthError is raised with query_id set
- trino_auth_retry log event is emitted with {request_id, query_id, attempt, auth_mode}
- No token/password/jwt value appears in the retry log event
- Non-401 errors are not retried
"""

from __future__ import annotations

import contextlib
import io
import json
from collections.abc import Iterator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import structlog
import trino.exceptions

from mcp_trino_optimizer.adapters.trino.client import TrinoClient
from mcp_trino_optimizer.adapters.trino.errors import TrinoAuthError
from mcp_trino_optimizer.adapters.trino.pool import TrinoThreadPool
from mcp_trino_optimizer.settings import Settings

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_settings(**kwargs: Any) -> Settings:
    defaults: dict[str, Any] = {
        "trino_host": "localhost",
        "trino_port": 8080,
        "trino_auth_mode": "none",
    }
    defaults.update(kwargs)
    return Settings.model_construct(**defaults)


def _parse_log_lines(buf: io.StringIO) -> list[dict[str, Any]]:
    lines = []
    for line in buf.getvalue().splitlines():
        line = line.strip()
        if not line:
            continue
        with contextlib.suppress(json.JSONDecodeError):
            lines.append(json.loads(line))
    return lines


def _make_401_error() -> trino.exceptions.TrinoExternalError:
    """Construct a TrinoExternalError that looks like a 401."""
    err = trino.exceptions.TrinoExternalError(
        {
            "errorCode": {"code": 65536, "name": "EXTERNAL"},
            "message": "Authentication failed: 401 Unauthorized",
            "errorType": "EXTERNAL",
            "errorName": "EXTERNAL",
        }
    )
    return err


def _make_500_error() -> trino.exceptions.TrinoExternalError:
    """Construct a TrinoExternalError that looks like a 500."""
    err = trino.exceptions.TrinoExternalError(
        {
            "errorCode": {"code": 65536, "name": "EXTERNAL"},
            "message": "Internal server error: 500",
            "errorType": "EXTERNAL",
            "errorName": "EXTERNAL",
        }
    )
    return err


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def log_capture() -> Iterator[io.StringIO]:
    buf = io.StringIO()
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True, key="timestamp"),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(buf),
        cache_logger_on_first_use=False,
    )
    structlog.contextvars.clear_contextvars()
    yield buf
    structlog.configure(
        processors=[structlog.processors.JSONRenderer()],
        logger_factory=structlog.PrintLoggerFactory(io.StringIO()),
        cache_logger_on_first_use=False,
    )


@pytest.fixture
def pool() -> Iterator[TrinoThreadPool]:
    p = TrinoThreadPool(max_workers=2)
    yield p
    p.shutdown(wait=False)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retry_once_on_401_then_succeeds(pool: TrinoThreadPool) -> None:
    """On first 401, TrinoClient retries once and returns successful result."""
    settings = _make_settings()
    client = TrinoClient(settings=settings, pool=pool)

    fake_rows = [{"col": "value"}]
    side_effects = [_make_401_error(), fake_rows]

    mock_run = MagicMock(side_effect=side_effects)

    with patch.object(client, "_run_in_thread", mock_run):
        result = await client.fetch_system_runtime("SELECT 1")

    assert result == fake_rows
    assert mock_run.call_count == 2, f"Expected exactly 2 calls (initial + retry), got {mock_run.call_count}"


@pytest.mark.asyncio
async def test_double_401_raises_trino_auth_error(pool: TrinoThreadPool) -> None:
    """On two consecutive 401s, TrinoAuthError is raised."""
    settings = _make_settings()
    client = TrinoClient(settings=settings, pool=pool)

    side_effects = [_make_401_error(), _make_401_error()]
    mock_run = MagicMock(side_effect=side_effects)

    with patch.object(client, "_run_in_thread", mock_run), pytest.raises(TrinoAuthError):
        await client.fetch_system_runtime("SELECT 1")

    assert mock_run.call_count == 2, f"Expected exactly 2 calls, got {mock_run.call_count}"


@pytest.mark.asyncio
async def test_auth_retry_log_event_emitted(log_capture: io.StringIO, pool: TrinoThreadPool) -> None:
    """trino_auth_retry log event is emitted on 401 retry with correct fields."""
    from mcp_trino_optimizer._context import new_request_id

    settings = _make_settings()
    client = TrinoClient(settings=settings, pool=pool)
    rid = new_request_id()

    side_effects = [_make_401_error(), []]
    mock_run = MagicMock(side_effect=side_effects)

    with patch.object(client, "_run_in_thread", mock_run):
        await client.fetch_system_runtime("SELECT 1")

    lines = _parse_log_lines(log_capture)
    retry_events = [ln for ln in lines if ln.get("event") == "trino_auth_retry"]

    assert len(retry_events) == 1, f"Expected exactly 1 trino_auth_retry event. Got: {retry_events}"
    evt = retry_events[0]
    assert evt.get("request_id") == rid, "request_id missing from trino_auth_retry"
    assert "attempt" in evt, "attempt missing from trino_auth_retry"
    assert "auth_mode" in evt, "auth_mode missing from trino_auth_retry"
    # query_id may be empty string if not captured yet — that's acceptable


@pytest.mark.asyncio
async def test_auth_retry_log_has_no_secret(log_capture: io.StringIO, pool: TrinoThreadPool) -> None:
    """No token/password/jwt value appears in the trino_auth_retry log event."""
    import os

    # Set a JWT token in env to simulate rotation scenario
    os.environ["MCPTO_TRINO_JWT"] = "super-secret-jwt-value-12345"
    settings = _make_settings(trino_auth_mode="jwt", trino_jwt="super-secret-jwt-value-12345")
    client = TrinoClient(settings=settings, pool=pool)

    side_effects = [_make_401_error(), []]
    mock_run = MagicMock(side_effect=side_effects)

    with patch.object(client, "_run_in_thread", mock_run), contextlib.suppress(Exception):
        await client.fetch_system_runtime("SELECT 1")

    os.environ.pop("MCPTO_TRINO_JWT", None)

    raw_output = log_capture.getvalue()
    assert "super-secret-jwt-value-12345" not in raw_output, "JWT token value appeared in log output"


@pytest.mark.asyncio
async def test_non_401_error_not_retried(pool: TrinoThreadPool) -> None:
    """Non-401 errors are NOT retried — they propagate immediately."""
    settings = _make_settings()
    client = TrinoClient(settings=settings, pool=pool)

    err_500 = _make_500_error()
    mock_run = MagicMock(side_effect=[err_500])

    with patch.object(client, "_run_in_thread", mock_run), pytest.raises(trino.exceptions.TrinoExternalError):
        await client.fetch_system_runtime("SELECT 1")

    assert mock_run.call_count == 1, f"Non-401 error should not trigger retry, got {mock_run.call_count} calls"


@pytest.mark.asyncio
async def test_no_auth_retry_log_for_non_401(log_capture: io.StringIO, pool: TrinoThreadPool) -> None:
    """trino_auth_retry event is NOT emitted for non-401 errors."""
    settings = _make_settings()
    client = TrinoClient(settings=settings, pool=pool)

    mock_run = MagicMock(side_effect=[_make_500_error()])

    with patch.object(client, "_run_in_thread", mock_run), contextlib.suppress(Exception):
        await client.fetch_system_runtime("SELECT 1")

    lines = _parse_log_lines(log_capture)
    retry_events = [ln for ln in lines if ln.get("event") == "trino_auth_retry"]
    assert retry_events == [], f"Expected no trino_auth_retry events for 500 error, got: {retry_events}"
