---
phase: 01-skeleton-safety-foundation
plan: 03
type: execute
wave: 1
depends_on:
  - 01-01-test-harness-scaffold
files_modified:
  - src/mcp_trino_optimizer/settings.py
  - src/mcp_trino_optimizer/logging_setup.py
  - src/mcp_trino_optimizer/_context.py
  - src/mcp_trino_optimizer/_runtime.py
  - tests/test_runtime.py
autonomous: true
requirements:
  - PLAT-06
  - PLAT-07
  - PLAT-08
must_haves:
  truths:
    - "Settings loads from OS env > .env > defaults with MCPTO_ prefix"
    - "load_settings_or_die() emits a single structured JSON error line to stderr and sys.exit(2) on any ValidationError, before any transport starts"
    - "Settings with transport=http and no bearer_token raises ValidationError at model_validator time (D-07 fail-fast)"
    - "configure_logging() routes structlog to stderr exclusively; no stdout handlers are installed"
    - "Every log line emitted after configure_logging contains timestamp (ISO8601 UTC), package_version, git_sha fields; request_id and tool_name are bound via contextvars at tool entry"
    - "Redaction processor hard-redacts any dict key in the denylist (authorization, x-trino-extra-credentials, cookie, token, password, api_key, apikey, bearer, secret, ssl_password) and any key matching credential.* pattern, case-insensitively, recursively, and at any dict depth"
    - "Any pydantic.SecretStr value renders as [REDACTED] regardless of the key it's stored under"
    - "_resolve_git_sha() never raises: three-tier fallback (env var MCPTO_GIT_SHA → baked _git_sha.txt → git rev-parse with 1s timeout → 'unknown')"
  artifacts:
    - path: "src/mcp_trino_optimizer/settings.py"
      provides: "Settings BaseSettings class + load_settings_or_die() fail-fast entry point"
      contains: "class Settings"
    - path: "src/mcp_trino_optimizer/logging_setup.py"
      provides: "REDACTION_DENYLIST + _redact_processor + configure_logging + get_logger"
      contains: "def configure_logging"
    - path: "src/mcp_trino_optimizer/_context.py"
      provides: "new_request_id + current_request_id contextvar helpers"
      contains: "def new_request_id"
    - path: "src/mcp_trino_optimizer/_runtime.py"
      provides: "RuntimeInfo dataclass + runtime_info() + _resolve_git_sha() + set_transport()"
      contains: "def _resolve_git_sha"
  key_links:
    - from: "src/mcp_trino_optimizer/settings.py"
      to: "pydantic_settings.BaseSettings"
      via: "env_prefix MCPTO_, env_file .env, extra=forbid"
      pattern: 'env_prefix\s*=\s*"MCPTO_"'
    - from: "src/mcp_trino_optimizer/logging_setup.py"
      to: "sys.stderr"
      via: "PrintLoggerFactory(file=sys.stderr)"
      pattern: "file=sys\\.stderr"
    - from: "src/mcp_trino_optimizer/logging_setup.py"
      to: "SecretStr rendering"
      via: "_redact_processor isinstance check"
      pattern: "isinstance.*SecretStr"
---

<objective>
Ship the three "cross-cutting infrastructure" modules that every other plan consumes:

1. `settings.py` — pydantic-settings `Settings` class with fail-fast loading (PLAT-08, D-05, D-06, D-07, D-08)
2. `logging_setup.py` — structlog pipeline with redaction processor and stderr-only output (PLAT-06, PLAT-07, D-09, D-12 layer 1)
3. `_runtime.py` + `_context.py` — runtime info (git_sha resolver, package version, transport) + contextvar helpers for request_id/tool_name binding

These three modules have NO file overlap with plan 01-02 (safety primitives), so they run in parallel in Wave 1. The only shared dependency is the package shell created in plan 01-01.

