"""Typer CLI entry point (D-15).

Precedence: CLI flags > OS env (MCPTO_*) > .env > defaults.

CRITICAL: Belt-and-suspenders stdout discipline — route stdlib logging
and warnings to stderr BEFORE any domain import. Plan 01-03's
configure_logging repeats this with force=True, but doing it here
protects against any import-time side effects in Typer or FastMCP.
"""

from __future__ import annotations

# --- BELT-AND-SUSPENDERS: route everything to stderr before any import ---
import logging
import sys

logging.basicConfig(stream=sys.stderr, level=logging.INFO, force=True)
logging.captureWarnings(True)

# --- Normal imports after stderr lock-in ---
from typing import Optional  # noqa: E402

import typer  # noqa: E402

app = typer.Typer(
    name="mcp-trino-optimizer",
    add_completion=False,
    no_args_is_help=True,
    help="MCP server for Trino + Iceberg query optimization.",
)


@app.callback()
def _root() -> None:
    """Top-level callback — forces Typer to treat subcommands as subcommands.

    Without an explicit callback, a single-command Typer app collapses into
    ``mcp-trino-optimizer [options]`` (the subcommand name is swallowed).
    Registering a no-op callback restores the documented ``mcp-trino-optimizer
    serve [options]`` invocation shape that tests and docs assume.
    """


@app.command()
def serve(
    transport: str = typer.Option("stdio", "--transport", help="stdio or http"),
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8080, "--port"),
    log_level: str = typer.Option("INFO", "--log-level"),
    bearer_token: Optional[str] = typer.Option(  # noqa: UP045
        None,
        "--bearer-token",
        help=("Override MCPTO_HTTP_BEARER_TOKEN. Required for --transport http."),
        envvar=None,  # pydantic-settings reads env; Typer does not
    ),
) -> None:
    """Start the MCP server."""
    from mcp_trino_optimizer.settings import load_settings_or_die

    overrides: dict[str, object] = {
        "transport": transport,
        "http_host": host,
        "http_port": port,
        "log_level": log_level,
    }
    if bearer_token is not None:
        overrides["http_bearer_token"] = bearer_token

    # Fail-fast on any invalid / missing required setting.
    # load_settings_or_die prints a structured JSON error to stderr and
    # sys.exit(2) BEFORE any transport binds.
    settings = load_settings_or_die(**overrides)

    # Only now is it safe to configure structlog — Settings loaded cleanly.
    from mcp_trino_optimizer._runtime import runtime_info
    from mcp_trino_optimizer.logging_setup import configure_logging

    info = runtime_info(settings.log_level)
    configure_logging(
        settings.log_level,
        package_version=info.package_version,
        git_sha=info.git_sha,
    )

    from mcp_trino_optimizer.app import build_app

    mcp = build_app()

    from mcp_trino_optimizer.transports import run_stdio, run_streamable_http

    if settings.transport == "stdio":
        run_stdio(mcp)
    else:
        # D-07: bearer token is guaranteed non-None here because
        # Settings._require_bearer_for_http validated it.
        assert settings.http_bearer_token is not None
        run_streamable_http(
            mcp,
            host=settings.http_host,
            port=settings.http_port,
            bearer_token=settings.http_bearer_token.get_secret_value(),
        )


if __name__ == "__main__":
    app()
