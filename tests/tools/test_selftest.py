"""PLAT-09: mcp_selftest tool round-trip test.

Verifies the tool returns mandatory fields (server_version, transport, echo,
capabilities) and that request_id/tool_name bind into the log context.

Landed by plan 01-04.
"""

from __future__ import annotations

import pytest

try:
    from mcp_trino_optimizer import app as app_mod  # landed in plan 01-04
except ImportError:
    app_mod = None  # type: ignore[assignment]

pytestmark = pytest.mark.skipif(app_mod is None, reason="mcp_trino_optimizer.app not yet implemented")


async def _invoke_selftest(mcp: object, echo: str = "hello") -> dict:
    """Invoke mcp_selftest via the FastMCP tool manager. Returns the response dict."""
    tool_manager = mcp._tool_manager  # type: ignore[attr-defined]
    result = await tool_manager.call_tool("mcp_selftest", {"echo": echo})
    return result  # type: ignore[return-value]


async def test_selftest_returns_mandatory_fields() -> None:
    mcp = app_mod.build_app()
    result = await _invoke_selftest(mcp)
    assert "server_version" in result
    assert "transport" in result
    assert "echo" in result
    assert "capabilities" in result


async def test_selftest_echo_round_trip() -> None:
    mcp = app_mod.build_app()
    result = await _invoke_selftest(mcp, echo="hello world")
    assert result["echo"] == "hello world"


async def test_selftest_binds_request_id_and_tool_name(
    capsys: pytest.CaptureFixture[str],
) -> None:
    import json

    mcp = app_mod.build_app()
    await _invoke_selftest(mcp, echo="bind_test")
    captured = capsys.readouterr()
    # Find a log line with tool_name and request_id bound
    for line in captured.err.strip().splitlines():
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if data.get("tool_name") == "mcp_selftest" and "request_id" in data:
            return
    raise AssertionError(f"No log line bound request_id + tool_name=mcp_selftest; stderr: {captured.err}")


async def test_selftest_capabilities_is_list() -> None:
    mcp = app_mod.build_app()
    result = await _invoke_selftest(mcp)
    caps = result["capabilities"]
    assert isinstance(caps, list)
    for cap in caps:
        assert isinstance(cap, str)