Purpose: Isolate the "infrastructure/plumbing" layer from the "safety primitives" layer so both can be built and unit-tested in parallel.
Output: Settings loads correctly, fail-fast works, logging pipeline emits redacted JSON to stderr, git_sha resolver never raises.
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
@tests/test_settings.py
@tests/logging/test_structured_fields.py
@tests/logging/test_redaction.py

<interfaces>
<!-- What this plan EXPORTS that later plans (01-04 app/cli/transports) depend on: -->

```python
# settings.py
from pydantic import SecretStr
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    transport: Literal["stdio", "http"]   # default "stdio"
    http_host: str                          # default "127.0.0.1"
    http_port: int                          # default 8080, 1 <= x <= 65535
    http_bearer_token: SecretStr | None     # default None, required when transport=http
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"]  # default "INFO"

def load_settings_or_die(**overrides: object) -> Settings: ...
    # Prints structured JSON error to stderr + sys.exit(2) on failure.

# logging_setup.py
REDACTION_DENYLIST: frozenset[str]  # module-level constant

def configure_logging(
    level: str = "INFO",
    *,
    package_version: str,
    git_sha: str,
) -> None: ...

def get_logger(name: str = "") -> structlog.stdlib.BoundLogger: ...

# _runtime.py
@dataclass(frozen=True)
class RuntimeInfo:
    package_version: str
    python_version: str
    git_sha: str
    log_level: str
    started_at: str  # ISO8601 UTC
    transport: str

def runtime_info(log_level: str = "INFO") -> RuntimeInfo: ...
def set_transport(t: str) -> None: ...
def _resolve_git_sha() -> str: ...  # never raises

# _context.py
def new_request_id() -> str: ...
def current_request_id() -> str: ...
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Implement settings.py + _runtime.py + _context.py</name>
  <files>src/mcp_trino_optimizer/settings.py, src/mcp_trino_optimizer/_runtime.py, src/mcp_trino_optimizer/_context.py, tests/test_runtime.py</files>
  <read_first>
    - /Users/allen/repo/mcp-trino-optimizer/.planning/phases/01-skeleton-safety-foundation/01-RESEARCH.md §6 (Settings template — copy verbatim), §11.2 (git_sha three-tier fallback), §5.2 (request_id contextvars)
    - /Users/allen/repo/mcp-trino-optimizer/.planning/phases/01-skeleton-safety-foundation/01-CONTEXT.md D-05, D-06, D-07, D-08 (Settings contract), Claude's Discretion on git_sha
    - /Users/allen/repo/mcp-trino-optimizer/tests/test_settings.py (the test contract to satisfy)
    - /Users/allen/repo/mcp-trino-optimizer/CLAUDE.md Version Compatibility table (pydantic-settings>=2.13)
  </read_first>
  <behavior>
    **settings.py:**
    - `Settings()` with no env + defaults: transport="stdio", http_host="127.0.0.1", http_port=8080, http_bearer_token=None, log_level="INFO"
    - `MCPTO_TRANSPORT=http` + `MCPTO_HTTP_BEARER_TOKEN=x` → transport="http", bearer loaded as SecretStr
    - `MCPTO_TRANSPORT=http` WITHOUT bearer token → ValidationError via `_require_bearer_for_http` model_validator
    - `Settings(transport="http", http_bearer_token="x")` (init kwargs) → precedence beats env
    - `MCPTO_UNKNOWN_FIELD=x` → ValidationError (`extra="forbid"`)
    - `MCPTO_HTTP_PORT=0` or `MCPTO_HTTP_PORT=70000` → ValidationError
    - `load_settings_or_die()` on invalid config: writes single JSON line `{"level":"error","event":"settings_error","errors":[...]}` to stderr + `sys.exit(2)`. NO structlog dependency (settings loads BEFORE logging configuration)

    **_runtime.py:**
    - `_resolve_git_sha()` tier 1: reads `MCPTO_GIT_SHA` env var, truncates to 12 chars
    - `_resolve_git_sha()` tier 2: reads `_git_sha.txt` from `importlib.resources.files("mcp_trino_optimizer")`, truncates to 12 chars
    - `_resolve_git_sha()` tier 3: `subprocess.run(["git", "rev-parse", "HEAD"], timeout=1)`, captures stdout, truncates
    - `_resolve_git_sha()` tier 4 (fallback): returns `"unknown"` — NEVER raises
    - `runtime_info()` returns a frozen dataclass with package_version (from `importlib.metadata.version("mcp-trino-optimizer")` with `PackageNotFoundError` fallback to `"0.0.0-dev"`), python_version, git_sha, log_level, started_at (captured at module import), transport (from module-level `_transport`)
    - `set_transport("stdio" | "http")` updates the module global before `runtime_info()` is called by tools

    **_context.py:**
    - `new_request_id()` generates a UUID hex truncated to 16 chars, sets the contextvar AND binds it to structlog contextvars
    - `current_request_id()` reads the contextvar
  </behavior>
  <action>
    ### File 1: `src/mcp_trino_optimizer/settings.py`

    COPY RESEARCH.md §6 VERBATIM:

    ```python
    # src/mcp_trino_optimizer/settings.py
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
        """Phase 1 config surface.

        See CONTEXT.md D-05..D-08 for the binding contract. Trino-side
        settings (host, port, auth, TLS) defer to Phase 2.
        """

        model_config = SettingsConfigDict(
            env_prefix="MCPTO_",
            env_file=".env",
            env_file_encoding="utf-8",
            case_sensitive=False,
            extra="forbid",  # unknown fields → ValidationError
        )

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

        @model_validator(mode="after")
        def _require_bearer_for_http(self) -> "Settings":
            if self.transport == "http" and self.http_bearer_token is None:
                raise ValueError(
                    "http_bearer_token is required when transport=http. "
                    "Set MCPTO_HTTP_BEARER_TOKEN or pass --bearer-token on the CLI."
                )
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
            err_line = orjson.dumps(
                {
                    "level": "error",
                    "event": "settings_error",
                    "errors": e.errors(include_url=False),
                }
            ).decode("utf-8")
            sys.stderr.write(err_line + "\n")
            sys.stderr.flush()
            sys.exit(2)


    __all__ = ["Settings", "load_settings_or_die"]
    ```

    ### File 2: `src/mcp_trino_optimizer/_runtime.py`

    Copy RESEARCH.md §11.2 VERBATIM:

    ```python
    # src/mcp_trino_optimizer/_runtime.py
    """Runtime info — package version, python version, git sha, transport, started_at.

    Consumed by the mcp_selftest tool (plan 01-04) and the logging pipeline
    (this plan) to populate the static fields every log line carries.

    CRITICAL: _resolve_git_sha() must NEVER raise — see CONTEXT.md Claude's
    Discretion and RESEARCH.md §11.2. Three-tier fallback:
      1. MCPTO_GIT_SHA env var (CI / Docker build arg)
      2. Baked _git_sha.txt file in the installed package (release builds)
      3. `git rev-parse HEAD` subprocess with 1s timeout (dev installs)
      4. Fallback: "unknown"
    """
    from __future__ import annotations

    import datetime as dt
    import importlib.metadata
    import importlib.resources
    import os
    import subprocess
    import sys
    from dataclasses import dataclass


    @dataclass(frozen=True)
    class RuntimeInfo:
        package_version: str
        python_version: str
        git_sha: str
        log_level: str
        started_at: str
        transport: str


    _started_at: str = dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z")
    _transport: str = "unknown"


    def set_transport(t: str) -> None:
        """Called by transports.run_stdio / run_streamable_http at startup."""
        global _transport
        _transport = t


    def _resolve_git_sha() -> str:
        """Return the first git SHA we can find without raising.

        Three-tier fallback — always returns a string.
        """
        # Tier 1: env var
        sha = os.environ.get("MCPTO_GIT_SHA")
        if sha:
            return sha.strip()[:12]

        # Tier 2: baked file in package resources
        try:
            files = importlib.resources.files("mcp_trino_optimizer")
            sha_file = files.joinpath("_git_sha.txt")
            if sha_file.is_file():
                return sha_file.read_text(encoding="utf-8").strip()[:12]
        except (FileNotFoundError, ModuleNotFoundError, AttributeError, OSError):
            pass

        # Tier 3: runtime git rev-parse (dev installs)
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                timeout=1,
                check=False,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()[:12]
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            pass

        # Tier 4: final fallback
        return "unknown"


    def runtime_info(log_level: str = "INFO") -> RuntimeInfo:
        try:
            pv = importlib.metadata.version("mcp-trino-optimizer")
        except importlib.metadata.PackageNotFoundError:
            pv = "0.0.0-dev"
        return RuntimeInfo(
            package_version=pv,
            python_version=sys.version.split()[0],
            git_sha=_resolve_git_sha(),
            log_level=log_level,
            started_at=_started_at,
            transport=_transport,
        )


    __all__ = ["RuntimeInfo", "runtime_info", "set_transport"]
    ```

    ### File 3: `src/mcp_trino_optimizer/_context.py`

    Copy RESEARCH.md §5.2:

    ```python
    # src/mcp_trino_optimizer/_context.py
    """Request-ID contextvars for structlog binding (RESEARCH.md §5.2).

    FastMCP's async tool dispatch uses anyio, which propagates Python
    contextvars natively. Binding request_id at tool entry ensures every
    log call inside the tool handler inherits it without manual plumbing.
    """
    from __future__ import annotations

    import contextvars
    import uuid

    import structlog

    _request_id: contextvars.ContextVar[str] = contextvars.ContextVar(
        "request_id", default=""
    )


    def new_request_id() -> str:
        """Generate + bind a new request_id; returns it for caller use."""
        rid = uuid.uuid4().hex[:16]
        _request_id.set(rid)
        structlog.contextvars.bind_contextvars(request_id=rid)
        return rid


    def current_request_id() -> str:
        return _request_id.get()


    __all__ = ["current_request_id", "new_request_id"]
    ```

    **Add a dedicated unit test `tests/test_runtime.py`** (not in Wave 0 list; specific to this plan's primitives):

    ```python
    """Unit tests for _runtime: git_sha resolver must never raise."""
    from __future__ import annotations

    import pytest

    from mcp_trino_optimizer._runtime import (
        RuntimeInfo,
        _resolve_git_sha,
        runtime_info,
        set_transport,
    )


    def test_resolve_git_sha_env_var(monkeypatch):
        monkeypatch.setenv("MCPTO_GIT_SHA", "deadbeefcafe00000000")
        assert _resolve_git_sha() == "deadbeefcafe"


    def test_resolve_git_sha_fallback_when_everything_fails(monkeypatch, tmp_path):
        monkeypatch.delenv("MCPTO_GIT_SHA", raising=False)
        monkeypatch.setenv("PATH", "")  # hide git binary
        # In a dir without .git, subprocess returns non-zero
        monkeypatch.chdir(tmp_path)
        result = _resolve_git_sha()
        assert isinstance(result, str)
        # Either "unknown" (no git) or a real sha (CI runners have git on PATH)
        assert len(result) > 0


    def test_resolve_git_sha_never_raises():
        # Direct smoke: call it, must not raise
        result = _resolve_git_sha()
        assert isinstance(result, str)
        assert len(result) > 0


    def test_runtime_info_has_all_fields():
        info = runtime_info("DEBUG")
        assert isinstance(info, RuntimeInfo)
        assert info.log_level == "DEBUG"
        assert info.package_version  # either real or "0.0.0-dev"
        assert info.python_version
        assert info.git_sha
        assert info.started_at
        assert info.transport  # default "unknown" or set via set_transport


    def test_set_transport_updates_runtime_info():
        set_transport("stdio")
        assert runtime_info().transport == "stdio"
        set_transport("http")
        assert runtime_info().transport == "http"
        set_transport("unknown")  # reset
    ```
  </action>
  <verify>
    <automated>cd /Users/allen/repo/mcp-trino-optimizer && uv run pytest tests/test_settings.py tests/test_runtime.py -v && uv run mypy src/mcp_trino_optimizer/settings.py src/mcp_trino_optimizer/_runtime.py src/mcp_trino_optimizer/_context.py</automated>
  </verify>
  <acceptance_criteria>
    - `uv run pytest tests/test_settings.py -v` — all tests pass
    - `uv run pytest tests/test_runtime.py -v` — all tests pass
    - `grep -c 'env_prefix="MCPTO_"' src/mcp_trino_optimizer/settings.py` returns `1`
    - `grep -c 'extra="forbid"' src/mcp_trino_optimizer/settings.py` returns `1`
    - `grep -c "sys.exit(2)" src/mcp_trino_optimizer/settings.py` returns `1`
    - `grep -c '"event": "settings_error"' src/mcp_trino_optimizer/settings.py` returns `1`
    - `grep -c "def _require_bearer_for_http" src/mcp_trino_optimizer/settings.py` returns `1`
    - `grep -c "SecretStr" src/mcp_trino_optimizer/settings.py` returns at least `2`
    - `grep -c "ge=1" src/mcp_trino_optimizer/settings.py` returns `1` (port validation)
    - `grep -c "le=65535" src/mcp_trino_optimizer/settings.py` returns `1`
    - `grep -c "MCPTO_GIT_SHA" src/mcp_trino_optimizer/_runtime.py` returns at least `1`
    - `grep -c "timeout=1" src/mcp_trino_optimizer/_runtime.py` returns `1`
    - `grep -c 'return "unknown"' src/mcp_trino_optimizer/_runtime.py` returns `1`
    - `grep -c "dt.UTC" src/mcp_trino_optimizer/_runtime.py` returns `1`
    - `uv run python -c "from mcp_trino_optimizer._runtime import _resolve_git_sha; print(_resolve_git_sha())"` exits 0 (never raises)
    - `uv run pytest tests/test_settings.py::test_http_without_bearer_token_raises -x` passes (D-07 fail-fast coverage via the stub landed in plan 01-01 Task 2)
    - `uv run mypy src/mcp_trino_optimizer/settings.py src/mcp_trino_optimizer/_runtime.py src/mcp_trino_optimizer/_context.py` exits 0 in strict mode
  </acceptance_criteria>
  <done>Settings fail-fast works per D-07/D-08; git_sha resolver never raises and has three-tier fallback; runtime_info returns a frozen dataclass with every mandatory field; _context has working contextvars helpers; all existing stub tests plus new runtime tests pass.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Implement logging_setup.py with redaction processor</name>
  <files>src/mcp_trino_optimizer/logging_setup.py</files>
  <read_first>
    - /Users/allen/repo/mcp-trino-optimizer/.planning/phases/01-skeleton-safety-foundation/01-RESEARCH.md §5 (structlog pipeline — copy §5.1 verbatim, note the processor order)
    - /Users/allen/repo/mcp-trino-optimizer/.planning/phases/01-skeleton-safety-foundation/01-CONTEXT.md D-09 (denylist + SecretStr contract), D-12 layer 1 (stderr only)
    - /Users/allen/repo/mcp-trino-optimizer/tests/logging/test_redaction.py (test contract — denylist cases including credential.* pattern, case-insensitive, nested, list-of-dicts, SecretStr)
    - /Users/allen/repo/mcp-trino-optimizer/tests/logging/test_structured_fields.py (PLAT-06 mandatory fields contract)
    - /Users/allen/repo/mcp-trino-optimizer/CLAUDE.md (structlog>=25.5.0, orjson>=3.10, NEVER write to stdout)
  </read_first>
  <behavior>
    - `REDACTION_DENYLIST` is a module-level `frozenset[str]` containing lowercase keys: `authorization`, `x-trino-extra-credentials`, `cookie`, `token`, `password`, `api_key`, `apikey`, `bearer`, `secret`, `ssl_password`
    - `_CREDENTIAL_PATTERN = re.compile(r"^credential\.", re.IGNORECASE)` — matches `credential.user`, `credential.password`, etc.
    - `_redact_processor` walks the event_dict recursively:
      - If value is `SecretStr`, return `"[REDACTED]"`
      - If value is a `dict`, recurse AND check each key against denylist/pattern (case-insensitive via `.lower()`)
      - If value is a list or tuple, recurse into each element
      - Plain values pass through untouched
    - `configure_logging(level, *, package_version, git_sha)` sets up:
      - `logging.basicConfig(stream=sys.stderr, level=..., force=True)` — force stdlib logging to stderr
      - `logging.captureWarnings(True)` — route warnings through logging
      - `structlog.configure(...)` with the processor list IN THIS EXACT ORDER:
        1. `structlog.contextvars.merge_contextvars`
        2. `structlog.stdlib.add_log_level`
        3. `structlog.stdlib.add_logger_name`
        4. `structlog.processors.TimeStamper(fmt="iso", utc=True, key="timestamp")`
        5. Lambda that injects `package_version` and `git_sha` as static fields
        6. `_redact_processor` — MUST run before serialization
        7. `structlog.processors.StackInfoRenderer()`
        8. `structlog.processors.format_exc_info`
        9. `_orjson_renderer` — final JSON
      - `logger_factory=structlog.PrintLoggerFactory(file=sys.stderr)` — explicit stderr binding
    - `get_logger(name="")` returns a structlog BoundLogger
    - NO stdout handlers are ever installed; `sys.stdout` is never referenced in this module
  </behavior>
  <action>
    COPY RESEARCH.md §5.1 VERBATIM with one addition: the module must expose `REDACTION_DENYLIST` at module level (not just inside `_redact_processor`) so tests can reference it. The full module:

    ```python
    # src/mcp_trino_optimizer/logging_setup.py
    """structlog pipeline: stderr-only JSON with redaction (PLAT-06, PLAT-07, D-09, D-12 layer 1).

    Processor order is LOAD-BEARING:
      1. merge_contextvars (request_id, tool_name from contextvars)
      2. add_log_level + add_logger_name
      3. TimeStamper ISO8601 UTC
      4. Static fields lambda (package_version, git_sha)
      5. REDACTION — must run BEFORE serialization
      6. StackInfoRenderer + format_exc_info (exceptions)
      7. _orjson_renderer — final JSON on stderr

    NEVER references sys.stdout. The stdout-discipline guarantee depends on
    this module never installing a stdout handler (D-12 layer 1 of 3).
    """
    from __future__ import annotations

    import logging
    import re
    import sys
    from typing import Any

    import orjson
    import structlog
    from pydantic import SecretStr

    REDACTION_DENYLIST: frozenset[str] = frozenset(
        {
            "authorization",
            "x-trino-extra-credentials",
            "cookie",
            "token",
            "password",
            "api_key",
            "apikey",
            "bearer",
            "secret",
            "ssl_password",
        }
    )

    _CREDENTIAL_PATTERN = re.compile(r"^credential\.", re.IGNORECASE)


    def _redact_processor(
        logger: Any,
        method_name: str,
        event_dict: dict[str, Any],
    ) -> dict[str, Any]:
        """Recursively redact secret-shaped keys and SecretStr values.

        - Any dict key matching REDACTION_DENYLIST (case-insensitive) → [REDACTED]
        - Any dict key matching r"^credential\\." → [REDACTED]
        - Any value of type pydantic.SecretStr → [REDACTED]
        - Recurses into nested dicts, lists, tuples at any depth
        """

        def _walk(obj: Any) -> Any:
            if isinstance(obj, SecretStr):
                return "[REDACTED]"
            if isinstance(obj, dict):
                return {
                    k: (
                        "[REDACTED]"
                        if (
                            isinstance(k, str)
                            and (
                                k.lower() in REDACTION_DENYLIST
                                or _CREDENTIAL_PATTERN.match(k)
                            )
                        )
                        else _walk(v)
                    )
                    for k, v in obj.items()
                }
            if isinstance(obj, (list, tuple)):
                return type(obj)(_walk(x) for x in obj)
            return obj

        return _walk(event_dict)  # type: ignore[no-any-return]


    def _orjson_renderer(
        logger: Any,
        method_name: str,
        event_dict: dict[str, Any],
    ) -> str:
        return orjson.dumps(event_dict).decode("utf-8")


    def configure_logging(
        level: str = "INFO",
        *,
        package_version: str,
        git_sha: str,
    ) -> None:
        """Configure structlog for stderr-only JSON output with redaction.

        Must be called exactly once at process startup, BEFORE any log calls.
        """
        numeric_level = getattr(logging, level.upper())

        # Force stdlib logging to stderr (belt-and-suspenders; any library
        # using stdlib logging won't leak to stdout).
        logging.basicConfig(
            stream=sys.stderr,
            level=numeric_level,
            format="%(message)s",
            force=True,
        )
        logging.captureWarnings(True)

        structlog.configure(
            wrapper_class=structlog.make_filtering_bound_logger(numeric_level),
            processors=[
                structlog.contextvars.merge_contextvars,
                structlog.stdlib.add_log_level,
                structlog.stdlib.add_logger_name,
                structlog.processors.TimeStamper(
                    fmt="iso", utc=True, key="timestamp"
                ),
                # Inject static process-wide fields (PLAT-06).
                lambda _l, _m, ev: {
                    **ev,
                    "package_version": package_version,
                    "git_sha": git_sha,
                },
                # REDACTION — must run before any serialization processor.
                _redact_processor,
                structlog.processors.StackInfoRenderer(),
                structlog.processors.format_exc_info,
                # Final JSON render via orjson.
                _orjson_renderer,
            ],
            logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
            cache_logger_on_first_use=True,
        )


    def get_logger(name: str = "") -> Any:
        """Return a bound structlog logger."""
        return structlog.get_logger(name)


    __all__ = [
        "REDACTION_DENYLIST",
        "configure_logging",
        "get_logger",
    ]
    ```

    **Key properties to verify manually if mypy trips:**
    - `return _walk(event_dict)` may need a `cast(dict[str, Any], ...)` in strict mode; the type ignore comment is present already.
    - structlog type stubs sometimes lag — if mypy complains about `structlog.get_logger`, use `# type: ignore[no-any-return]` or type the return as `Any` (as done above).
  </action>
  <verify>
    <automated>cd /Users/allen/repo/mcp-trino-optimizer && uv run pytest tests/logging/test_redaction.py tests/logging/test_structured_fields.py -v && uv run mypy src/mcp_trino_optimizer/logging_setup.py && ! grep -n "sys\.stdout" src/mcp_trino_optimizer/logging_setup.py</automated>
  </verify>
  <acceptance_criteria>
    - `uv run pytest tests/logging/test_redaction.py -v` — all tests pass (SecretStr, denylist case-insensitive, credential.* pattern, nested, list-of-dicts)
    - `uv run pytest tests/logging/test_structured_fields.py -v` — timestamp + package_version + git_sha present in log line
    - `grep -c "sys\.stdout" src/mcp_trino_optimizer/logging_setup.py` returns `0` (zero references to sys.stdout — D-12 layer 1)
    - `grep -c "sys\.stderr" src/mcp_trino_optimizer/logging_setup.py` returns at least `3` (basicConfig + PrintLoggerFactory)
    - `grep -c "REDACTION_DENYLIST" src/mcp_trino_optimizer/logging_setup.py` returns at least `2`
    - `grep -c '"authorization"' src/mcp_trino_optimizer/logging_setup.py` returns `1`
    - `grep -c '"x-trino-extra-credentials"' src/mcp_trino_optimizer/logging_setup.py` returns `1`
    - `grep -c '"cookie"' src/mcp_trino_optimizer/logging_setup.py` returns `1`
    - `grep -c '"ssl_password"' src/mcp_trino_optimizer/logging_setup.py` returns `1`
    - `grep -c "credential" src/mcp_trino_optimizer/logging_setup.py` returns at least `1` (pattern)
    - `grep -c "SecretStr" src/mcp_trino_optimizer/logging_setup.py` returns at least `2`
    - `grep -c "TimeStamper" src/mcp_trino_optimizer/logging_setup.py` returns `1`
    - `grep -c 'utc=True' src/mcp_trino_optimizer/logging_setup.py` returns `1` (ISO8601 UTC)
    - `grep -c "PrintLoggerFactory" src/mcp_trino_optimizer/logging_setup.py` returns `1`
    - `grep -c "force=True" src/mcp_trino_optimizer/logging_setup.py` returns `1` (stdlib logging force-override)
    - `grep -c "captureWarnings" src/mcp_trino_optimizer/logging_setup.py` returns `1`
    - `uv run mypy src/mcp_trino_optimizer/logging_setup.py` exits 0 in strict mode
  </acceptance_criteria>
  <done>All redaction tests pass (SecretStr, denylist case-insensitive, credential.* pattern, nested dicts, list of dicts, normal fields untouched). Every log line contains timestamp, package_version, git_sha. Zero sys.stdout references. Processor order matches RESEARCH.md §5.1 exactly.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Env var / .env → Settings model | pydantic validator gate blocks typos and missing required fields |
