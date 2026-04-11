# ruff: noqa: T20
"""Transport entry points: stdio (with stdout guard) + Streamable HTTP (with bearer middleware).

CRITICAL DESIGN NOTES (from RESEARCH.md §1, §3.4, §3.5):

1. Stdio cannot use mcp.run("stdio") directly. FastMCP's stdio_server()
   captures sys.stdout.buffer AT CALL TIME. To install our SentinelWriter
   for stray-write detection we must:
     a. dup fd 1 BEFORE touching sys.stdout
     b. pass the pristine TextIOWrapper to stdio_server(stdout=...)
     c. install_stdout_guard() so everything else that writes to sys.stdout
        is captured as a violation

2. Streamable HTTP cannot use mcp.run("streamable-http") with built-in
   auth. FastMCP's AuthSettings requires an OAuth issuer_url and is not
   fit for static bearer tokens. The correct pattern is:
     a. Get the Starlette app: mcp.streamable_http_app()
     b. Wrap with our StaticBearerMiddleware
     c. Run via uvicorn directly with log_level="error"
"""

from __future__ import annotations

import asyncio
import hmac
import os
from io import TextIOWrapper
from typing import Any

import anyio
import uvicorn
from mcp.server.fastmcp import FastMCP
from mcp.server.stdio import stdio_server
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

from mcp_trino_optimizer._runtime import set_transport
from mcp_trino_optimizer.logging_setup import get_logger
from mcp_trino_optimizer.safety.stdout_guard import install_stdout_guard

# ════════════════════════════════════════════════════════════════════
# Stdio transport
# ════════════════════════════════════════════════════════════════════


def run_stdio(mcp: FastMCP) -> None:
    """Run MCP on stdio with a pristine duplicated stdout fd.

    The FastMCP stdio transport captures sys.stdout.buffer at call time
    (verified v1.27.0 src/mcp/server/stdio.py). To install a SentinelWriter
    on sys.stdout for stray-write detection, we give the SDK its own
    duplicated file descriptor and then replace sys.stdout.
    """
    # 1. Duplicate stdout fd BEFORE anything touches sys.stdout.
    pristine_fd = os.dup(1)
    pristine_stdout = TextIOWrapper(
        os.fdopen(pristine_fd, "wb"),
        encoding="utf-8",
        newline="",  # LF-only — Windows-safe JSON-RPC framing
        write_through=True,
    )

    # 2. Install the sentinel writer on sys.stdout.
    #    Any subsequent stray write becomes a stdout_violation event.
    install_stdout_guard()

    # 3. Mark the runtime transport so selftest reflects it.
    set_transport("stdio")

    async def _run() -> None:
        # anyio.wrap_file turns the sync TextIOWrapper into an async stream
        # the SDK can read/write through its internal anyio-based loop.
        async with stdio_server(
            stdout=anyio.wrap_file(pristine_stdout),
        ) as (read_stream, write_stream):
            await mcp._mcp_server.run(  # type: ignore[attr-defined,unused-ignore]
                read_stream,
                write_stream,
                mcp._mcp_server.create_initialization_options(),  # type: ignore[attr-defined,unused-ignore]
            )

    anyio.run(_run)


# ════════════════════════════════════════════════════════════════════
# Streamable HTTP transport + StaticBearerMiddleware
# ════════════════════════════════════════════════════════════════════


class StaticBearerMiddleware(BaseHTTPMiddleware):
    """Require ``Authorization: Bearer <token>`` on every /mcp request.

    - Uses hmac.compare_digest for constant-time comparison (T-01-08).
    - Returns 401 on missing/invalid tokens.
    - Never logs the token itself (T-01-04 info disclosure).
    - Bypasses FastMCP's built-in AuthSettings because that requires
      an OAuth issuer_url and is not fit for static bearer tokens
      (verified v1.27.0 src/mcp/server/auth/settings.py).
    """

    def __init__(self, app: ASGIApp, *, token: str) -> None:
        super().__init__(app)
        self._token_bytes = token.encode("utf-8")

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        auth_header = request.headers.get("authorization", "")
        if not auth_header.lower().startswith("bearer "):
            return JSONResponse(
                {"error": "unauthorized"},
                status_code=401,
            )
        presented = auth_header[len("bearer ") :].encode("utf-8")
        if not hmac.compare_digest(presented, self._token_bytes):
            return JSONResponse(
                {"error": "unauthorized"},
                status_code=401,
            )
        result: Response = await call_next(request)
        return result


def run_streamable_http(
    mcp: FastMCP,
    *,
    host: str,
    port: int,
    bearer_token: str,
) -> None:
    """Run MCP on Streamable HTTP with static bearer token auth."""
    set_transport("http")

    log = get_logger(__name__)
    log.warning(
        "plaintext_http_warning",
        message=(
            "This server binds plaintext HTTP. Put a reverse proxy "
            "(nginx, Caddy, Traefik) in front for TLS termination in "
            "production. Phase 1 does not manage TLS."
        ),
        host=host,
        port=port,
    )

    app = mcp.streamable_http_app()
    app.add_middleware(StaticBearerMiddleware, token=bearer_token)

    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="error",  # let structlog own logging; suppress uvicorn access log
        # Do NOT pass log_config — uvicorn's default log_config writes to
        # stdout. We already forced stdlib logging to stderr in logging_setup.
    )
    server = uvicorn.Server(config)
    asyncio.run(server.serve())


__all__ = [
    "StaticBearerMiddleware",
    "run_stdio",
    "run_streamable_http",
]
