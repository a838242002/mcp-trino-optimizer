"""Unit tests for Settings auth-mode validation and auth builder — Task 2.

Tests:
  - Settings accepts valid auth configurations for none/basic/jwt modes
  - Settings fails fast (ValidationError) on missing required auth fields
  - build_authentication() returns the correct trino.auth type per mode
  - PerCallJWTAuthentication re-reads JWT from os.environ on every call
"""

from __future__ import annotations

import pytest
from pydantic import SecretStr, ValidationError

from mcp_trino_optimizer.adapters.trino.auth import PerCallJWTAuthentication, build_authentication
from mcp_trino_optimizer.settings import Settings

# ---------------------------------------------------------------------------
# Settings validation
# ---------------------------------------------------------------------------


def test_settings_auth_mode_none_succeeds() -> None:
    """auth_mode=none requires no additional fields."""
    s = Settings(trino_host="localhost", trino_auth_mode="none")
    assert s.trino_auth_mode == "none"
    assert s.trino_host == "localhost"


def test_settings_auth_mode_basic_succeeds() -> None:
    """auth_mode=basic with user+password succeeds."""
    s = Settings(
        trino_host="localhost",
        trino_auth_mode="basic",
        trino_user="alice",
        trino_password=SecretStr("s3cr3t"),
    )
    assert s.trino_auth_mode == "basic"
    assert s.trino_user == "alice"
    assert s.trino_password is not None
    assert s.trino_password.get_secret_value() == "s3cr3t"


def test_settings_auth_mode_basic_missing_user_fails() -> None:
    """auth_mode=basic without trino_user raises ValidationError."""
    with pytest.raises(ValidationError, match=r"(?i)(user|basic|trino_user)"):
        Settings(
            trino_host="localhost",
            trino_auth_mode="basic",
            trino_password=SecretStr("s3cr3t"),
        )


def test_settings_auth_mode_basic_missing_password_fails() -> None:
    """auth_mode=basic without trino_password raises ValidationError."""
    with pytest.raises(ValidationError, match=r"(?i)(password|basic|trino_password)"):
        Settings(
            trino_host="localhost",
            trino_auth_mode="basic",
            trino_user="alice",
        )


def test_settings_auth_mode_basic_missing_both_fails() -> None:
    """auth_mode=basic without user or password raises ValidationError."""
    with pytest.raises(ValidationError):
        Settings(trino_host="localhost", trino_auth_mode="basic")


def test_settings_auth_mode_jwt_succeeds() -> None:
    """auth_mode=jwt with trino_jwt token succeeds."""
    s = Settings(
        trino_host="localhost",
        trino_auth_mode="jwt",
        trino_jwt=SecretStr("tok.en.here"),
    )
    assert s.trino_auth_mode == "jwt"
    assert s.trino_jwt is not None
    assert s.trino_jwt.get_secret_value() == "tok.en.here"


def test_settings_auth_mode_jwt_missing_token_fails() -> None:
    """auth_mode=jwt without trino_jwt raises ValidationError."""
    with pytest.raises(ValidationError, match=r"(?i)(jwt|token|trino_jwt)"):
        Settings(trino_host="localhost", trino_auth_mode="jwt")


def test_settings_trino_defaults() -> None:
    """Default Trino settings have correct values."""
    s = Settings()
    assert s.trino_port == 8080
    assert s.trino_catalog == "iceberg"
    assert s.trino_schema is None
    assert s.trino_auth_mode == "none"
    assert s.trino_verify_ssl is True
    assert s.trino_ca_bundle is None
    assert s.trino_query_timeout_sec == 60
    assert s.max_concurrent_queries == 4


# ---------------------------------------------------------------------------
# build_authentication() return types
# ---------------------------------------------------------------------------


def test_build_authentication_none_returns_none() -> None:
    """auth_mode=none returns None (no auth object)."""
    s = Settings(trino_auth_mode="none")
    result = build_authentication(s)
    assert result is None


def test_build_authentication_basic_returns_basic_auth() -> None:
    """auth_mode=basic returns a BasicAuthentication instance."""
    from trino.auth import BasicAuthentication

    s = Settings(
        trino_auth_mode="basic",
        trino_user="bob",
        trino_password=SecretStr("pass"),
    )
    result = build_authentication(s)
    assert isinstance(result, BasicAuthentication)


def test_build_authentication_jwt_returns_per_call_jwt() -> None:
    """auth_mode=jwt returns a PerCallJWTAuthentication instance."""
    s = Settings(
        trino_auth_mode="jwt",
        trino_jwt=SecretStr("tok"),
    )
    result = build_authentication(s)
    assert isinstance(result, PerCallJWTAuthentication)


# ---------------------------------------------------------------------------
# PerCallJWTAuthentication re-reads env on each call
# ---------------------------------------------------------------------------


def test_per_call_jwt_reads_env_on_each_call(monkeypatch: pytest.MonkeyPatch) -> None:
    """PerCallJWTAuthentication must re-read os.environ on every set_http_session call."""
    import requests

    auth = PerCallJWTAuthentication(env_var="MCPTO_TRINO_JWT_TEST")

    monkeypatch.setenv("MCPTO_TRINO_JWT_TEST", "first-token")
    session1 = requests.Session()
    auth.set_http_session(session1)
    assert session1.headers.get("Authorization") == "Bearer first-token"

    monkeypatch.setenv("MCPTO_TRINO_JWT_TEST", "second-token")
    session2 = requests.Session()
    auth.set_http_session(session2)
    assert session2.headers.get("Authorization") == "Bearer second-token"


def test_per_call_jwt_missing_env_sends_empty_bearer(monkeypatch: pytest.MonkeyPatch) -> None:
    """PerCallJWTAuthentication with missing env var sends empty bearer (not crash)."""
    import requests

    auth = PerCallJWTAuthentication(env_var="MCPTO_TRINO_JWT_NONEXISTENT_XYZ")
    monkeypatch.delenv("MCPTO_TRINO_JWT_NONEXISTENT_XYZ", raising=False)

    session = requests.Session()
    auth.set_http_session(session)
    # Should not raise; empty token is an Trino-side auth failure, not a crash
    assert "Authorization" in session.headers


def test_per_call_jwt_default_env_var() -> None:
    """PerCallJWTAuthentication default env_var is MCPTO_TRINO_JWT."""
    auth = PerCallJWTAuthentication()
    assert auth._env_var == "MCPTO_TRINO_JWT"
