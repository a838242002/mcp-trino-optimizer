"""PLAT-10: Every registered tool's JSON Schema passes the lint contract.

Covers:
- additionalProperties: false on every object type
- maxLength on every string (bounded by MAX_STRING_LEN)
- maxItems on every array
- Fake "bad tool" cases to lock in negative test coverage

Landed by plan 01-02 (schema_lint) + 01-04 (build_app).
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel, Field

try:
    from mcp_trino_optimizer.safety import schema_lint as lint  # landed in plan 01-02
except ImportError:
    lint = None  # type: ignore[assignment]

try:
    from mcp_trino_optimizer import app as app_mod  # landed in plan 01-04
except ImportError:
    app_mod = None  # type: ignore[assignment]


# Module-level BaseModel so Python 3.12+ (PEP 563 lazy annotations) and
# FastMCP's eval_str=True signature inspection can resolve the type hint
# when LooseInput is used as a tool parameter annotation. Defining it
# inside the test function breaks inspect.signature(eval_str=True).
class LooseInput(BaseModel):
    # No model_config with extra='forbid' → additionalProperties not false
    name: str = Field(max_length=100)

# Module-level guard only gates on schema_lint — the negative-case tests
# construct a throwaway FastMCP inline and don't need app.build_app().
pytestmark = pytest.mark.skipif(
    lint is None,
    reason="mcp_trino_optimizer.safety.schema_lint not yet implemented",
)


@pytest.mark.skipif(
    app_mod is None,
    reason="mcp_trino_optimizer.app not yet implemented (lands in plan 01-04)",
)
def test_all_tools_are_schema_compliant() -> None:
    mcp = app_mod.build_app()
    # Should not raise — build_app() already calls assert_tools_compliant,
    # but the explicit call here is the test's assertion surface.
    lint.assert_tools_compliant(mcp)


def test_schema_lint_detects_violation() -> None:
    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP(name="test")

    @mcp.tool()
    def bad_tool(sql: str) -> str:  # `str` with no Field constraint → no maxLength
        return sql

    with pytest.raises(lint.SchemaLintError, match="maxLength"):
        lint.assert_tools_compliant(mcp)


def test_schema_lint_rejects_missing_max_length() -> None:
    """Explicit: a string field without Field(max_length=...) must trigger a
    violation whose message contains 'maxLength'."""
    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP(name="test")

    @mcp.tool()
    def missing_max_length(freeform: str) -> str:
        return freeform

    with pytest.raises(lint.SchemaLintError, match="maxLength"):
        lint.assert_tools_compliant(mcp)


def test_schema_lint_rejects_missing_additional_properties_false() -> None:
    """A BaseModel input without `model_config = ConfigDict(extra='forbid')`
    must trigger an additionalProperties violation."""
    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP(name="test")

    @mcp.tool()
    def loose_tool(payload: LooseInput) -> str:
        return payload.name

    with pytest.raises(lint.SchemaLintError, match="additionalProperties"):
        lint.assert_tools_compliant(mcp)


def test_schema_lint_rejects_array_without_max_items() -> None:
    """A `list[str]` field without `Field(max_length=...)` on the list must
    trigger a maxItems violation."""
    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP(name="test")

    @mcp.tool()
    def array_no_cap(items: list[str]) -> int:
        return len(items)

    with pytest.raises(lint.SchemaLintError, match="maxItems"):
        lint.assert_tools_compliant(mcp)