| log call → stderr | Redaction processor runs before serialization; stdout never touched |
| Settings error → operator | Fail-fast with a single structured JSON error line prevents partial/degraded startup |
| git_sha resolver → subprocess | `timeout=1`, `check=False`, all exceptions caught; no user input reaches argv |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-01-02 | Spoofing/Elevation | HTTP transport starts without bearer token → unauth access | mitigate | `_require_bearer_for_http` model_validator raises ValidationError; `load_settings_or_die` exits with structured error BEFORE any port binds |
| T-01-03 | Repudiation | Missing audit fields in log lines | mitigate | `configure_logging` injects `package_version` + `git_sha` as static process fields; `TimeStamper` ensures every line has ISO8601 UTC timestamp; `contextvars` path binds `request_id` + `tool_name` at tool entry (plan 01-04) |
| T-01-04 | Information disclosure | Secrets leaked in log dicts | mitigate | `_redact_processor` + `REDACTION_DENYLIST` + `credential.*` pattern + `SecretStr` isinstance check; recursive walker covers nested structures; unit tests lock the contract including adversarial cases |
| T-01-01 | DoS | Log handler writes to stdout | mitigate | `configure_logging` never references `sys.stdout`; `PrintLoggerFactory(file=sys.stderr)` is explicit; grep assertion in acceptance criteria enforces zero `sys.stdout` references in the file |
</threat_model>

<verification>
Run `uv run pytest tests/test_settings.py tests/test_runtime.py tests/logging/ -v` — all must pass. Run `uv run mypy src/mcp_trino_optimizer/settings.py src/mcp_trino_optimizer/_runtime.py src/mcp_trino_optimizer/_context.py src/mcp_trino_optimizer/logging_setup.py` — strict mode must be clean. Grep for `sys.stdout` in logging_setup.py — must return zero hits.
</verification>

<success_criteria>
- Settings fail-fast works: `transport=http` without bearer → `load_settings_or_die` prints JSON error + exits 2
- Settings `extra="forbid"` rejects typo'd MCPTO_* env vars
- Port range validation (1-65535) enforced
- `_resolve_git_sha` never raises and returns a string in all conditions (env var, baked file, git, fallback)
- `configure_logging` routes structlog to stderr exclusively; every log line contains timestamp, package_version, git_sha
- Redaction handles SecretStr, case-insensitive denylist, credential.* pattern, nested dicts, lists of dicts
- mypy strict clean on all four modules
</success_criteria>

<output>
After completion, create `.planning/phases/01-skeleton-safety-foundation/01-03-SUMMARY.md`
</output>
