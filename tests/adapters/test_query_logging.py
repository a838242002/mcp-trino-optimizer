"""Tests for query logging invariants in TrinoClient (D-28, T-02-10, T-02-11).

Verifies:
- trino_query_executed log event is emitted after query execution
- event contains: request_id, statement_hash, duration_ms, auth_mode
- raw SQL never appears in any log line
- statement_hash is SHA-256 of the SQL string
"""

from __future__ import annotations

import hashlib
import io
import json
from collections.abc import Iterator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import structlog

from mcp_trino_optimizer.adapters.trino.client import TrinoClient
from mcp_trino_optimizer.adapters.trino.pool import TrinoThreadPool
from mcp_trino_optimizer.settings import Settings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_settings(**kwargs: Any) -> Settings:
    """Build a minimal Settings with test defaults."""
    defaults: dict[str, Any] = {
        "trino_host": "localhost",
        "trino_port": 8080,
        "trino_auth_mode": "none",
    }
    defaults.update(kwargs)
    return Settings.model_construct(**defaults)


def _capture_log_lines(output: io.StringIO) -> list[dict[str, Any]]:
    """Parse newline-delimited JSON log lines from a StringIO capture."""
    lines = []
    for line in output.getvalue().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            lines.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return lines


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def log_capture() -> Iterator[io.StringIO]:
    """Redirect structlog output to a StringIO buffer for test inspection."""
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

    # Restore to a no-op configuration after test
    structlog.configure(
        processors=[structlog.processors.JSONRenderer()],
        logger_factory=structlog.PrintLoggerFactory(io.StringIO()),
        cache_logger_on_first_use=False,
    )


@pytest.fixture()
def pool() -> Iterator[TrinoThreadPool]:
    p = TrinoThreadPool(max_workers=2)
    yield p
    p.shutdown(wait=False)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trino_query_executed_event_emitted(
    log_capture: io.StringIO, pool: TrinoThreadPool
) -> None:
    """trino_query_executed log event is emitted after a successful query."""
    sql = "SELECT 1"
    expected_hash = hashlib.sha256(sql.encode()).hexdigest()

    settings = _make_settings()
    client = TrinoClient(settings=settings, pool=pool)

    # Mock _run_in_thread to avoid real network calls
    fake_rows = [{"_col0": 1}]
    mock_run = MagicMock(return_value=fake_rows)

    with patch.object(client, "_run_in_thread", mock_run):
        result = await client.fetch_system_runtime(sql)

    lines = _capture_log_lines(log_capture)
    exec_events = [ln for ln in lines if ln.get("event") == "trino_query_executed"]

    assert len(exec_events) >= 1, (
        f"Expected at least one trino_query_executed event. Got lines: {lines}"
    )
    evt = exec_events[0]
    assert evt.get("statement_hash") == expected_hash, (
        f"statement_hash mismatch. Expected {expected_hash}, got {evt.get('statement_hash')}"
    )
    assert "duration_ms" in evt, "duration_ms missing from trino_query_executed"
    assert "auth_mode" in evt, "auth_mode missing from trino_query_executed"


@pytest.mark.asyncio
async def test_raw_sql_never_in_log(
    log_capture: io.StringIO, pool: TrinoThreadPool
) -> None:
    """Raw SQL text must never appear in any log line (T-02-10)."""
    sql = "SELECT secret_column FROM sensitive_table"

    settings = _make_settings()
    client = TrinoClient(settings=settings, pool=pool)

    fake_rows: list[dict[str, Any]] = []
    mock_run = MagicMock(return_value=fake_rows)

    with patch.object(client, "_run_in_thread", mock_run):
        await client.fetch_system_runtime(sql)

    raw_output = log_capture.getvalue()
    # Neither the full SQL nor distinctive substrings should appear
    assert "secret_column" not in raw_output, (
        "Raw SQL appeared in log output (field name found)"
    )
    assert "sensitive_table" not in raw_output, (
        "Raw SQL appeared in log output (table name found)"
    )


@pytest.mark.asyncio
async def test_statement_hash_is_sha256(
    log_capture: io.StringIO, pool: TrinoThreadPool
) -> None:
    """statement_hash must be SHA-256(sql.encode()).hexdigest()."""
    sql = "SELECT count(*) FROM iceberg.default.orders"
    expected_hash = hashlib.sha256(sql.encode()).hexdigest()

    settings = _make_settings()
    client = TrinoClient(settings=settings, pool=pool)

    mock_run = MagicMock(return_value=[])

    with patch.object(client, "_run_in_thread", mock_run):
        await client.fetch_system_runtime(sql)

    lines = _capture_log_lines(log_capture)
    exec_events = [ln for ln in lines if ln.get("event") == "trino_query_executed"]

    assert exec_events, "No trino_query_executed event found"
    assert exec_events[0]["statement_hash"] == expected_hash


@pytest.mark.asyncio
async def test_request_id_in_log_event(
    log_capture: io.StringIO, pool: TrinoThreadPool
) -> None:
    """request_id must be present in the trino_query_executed log event."""
    from mcp_trino_optimizer._context import new_request_id

    sql = "SELECT 1"
    rid = new_request_id()

    settings = _make_settings()
    client = TrinoClient(settings=settings, pool=pool)

    mock_run = MagicMock(return_value=[])

    with patch.object(client, "_run_in_thread", mock_run):
        await client.fetch_system_runtime(sql)

    lines = _capture_log_lines(log_capture)
    exec_events = [ln for ln in lines if ln.get("event") == "trino_query_executed"]

    assert exec_events, "No trino_query_executed event found"
    assert exec_events[0].get("request_id") == rid
