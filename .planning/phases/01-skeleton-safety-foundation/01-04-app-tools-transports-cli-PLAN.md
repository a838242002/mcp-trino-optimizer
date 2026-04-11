---
phase: 01-skeleton-safety-foundation
plan: 04
type: execute
wave: 2
depends_on:
  - 01-01-test-harness-scaffold
  - 01-02-safety-primitives
  - 01-03-settings-logging-runtime
files_modified:
  - src/mcp_trino_optimizer/app.py
  - src/mcp_trino_optimizer/tools/__init__.py
  - src/mcp_trino_optimizer/tools/selftest.py
  - src/mcp_trino_optimizer/tools/_middleware.py
  - src/mcp_trino_optimizer/transports.py
  - src/mcp_trino_optimizer/cli.py
autonomous: true
requirements:
  - PLAT-02
  - PLAT-03
  - PLAT-05
  - PLAT-09
  - PLAT-10
must_haves:
  truths:
    - "mcp-trino-optimizer serve starts on stdio transport by default and answers JSON-RPC initialize"
    - "mcp-trino-optimizer serve --transport http binds 127.0.0.1:8080 and enforces bearer token via StaticBearerMiddleware using hmac.compare_digest"
    - "build_app() constructs a FastMCP instance, calls tools.discover_and_register(mcp) which auto-discovers every sibling module in tools/ and calls each module's register(mcp) entry point (D-04), then calls assert_tools_compliant(mcp) — failing compliance raises SchemaLintError before the server starts"
    - "The mcp_selftest tool returns server_version, transport, echo, python_version, package_version, git_sha, log_level, started_at, capabilities"
    - "run_stdio() installs the stdout_guard AFTER duplicating fd 1 and passes the pristine stream to stdio_server(stdout=...) — matching RESEARCH.md §3.4 exactly"
    - "run_streamable_http() wraps mcp.streamable_http_app() with StaticBearerMiddleware then serves via uvicorn.Server with log_level='error'"
    - "HTTP transport startup emits a WARNING log 'plaintext_http_warning' reminding the operator to use a reverse proxy for TLS (RESEARCH.md §20 Q3)"
    - "tool_envelope decorator binds request_id and tool_name contextvars so every log line inside the tool handler carries them"
  artifacts:
    - path: "src/mcp_trino_optimizer/app.py"
      provides: "build_app() — FastMCP construction + tool registration + schema_lint"
      contains: "def build_app"
    - path: "src/mcp_trino_optimizer/tools/selftest.py"
      provides: "mcp_selftest tool with SelftestInput/SelftestOutput pydantic models + register(mcp)"
      contains: "def mcp_selftest"
    - path: "src/mcp_trino_optimizer/tools/_middleware.py"
      provides: "tool_envelope decorator binding request_id/tool_name contextvars"
      contains: "def tool_envelope"
    - path: "src/mcp_trino_optimizer/transports.py"
      provides: "run_stdio() + run_streamable_http() + StaticBearerMiddleware"
      contains: "class StaticBearerMiddleware"
    - path: "src/mcp_trino_optimizer/cli.py"
      provides: "Typer app with serve subcommand"
      contains: "app = typer.Typer"
  key_links:
    - from: "src/mcp_trino_optimizer/app.py"
      to: "src/mcp_trino_optimizer/safety/schema_lint.py"
      via: "assert_tools_compliant(mcp) call after tool registration"
      pattern: "assert_tools_compliant"
    - from: "src/mcp_trino_optimizer/transports.py"
      to: "src/mcp_trino_optimizer/safety/stdout_guard.py"
      via: "install_stdout_guard() inside run_stdio after fd dup"
      pattern: "install_stdout_guard"
    - from: "src/mcp_trino_optimizer/transports.py"
      to: "hmac.compare_digest"
      via: "StaticBearerMiddleware.dispatch constant-time compare"
      pattern: "hmac\\.compare_digest"
    - from: "src/mcp_trino_optimizer/cli.py"
      to: "src/mcp_trino_optimizer/settings.py"
      via: "load_settings_or_die(**overrides)"
      pattern: "load_settings_or_die"
    - from: "src/mcp_trino_optimizer/tools/__init__.py"
      to: "every sibling module in tools/"
      via: "pkgutil.iter_modules + importlib.import_module + module.register(mcp) entry point (D-04)"
      pattern: "discover_and_register"
    - from: "src/mcp_trino_optimizer/tools/selftest.py"
      to: "mcp.tool()"
      via: "module-level register(mcp) function invoked by tools.discover_and_register"
      pattern: "def register"
