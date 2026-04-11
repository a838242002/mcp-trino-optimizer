"""Unit tests for the SentinelWriter stdout discipline layer.

Landed by plan 01-02 — these tests validate the layer-2 stdout guard in
isolation (layer 3 in CI smoke-tests the full stdio channel).
"""

from __future__ import annotations

import sys

import pytest

from mcp_trino_optimizer.safety.stdout_guard import (
    SentinelWriter,
    install_stdout_guard,
    uninstall_stdout_guard,
)


@pytest.fixture(autouse=True)
def _cleanup() -> object:
    yield
    uninstall_stdout_guard()


def test_install_replaces_sys_stdout() -> None:
    original = sys.stdout
    install_stdout_guard()
    assert isinstance(sys.stdout, SentinelWriter)
    uninstall_stdout_guard()
    assert sys.stdout is original


def test_install_is_idempotent() -> None:
    install_stdout_guard()
    first = sys.stdout
    install_stdout_guard()
    assert sys.stdout is first


def test_stray_write_is_logged_not_raised(capsys: pytest.CaptureFixture[str]) -> None:
    install_stdout_guard()
    sys.stdout.write("stray content from a careless print call\n")
    captured = capsys.readouterr()
    # Either structlog (if configured) or fallback JSON on stderr
    assert "stdout_violation" in captured.err
    assert "stray content" in captured.err
    assert captured.out == ""  # SentinelWriter drops the content


def test_whitespace_only_write_is_silent(capsys: pytest.CaptureFixture[str]) -> None:
    install_stdout_guard()
    sys.stdout.write("")
    sys.stdout.write("\n")
    sys.stdout.write("   ")
    captured = capsys.readouterr()
    assert "stdout_violation" not in captured.err


def test_fileno_raises_oserror() -> None:
    writer = SentinelWriter()
    with pytest.raises(OSError):
        writer.fileno()


def test_sentinel_attributes() -> None:
    writer = SentinelWriter()
    assert writer.isatty() is False
    assert writer.writable() is True
    assert writer.readable() is False
    assert writer.seekable() is False
    assert writer.encoding == "utf-8"
