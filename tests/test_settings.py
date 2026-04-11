"""PLAT-08: pydantic-settings precedence + D-07 fail-fast + D-08 structured error.

Landed by plan 01-03.
"""

from __future__ import annotations

import json

import pytest

try:
    from mcp_trino_optimizer import settings as settings_mod  # landed in plan 01-03
except ImportError:
    settings_mod = None  # type: ignore[assignment]

pytestmark = pytest.mark.skipif(
    settings_mod is None, reason="mcp_trino_optimizer.settings not yet implemented"
)


def test_default_transport_is_stdio(clean_env: pytest.MonkeyPatch) -> None:
    s = settings_mod.Settings()
    assert s.transport == "stdio"


def test_env_var_precedence_over_default(clean_env: pytest.MonkeyPatch) -> None:
    clean_env.setenv("MCPTO_TRANSPORT", "http")
    clean_env.setenv("MCPTO_HTTP_BEARER_TOKEN", "a" * 32)
    s = settings_mod.Settings()
    assert s.transport == "http"


def test_cli_override_precedence_over_env(clean_env: pytest.MonkeyPatch) -> None:
    """Init kwargs must beat env vars (pydantic-settings source precedence)."""
    clean_env.setenv("MCPTO_TRANSPORT", "http")
    clean_env.setenv("MCPTO_HTTP_BEARER_TOKEN", "a" * 32)
    s = settings_mod.Settings(transport="stdio")
    assert s.transport == "stdio"


def test_http_without_bearer_token_raises(clean_env: pytest.MonkeyPatch) -> None:
    """D-07: transport=http + no bearer token → ValidationError."""
    from pydantic import ValidationError

    clean_env.setenv("MCPTO_TRANSPORT", "http")
    clean_env.delenv("MCPTO_HTTP_BEARER_TOKEN", raising=False)
    with pytest.raises(ValidationError):
        settings_mod.Settings()


def test_load_settings_or_die_exits_on_missing_bearer(
    clean_env: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """D-08: fail-fast must emit a structured JSON 'settings_error' line
    to stderr and exit non-zero."""
    clean_env.setenv("MCPTO_TRANSPORT", "http")
    clean_env.delenv("MCPTO_HTTP_BEARER_TOKEN", raising=False)
    load_or_die = getattr(settings_mod, "load_settings_or_die", None)
    if load_or_die is None:
        pytest.skip("load_settings_or_die not yet implemented")
    with pytest.raises(SystemExit):
        load_or_die()
    captured = capsys.readouterr()
    # Must be structured JSON on stderr
    last_line = captured.err.strip().splitlines()[-1]
    data = json.loads(last_line)
    assert data.get("event") == "settings_error"


def test_extra_env_var_rejected(clean_env: pytest.MonkeyPatch) -> None:
    """D-08: unknown env var must raise ValidationError (extra='forbid')."""
    from pydantic import ValidationError

    # Extra kwargs should fail when extra='forbid'
    with pytest.raises(ValidationError):
        settings_mod.Settings(unknown_field="x")


def test_http_port_range_validation(clean_env: pytest.MonkeyPatch) -> None:
    """Port must be in the 1..65535 range."""
    from pydantic import ValidationError

    clean_env.setenv("MCPTO_HTTP_BEARER_TOKEN", "a" * 32)
    with pytest.raises(ValidationError):
        settings_mod.Settings(transport="http", http_port=0)
    with pytest.raises(ValidationError):
        settings_mod.Settings(transport="http", http_port=70000)


def test_log_level_default_is_info(clean_env: pytest.MonkeyPatch) -> None:
    s = settings_mod.Settings()
    assert s.log_level == "INFO"