---

<objective>
Wire the app together. This plan creates the `FastMCP` instance, the single `mcp_selftest` tool, the stdio and Streamable HTTP transport entry points (including the critical stdout-fd-duplication pattern and the static bearer token middleware), and the Typer CLI that ties everything to `Settings`. After this plan lands, running `mcp-trino-optimizer serve` actually works end-to-end; the stdio smoke test flips green and so does the HTTP bearer test.

Critical SDK-interaction details (from RESEARCH.md §1 findings 1, 2, 3):
- FastMCP's `stdio_server()` captures `sys.stdout.buffer` AT CALL TIME — we cannot use `mcp.run("stdio")` naively because `install_stdout_guard` must run AFTER fd 1 is duplicated and BEFORE FastMCP reads sys.stdout. The only correct pattern is reimplementing a small `run_stdio_async()` with `os.dup(1)` + explicit `stdio_server(stdout=pristine)`.
- FastMCP's built-in `AuthSettings` requires an OAuth `issuer_url` — it's the wrong tool for a static bearer token. The correct pattern is wrapping `mcp.streamable_http_app()` (Starlette ASGI) with our own `BaseHTTPMiddleware` and running it through `uvicorn.Server` directly.
- `schema_lint.assert_tools_compliant(mcp)` must be called inside `build_app()` AFTER every tool registers — this is D-11's runtime guard that complements the CI test in plan 01-02.

Purpose: Ship a fully functional MCP server that any Claude Code user can talk to via stdio AND any HTTPS client can talk to via Streamable HTTP with bearer auth.
Output: `mcp-trino-optimizer serve` starts, answers `initialize`, returns valid `mcp_selftest` responses, and the stdio smoke test + HTTP bearer tests all flip green.
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
@src/mcp_trino_optimizer/settings.py
@src/mcp_trino_optimizer/logging_setup.py
@src/mcp_trino_optimizer/_runtime.py
@src/mcp_trino_optimizer/_context.py
@src/mcp_trino_optimizer/safety/envelope.py
@src/mcp_trino_optimizer/safety/stdout_guard.py
@src/mcp_trino_optimizer/safety/schema_lint.py
@tests/smoke/test_stdio_initialize.py
@tests/smoke/test_http_bearer.py
@tests/tools/test_selftest.py
@tests/safety/test_schema_lint.py

<interfaces>
<!-- SDK surfaces this plan interacts with (verified v1.27.0 in RESEARCH.md §1): -->

```python
# mcp.server.fastmcp
from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    name="mcp-trino-optimizer",
    instructions="Trino + Iceberg SQL optimizer",
    host="127.0.0.1",
    port=8080,
    log_level="INFO",
)

# Tool registration (via @mcp.tool() decorator)
@mcp.tool(name="...", title="...", description="...")
def my_tool(inp: MyInputModel) -> MyOutputModel: ...

# Schema introspection (plan 01-02 already uses this):
for tool in mcp._tool_manager.list_tools():
    tool.name       # str
    tool.parameters # dict[str, Any]  -- JSON Schema

# Streamable HTTP ASGI app:
starlette_app = mcp.streamable_http_app()  # returns Starlette instance

# Stdio transport context manager (bypasses mcp.run()):
from mcp.server.stdio import stdio_server
async with stdio_server(stdin=..., stdout=pristine_stdout) as (read, write):
    await mcp._mcp_server.run(
        read, write, mcp._mcp_server.create_initialization_options()
    )
```

<!-- Modules consumed from plans 01-02 / 01-03: -->

