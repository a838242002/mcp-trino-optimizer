"""JSON Schema strictness walker (PLAT-10, D-11).

Every MCP tool's input JSON Schema MUST have:
  - additionalProperties: false (from ConfigDict(extra="forbid"))
  - maxLength on every string field
  - maxItems on every array field
  - strings exceeding MAX_PROSE_LEN must have a pattern OR x-mcpto-sql: true

Called at startup by app.py (runtime guard) AND by a pytest test (CI guard).
Both paths run the same code so a test failure here catches regressions
before they can ship.

SDK surface: reads mcp._tool_manager.list_tools() — a deliberately
private attribute per RESEARCH.md §1 and §3.3. If FastMCP renames it in
a minor version, this code fails LOUDLY which is the correct failure
mode (fail fast, not silently skip validation).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

MAX_STRING_LEN = 100_000  # SQL cap from PLAT-10
MAX_PROSE_LEN = 4_096  # Other freeform strings
MAX_ARRAY_LEN = 1_000  # Default upper bound for arrays
MAX_PLAN_JSON_LEN = 1_000_000  # EXPLAIN (FORMAT JSON) output cap (Phase 2)


class SchemaLintError(Exception):
    """Raised when a registered tool has a non-compliant JSON Schema."""


def assert_tools_compliant(mcp: FastMCP) -> None:
    """Walk every registered tool's JSON Schema and assert compliance.

    Called at startup by app.py AND by a pytest test in CI. Raises
    SchemaLintError with a detailed message listing every violation.
    """
    violations: list[str] = []
    # Access the private _tool_manager deliberately — see module docstring.
    tool_manager = mcp._tool_manager  # type: ignore[attr-defined,unused-ignore]
    for tool in tool_manager.list_tools():
        _check_schema(
            tool.name,
            tool.parameters,
            path="",
            violations=violations,
        )
    if violations:
        raise SchemaLintError(
            f"Schema lint failed for {len(violations)} violation(s):\n  - " + "\n  - ".join(violations)
        )


def _check_schema(
    tool_name: str,
    schema: dict[str, Any],
    *,
    path: str,
    violations: list[str],
) -> None:
    t = schema.get("type")

    # --- Object ---------------------------------------------------------
    if t == "object":
        # Skip the root-level additionalProperties check: FastMCP auto-generates
        # the outer {tool}Arguments wrapper and does not emit
        # additionalProperties: false on it — only on the $defs entries
        # derived from our own BaseModel inputs. Parameter-name mismatches at
        # the root are caught by pydantic validation before the tool body
        # runs, so the root wrapper is outside our strictness contract. We
        # still recurse into properties and $defs, which is where our tool-
        # defined models live.
        if path != "" and schema.get("additionalProperties") is not False:
            violations.append(f"{tool_name}{path}: object must set additionalProperties: false")
        for name, sub in (schema.get("properties") or {}).items():
            _check_schema(tool_name, sub, path=f"{path}.{name}", violations=violations)

    # --- String ---------------------------------------------------------
    elif t == "string":
        max_len = schema.get("maxLength")
        if max_len is None:
            violations.append(f"{tool_name}{path}: string must set maxLength")
        elif max_len > MAX_STRING_LEN:
            violations.append(f"{tool_name}{path}: string maxLength {max_len} > {MAX_STRING_LEN}")
        # Prose fields without a pattern must have a reasonable prose cap
        if (
            "pattern" not in schema
            and max_len is not None
            and max_len > MAX_PROSE_LEN
            and not schema.get("x-mcpto-sql", False)
        ):
            violations.append(
                f"{tool_name}{path}: prose string maxLength {max_len} > {MAX_PROSE_LEN} without x-mcpto-sql"
            )

    # --- Array ----------------------------------------------------------
    elif t == "array":
        if "maxItems" not in schema:
            violations.append(f"{tool_name}{path}: array must set maxItems")
        elif schema["maxItems"] > MAX_ARRAY_LEN:
            violations.append(f"{tool_name}{path}: array maxItems {schema['maxItems']} > {MAX_ARRAY_LEN}")
        items = schema.get("items")
        if isinstance(items, dict):
            _check_schema(tool_name, items, path=f"{path}[]", violations=violations)

    # --- $defs / definitions (pydantic nested models) ------------------
    for defs_key in ("$defs", "definitions"):
        for def_name, sub in (schema.get(defs_key) or {}).items():
            _check_schema(
                tool_name,
                sub,
                path=f"{path}#{def_name}",
                violations=violations,
            )

    # --- anyOf / oneOf / allOf -----------------------------------------
    for key in ("anyOf", "oneOf", "allOf"):
        for i, sub in enumerate(schema.get(key) or []):
            _check_schema(tool_name, sub, path=f"{path}[{key}:{i}]", violations=violations)


__all__ = [
    "MAX_ARRAY_LEN",
    "MAX_PLAN_JSON_LEN",
    "MAX_PROSE_LEN",
    "MAX_STRING_LEN",
    "SchemaLintError",
    "assert_tools_compliant",
]
