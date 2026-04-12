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
    """Phase 1 + Phase 2 config surface.

    See CONTEXT.md D-05..D-08 for the Phase 1 binding contract.
    Phase 2 adds Trino adapter settings (host, port, auth, TLS, concurrency).
    """

    model_config = SettingsConfigDict(
        env_prefix="MCPTO_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="forbid",  # unknown fields → ValidationError
    )

    # ── MCP transport ────────────────────────────────────────────────────
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

    # ── Trino adapter (Phase 2) ──────────────────────────────────────────
    trino_host: str | None = Field(
        default=None,
        description="Trino coordinator hostname. Required for live mode.",
    )
    trino_port: int = Field(
        default=8080,
        ge=1,
        le=65535,
        description="Trino coordinator port.",
    )
    trino_catalog: str = Field(
        default="iceberg",
        description="Default Trino catalog.",
    )
    trino_schema: str | None = Field(
        default=None,
        description="Default Trino schema.",
    )
    trino_auth_mode: Literal["none", "basic", "jwt"] = Field(
        default="none",
        description="Trino authentication mode.",
    )
    trino_user: str | None = Field(
        default=None,
        description="Trino user for basic auth.",
    )
    trino_password: SecretStr | None = Field(
        default=None,
        description="Trino password for basic auth.",
    )
    trino_jwt: SecretStr | None = Field(
        default=None,
        description="Trino JWT token for jwt auth.",
    )
    trino_verify_ssl: bool = Field(
        default=True,
        description="Verify SSL certificates for Trino connections.",
    )
    trino_ca_bundle: str | None = Field(
        default=None,
        description="Path to CA bundle for Trino TLS.",
    )
    trino_query_timeout_sec: int = Field(
        default=60,
        ge=1,
        le=1800,
        description="Wall-clock timeout per Trino query in seconds.",
    )
    max_concurrent_queries: int = Field(
        default=4,
        ge=1,
        le=32,
        description="Max concurrent Trino queries per MCP process.",
    )

    # ── Recommender (Phase 5) ────────────────────────────────────────────
    recommender_tier_p1: float = Field(
        default=2.4,
        description="Priority score threshold for P1 tier.",
    )
    recommender_tier_p2: float = Field(
        default=1.2,
        description="Priority score threshold for P2 tier.",
    )
    recommender_tier_p3: float = Field(
        default=0.5,
        description="Priority score threshold for P3 tier.",
    )
    recommender_top_n_bottleneck: int = Field(
        default=5,
        ge=1,
        le=50,
        description="Number of top operators in bottleneck ranking (D-08).",
    )

    @model_validator(mode="after")
    def _require_bearer_for_http(self) -> Settings:
        if self.transport == "http" and self.http_bearer_token is None:
            raise ValueError(
                "http_bearer_token is required when transport=http. "
                "Set MCPTO_HTTP_BEARER_TOKEN or pass --bearer-token on the CLI."
            )
        return self

    @model_validator(mode="after")
    def _require_trino_auth_fields(self) -> Settings:
        """Fail fast on invalid auth config before any network call (T-02-04)."""
        if self.trino_auth_mode == "basic":
            if self.trino_user is None:
                raise ValueError("trino_user is required when trino_auth_mode=basic. Set MCPTO_TRINO_USER.")
            if self.trino_password is None:
                raise ValueError("trino_password is required when trino_auth_mode=basic. Set MCPTO_TRINO_PASSWORD.")
        if self.trino_auth_mode == "jwt" and self.trino_jwt is None:
            raise ValueError("trino_jwt is required when trino_auth_mode=jwt. Set MCPTO_TRINO_JWT.")
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