```python
from mcp_trino_optimizer.settings import Settings, load_settings_or_die
from mcp_trino_optimizer.logging_setup import configure_logging, get_logger
from mcp_trino_optimizer._runtime import runtime_info, set_transport
from mcp_trino_optimizer._context import new_request_id
from mcp_trino_optimizer.safety.envelope import wrap_untrusted  # imported but not used in Phase 1
from mcp_trino_optimizer.safety.stdout_guard import install_stdout_guard
from mcp_trino_optimizer.safety.schema_lint import assert_tools_compliant
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Build app.py + tools/selftest.py + tools/_middleware.py</name>
  <files>src/mcp_trino_optimizer/app.py, src/mcp_trino_optimizer/tools/selftest.py, src/mcp_trino_optimizer/tools/_middleware.py, src/mcp_trino_optimizer/tools/__init__.py</files>
  <read_first>
    - /Users/allen/repo/mcp-trino-optimizer/.planning/phases/01-skeleton-safety-foundation/01-RESEARCH.md §3.1 (build_app + register pattern), §3.2 (selftest tool example), §5.2 (tool_envelope middleware), §11 (mcp_selftest response shape)
    - /Users/allen/repo/mcp-trino-optimizer/.planning/phases/01-skeleton-safety-foundation/01-CONTEXT.md D-04 (tool auto-registration), Claude's Discretion on mcp_selftest fields
    - /Users/allen/repo/mcp-trino-optimizer/tests/tools/test_selftest.py (PLAT-09 contract)
    - /Users/allen/repo/mcp-trino-optimizer/src/mcp_trino_optimizer/safety/schema_lint.py (the assertion to call)
    - /Users/allen/repo/mcp-trino-optimizer/src/mcp_trino_optimizer/_runtime.py (runtime_info to fetch version/git_sha/etc.)
  </read_first>
  <behavior>
    **app.py:**
    - `build_app()` constructs a `FastMCP` with name, instructions, host/port defaults (overridden later by transports.py)
    - Calls `tools.discover_and_register(mcp)` ONCE to auto-register every tool module per D-04 (adding a new tool in a later phase = new file in `tools/`, nothing else changes)
    - After auto-registration, calls `assert_tools_compliant(mcp)` — if any tool is non-compliant, `SchemaLintError` crashes the server before it listens
    - Returns the configured `mcp` instance
    - app.py MUST NOT contain any direct `from mcp_trino_optimizer.tools import selftest` line — that would defeat the auto-discovery contract

    **tools/selftest.py:**
    - Defines `SelftestInput(BaseModel)` with `model_config = ConfigDict(extra="forbid")` and a single field `echo: Annotated[str, Field(max_length=1024)]` with default `""`
    - Defines `SelftestOutput(BaseModel)` with fields: `server_version`, `transport`, `echo`, `python_version`, `package_version`, `git_sha`, `log_level`, `started_at`, `capabilities: list[str]`
    - The `capabilities` list Field uses `max_length=10` to satisfy schema_lint's `maxItems` requirement
    - `register(mcp)` function decorates `mcp_selftest` with `@mcp.tool(name="mcp_selftest", title="Server self-test", description=...)` where description is a STATIC string (no user input, prevents tool-description injection per MCP-17 intent)
    - The tool body reads `runtime_info()` and returns a `SelftestOutput`
    - The tool is wrapped with `tool_envelope("mcp_selftest")` so request_id/tool_name contextvars are bound for every log call inside

    **tools/_middleware.py:**
    - `tool_envelope(tool_name: str)` returns a decorator that, on every tool invocation:
      1. Calls `structlog.contextvars.clear_contextvars()`
      2. Calls `new_request_id()` to generate + bind a request_id
      3. Calls `structlog.contextvars.bind_contextvars(tool_name=tool_name)`
      4. Invokes the underlying function with `*args, **kwargs`
    - Per RESEARCH.md §5.2, Phase 1's selftest is sync so this decorator is sync. Phase 2 will add an async variant.

    **tools/__init__.py:**
    - Implements `discover_and_register(mcp: FastMCP) -> int` per D-04 auto-registration contract:
      1. Uses `pkgutil.iter_modules(__path__)` to enumerate sibling modules under `tools/`
      2. Skips any module whose name starts with `_` (e.g. `_middleware`) or is a dunder
      3. For each remaining module: `importlib.import_module(f".{name}", package=__name__)`
      4. Fetches `getattr(module, "register", None)`; if callable, calls it with `mcp` and increments a counter
      5. Returns the number of tool modules successfully registered (used for a startup log line)
    - Preserves the `register(mcp)` entry-point indirection so the module-level `@mcp.tool()` decorator never fires at import time (avoids the circular-import hazard from RESEARCH.md §3.1)
    - Adding a new tool in Phase 8 = new file in `tools/` with a `register(mcp)` function — nothing else changes (D-04 promise)
  </behavior>
  <action>
    ### File 1: `src/mcp_trino_optimizer/tools/_middleware.py`

    ```python
    # src/mcp_trino_optimizer/tools/_middleware.py
    """Tool decorator middleware: request_id + tool_name contextvars binding.

    Every tool's entry point is wrapped with tool_envelope(tool_name) so every
    log call inside the handler inherits request_id and tool_name via structlog
    contextvars. This satisfies PLAT-06's mandatory fields for log lines
    emitted during tool execution.

    Phase 1 ships only a sync decorator (selftest is sync). Phase 2 will add
    an async variant when Trino-touching tools land.
    """
    from __future__ import annotations

    import functools
    from collections.abc import Callable
    from typing import Any, TypeVar

    import structlog

    from mcp_trino_optimizer._context import new_request_id

    F = TypeVar("F", bound=Callable[..., Any])


    def tool_envelope(tool_name: str) -> Callable[[F], F]:
        """Bind request_id + tool_name contextvars around a sync tool handler."""

        def deco(fn: F) -> F:
            @functools.wraps(fn)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                structlog.contextvars.clear_contextvars()
                rid = new_request_id()
                structlog.contextvars.bind_contextvars(
                    request_id=rid,
                    tool_name=tool_name,
                )
                return fn(*args, **kwargs)

            return wrapper  # type: ignore[return-value]

        return deco


    __all__ = ["tool_envelope"]
    ```

    ### File 2: `src/mcp_trino_optimizer/tools/selftest.py`

    Follow RESEARCH.md §3.2 as the template. Updated to import from our real modules:

    ```python
    # src/mcp_trino_optimizer/tools/selftest.py
    """mcp_selftest tool — server health probe (PLAT-09).

    Returns server version, transport, capabilities, and a round-trip echo.
    No Trino access, no user-origin strings in output → no untrusted_content
    envelope needed. The echo field round-trips client input verbatim.
    """
    from __future__ import annotations

    from typing import Annotated, Literal

    from mcp.server.fastmcp import FastMCP
    from pydantic import BaseModel, ConfigDict, Field

    from mcp_trino_optimizer._runtime import runtime_info
    from mcp_trino_optimizer.tools._middleware import tool_envelope


    class SelftestInput(BaseModel):
        model_config = ConfigDict(extra="forbid")  # additionalProperties: false

        echo: Annotated[
            str,
            Field(
                default="",
                min_length=0,
                max_length=1024,
                description="Client-supplied string to echo back. Max 1KB.",
            ),
        ] = ""


    class SelftestOutput(BaseModel):
        model_config = ConfigDict(extra="forbid")

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
        """Register mcp_selftest on the given FastMCP instance."""

        @mcp.tool(
            name="mcp_selftest",
            title="Server self-test",
            description=_STATIC_DESCRIPTION,
        )
        @tool_envelope("mcp_selftest")
        def mcp_selftest(inp: SelftestInput) -> SelftestOutput:
            info = runtime_info()
            return SelftestOutput(
                server_version=info.package_version,
                transport=info.transport,  # type: ignore[arg-type]
                echo=inp.echo,
                python_version=info.python_version,
                package_version=info.package_version,
                git_sha=info.git_sha,
                log_level=info.log_level,
                started_at=info.started_at,
                capabilities=["stdio", "streamable-http", "mcp_selftest"],
            )


    __all__ = ["SelftestInput", "SelftestOutput", "register"]
    ```

    ### File 3: `src/mcp_trino_optimizer/tools/__init__.py`

    Replace the placeholder with the auto-discovery implementation per D-04:

    ```python
    """MCP tool auto-registration (D-04).

    tools/__init__.py.discover_and_register(mcp) walks every sibling module
    under tools/ and calls each module's register(mcp) entry point. Adding
    a new tool in a later phase = new file in tools/; nothing else changes.

    Why a register() entry point instead of module-level @mcp.tool() decorators:
    module-level decorators fire at import time and would require `mcp` to be
    imported at the top of every tool module, creating a circular-import
    hazard with app.py (see RESEARCH.md §3.1). The register() indirection
    breaks the cycle by deferring mcp binding until runtime.
    """
    from __future__ import annotations

    import importlib
    import pkgutil
    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from mcp.server.fastmcp import FastMCP


    def discover_and_register(mcp: "FastMCP") -> int:
        """Auto-discover every tool module in tools/ and call its register(mcp).

        Returns the number of tool modules successfully registered.

        Skips:
          - dunder modules (__init__, __main__)
          - private modules whose name starts with '_' (e.g. _middleware)

        A tool module is expected to expose a top-level ``register(mcp)``
        callable. Modules without one are silently ignored (helper modules).
        """
        registered = 0
        for _finder, name, _ispkg in pkgutil.iter_modules(__path__):
            if name.startswith("_"):
                continue
            module = importlib.import_module(f".{name}", package=__name__)
            register_fn = getattr(module, "register", None)
            if callable(register_fn):
                register_fn(mcp)
                registered += 1
        return registered


    __all__ = ["discover_and_register"]
    ```

    ### File 4: `src/mcp_trino_optimizer/app.py`

    ```python
    # src/mcp_trino_optimizer/app.py
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
            port=8080,          # overridden by transports.run_streamable_http
            log_level="INFO",   # structlog owns real logging; this is SDK-side
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
    ```

    **Assumption A1 mitigation note (RESEARCH.md §19):** When you run `test_all_tools_are_schema_compliant` the first time, it may fail if pydantic-core does not emit `additionalProperties: false` for `ConfigDict(extra="forbid")`. If that happens, add `json_schema_extra={"additionalProperties": False}` to the model_config of both `SelftestInput` and `SelftestOutput`:
    ```python
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"additionalProperties": False},
    )
    ```
    Try the default (clean `extra="forbid"`) first; only add the fallback if the test fails.
  </action>
  <verify>
    <automated>cd /Users/allen/repo/mcp-trino-optimizer && uv run pytest tests/tools/test_selftest.py tests/safety/test_schema_lint.py -v && uv run mypy src/mcp_trino_optimizer/app.py src/mcp_trino_optimizer/tools/</automated>
  </verify>
  <acceptance_criteria>
    - `uv run pytest tests/tools/test_selftest.py -v` — all tests pass (no importorskip skips left)
    - `uv run pytest tests/safety/test_schema_lint.py::test_all_tools_are_schema_compliant -v` passes (was previously skipped)
    - `uv run python -c "from mcp_trino_optimizer.app import build_app; m=build_app(); print([t.name for t in m._tool_manager.list_tools()])"` prints `['mcp_selftest']`
    - `grep -c "def build_app" src/mcp_trino_optimizer/app.py` returns `1`
    - `grep -c "assert_tools_compliant" src/mcp_trino_optimizer/app.py` returns `1`
    - `grep -c "discover_and_register" src/mcp_trino_optimizer/app.py` returns `1` (D-04 auto-registration)
    - `grep -c "from mcp_trino_optimizer.tools import selftest" src/mcp_trino_optimizer/app.py` returns `0` (D-04: app.py must NOT import tool modules directly)
    - `grep -c "def discover_and_register" src/mcp_trino_optimizer/tools/__init__.py` returns `1`
    - `grep -c "pkgutil.iter_modules" src/mcp_trino_optimizer/tools/__init__.py` returns `1`
    - `grep -c "importlib.import_module" src/mcp_trino_optimizer/tools/__init__.py` returns `1`
    - `grep -c 'extra="forbid"' src/mcp_trino_optimizer/tools/selftest.py` returns at least `2` (SelftestInput + SelftestOutput)
    - `grep -c "max_length" src/mcp_trino_optimizer/tools/selftest.py` returns at least `5` (every string field capped)
    - `grep -c "tool_envelope" src/mcp_trino_optimizer/tools/selftest.py` returns `1`
    - `grep -c "@mcp.tool" src/mcp_trino_optimizer/tools/selftest.py` returns `1`
    - `grep -c "_STATIC_DESCRIPTION" src/mcp_trino_optimizer/tools/selftest.py` returns at least `2` (definition + usage)
    - `grep -c "new_request_id" src/mcp_trino_optimizer/tools/_middleware.py` returns `1`
    - `grep -c "clear_contextvars" src/mcp_trino_optimizer/tools/_middleware.py` returns `1`
    - `uv run mypy src/mcp_trino_optimizer/app.py src/mcp_trino_optimizer/tools/` exits 0 in strict mode
  </acceptance_criteria>
  <done>build_app() returns a FastMCP with mcp_selftest registered; schema_lint runtime guard activates; the tool returns a complete SelftestOutput with all fields populated from runtime_info; contextvars bind correctly so logs inside the tool carry request_id + tool_name.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Build transports.py (stdio + Streamable HTTP + StaticBearerMiddleware) and cli.py</name>
  <files>src/mcp_trino_optimizer/transports.py, src/mcp_trino_optimizer/cli.py</files>
  <read_first>
    - /Users/allen/repo/mcp-trino-optimizer/.planning/phases/01-skeleton-safety-foundation/01-RESEARCH.md §3.4 (run_stdio pattern — copy verbatim; CRITICAL fd duplication semantics), §3.5 (StaticBearerMiddleware + run_streamable_http — copy verbatim), §7 (Typer CLI template — copy verbatim), §20 Q3 (plaintext HTTP warning banner)
    - /Users/allen/repo/mcp-trino-optimizer/.planning/phases/01-skeleton-safety-foundation/01-CONTEXT.md D-12 (three-layer stdout discipline, behavior contract), D-15 (CLI subcommand shape), D-07 (bearer token fail-fast)
    - /Users/allen/repo/mcp-trino-optimizer/tests/smoke/test_stdio_initialize.py (the contract this must satisfy)
    - /Users/allen/repo/mcp-trino-optimizer/tests/smoke/test_http_bearer.py (the HTTP contract)
    - /Users/allen/repo/mcp-trino-optimizer/src/mcp_trino_optimizer/safety/stdout_guard.py (install_stdout_guard interface)
    - /Users/allen/repo/mcp-trino-optimizer/src/mcp_trino_optimizer/settings.py (load_settings_or_die interface)
  </read_first>
  <behavior>
    **transports.run_stdio(mcp):**
    - FIRST: `os.dup(1)` to get a pristine fd for stdout BEFORE touching sys.stdout
    - Wrap the pristine fd in a `TextIOWrapper(os.fdopen(pristine_fd, "wb"), encoding="utf-8", write_through=True)`
    - THEN: `install_stdout_guard()` — replaces `sys.stdout` with SentinelWriter
    - `set_transport("stdio")` so runtime_info reflects the current mode
    - Run an anyio loop calling `stdio_server(stdout=anyio.wrap_file(pristine_stdout))` and passing read/write streams to `mcp._mcp_server.run(...)`
    - This MUST NOT use `mcp.run("stdio")` — that would capture the poisoned sys.stdout

    **transports.run_streamable_http(mcp, *, host, port, bearer_token):**
    - `set_transport("http")`
    - Fetches `app = mcp.streamable_http_app()` (returns a Starlette instance)
    - `app.add_middleware(StaticBearerMiddleware, token=bearer_token)`
    - Emits WARNING log `plaintext_http_warning` telling the operator to use a reverse proxy for TLS in production (RESEARCH.md §20 Q3)
    - Runs via `uvicorn.Config(app, host=host, port=port, log_level="error")` + `uvicorn.Server(config).serve()`

    **StaticBearerMiddleware:**
    - Extends `starlette.middleware.base.BaseHTTPMiddleware`
    - `__init__(self, app, *, token: str)` stores `self._token_bytes = token.encode("utf-8")`
    - `dispatch(request, call_next)`:
      - Read `request.headers.get("authorization", "")`
      - If no `"bearer "` prefix (case-insensitive) → return 401 JSONResponse `{"error": "unauthorized"}`
      - Extract presented token, `hmac.compare_digest(presented.encode("utf-8"), self._token_bytes)` — MUST use hmac for constant-time compare
      - On match: `await call_next(request)`
      - On mismatch: 401 JSONResponse
    - NEVER logs the token itself (token should not appear in any log line)

    **cli.py:**
    - Typer app with `serve` subcommand
    - Options: `--transport [stdio|http]` default stdio, `--host` default 127.0.0.1, `--port` default 8080, `--log-level` default INFO, `--bearer-token` optional str (for --transport http)
    - Inside `serve()`:
      1. Build overrides dict from CLI args
      2. Call `load_settings_or_die(**overrides)` — exits on error BEFORE any transport code runs
      3. Call `configure_logging(settings.log_level, package_version=..., git_sha=...)` using `runtime_info()`
      4. Call `build_app()` to construct FastMCP
      5. Dispatch to `run_stdio(mcp)` or `run_streamable_http(mcp, host=..., port=..., bearer_token=...)` based on `settings.transport`
    - Module-top-level code (BEFORE any domain imports): `logging.basicConfig(stream=sys.stderr, level=logging.INFO, force=True)` + `logging.captureWarnings(True)` — belt-and-suspenders stdout discipline (RESEARCH.md §4.4)

    **Windows gotcha (RESEARCH.md §12.1):** On Windows, `TextIOWrapper` on a duplicated fd may default to cp1252. Force `encoding="utf-8"` and `newline=""` on the TextIOWrapper so JSON-RPC frames use `\n` exactly.
  </behavior>
  <action>
    ### File 1: `src/mcp_trino_optimizer/transports.py`

    ```python
    # src/mcp_trino_optimizer/transports.py
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
    import sys
    from io import TextIOWrapper

    import anyio
    import uvicorn
    from mcp.server.fastmcp import FastMCP
    from mcp.server.stdio import stdio_server
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.requests import Request
    from starlette.responses import JSONResponse
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
                await mcp._mcp_server.run(
                    read_stream,
                    write_stream,
                    mcp._mcp_server.create_initialization_options(),
                )

        anyio.run(_run)


    # ════════════════════════════════════════════════════════════════════
    # Streamable HTTP transport + StaticBearerMiddleware
    # ════════════════════════════════════════════════════════════════════


    class StaticBearerMiddleware(BaseHTTPMiddleware):
        """Require `Authorization: Bearer <token>` on every /mcp request.

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

        async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
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
            return await call_next(request)


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
    ```

    ### File 2: `src/mcp_trino_optimizer/cli.py`

    COPY RESEARCH.md §7 VERBATIM, updated for real module paths:

    ```python
    # src/mcp_trino_optimizer/cli.py
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
    from typing import Optional

    import typer

    app = typer.Typer(
        name="mcp-trino-optimizer",
        add_completion=False,
        no_args_is_help=True,
        help="MCP server for Trino + Iceberg query optimization.",
    )


    @app.command()
    def serve(
        transport: str = typer.Option(
            "stdio", "--transport", help="stdio or http"
        ),
        host: str = typer.Option("127.0.0.1", "--host"),
        port: int = typer.Option(8080, "--port"),
        log_level: str = typer.Option("INFO", "--log-level"),
        bearer_token: Optional[str] = typer.Option(
            None,
            "--bearer-token",
            help=(
                "Override MCPTO_HTTP_BEARER_TOKEN. "
                "Required for --transport http."
            ),
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
    ```

    **After writing both files, run the full test suite once to verify the stdio smoke test flips green.** If `test_stdio_initialize_produces_only_json_rpc_on_stdout` fails because FastMCP writes a banner on import (RESEARCH.md assumption A5), the fix is to ensure `install_stdout_guard()` is called BEFORE `from mcp.server.fastmcp import FastMCP` is triggered. The current structure is safe because `build_app()` is called after `run_stdio()` installs the guard — but if FastMCP is re-imported inside `stdio_server(...)` and writes something pre-capture, add an explicit `import mcp.server.fastmcp` at the top of `run_stdio` AFTER `install_stdout_guard()`.

    For the HTTP bearer test, the test relies on spawning the actual CLI — if the test is unable to bind 127.0.0.1:8080 reliably in CI, use port 0 or a random high port. Phase 1 ships the test with the documented default 8080; if flakiness appears, amend the test to use a fixture-allocated port.
  </action>
  <verify>
    <automated>cd /Users/allen/repo/mcp-trino-optimizer && uv run pytest tests/smoke/test_stdio_initialize.py tests/smoke/test_http_bearer.py -v && uv run mypy src/mcp_trino_optimizer/transports.py src/mcp_trino_optimizer/cli.py && uv run mcp-trino-optimizer --help</automated>
  </verify>
  <acceptance_criteria>
    - `uv run mcp-trino-optimizer --help` exits 0 and displays the serve subcommand
    - `uv run mcp-trino-optimizer serve --help` exits 0 and lists `--transport`, `--host`, `--port`, `--log-level`, `--bearer-token` options
    - `uv run pytest tests/smoke/test_stdio_initialize.py::test_stdio_initialize_produces_only_json_rpc_on_stdout -v` passes (PLAT-02, PLAT-05)
    - `uv run pytest tests/smoke/test_http_bearer.py::test_http_transport_fails_fast_without_bearer_token -v` passes (PLAT-03, D-07)
    - `grep -c "os\.dup(1)" src/mcp_trino_optimizer/transports.py` returns `1` (fd duplication BEFORE guard install)
    - `grep -c "install_stdout_guard()" src/mcp_trino_optimizer/transports.py` returns `1`
    - `grep -c "hmac.compare_digest" src/mcp_trino_optimizer/transports.py` returns `1` (constant-time compare)
    - `grep -c "class StaticBearerMiddleware" src/mcp_trino_optimizer/transports.py` returns `1`
    - `grep -c "plaintext_http_warning" src/mcp_trino_optimizer/transports.py` returns `1` (RESEARCH.md §20 Q3)
    - `grep -c 'log_level="error"' src/mcp_trino_optimizer/transports.py` returns `1` (uvicorn suppress)
    - `grep -c 'encoding="utf-8"' src/mcp_trino_optimizer/transports.py` returns at least `1` (Windows gotcha)
    - `grep -c "newline=\"\"" src/mcp_trino_optimizer/transports.py` returns `1` (Windows CRLF protection)
    - `grep -c "load_settings_or_die" src/mcp_trino_optimizer/cli.py` returns `1`
    - `grep -c "configure_logging" src/mcp_trino_optimizer/cli.py` returns `1`
    - `grep -c "build_app" src/mcp_trino_optimizer/cli.py` returns `1`
    - `grep -c "stream=sys.stderr" src/mcp_trino_optimizer/cli.py` returns `1` (belt-and-suspenders)
    - `grep -c "force=True" src/mcp_trino_optimizer/cli.py` returns `1`
    - `uv run mypy src/mcp_trino_optimizer/transports.py src/mcp_trino_optimizer/cli.py` exits 0 in strict mode
  </acceptance_criteria>
  <done>mcp-trino-optimizer CLI starts the server end-to-end; stdio smoke test passes; HTTP bearer fail-fast test passes; stdout discipline (fd dup + guard install + sentinel writer) works; bearer middleware uses hmac.compare_digest; plaintext HTTP warning is emitted on HTTP startup.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| sys.stdout → JSON-RPC framing | run_stdio duplicates fd 1 BEFORE installing SentinelWriter so FastMCP's pristine writer never sees our guard |
| HTTP Authorization header → middleware | StaticBearerMiddleware validates with hmac.compare_digest (constant-time) |
| CLI flags → Settings | Typer → overrides dict → load_settings_or_die → fail-fast validator |
| Tool handler → log lines | tool_envelope decorator binds request_id + tool_name contextvars at entry |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-01-01 | DoS | Stray stdout write corrupts JSON-RPC | mitigate | run_stdio dup-fd + install_stdout_guard pattern; smoke test proves stdout after initialize is pure JSON-RPC (automated: `pytest tests/smoke/test_stdio_initialize.py::test_stdio_initialize_produces_only_json_rpc_on_stdout`) |
| T-01-02 | Spoofing/Elevation | HTTP transport started without bearer token | mitigate | Settings fail-fast from plan 01-03 runs in cli.py before build_app; load_settings_or_die exits 2 with structured error (automated: `pytest tests/smoke/test_http_bearer.py::test_http_transport_fails_fast_without_bearer_token`) |
| T-01-05 | Tampering | Tool with loose JSON Schema | mitigate | app.build_app calls assert_tools_compliant(mcp) as the runtime guard complement to the CI test (automated: `pytest tests/safety/test_schema_lint.py::test_all_tools_are_schema_compliant`) |
| T-01-07 | Elevation | HTTP port exposed to LAN | mitigate | Settings defaults http_host=127.0.0.1; run_streamable_http emits plaintext_http_warning log reminding operator to use reverse proxy |
| T-01-08 | Info disclosure (timing) | Non-constant-time bearer compare | mitigate | StaticBearerMiddleware uses hmac.compare_digest; bearer token never appears in any log line (middleware doesn't log it) |
</threat_model>

<verification>
Run the complete smoke test suite: `uv run pytest tests/smoke/ tests/tools/ tests/safety/ -v`. All tests must be green. Run `uv run mcp-trino-optimizer --help` and `uv run mcp-trino-optimizer serve --help` — both must exit 0 and display the expected options. Run `uv run mypy src/` in strict mode — zero errors.
</verification>

<success_criteria>
- `mcp-trino-optimizer serve` starts on stdio by default and answers JSON-RPC initialize
- `mcp-trino-optimizer serve --transport http` without bearer token fails fast with structured JSON error on stderr
- `mcp-trino-optimizer serve --transport http --bearer-token ...` starts HTTP server on 127.0.0.1:8080
- stdio smoke test (bytes mode, communicate timeout) passes: every byte on stdout parses as a valid JSON-RPC frame
- HTTP bearer test passes: 401 on missing/wrong token, 200 on correct token
- mcp_selftest tool returns all mandatory fields (server_version, transport, echo, capabilities) plus discretionary fields (python_version, package_version, git_sha, log_level, started_at)
- assert_tools_compliant runs at startup; SchemaLintError crashes the server BEFORE it listens
- mypy strict clean on all new modules
</success_criteria>

<output>
After completion, create `.planning/phases/01-skeleton-safety-foundation/01-04-SUMMARY.md`
</output>
