"""Phase 1 Settings — pydantic-settings surface (PLAT-08, D-05..D-08).

Precedence: CLI init kwargs > OS env (MCPTO_*) > .env file > defaults.
Fail-fast: ValidationError → single JSON line to stderr → sys.exit(2)
BEFORE any transport binds a port. No partial startup.
"""

from __future__ import annotations

import sys
from typing import Any, Literal

import orjson
from pydantic import Field, SecretStr, ValidationError, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Phase 1 config surface.

    See CONTEXT.md D-05..D-08 for the binding contract. Trino-side
    settings (host, port, auth, TLS) defer to Phase 2.
    """

    model_config = SettingsConfigDict(
        env_prefix="MCPTO_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="forbid",  # unknown fields → ValidationError
    )

    transport: Literal["stdio", "http"] = Field(
        default="stdio",
        description="Which MCP transport to serve on.",
    )
    http_host: str = Field(
        default="127.0.0.1",
        description="Bind address for Streamable HTTP transport.",
    )
    http_port: int = Field(
        default=8080,
        ge=1,
        le=65535,
        description="Port for Streamable HTTP transport.",
    )
    http_bearer_token: SecretStr | None = Field(
        default=None,
        description=(
            "Static bearer token for Streamable HTTP transport. "
            "REQUIRED when transport=http; no default, no autogen (D-07)."
        ),
    )
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(
        default="INFO",
        description="structlog logging level.",
    )

    @model_validator(mode="after")
    def _require_bearer_for_http(self) -> Settings:
        if self.transport == "http" and self.http_bearer_token is None:
            raise ValueError(
                "http_bearer_token is required when transport=http. "
                "Set MCPTO_HTTP_BEARER_TOKEN or pass --bearer-token on the CLI."
            )
        return self


def load_settings_or_die(**overrides: Any) -> Settings:
    """Load Settings; on any ValidationError, emit a structured JSON
    error line to stderr and exit with code 2 BEFORE any transport starts.

    Called from cli.py before configure_logging runs — which is why we
    use orjson directly here instead of structlog.
    """
    try:
        return Settings(**overrides)
    except ValidationError as e:
        # include_context=False strips the ctx field which can hold non-
        # JSON-serializable values like ValueError instances from our
        # model_validator. include_input=False drops the raw input payload
        # (may contain secrets).
        err_line = orjson.dumps(
            {
                "level": "error",
                "event": "settings_error",
                "errors": e.errors(
                    include_url=False,
                    include_context=False,
                    include_input=False,
                ),
            }
        ).decode("utf-8")
        sys.stderr.write(err_line + "\n")
        sys.stderr.flush()
        sys.exit(2)


__all__ = ["Settings", "load_settings_or_die"]
