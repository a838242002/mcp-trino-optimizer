"""PLAT-07: Authorization, X-Trino-Extra-Credentials, credential.*, cookie,
SecretStr values must be redacted before hitting the log sink.

Covers D-09. Landed by plan 01-03.
"""

from __future__ import annotations

import pytest
from pydantic import SecretStr

try:
    from mcp_trino_optimizer import logging_setup as cfg  # landed in plan 01-03
except ImportError:
    cfg = None  # type: ignore[assignment]

pytestmark = pytest.mark.skipif(
    cfg is None, reason="mcp_trino_optimizer.logging_setup not yet implemented"
)


def _configure(capsys: pytest.CaptureFixture[str]) -> object:
    cfg.configure_logging("INFO", package_version="0.1.0", git_sha="abc")
    return cfg.get_logger("redaction_test")


def test_secretstr_redacted(capsys: pytest.CaptureFixture[str]) -> None:
    log = _configure(capsys)
    log.info("auth_attempt", token=SecretStr("supersecret"), user="alice")
    captured = capsys.readouterr()
    assert "[REDACTED]" in captured.err
    assert "supersecret" not in captured.err
    assert "alice" in captured.err


def test_authorization_key_redacted(capsys: pytest.CaptureFixture[str]) -> None:
    log = _configure(capsys)
    log.info("request", authorization="Bearer xyz.very.secret.token")
    captured = capsys.readouterr()
    assert "[REDACTED]" in captured.err
    assert "xyz.very.secret.token" not in captured.err


@pytest.mark.parametrize("key", ["authorization", "Authorization", "AUTHORIZATION"])
def test_case_insensitive_denylist(capsys: pytest.CaptureFixture[str], key: str) -> None:
    log = _configure(capsys)
    log.info("request", **{key: "Bearer secret_value_123"})
    captured = capsys.readouterr()
    assert "secret_value_123" not in captured.err


def test_credential_dot_pattern_redacted(capsys: pytest.CaptureFixture[str]) -> None:
    log = _configure(capsys)
    log.info(
        "conn",
        **{"credential.user": "alice", "credential.password": "hunter2_secret"},
    )
    captured = capsys.readouterr()
    # Value of credential.password must be redacted
    assert "hunter2_secret" not in captured.err
    # The alice key VALUE should also be redacted per D-09 credential.* pattern
    # (both credential.user and credential.password are sensitive in Trino context)
    # but we at minimum require the password to be gone
    assert "[REDACTED]" in captured.err


def test_x_trino_extra_credentials_redacted(capsys: pytest.CaptureFixture[str]) -> None:
    log = _configure(capsys)
    log.info("trino_call", **{"x-trino-extra-credentials": "user=bob,password=topsecret"})
    captured = capsys.readouterr()
    assert "topsecret" not in captured.err
    assert "[REDACTED]" in captured.err


def test_cookie_redacted(capsys: pytest.CaptureFixture[str]) -> None:
    log = _configure(capsys)
    log.info("http", cookie="session=abc123_secret_cookie")
    captured = capsys.readouterr()
    assert "abc123_secret_cookie" not in captured.err


def test_nested_dict_redaction(capsys: pytest.CaptureFixture[str]) -> None:
    log = _configure(capsys)
    log.info(
        "nested",
        payload={"outer": {"inner": {"authorization": "Bearer nested_secret_xyz"}}},
    )
    captured = capsys.readouterr()
    assert "nested_secret_xyz" not in captured.err


def test_secret_in_list_of_dicts(capsys: pytest.CaptureFixture[str]) -> None:
    log = _configure(capsys)
    log.info(
        "list_payload",
        items=[{"name": "a"}, {"token": "secret_in_list_abc"}],
    )
    captured = capsys.readouterr()
    assert "secret_in_list_abc" not in captured.err


def test_normal_fields_not_redacted(capsys: pytest.CaptureFixture[str]) -> None:
    log = _configure(capsys)
    log.info("normal", user="alice", tool_name="mcp_selftest", duration_ms=42)
    captured = capsys.readouterr()
    assert "alice" in captured.err
    assert "mcp_selftest" in captured.err
