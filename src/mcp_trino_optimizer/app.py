"""FastMCP app construction + tool auto-registration + schema_lint.

build_app() is the single entry point that CLI, tests, and transports
all use. It delegates tool registration to tools.discover_and_register
per D-04 (auto-registration) so adding a new tool in a later phase is
ONE new file in tools/ and nothing else. Then it calls
assert_tools_compliant(mcp) as a runtime guard — any non-compliant tool
crashes the server at startup BEFORE it listens, complementing the CI
test that runs the same assertion.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from mcp_trino_optimizer import tools
from mcp_trino_optimizer.logging_setup import get_logger
from mcp_trino_optimizer.safety.schema_lint import assert_tools_compliant


def build_app() -> FastMCP:
    """Construct the FastMCP app, auto-register tools, and enforce schema lint."""
    mcp = FastMCP(
        name="mcp-trino-optimizer",
        instructions=(
            "Model Context Protocol server for Trino + Iceberg query "
            "optimization. Analyzes plans, surfaces rule findings, and "
            "suggests safe rewrites."
        ),
        host="127.0.0.1",  # overridden by transports.run_streamable_http
        port=8080,  # overridden by transports.run_streamable_http
        log_level="INFO",  # structlog owns real logging; this is SDK-side
    )

    # D-04: auto-discover + auto-register every tool module in tools/.
    # Phase 1 registers exactly one: selftest. Phase 8 adds more files to
    # tools/ and this call picks them up with zero app.py edits. The
    # register(mcp) entry-point indirection avoids the circular import
    # hazard that module-level @mcp.tool() decorators would create.
    count = tools.discover_and_register(mcp)
    get_logger(__name__).info("tools_registered", count=count)

    # Runtime guard: every registered tool's JSON Schema must be compliant.
    # assert_tools_compliant raises SchemaLintError on violation → crashes
    # the server BEFORE it binds any port.
    assert_tools_compliant(mcp)

    return mcp


__all__ = ["build_app"]
