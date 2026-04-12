"""Trino authentication builder — D-12, D-13, D-14.

Provides:
  - build_authentication(settings) → Authentication | None
    Produces the correct trino.auth object for none/basic/jwt modes.

  - PerCallJWTAuthentication
    JWT bearer auth that re-reads the token from os.environ on EVERY
    set_http_session call — so token rotation takes effect without a restart.
    Token is never stored as a field value or logged.

Security notes (T-02-03):
  - JWT is stored in settings as SecretStr; structlog redaction denylist
    covers the env var name and 'authorization' header value.
  - PerCallJWTAuthentication intentionally does NOT cache the token value;
    the env var is the source of truth at call time.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import requests
from trino.auth import Authentication, BasicAuthentication

if TYPE_CHECKING:
    from mcp_trino_optimizer.settings import Settings

__all__ = ["PerCallJWTAuthentication", "build_authentication"]


class PerCallJWTAuthentication(Authentication):
    """JWT bearer authentication that re-reads the token from os.environ on each call.

    Unlike trino-python-client's built-in ``JWTAuthentication`` which holds
    the token as a fixed string, this class reads ``os.environ[env_var]`` on
    every ``set_http_session`` invocation. This allows token rotation (e.g.
    short-lived tokens from a secrets manager) to take effect without
    restarting the MCP process.

    Args:
        env_var: Name of the environment variable holding the JWT token.
                 Defaults to ``"MCPTO_TRINO_JWT"`` (the pydantic-settings
                 env name for ``Settings.trino_jwt``).
    """

    def __init__(self, env_var: str = "MCPTO_TRINO_JWT") -> None:
        self._env_var = env_var

    def set_http_session(self, http_session: requests.Session) -> requests.Session:
        """Inject the current JWT from os.environ into the HTTP session headers.

        Called by the trino-python-client before each request. Reading from
        os.environ here (not ``__init__``) ensures the latest token is used.
        """
        token = os.environ.get(self._env_var, "")
        http_session.headers["Authorization"] = f"Bearer {token}"
        return http_session


def build_authentication(settings: Settings) -> Authentication | None:
    """Build a trino.auth.Authentication object from Settings.

    Args:
        settings: Validated Settings instance (auth fields already validated
                  by Settings._require_trino_auth_fields).

    Returns:
        - ``None`` for auth_mode="none"
        - ``BasicAuthentication`` for auth_mode="basic"
        - ``PerCallJWTAuthentication`` for auth_mode="jwt"

    Raises:
        ValueError: If auth_mode is unrecognised (defensive; should not occur
                    after Settings validation).
    """
    mode = settings.trino_auth_mode

    if mode == "none":
        return None

    if mode == "basic":
        # trino_user and trino_password are guaranteed non-None by Settings validator
        assert settings.trino_user is not None, "trino_user must be set for basic auth"
        assert settings.trino_password is not None, "trino_password must be set for basic auth"
        return BasicAuthentication(
            settings.trino_user,
            settings.trino_password.get_secret_value(),
        )

    if mode == "jwt":
        # PerCallJWTAuthentication re-reads from env on each request
        return PerCallJWTAuthentication()

    raise ValueError(f"Unrecognised trino_auth_mode: {mode!r}")
