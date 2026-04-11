"""Shared pytest fixtures for Phase 1.

Fixtures provided here:
- subprocess_runner: spawn the mcp-trino-optimizer CLI in bytes mode
- bearer_token: a deterministic test token (32 hex chars)
- clean_env: monkeypatched env with MCPTO_* vars wiped
- capture_stderr: pytest capsys wrapper for reading structured log lines
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Iterator

import pytest


@pytest.fixture
def bearer_token() -> str:
    return "a" * 32


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    """Wipe every MCPTO_* env var so tests see a clean slate."""
    for key in list(os.environ):
        if key.startswith("MCPTO_"):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("MCPTO_GIT_SHA", "test0000")
    return monkeypatch


@pytest.fixture
def spawn_server() -> Iterator[object]:
    """Factory for subprocess.Popen bound to the installed CLI.

    Yields a callable that accepts args and env kwargs. See
    01-RESEARCH.md §15 for the bytes-mode pattern Windows requires.
    """
    procs: list[subprocess.Popen[bytes]] = []

    def _spawn(*args: str, env: dict[str, str] | None = None) -> subprocess.Popen[bytes]:
        proc_env = os.environ.copy()
        proc_env.setdefault("MCPTO_GIT_SHA", "test0000")
        proc_env.setdefault("PYTHONUNBUFFERED", "1")
        if env:
            proc_env.update(env)
        proc = subprocess.Popen(
            ["mcp-trino-optimizer", *args],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
            env=proc_env,
        )
        procs.append(proc)
        return proc

    yield _spawn

    for p in procs:
        if p.poll() is None:
            p.kill()
            p.wait(timeout=5)
