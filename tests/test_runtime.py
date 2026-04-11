"""Unit tests for _runtime: git_sha resolver must never raise.

Landed by plan 01-03.
"""

from __future__ import annotations

import pytest

from mcp_trino_optimizer._runtime import (
    RuntimeInfo,
    _resolve_git_sha,
    runtime_info,
    set_transport,
)


def test_resolve_git_sha_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MCPTO_GIT_SHA", "deadbeefcafe00000000")
    assert _resolve_git_sha() == "deadbeefcafe"


def test_resolve_git_sha_fallback_when_everything_fails(monkeypatch: pytest.MonkeyPatch, tmp_path: object) -> None:
    monkeypatch.delenv("MCPTO_GIT_SHA", raising=False)
    monkeypatch.setenv("PATH", "")  # hide git binary
    # In a dir without .git, subprocess returns non-zero
    monkeypatch.chdir(tmp_path)  # type: ignore[arg-type]
    result = _resolve_git_sha()
    assert isinstance(result, str)
    # Either "unknown" (no git) or a real sha (CI runners have git on PATH)
    assert len(result) > 0


def test_resolve_git_sha_never_raises() -> None:
    # Direct smoke: call it, must not raise
    result = _resolve_git_sha()
    assert isinstance(result, str)
    assert len(result) > 0


def test_runtime_info_has_all_fields() -> None:
    info = runtime_info("DEBUG")
    assert isinstance(info, RuntimeInfo)
    assert info.log_level == "DEBUG"
    assert info.package_version  # either real or "0.0.0-dev"
    assert info.python_version
    assert info.git_sha
    assert info.started_at
    assert info.transport  # default "unknown" or set via set_transport


def test_set_transport_updates_runtime_info() -> None:
    set_transport("stdio")
    assert runtime_info().transport == "stdio"
    set_transport("http")
    assert runtime_info().transport == "http"
    set_transport("unknown")  # reset
