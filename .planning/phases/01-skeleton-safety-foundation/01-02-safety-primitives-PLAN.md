---
phase: 01-skeleton-safety-foundation
plan: 02
type: execute
wave: 1
depends_on:
  - 01-01-test-harness-scaffold
files_modified:
  - src/mcp_trino_optimizer/safety/envelope.py
  - src/mcp_trino_optimizer/safety/stdout_guard.py
  - src/mcp_trino_optimizer/safety/schema_lint.py
  - tests/safety/test_stdout_guard.py
autonomous: true
requirements:
  - PLAT-05
  - PLAT-10
  - PLAT-11
must_haves:
  truths:
    - "wrap_untrusted(s) returns exactly {'source': 'untrusted', 'content': s} with no transformation, no delimiters, no escaping"
    - "install_stdout_guard() replaces sys.stdout with a SentinelWriter; a second call is a no-op"
    - "assert_tools_compliant(mcp) walks every registered tool's JSON Schema and raises SchemaLintError on any violation (missing additionalProperties: false, missing maxLength on strings, missing maxItems on arrays)"
    - "SentinelWriter.write captures stray writes and routes them to structlog as 'stdout_violation' without writing to stdout"
    - "The test 'fake bad tool without Field(max_length=...)' triggers a SchemaLintError with a message containing 'maxLength'"
  artifacts:
    - path: "src/mcp_trino_optimizer/safety/envelope.py"
      provides: "wrap_untrusted() untrusted-content envelope helper"
      contains: "def wrap_untrusted"
    - path: "src/mcp_trino_optimizer/safety/stdout_guard.py"
      provides: "SentinelWriter + install_stdout_guard() + uninstall_stdout_guard()"
      contains: "class SentinelWriter"
    - path: "src/mcp_trino_optimizer/safety/schema_lint.py"
      provides: "assert_tools_compliant(mcp) + SchemaLintError + _check_schema walker"
      contains: "def assert_tools_compliant"
  key_links:
    - from: "src/mcp_trino_optimizer/safety/schema_lint.py"
      to: "mcp._tool_manager.list_tools()"
      via: "private attribute access to get raw tool.parameters JSON Schema"
      pattern: "_tool_manager"
    - from: "src/mcp_trino_optimizer/safety/stdout_guard.py"
      to: "logging_setup.get_logger"
      via: "lazy import inside SentinelWriter.write to avoid circular import"
      pattern: "from mcp_trino_optimizer.logging_setup import"
---

<objective>
Ship the three safety primitives that every downstream plan depends on:
1. `wrap_untrusted()` — the untrusted-content envelope (PLAT-11, D-10, mitigates T-01-06 indirect prompt injection)
2. `install_stdout_guard()` + `SentinelWriter` — the stdout discipline layer (PLAT-05, D-12 layer 2, mitigates T-01-01 stdio corruption DoS)
3. `assert_tools_compliant(mcp)` + `SchemaLintError` — the JSON Schema strictness walker (PLAT-10, D-11, mitigates T-01-05 schema tampering)

These are pure, dependency-free primitives with ONE consumer (the app built in plan 01-04). They can be built in parallel with settings/logging (plan 01-03) because there's zero file overlap. Tests exist already as stubs from plan 01-01 and flip green the moment the modules exist. Critical property: schema_lint reads `mcp._tool_manager.list_tools()` — a deliberately private SDK attribute per RESEARCH.md §3.3 and §1 finding 1.

Purpose: Isolate the three hardest safety primitives into a plan whose only job is correctness of those primitives. Every downstream plan wires them up; this plan proves they work.
Output: Three hardened safety modules with all unit tests green.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/01-skeleton-safety-foundation/01-CONTEXT.md
@.planning/phases/01-skeleton-safety-foundation/01-RESEARCH.md
@.planning/phases/01-skeleton-safety-foundation/01-VALIDATION.md
@CLAUDE.md
@src/mcp_trino_optimizer/__init__.py
@src/mcp_trino_optimizer/safety/__init__.py
@tests/safety/test_envelope.py
@tests/safety/test_schema_lint.py

