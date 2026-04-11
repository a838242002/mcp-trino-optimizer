"""PLAT-06: Every log line carries request_id, tool_name, git_sha, package_version, ISO8601 UTC timestamp.

Landed by plan 01-03.
"""

from __future__ import annotations

import json

import pytest

try:
    from mcp_trino_optimizer import logging_setup as cfg  # landed in plan 01-03
except ImportError:
    cfg = None  # type: ignore[assignment]

pytestmark = pytest.mark.skipif(cfg is None, reason="mcp_trino_optimizer.logging_setup not yet implemented")


def test_log_line_contains_mandatory_fields(capsys: pytest.CaptureFixture[str]) -> None:
    cfg.configure_logging("INFO", package_version="0.1.0", git_sha="abc123456789")
    log = cfg.get_logger("test")
    log.info("test_event", extra_field="hello")
    captured = capsys.readouterr()
    line = captured.err.strip().splitlines()[-1]
    data = json.loads(line)
    assert "timestamp" in data
    assert data.get("package_version") == "0.1.0"
    assert data.get("git_sha") == "abc123456789"
    # request_id + tool_name are bound via contextvars at tool entry —
    # tested in tests/tools/test_selftest.py


def test_log_line_timestamp_is_iso8601_utc(capsys: pytest.CaptureFixture[str]) -> None:
    cfg.configure_logging("INFO", package_version="0.1.0", git_sha="abc123456789")
    log = cfg.get_logger("test")
    log.info("ts_event")
    captured = capsys.readouterr()
    line = captured.err.strip().splitlines()[-1]
    data = json.loads(line)
    ts = data.get("timestamp", "")
    # ISO8601 UTC ends with Z or +00:00
    assert ts.endswith("Z") or ts.endswith("+00:00"), f"timestamp not UTC: {ts}"


def test_log_line_includes_level(capsys: pytest.CaptureFixture[str]) -> None:
    cfg.configure_logging("INFO", package_version="0.1.0", git_sha="abc123456789")
    log = cfg.get_logger("test")
    log.warning("level_event")
    captured = capsys.readouterr()
    line = captured.err.strip().splitlines()[-1]
    data = json.loads(line)
    assert str(data.get("level", "")).lower() == "warning"
