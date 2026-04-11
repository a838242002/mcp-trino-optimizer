# ruff: noqa: T20
"""Stdout discipline layer 2 (of 3) for stdio mode (PLAT-05, D-12 layer 2).

Three-layer stdout discipline:
  Layer 1 (logging_setup): structlog writes to stderr only.
  Layer 2 (this file): sys.stdout replaced with SentinelWriter that captures
                       stray writes and routes them to structlog as violations.
  Layer 3 (smoke test): CI spawns the server and asserts every byte on stdout
                        is a valid JSON-RPC frame.

CRITICAL: Install AFTER FastMCP's stdio_server() has captured the pristine
fd (see RESEARCH.md §3.4). Installing too early poisons FastMCP's writer.
The transports.run_stdio() orchestrates the correct order.
"""

from __future__ import annotations

import sys
from typing import Any

_installed: bool = False
_original_stdout: Any = None


class SentinelWriter:
    """A write-like object that captures stray stdout writes as violations.

    Installed on sys.stdout in stdio mode AFTER the pristine stdout fd has
    been duplicated and handed to FastMCP. Any subsequent write that reaches
    this object is, by definition, a stray write that would have corrupted
    the JSON-RPC channel — we log it and drop it.

    Uses lazy import of logging_setup to avoid circular import at module
    load time. Falls back to raw stderr write if structlog isn't configured.
    """

    encoding = "utf-8"
    errors = "replace"

    def write(self, data: str) -> int:
        if not data or not data.strip():
            # Ignore empty / whitespace-only flushes. Python frequently
            # calls write("\n") or write("") at shutdown.
            return len(data) if data else 0
        # Lazy import — logging_setup is plan 01-03 and may race with us.
        try:
            from mcp_trino_optimizer.logging_setup import (  # type: ignore[import-not-found]
                get_logger,
            )

            get_logger(__name__).error(
                "stdout_violation",
                bytes_len=len(data),
                preview=data[:200],
            )
        except Exception:  # noqa: BLE001 — fallback must not raise
            # Fallback: raw JSON line to stderr so the event is never lost.
            import json

            fallback = json.dumps(
                {
                    "event": "stdout_violation",
                    "level": "error",
                    "bytes_len": len(data),
                    "preview": data[:200],
                    "note": "logging_setup unavailable; fallback path",
                }
            )
            sys.stderr.write(fallback + "\n")
            sys.stderr.flush()
        return len(data)

    def flush(self) -> None:
        pass

    def isatty(self) -> bool:
        return False

    def writable(self) -> bool:
        return True

    def readable(self) -> bool:
        return False

    def seekable(self) -> bool:
        return False

    def fileno(self) -> int:
        # rich / colorama probe fileno(); OSError is the idiomatic "no fd" signal.
        raise OSError("SentinelWriter has no file descriptor")


def install_stdout_guard() -> None:
    """Replace sys.stdout with a SentinelWriter. Idempotent."""
    global _installed, _original_stdout
    if _installed:
        return
    _original_stdout = sys.stdout
    sys.stdout = SentinelWriter()  # type: ignore[assignment,unused-ignore]
    _installed = True


def uninstall_stdout_guard() -> None:
    """Restore the original stdout. Used only by tests."""
    global _installed, _original_stdout
    if not _installed:
        return
    sys.stdout = _original_stdout
    _original_stdout = None
    _installed = False


__all__ = [
    "SentinelWriter",
    "install_stdout_guard",
    "uninstall_stdout_guard",
]