<interfaces>
<!-- FastMCP SDK surface that schema_lint relies on (from RESEARCH.md §3.3, §1): -->
<!--   mcp._tool_manager: ToolManager (private attribute, v1.27.0)               -->
<!--   mcp._tool_manager.list_tools() -> list[Tool]                              -->
<!--   Tool.name: str                                                             -->
<!--   Tool.description: str                                                      -->
<!--   Tool.parameters: dict[str, Any]  ← THIS IS THE JSON SCHEMA                 -->
<!--   Tool.output_schema: dict[str, Any] | None                                  -->
<!-- Generated via pydantic.BaseModel.model_json_schema(by_alias=True).           -->
<!-- Field(max_length=N, pattern=...) becomes JSON Schema maxLength / pattern.    -->
<!-- ConfigDict(extra="forbid") becomes additionalProperties: false.              -->

<!-- What this plan EXPORTS that later plans depend on: -->

```python
# safety.envelope
from typing import Literal, TypedDict

class UntrustedEnvelope(TypedDict):
    source: Literal["untrusted"]
    content: str

def wrap_untrusted(content: str) -> UntrustedEnvelope: ...

# safety.stdout_guard
class SentinelWriter: ...  # write, flush, isatty, fileno, writable, readable, seekable

def install_stdout_guard() -> None: ...  # idempotent
def uninstall_stdout_guard() -> None: ...  # test-only

# safety.schema_lint
MAX_STRING_LEN: int  # 100_000 (SQL cap)
MAX_PROSE_LEN: int   # 4_096 (other freeform strings)
MAX_ARRAY_LEN: int   # 1_000

class SchemaLintError(Exception): ...

def assert_tools_compliant(mcp: "FastMCP") -> None: ...  # raises SchemaLintError on violation
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Implement safety/envelope.py (the untrusted-content envelope)</name>
  <files>src/mcp_trino_optimizer/safety/envelope.py</files>
  <read_first>
    - /Users/allen/repo/mcp-trino-optimizer/.planning/phases/01-skeleton-safety-foundation/01-RESEARCH.md §10 (wrap_untrusted contract + test — copy verbatim)
    - /Users/allen/repo/mcp-trino-optimizer/.planning/phases/01-skeleton-safety-foundation/01-CONTEXT.md D-10 (exact pure-JSON envelope contract)
    - /Users/allen/repo/mcp-trino-optimizer/tests/safety/test_envelope.py (the tests this module must satisfy — already stubbed in plan 01-01)
  </read_first>
  <behavior>
    - `wrap_untrusted("hello")` returns `{"source": "untrusted", "content": "hello"}` — exact dict, not a string
    - `wrap_untrusted("")` returns `{"source": "untrusted", "content": ""}`
    - `wrap_untrusted(adversarial)` preserves control characters, injection attempts, triple-backticks, and `<|im_start|>` markers verbatim with zero transformation
    - Return type is a `TypedDict` so mypy strict mode sees the exact literal type `"untrusted"`
    - No escaping, no delimiters, no nested markers — the MCP client is responsible for safe rendering (D-10)
  </behavior>
  <action>
    Write `src/mcp_trino_optimizer/safety/envelope.py` by COPYING RESEARCH.md §10 VERBATIM:

    ```python
    # src/mcp_trino_optimizer/safety/envelope.py
    """Untrusted-content envelope for tool responses (PLAT-11, D-10).

    Every tool response that embeds a user-origin string (SQL, pasted
    EXPLAIN JSON, Trino error messages, remote metadata) MUST route that
    string through wrap_untrusted() before putting it into a response.

    The envelope is a pure JSON shape — no delimiters, no escaping, no
    nested markers. The MCP client is responsible for rendering the
    envelope safely for LLM consumption.

    See PLAT-11, PITFALLS.md §Pitfall 8 (indirect prompt injection),
    CONTEXT.md D-10, RESEARCH.md §10.
    """
    from __future__ import annotations

    from typing import Literal, TypedDict


    class UntrustedEnvelope(TypedDict):
        source: Literal["untrusted"]
        content: str


    def wrap_untrusted(content: str) -> UntrustedEnvelope:
        """Wrap a user-origin string in the untrusted-content envelope.

        Args:
            content: Any user-origin string. Preserved verbatim.

        Returns:
            Exactly `{"source": "untrusted", "content": content}`.
            No transformation. The MCP client distinguishes untrusted
            content by checking the `source` field.
        """
        return {"source": "untrusted", "content": content}


    __all__ = ["UntrustedEnvelope", "wrap_untrusted"]
    ```

    DO NOT add sanitization, HTML escaping, base64 encoding, or any transformation. The contract is PURE passthrough inside a fixed JSON shape.
  </action>
  <verify>
    <automated>cd /Users/allen/repo/mcp-trino-optimizer && uv run pytest tests/safety/test_envelope.py -v</automated>
  </verify>
  <acceptance_criteria>
    - `uv run pytest tests/safety/test_envelope.py -v` — ALL tests pass (no skips, no xfails)
    - `grep -c "def wrap_untrusted" src/mcp_trino_optimizer/safety/envelope.py` returns `1`
    - `grep -c "return {\"source\": \"untrusted\", \"content\": content}" src/mcp_trino_optimizer/safety/envelope.py` returns `1` — exact shape, no transformation
    - `grep -c "TypedDict\|UntrustedEnvelope" src/mcp_trino_optimizer/safety/envelope.py` returns at least `2`
    - `uv run python -c "from mcp_trino_optimizer.safety.envelope import wrap_untrusted; assert wrap_untrusted('x') == {'source': 'untrusted', 'content': 'x'}"` exits 0
    - `uv run mypy src/mcp_trino_optimizer/safety/envelope.py` exits 0 in strict mode
  </acceptance_criteria>
  <done>wrap_untrusted passes every unit test from plan 01-01 including the adversarial prompt-injection cases; mypy strict is clean; no transformation applied to content.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Implement safety/stdout_guard.py (the SentinelWriter stdout discipline layer)</name>
  <files>src/mcp_trino_optimizer/safety/stdout_guard.py, tests/safety/test_stdout_guard.py</files>
  <read_first>
    - /Users/allen/repo/mcp-trino-optimizer/.planning/phases/01-skeleton-safety-foundation/01-RESEARCH.md §4 (stdout guard behavior contract + implementation — copy verbatim)
    - /Users/allen/repo/mcp-trino-optimizer/.planning/phases/01-skeleton-safety-foundation/01-CONTEXT.md D-12 (three-layer stdout discipline, behavior contract)
  </read_first>
  <behavior>
    - `install_stdout_guard()` replaces `sys.stdout` with a `SentinelWriter`
    - Calling `install_stdout_guard()` twice is a no-op (idempotent)
    - `uninstall_stdout_guard()` restores the original `sys.stdout` (test-only)
    - `SentinelWriter.write(data)` with non-whitespace data logs a `stdout_violation` ERROR event via structlog (NOT via direct stderr write) and returns the byte count
    - `SentinelWriter.write(data)` with empty or whitespace-only data is silent and returns quickly (avoids noise from flushes)
    - `SentinelWriter.fileno()` raises `OSError` (idiomatic "no fd" signal so rich/colorama probe falls back to no-color mode)
    - `SentinelWriter.isatty()` returns False, `writable()` returns True, `readable()` returns False, `seekable()` returns False
    - Import of `mcp_trino_optimizer.logging_setup` must be LAZY (inside `write`) to avoid circular import because logging_setup lives in plan 01-03 and that module imports things from elsewhere
  </behavior>
  <action>
    Write `src/mcp_trino_optimizer/safety/stdout_guard.py` by COPYING RESEARCH.md §4.3 VERBATIM. The critical behavioral constraints:

    1. The `SentinelWriter.write` method MUST use a LAZY import of `logging_setup.get_logger` — any top-level import creates a chicken-and-egg problem because plan 01-03 hasn't landed `logging_setup.py` yet and this plan may execute in parallel.

    2. Use a fallback path: if `logging_setup` is not yet importable (e.g., during tests that don't call `configure_logging`), write directly to `sys.stderr.buffer` with a JSON-serialized line. This ensures the guard works in isolation.

    Final module:

    ```python
    # src/mcp_trino_optimizer/safety/stdout_guard.py
    # ruff: noqa: T20
    """Stdout discipline layer 2 (of 3) for stdio mode (PLAT-05, D-12 layer 2).

    Three-layer stdout discipline:
      Layer 1 (logging_setup): structlog writes to stderr only.
      Layer 2 (this file): sys.stdout replaced with SentinelWriter that captures
                           stray writes and routes them to structlog as violations.
      Layer 3 (smoke test): CI spawns the server and asserts every byte on stdout
                            is a valid JSON-RPC frame.

    CRITICAL: Install AFTER FastMCP's stdio_server() has captured the pristine
    fd (see RESEARCH.md §3.4). Installing too early poisons FastMCP's writer.
    The transports.run_stdio() orchestrates the correct order.
    """
    from __future__ import annotations

    import sys
    from typing import Any

    _installed: bool = False
    _original_stdout: Any = None


    class SentinelWriter:
        """A write-like object that captures stray stdout writes as violations.

        Installed on sys.stdout in stdio mode AFTER the pristine stdout fd has
        been duplicated and handed to FastMCP. Any subsequent write that reaches
        this object is, by definition, a stray write that would have corrupted
        the JSON-RPC channel — we log it and drop it.

        Uses lazy import of logging_setup to avoid circular import at module
        load time. Falls back to raw stderr write if structlog isn't configured.
        """

        encoding = "utf-8"
        errors = "replace"

        def write(self, data: str) -> int:
            if not data or not data.strip():
                # Ignore empty / whitespace-only flushes. Python frequently
                # calls write("\n") or write("") at shutdown.
                return len(data) if data else 0
            # Lazy import — logging_setup is plan 01-03 and may race with us.
            try:
                from mcp_trino_optimizer.logging_setup import get_logger
                get_logger(__name__).error(
                    "stdout_violation",
                    bytes_len=len(data),
                    preview=data[:200],
                )
            except Exception:  # noqa: BLE001 — fallback must not raise
                # Fallback: raw JSON line to stderr so the event is never lost.
                import json
                fallback = json.dumps({
                    "event": "stdout_violation",
                    "level": "error",
                    "bytes_len": len(data),
                    "preview": data[:200],
                    "note": "logging_setup unavailable; fallback path",
                })
                sys.stderr.write(fallback + "\n")
                sys.stderr.flush()
            return len(data)

        def flush(self) -> None:
            pass

        def isatty(self) -> bool:
            return False

        def writable(self) -> bool:
            return True

        def readable(self) -> bool:
            return False

        def seekable(self) -> bool:
            return False

        def fileno(self) -> int:
            # rich / colorama probe fileno(); OSError is the idiomatic "no fd" signal.
            raise OSError("SentinelWriter has no file descriptor")


    def install_stdout_guard() -> None:
        """Replace sys.stdout with a SentinelWriter. Idempotent."""
        global _installed, _original_stdout
        if _installed:
            return
        _original_stdout = sys.stdout
        sys.stdout = SentinelWriter()  # type: ignore[assignment]
        _installed = True


    def uninstall_stdout_guard() -> None:
        """Restore the original stdout. Used only by tests."""
        global _installed, _original_stdout
        if not _installed:
            return
        sys.stdout = _original_stdout
        _original_stdout = None
        _installed = False


    __all__ = [
        "SentinelWriter",
        "install_stdout_guard",
        "uninstall_stdout_guard",
    ]
    ```

    **Add a dedicated unit test file** `tests/safety/test_stdout_guard.py` (this is NOT in plan 01-01's Wave 0 list — add it here because it's specific to this primitive and doesn't map to a PLAT-ID directly, just supports PLAT-05 coverage):

    ```python
    """Unit tests for the SentinelWriter stdout discipline layer."""
    from __future__ import annotations

    import sys

    import pytest

    from mcp_trino_optimizer.safety.stdout_guard import (
        SentinelWriter,
        install_stdout_guard,
        uninstall_stdout_guard,
    )


    @pytest.fixture(autouse=True)
    def _cleanup():
        yield
        uninstall_stdout_guard()


    def test_install_replaces_sys_stdout():
        original = sys.stdout
        install_stdout_guard()
        assert isinstance(sys.stdout, SentinelWriter)
        uninstall_stdout_guard()
        assert sys.stdout is original


    def test_install_is_idempotent():
        install_stdout_guard()
        first = sys.stdout
        install_stdout_guard()
        assert sys.stdout is first


    def test_stray_write_is_logged_not_raised(capsys):
        install_stdout_guard()
        sys.stdout.write("stray content from a careless print call\n")
        captured = capsys.readouterr()
        # Either structlog (if configured) or fallback JSON on stderr
        assert "stdout_violation" in captured.err
        assert "stray content" in captured.err
        assert captured.out == ""  # SentinelWriter drops the content


    def test_whitespace_only_write_is_silent(capsys):
        install_stdout_guard()
        sys.stdout.write("")
        sys.stdout.write("\n")
        sys.stdout.write("   ")
        captured = capsys.readouterr()
        assert "stdout_violation" not in captured.err


    def test_fileno_raises_oserror():
        writer = SentinelWriter()
        with pytest.raises(OSError):
            writer.fileno()


    def test_sentinel_attributes():
        writer = SentinelWriter()
        assert writer.isatty() is False
        assert writer.writable() is True
        assert writer.readable() is False
        assert writer.seekable() is False
        assert writer.encoding == "utf-8"
    ```

    **IMPORTANT:** Add `tests/safety/test_stdout_guard.py` to the files_modified list mentally — it's a Task-2 side-output. Adjust the <files> list at the top of this task accordingly by also listing the test file.
  </action>
  <verify>
    <automated>cd /Users/allen/repo/mcp-trino-optimizer && uv run pytest tests/safety/test_stdout_guard.py -v && uv run mypy src/mcp_trino_optimizer/safety/stdout_guard.py</automated>
  </verify>
  <acceptance_criteria>
    - `tests/safety/test_stdout_guard.py` exists and all tests pass
    - `grep -c "class SentinelWriter" src/mcp_trino_optimizer/safety/stdout_guard.py` returns `1`
    - `grep -c "def install_stdout_guard" src/mcp_trino_optimizer/safety/stdout_guard.py` returns `1`
    - `grep -c "def uninstall_stdout_guard" src/mcp_trino_optimizer/safety/stdout_guard.py` returns `1`
    - `grep -c "fileno" src/mcp_trino_optimizer/safety/stdout_guard.py` returns at least `1` (required for rich/colorama probe)
    - `grep -c "from mcp_trino_optimizer.logging_setup import" src/mcp_trino_optimizer/safety/stdout_guard.py` returns `1` (lazy import inside method)
    - Second `install_stdout_guard()` call is a no-op (`test_install_is_idempotent` passes)
    - `uv run mypy src/mcp_trino_optimizer/safety/stdout_guard.py` exits 0 in strict mode
  </acceptance_criteria>
  <done>SentinelWriter captures stray writes, idempotent install/uninstall works, fileno() raises OSError, lazy logging_setup import avoids circular deps, unit tests all green.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: Implement safety/schema_lint.py (the JSON Schema strictness walker)</name>
  <files>src/mcp_trino_optimizer/safety/schema_lint.py</files>
  <read_first>
    - /Users/allen/repo/mcp-trino-optimizer/.planning/phases/01-skeleton-safety-foundation/01-RESEARCH.md §9 (schema_lint algorithm + §9.2 implementation — copy verbatim)
    - /Users/allen/repo/mcp-trino-optimizer/.planning/phases/01-skeleton-safety-foundation/01-RESEARCH.md §1 finding 1 (mcp._tool_manager.list_tools() is the SDK surface; private attr by design)
    - /Users/allen/repo/mcp-trino-optimizer/.planning/phases/01-skeleton-safety-foundation/01-RESEARCH.md §20 Q8 (fake bad tool test pattern)
    - /Users/allen/repo/mcp-trino-optimizer/.planning/phases/01-skeleton-safety-foundation/01-CONTEXT.md D-11 (schema-lint contract)
    - /Users/allen/repo/mcp-trino-optimizer/tests/safety/test_schema_lint.py (tests this must satisfy, already stubbed in plan 01-01)
  </read_first>
  <behavior>
    - `assert_tools_compliant(mcp)` with a clean FastMCP instance (our app) returns None
    - `assert_tools_compliant(mcp)` with a tool whose input is `sql: str` (no Field constraints) raises `SchemaLintError` whose message contains `"maxLength"`
    - `assert_tools_compliant(mcp)` with a tool whose input BaseModel is missing `ConfigDict(extra="forbid")` raises `SchemaLintError` whose message contains `"additionalProperties"`
    - `assert_tools_compliant(mcp)` with a tool that has a `list[str]` parameter without a bounded container raises `SchemaLintError` whose message contains `"maxItems"`
    - The walker recurses into `$defs` / `definitions` (pydantic v2 generates these for nested models) and into `anyOf` / `oneOf` / `allOf`
    - Constants: `MAX_STRING_LEN = 100_000` (the SQL cap from PLAT-10), `MAX_PROSE_LEN = 4_096`, `MAX_ARRAY_LEN = 1_000`
    - Strings longer than MAX_PROSE_LEN must either have a `pattern` OR an explicit `x-mcpto-sql: true` extension to opt in to the 100KB cap (per RESEARCH.md §9.1 identifier-detection-by-opt-in rule)
  </behavior>
  <action>
    Write `src/mcp_trino_optimizer/safety/schema_lint.py` by COPYING RESEARCH.md §9.2 VERBATIM with one tightening: constants module-level, SchemaLintError class, assert_tools_compliant function, `_check_schema` recursive walker. Full module:

    ```python
    # src/mcp_trino_optimizer/safety/schema_lint.py
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
    MAX_PROSE_LEN = 4_096      # Other freeform strings
    MAX_ARRAY_LEN = 1_000      # Default upper bound for arrays


    class SchemaLintError(Exception):
        """Raised when a registered tool has a non-compliant JSON Schema."""


    def assert_tools_compliant(mcp: "FastMCP") -> None:
        """Walk every registered tool's JSON Schema and assert compliance.

        Called at startup by app.py AND by a pytest test in CI. Raises
        SchemaLintError with a detailed message listing every violation.
        """
        violations: list[str] = []
        # Access the private _tool_manager deliberately — see module docstring.
        tool_manager = mcp._tool_manager  # type: ignore[attr-defined]
        for tool in tool_manager.list_tools():
            _check_schema(
                tool.name,
                tool.parameters,
                path="",
                violations=violations,
            )
        if violations:
            raise SchemaLintError(
                f"Schema lint failed for {len(violations)} violation(s):\n  - "
                + "\n  - ".join(violations)
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
            if schema.get("additionalProperties") is not False:
                violations.append(
                    f"{tool_name}{path}: object must set additionalProperties: false"
                )
            for name, sub in (schema.get("properties") or {}).items():
                _check_schema(
                    tool_name, sub, path=f"{path}.{name}", violations=violations
                )

        # --- String ---------------------------------------------------------
        elif t == "string":
            max_len = schema.get("maxLength")
            if max_len is None:
                violations.append(
                    f"{tool_name}{path}: string must set maxLength"
                )
            elif max_len > MAX_STRING_LEN:
                violations.append(
                    f"{tool_name}{path}: string maxLength {max_len} > {MAX_STRING_LEN}"
                )
            # Prose fields without a pattern must have a reasonable prose cap
            if (
                "pattern" not in schema
                and max_len is not None
                and max_len > MAX_PROSE_LEN
                and not schema.get("x-mcpto-sql", False)
            ):
                violations.append(
                    f"{tool_name}{path}: prose string maxLength {max_len} > "
                    f"{MAX_PROSE_LEN} without x-mcpto-sql"
                )

        # --- Array ----------------------------------------------------------
        elif t == "array":
            if "maxItems" not in schema:
                violations.append(
                    f"{tool_name}{path}: array must set maxItems"
                )
            elif schema["maxItems"] > MAX_ARRAY_LEN:
                violations.append(
                    f"{tool_name}{path}: array maxItems {schema['maxItems']} > {MAX_ARRAY_LEN}"
                )
            items = schema.get("items")
            if isinstance(items, dict):
                _check_schema(
                    tool_name, items, path=f"{path}[]", violations=violations
                )

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
                _check_schema(
                    tool_name, sub, path=f"{path}[{key}:{i}]", violations=violations
                )


    __all__ = [
        "MAX_ARRAY_LEN",
        "MAX_PROSE_LEN",
        "MAX_STRING_LEN",
        "SchemaLintError",
        "assert_tools_compliant",
    ]
    ```

    **Critical note for the executor on assumption A1 (RESEARCH.md §19):** The test `test_all_tools_are_schema_compliant` in plan 01-01's stub requires `build_app()` from plan 01-04 — it will stay `importorskip`-skipped until plan 01-04 lands. BUT the `test_schema_lint_detects_violation` test (which builds a throwaway `FastMCP()` in the test itself with a bad tool) WILL run in this plan and validates the walker logic. That test is your primary green signal for this task.

    If `test_schema_lint_detects_violation` fails because pydantic-core's schema generation does NOT emit `additionalProperties: false` for `extra="forbid"` (assumption A1), fix it by using `model_config = ConfigDict(extra="forbid", json_schema_extra={"additionalProperties": False})` in the fake test tool AND document the fallback in a module comment on schema_lint.py. But first verify the default path works — RESEARCH.md §19 rates A1 as a soft assumption with an easy fallback.
  </action>
  <verify>
    <automated>cd /Users/allen/repo/mcp-trino-optimizer && uv run pytest tests/safety/test_schema_lint.py::test_schema_lint_detects_violation tests/safety/test_schema_lint.py::test_schema_lint_rejects_missing_max_length tests/safety/test_schema_lint.py::test_schema_lint_rejects_array_without_max_items -v && uv run mypy src/mcp_trino_optimizer/safety/schema_lint.py</automated>
  </verify>
  <acceptance_criteria>
    - `uv run pytest tests/safety/test_schema_lint.py::test_schema_lint_detects_violation -v` passes (fake-bad-tool with `sql: str` triggers SchemaLintError with `maxLength` in the message)
    - `uv run pytest tests/safety/test_schema_lint.py::test_schema_lint_rejects_missing_max_length -v` passes
    - `uv run pytest tests/safety/test_schema_lint.py::test_schema_lint_rejects_array_without_max_items -v` passes
    - `test_all_tools_are_schema_compliant` remains skipped (build_app not yet implemented — lands in plan 01-04)
    - `grep -c "MAX_STRING_LEN = 100_000" src/mcp_trino_optimizer/safety/schema_lint.py` returns `1`
    - `grep -c "MAX_ARRAY_LEN = 1_000" src/mcp_trino_optimizer/safety/schema_lint.py` returns `1`
    - `grep -c "class SchemaLintError" src/mcp_trino_optimizer/safety/schema_lint.py` returns `1`
    - `grep -c "_tool_manager" src/mcp_trino_optimizer/safety/schema_lint.py` returns at least `1` (private SDK attribute access)
    - `grep -c "additionalProperties" src/mcp_trino_optimizer/safety/schema_lint.py` returns at least `2`
    - `grep -c '"\\$defs"\|"definitions"' src/mcp_trino_optimizer/safety/schema_lint.py` returns at least `1` (nested model recursion)
    - `grep -c "anyOf\|oneOf\|allOf" src/mcp_trino_optimizer/safety/schema_lint.py` returns at least `1`
    - `uv run mypy src/mcp_trino_optimizer/safety/schema_lint.py` exits 0 in strict mode
  </acceptance_criteria>
  <done>The walker detects missing `additionalProperties: false`, missing `maxLength`, missing `maxItems`, recurses into nested pydantic models, and raises SchemaLintError with detailed violation paths. The fake-bad-tool tests green; the test requiring build_app stays skipped until plan 01-04.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Tool input JSON Schema → pydantic validator | Strict schemas block payload injection and oversize attacks |
| Tool response user-origin strings → LLM client | wrap_untrusted envelope isolates strings from instructions |
| Python sys.stdout → JSON-RPC framing | SentinelWriter catches stray writes that would corrupt the channel |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-01-01 | DoS | sys.stdout corrupted by stray writes | mitigate | `SentinelWriter` captures stray writes as `stdout_violation` log events; smoke test in plan 01-06 CI asserts stdout is pure JSON-RPC (layer 3). Unit tests here cover layer 2 correctness. |
| T-01-05 | Tampering | Tool input JSON Schema missing `additionalProperties: false` allows payload injection | mitigate | `assert_tools_compliant` walks every registered tool; fake-bad-tool test proves detection works before real tools exist |
| T-01-06 | Tampering | Indirect prompt injection via echoed user content | mitigate | `wrap_untrusted()` envelope provides structured JSON the MCP client can key off the `source` field; unit tests lock the contract including adversarial inputs |
</threat_model>

<verification>
Run `uv run pytest tests/safety/ -v` — all tests in envelope and schema_lint that don't require build_app must pass. The stdout_guard tests are self-contained and must all pass. Run `uv run mypy src/mcp_trino_optimizer/safety/` and confirm strict mode is clean.
</verification>

<success_criteria>
- `wrap_untrusted` returns exactly `{"source": "untrusted", "content": content}` for every input including adversarial prompt-injection test cases
- `install_stdout_guard()` replaces sys.stdout idempotently; stray writes become logged `stdout_violation` events
- `assert_tools_compliant` detects missing `additionalProperties: false`, missing `maxLength`, missing `maxItems`; the fake-bad-tool test proves this
- `uv run mypy src/mcp_trino_optimizer/safety/` is clean in strict mode
- Every test in `tests/safety/test_envelope.py` and `tests/safety/test_stdout_guard.py` passes
- Tests in `tests/safety/test_schema_lint.py` that don't require `build_app` pass; ones that do remain skipped until plan 01-04
</success_criteria>

<output>
After completion, create `.planning/phases/01-skeleton-safety-foundation/01-02-SUMMARY.md`
</output>
