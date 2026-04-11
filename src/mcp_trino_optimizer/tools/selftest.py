"""mcp_selftest tool — server health probe (PLAT-09).

Returns server version, transport, capabilities, and a round-trip echo.
No Trino access, no user-origin strings in output → no untrusted_content
envelope needed. The echo field round-trips client input verbatim.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, cast

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field

from mcp_trino_optimizer._runtime import runtime_info
from mcp_trino_optimizer.tools._middleware import tool_envelope

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]
Transport = Literal["stdio", "http", "unknown"]


class SelftestOutput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"additionalProperties": False},
    )

    server_version: Annotated[str, Field(max_length=64)]
    transport: Literal["stdio", "http", "unknown"]
    echo: Annotated[str, Field(max_length=1024)]
    python_version: Annotated[str, Field(max_length=32)]
    package_version: Annotated[str, Field(max_length=64)]
    git_sha: Annotated[str, Field(max_length=16)]
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"]
    started_at: Annotated[str, Field(max_length=40)]
    capabilities: Annotated[
        list[Annotated[str, Field(max_length=64)]],
        Field(max_length=10),
    ]


_STATIC_DESCRIPTION = (
    "Returns server version, transport, capabilities, and a round-trip echo. "
    "Use as a protocol health probe. No Trino access required. "
    "Output contains no user-origin strings, so no untrusted_content envelope."
)


def register(mcp: FastMCP) -> None:
    """Register mcp_selftest on the given FastMCP instance.

    The handler takes ``echo`` as a direct parameter (not wrapped in a
    BaseModel input). FastMCP generates the ``mcp_selftestArguments``
    wrapper schema from the function signature and preserves the
    ``maxLength`` constraint via the ``Annotated[..., Field(...)]`` metadata,
    so schema_lint still catches a missing cap. Using a flat parameter
    keeps the tool invocable as ``call_tool("mcp_selftest", {"echo": "..."})``
    which matches the PLAT-09 contract in tests/tools/test_selftest.py.
    """

    @mcp.tool(
        name="mcp_selftest",
        title="Server self-test",
        description=_STATIC_DESCRIPTION,
    )
    @tool_envelope("mcp_selftest")
    def mcp_selftest(
        echo: Annotated[
            str,
            Field(
                default="",
                min_length=0,
                max_length=1024,
                description="Client-supplied string to echo back. Max 1KB.",
            ),
        ] = "",
    ) -> dict[str, Any]:
        info = runtime_info()
        # Validate the response shape via the SelftestOutput pydantic
        # model first, then return a plain dict so FastMCP's call_tool()
        # result subscripts cleanly in the PLAT-09 test contract.
        output = SelftestOutput(
            server_version=info.package_version,
            transport=cast(Transport, info.transport),
            echo=echo,
            python_version=info.python_version,
            package_version=info.package_version,
            git_sha=info.git_sha,
            log_level=cast(LogLevel, info.log_level),
            started_at=info.started_at,
            capabilities=["stdio", "streamable-http", "mcp_selftest"],
        )
        return output.model_dump()


__all__ = ["SelftestOutput", "register"]
