---
phase: 01-skeleton-safety-foundation
plan: 01
type: execute
wave: 0
depends_on: []
files_modified:
  - pyproject.toml
  - .gitignore
  - src/mcp_trino_optimizer/__init__.py
  - src/mcp_trino_optimizer/_version.py
  - src/mcp_trino_optimizer/py.typed
  - src/mcp_trino_optimizer/safety/__init__.py
  - src/mcp_trino_optimizer/tools/__init__.py
  - tests/__init__.py
  - tests/conftest.py
  - tests/smoke/__init__.py
  - tests/smoke/test_stdio_initialize.py
  - tests/smoke/test_http_bearer.py
  - tests/logging/__init__.py
  - tests/logging/test_structured_fields.py
  - tests/logging/test_redaction.py
  - tests/test_settings.py
  - tests/tools/__init__.py
  - tests/tools/test_selftest.py
  - tests/safety/__init__.py
  - tests/safety/test_schema_lint.py
  - tests/safety/test_envelope.py
  - tests/docs/__init__.py
  - tests/docs/test_readme_mcp_blocks.py
  - README.md
autonomous: true
requirements:
  - PLAT-01
  - PLAT-02
  - PLAT-03
  - PLAT-05
  - PLAT-06
  - PLAT-07
  - PLAT-08
  - PLAT-09
  - PLAT-10
  - PLAT-11
  - PLAT-12
must_haves:
  truths:
    - "The test framework installs cleanly via uv sync --all-extras on Python 3.11, 3.12, 3.13"
    - "Every PLAT-01..PLAT-13 stub test file exists at the path 01-VALIDATION.md references, even if its assertions are xfail/skip until later waves"
    - "A developer can run `uv run pytest --collect-only` and see every stub test collected without import errors"
    - "pyproject.toml declares every pinned dependency version from CLAUDE.md and RESEARCH.md §8 exactly"
  artifacts:
    - path: "pyproject.toml"
      provides: "Build backend, dependency pins, tool configs (ruff, mypy, pytest)"
      contains: "mcp[cli]>=1.27.0,<2"
    - path: "src/mcp_trino_optimizer/__init__.py"
      provides: "Importable package"
    - path: "src/mcp_trino_optimizer/_version.py"
      provides: "Static __version__ consumed by hatchling"
      contains: "__version__"
    - path: "tests/conftest.py"
      provides: "Shared fixtures (subprocess runner, monkeypatch env, bearer token, structlog capture)"
    - path: "tests/smoke/test_stdio_initialize.py"
      provides: "PLAT-02, PLAT-05 stub using subprocess bytes-mode pattern"
    - path: "tests/safety/test_envelope.py"
      provides: "PLAT-11 stub covering exact shape + adversarial inputs"
  key_links:
    - from: "pyproject.toml"
      to: "src/mcp_trino_optimizer/_version.py"
      via: "[tool.hatch.version].path"
      pattern: 'path\s*=\s*"src/mcp_trino_optimizer/_version\.py"'
    - from: "pyproject.toml"
      to: "pytest"
      via: "[tool.pytest.ini_options] asyncio_mode"
      pattern: 'asyncio_mode\s*=\s*"auto"'
---

<objective>
Land the project scaffold AND every Wave 0 stub test file BEFORE any production code exists. Per 01-VALIDATION.md, stub test files and framework installs MUST land before production code so downstream plans have `<automated>` hooks from their very first commit. This plan creates a working Python package, all dev dependencies, and every test file that VALIDATION.md §"Wave 0 Requirements" enumerates. Tests are stubbed with `pytest.xfail`/`pytest.skip` markers so they collect cleanly but don't pass until later plans land the production code. No production code lands here beyond the empty package `__init__.py` files.

Purpose: Establish the Nyquist-compliant test feedback loop on day one. Every subsequent plan's `<automated>` verify block points at a test file this plan creates.
Output: Installable dev environment, complete `tests/` tree, `pyproject.toml` with pinned deps.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/ROADMAP.md
@.planning/REQUIREMENTS.md
@.planning/phases/01-skeleton-safety-foundation/01-CONTEXT.md
@.planning/phases/01-skeleton-safety-foundation/01-RESEARCH.md
@.planning/phases/01-skeleton-safety-foundation/01-VALIDATION.md
@CLAUDE.md

<interfaces>
<!-- This plan CREATES the package shell. Downstream plans will import from: -->
<!--   mcp_trino_optimizer (package)                                          -->
<!--   mcp_trino_optimizer.safety (subpackage)                                -->
<!--   mcp_trino_optimizer.tools (subpackage)                                 -->
<!-- This plan ships only empty __init__.py files and a _version.py.         -->

Module skeleton (created by this plan, no logic yet):
```python
# src/mcp_trino_optimizer/__init__.py
from mcp_trino_optimizer._version import __version__
__all__ = ["__version__"]

# src/mcp_trino_optimizer/_version.py
__version__ = "0.1.0"

# src/mcp_trino_optimizer/safety/__init__.py
# (empty — populated in plan 01-02)

# src/mcp_trino_optimizer/tools/__init__.py
# (empty — populated in plan 01-04)
```
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Write pyproject.toml, .gitignore, _version.py, and package shells</name>
  <files>pyproject.toml, .gitignore, src/mcp_trino_optimizer/__init__.py, src/mcp_trino_optimizer/_version.py, src/mcp_trino_optimizer/py.typed, src/mcp_trino_optimizer/safety/__init__.py, src/mcp_trino_optimizer/tools/__init__.py, README.md</files>
  <read_first>
    - /Users/allen/repo/mcp-trino-optimizer/CLAUDE.md (TL;DR section — dependency pins are load-bearing)
    - /Users/allen/repo/mcp-trino-optimizer/.planning/phases/01-skeleton-safety-foundation/01-RESEARCH.md §8 (pyproject.toml skeleton — copy verbatim)
    - /Users/allen/repo/mcp-trino-optimizer/.planning/phases/01-skeleton-safety-foundation/01-CONTEXT.md D-01 (src-layout), D-13 (CONTRIBUTING.md split)
  </read_first>
  <action>
    Create `pyproject.toml` at repo root by COPYING THE RESEARCH.md §8 SKELETON VERBATIM. Required contents:

    1. `[build-system]`: `requires = ["hatchling>=1.25"]`, `build-backend = "hatchling.build"`
    2. `[project]`: name `mcp-trino-optimizer`, `dynamic = ["version"]`, `requires-python = ">=3.11"`, `license = "Apache-2.0"`, `readme = "README.md"`, authors, classifiers for Python 3.11/3.12/3.13 and macOS/Linux/Windows.
    3. `[project.dependencies]` (EXACT pins from CLAUDE.md — do NOT substitute):
       ```
       "mcp[cli]>=1.27.0,<2"
       "pydantic>=2.9,<3"
       "pydantic-settings>=2.13.1"
       "structlog>=25.5.0"
       "orjson>=3.10"
       "anyio>=4.4"
       "typer>=0.12"
       "uvicorn>=0.30"
       "httpx>=0.28.1"
       ```
    4. `[project.optional-dependencies].dev`:
       ```
       "pytest>=8.3"
       "pytest-asyncio>=1.3.0"
       "syrupy>=5.1.0"
       "mypy>=1.11"
       "ruff>=0.15.10"
       "pre-commit>=3.8"
       ```
    5. `[project.scripts]`: `mcp-trino-optimizer = "mcp_trino_optimizer.cli:app"` (NOTE: cli module doesn't exist yet — that's fine, the entry point is declarative)
    6. `[tool.hatch.version]`: `path = "src/mcp_trino_optimizer/_version.py"`
    7. `[tool.hatch.build.targets.wheel]`: `packages = ["src/mcp_trino_optimizer"]`
    8. `[tool.hatch.build.targets.sdist]`: include src package, README.md, CONTRIBUTING.md (exists in later plan — still list it), CLAUDE.md, LICENSE.
    9. `[tool.ruff]`: `line-length = 120`, `target-version = "py311"`, `src = ["src", "tests"]`.
    10. `[tool.ruff.lint]`: `select = ["E", "F", "I", "N", "B", "UP", "SIM", "RUF", "ASYNC", "PT", "T20"]`, `ignore = ["E501"]`.
    11. `[tool.ruff.lint.per-file-ignores]`: `"tests/**/*.py" = ["T20"]`, `"src/mcp_trino_optimizer/safety/stdout_guard.py" = ["T20"]`.
    12. `[tool.ruff.format]`: `quote-style = "double"`, `indent-style = "space"`.
    13. `[tool.mypy]`: `python_version = "3.11"`, `strict = true`, `warn_unreachable = true`, `warn_unused_configs = true`, `disallow_any_generics = true`.
    14. `[tool.pytest.ini_options]`: `asyncio_mode = "auto"`, `testpaths = ["tests"]`, `markers = ["integration: opt-in tests requiring docker-compose stack (Phase 2+)", "slow: long-running tests"]`.

    **IMPORTANT:** Do NOT add `filterwarnings = ["error"]` from RESEARCH.md §8 — it breaks Wave 0 where stub tests use `xfail`/`skip` and deprecation warnings from dev deps may fire. That stricter setting can land in a later plan.

    Create `.gitignore` with: `.venv/`, `.env`, `__pycache__/`, `*.pyc`, `dist/`, `build/`, `*.egg-info/`, `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`, `.coverage`, `htmlcov/`, `.DS_Store`.

    Create `src/mcp_trino_optimizer/_version.py`:
    ```python
    """Static version for hatchling version plugin.

    Rationale: CONTEXT.md Claude's Discretion requires git_sha fallback to
    'unknown' outside a git checkout. A static version file is the simplest
    wheel-install-clean guarantee (RESEARCH.md §8).
    """
    __version__ = "0.1.0"
    ```

    Create `src/mcp_trino_optimizer/__init__.py`:
    ```python
    """mcp-trino-optimizer — MCP server for Trino + Iceberg SQL optimization."""
    from mcp_trino_optimizer._version import __version__

    __all__ = ["__version__"]
    ```

    Create empty `src/mcp_trino_optimizer/py.typed` (PEP 561 marker — zero bytes).

    Create empty `src/mcp_trino_optimizer/safety/__init__.py` with a one-line docstring: `"""Safety primitives: stdout guard, schema lint, untrusted envelope."""`.

    Create empty `src/mcp_trino_optimizer/tools/__init__.py` with a one-line docstring: `"""MCP tool implementations. Plan 01-04 adds selftest."""`.

    Create `README.md` as a MINIMAL placeholder — a single H1 `# mcp-trino-optimizer` and one paragraph describing the project. Plan 01-05 will replace this with the full PLAT-12 README. This minimal README is needed now so `pyproject.toml`'s `readme = "README.md"` doesn't break the build.
  </action>
  <verify>
    <automated>cd /Users/allen/repo/mcp-trino-optimizer && uv sync --all-extras 2>&1 | tail -20 && uv run python -c "import mcp_trino_optimizer; print(mcp_trino_optimizer.__version__)"</automated>
  </verify>
  <acceptance_criteria>
    - `pyproject.toml` exists at repo root
    - `grep -c 'mcp\[cli\]>=1.27.0,<2' pyproject.toml` returns `1`
    - `grep -c 'pydantic-settings>=2.13.1' pyproject.toml` returns `1`
    - `grep -c 'structlog>=25.5.0' pyproject.toml` returns `1`
    - `grep -c 'orjson>=3.10' pyproject.toml` returns `1`
    - `grep -c 'ruff>=0.15.10' pyproject.toml` returns `1`
    - `grep -c 'pytest-asyncio>=1.3.0' pyproject.toml` returns `1`
    - `grep -c 'hatchling>=1.25' pyproject.toml` returns `1`
    - `grep -c 'mcp-trino-optimizer = "mcp_trino_optimizer.cli:app"' pyproject.toml` returns `1`
    - `grep -c 'T20' pyproject.toml` returns at least `2` (select + per-file-ignores)
    - `uv sync --all-extras` exits 0
    - `uv run python -c "import mcp_trino_optimizer; print(mcp_trino_optimizer.__version__)"` prints `0.1.0`
    - `src/mcp_trino_optimizer/py.typed` exists
    - `.gitignore` contains `.env` line: `grep -c '^\.env$' .gitignore` returns `1`
  </acceptance_criteria>
  <done>pyproject.toml is the authoritative build config with exact pinned versions from CLAUDE.md; `uv sync --all-extras` installs all deps; the package imports and exposes `__version__`.</done>
</task>

<task type="auto">
  <name>Task 2: Create tests/ tree + conftest + every Wave 0 stub test file</name>
  <files>tests/__init__.py, tests/conftest.py, tests/smoke/__init__.py, tests/smoke/test_stdio_initialize.py, tests/smoke/test_http_bearer.py, tests/logging/__init__.py, tests/logging/test_structured_fields.py, tests/logging/test_redaction.py, tests/test_settings.py, tests/tools/__init__.py, tests/tools/test_selftest.py, tests/safety/__init__.py, tests/safety/test_schema_lint.py, tests/safety/test_envelope.py, tests/docs/__init__.py, tests/docs/test_readme_mcp_blocks.py</files>
  <read_first>
    - /Users/allen/repo/mcp-trino-optimizer/.planning/phases/01-skeleton-safety-foundation/01-VALIDATION.md (Wave 0 Requirements + Per-Task Verification Map)
    - /Users/allen/repo/mcp-trino-optimizer/.planning/phases/01-skeleton-safety-foundation/01-RESEARCH.md §15 (stdio smoke test template — copy verbatim as the real implementation), §9.2 (schema lint test template), §10 (envelope test template), §5.3 (SecretStr redaction test), §11.2 (runtime info shape)
    - /Users/allen/repo/mcp-trino-optimizer/.planning/phases/01-skeleton-safety-foundation/01-CONTEXT.md D-07 (bearer token fail-fast), D-10 (envelope exact shape), D-12 (stdout discipline)
  </read_first>
  <action>
    Create every test file listed below. Each stub file must IMPORT the module it will test (allowing `xfail`/`skip` to trigger cleanly) OR use `pytest.importorskip(...)` when the module doesn't exist yet. Follow this pattern exactly for stubs:

    ```python
    import pytest
    mod = pytest.importorskip("mcp_trino_optimizer.safety.envelope")  # landed in plan 01-02
    ```

    Every test file carries a module-level docstring citing the PLAT-IDs it covers and the plan that will make it pass. DO NOT mark any test `@pytest.mark.skip` unconditionally — use `importorskip` so tests flip green automatically once production code lands.

    ### `tests/__init__.py`, `tests/smoke/__init__.py`, `tests/logging/__init__.py`, `tests/tools/__init__.py`, `tests/safety/__init__.py`, `tests/docs/__init__.py`
    Empty files (single-line docstring OK).

    ### `tests/conftest.py`
    Shared fixtures:
    ```python
    """Shared pytest fixtures for Phase 1.

    Fixtures provided here:
    - subprocess_runner: spawn the mcp-trino-optimizer CLI in bytes mode
    - bearer_token: a deterministic test token (32 hex chars)
    - clean_env: monkeypatched env with MCPTO_* vars wiped
    - capture_stderr: pytest capsys wrapper for reading structured log lines
    """
    from __future__ import annotations

    import os
    import subprocess
    import sys
    from collections.abc import Iterator

    import pytest


    @pytest.fixture
    def bearer_token() -> str:
        return "a" * 32


    @pytest.fixture
    def clean_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
        """Wipe every MCPTO_* env var so tests see a clean slate."""
        for key in list(os.environ):
            if key.startswith("MCPTO_"):
                monkeypatch.delenv(key, raising=False)
        monkeypatch.setenv("MCPTO_GIT_SHA", "test0000")
        return monkeypatch


    @pytest.fixture
    def spawn_server() -> Iterator[object]:
        """Factory for subprocess.Popen bound to the installed CLI.

        Yields a callable that accepts args and env kwargs. See
        01-RESEARCH.md §15 for the bytes-mode pattern Windows requires.
        """
        procs: list[subprocess.Popen[bytes]] = []

        def _spawn(*args: str, env: dict[str, str] | None = None) -> subprocess.Popen[bytes]:
            proc_env = os.environ.copy()
            proc_env.setdefault("MCPTO_GIT_SHA", "test0000")
            proc_env.setdefault("PYTHONUNBUFFERED", "1")
            if env:
                proc_env.update(env)
            proc = subprocess.Popen(
                ["mcp-trino-optimizer", *args],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=0,
                env=proc_env,
            )
            procs.append(proc)
            return proc

        yield _spawn

        for p in procs:
            if p.poll() is None:
                p.kill()
                p.wait(timeout=5)
    ```

    ### `tests/smoke/test_stdio_initialize.py` (PLAT-02, PLAT-05)
    Copy the full implementation from RESEARCH.md §15 VERBATIM. Do NOT stub — this test is a real implementation that the installed CLI (after plan 01-04) must pass. It will fail in Wave 0 because the CLI isn't wired yet. That's correct behavior: add `pytest.importorskip("mcp_trino_optimizer.cli")` at the top of the file so it skips cleanly until the CLI module exists.

    Include the `INITIALIZE_FRAME` constant and the `test_stdio_initialize_produces_only_json_rpc_on_stdout` function from RESEARCH.md §15 exactly.

    ### `tests/smoke/test_http_bearer.py` (PLAT-03)
    Stubs covering:
    - `test_http_transport_fails_fast_without_bearer_token` — spawns server with `--transport http` and no `MCPTO_HTTP_BEARER_TOKEN`, asserts exit code != 0 within 5 seconds AND that stderr contains the JSON error with `event: "settings_error"` (D-07, D-08).
    - `test_http_transport_rejects_missing_authorization_header` — spawns server with bearer token, sends request with no Authorization header, expects 401.
    - `test_http_transport_rejects_wrong_bearer_token` — expects 401.
    - `test_http_transport_accepts_correct_bearer_token` — expects 200.

    Top of file: `pytest.importorskip("mcp_trino_optimizer.cli")`. The HTTP tests require a running server which only exists after plan 01-04.

    ### `tests/logging/test_structured_fields.py` (PLAT-06)
    ```python
    """PLAT-06: Every log line carries request_id, tool_name, git_sha, package_version, ISO8601 UTC timestamp.

    Landed by plan 01-03.
    """
    from __future__ import annotations
    import json
    import pytest

    cfg = pytest.importorskip("mcp_trino_optimizer.logging_setup")


    def test_log_line_contains_mandatory_fields(capsys):
        cfg.configure_logging("INFO", package_version="0.1.0", git_sha="abc123456789")
        log = cfg.get_logger("test")
        log.info("test_event", extra_field="hello")
        captured = capsys.readouterr()
        line = captured.err.strip().splitlines()[-1]
        data = json.loads(line)
        assert "timestamp" in data
        assert data.get("package_version") == "0.1.0"
        assert data.get("git_sha") == "abc123456789"
        # request_id + tool_name are bound via contextvars at tool entry —
        # tested in tests/tools/test_selftest.py
    ```

    ### `tests/logging/test_redaction.py` (PLAT-07)
    Copy RESEARCH.md §5.3 `test_secretstr_redacted` and extend with:
    - `test_authorization_key_redacted` — dict with `authorization="Bearer xyz"` → `[REDACTED]`
    - `test_case_insensitive_denylist` — `Authorization`, `AUTHORIZATION`, `authorization` all redacted
    - `test_credential_dot_pattern_redacted` — dict with `{"credential.user": "alice", "credential.password": "x"}` → both values `[REDACTED]`
    - `test_x_trino_extra_credentials_redacted`
    - `test_cookie_redacted`
    - `test_nested_dict_redaction` — secret buried two levels deep
    - `test_secret_in_list_of_dicts` — list containing a secret dict
    - `test_normal_fields_not_redacted` — `user="alice"` survives

    Top of file: `cfg = pytest.importorskip("mcp_trino_optimizer.logging_setup")`.

    ### `tests/test_settings.py` (PLAT-08 + D-07 fail-fast)
    Stubs:
    - `test_default_transport_is_stdio`
    - `test_env_var_precedence_over_default` — `MCPTO_TRANSPORT=http` + bearer token → `settings.transport == "http"`
    - `test_cli_override_precedence_over_env` — init kwargs beat env
    - `test_http_without_bearer_token_raises` — ValidationError on `transport=http` + no token (D-07)
    - `test_load_settings_or_die_exits_on_missing_bearer` — uses `pytest.raises(SystemExit)` and captures stderr, asserts it contains `"event":"settings_error"`
    - `test_extra_env_var_rejected` — `MCPTO_UNKNOWN_FIELD=x` raises ValidationError (D-08, `extra="forbid"`)
    - `test_http_port_range_validation` — port 0 and 70000 rejected

    Top: `settings_mod = pytest.importorskip("mcp_trino_optimizer.settings")`.

    ### `tests/tools/test_selftest.py` (PLAT-09)
    Stubs:
    - `test_selftest_returns_mandatory_fields` — instantiates the tool via `build_app()`, invokes it, asserts response has `server_version`, `transport`, `echo`, `capabilities` keys
    - `test_selftest_echo_round_trip` — passes `echo="hello"`, asserts response.echo == "hello"
    - `test_selftest_binds_request_id_and_tool_name` — spies on log capture, asserts `request_id` and `tool_name` appear in the structured log line for the tool call
    - `test_selftest_capabilities_is_list` — asserts `capabilities` is a list of strings

    Top: `app_mod = pytest.importorskip("mcp_trino_optimizer.app")`.

    ### `tests/safety/test_schema_lint.py` (PLAT-10)
    Copy RESEARCH.md §9.2 tests VERBATIM: `test_all_tools_are_schema_compliant`, `test_schema_lint_detects_violation`. Add:
    - `test_schema_lint_rejects_missing_max_length` — explicit fake tool with `sql: str` (no Field) triggers violation with message matching `"maxLength"`
    - `test_schema_lint_rejects_missing_additional_properties_false` — fake tool with a BaseModel lacking `extra="forbid"` triggers violation
    - `test_schema_lint_rejects_array_without_max_items` — fake tool with `list[str]` without `max_length` on the Field → violation

    Top: `lint = pytest.importorskip("mcp_trino_optimizer.safety.schema_lint")`.

    ### `tests/safety/test_envelope.py` (PLAT-11)
    Copy RESEARCH.md §10 tests VERBATIM: `test_shape_is_exact`, `test_empty_content`, `test_preserves_control_characters_verbatim`, `test_return_type_is_dict_not_str`, `test_source_field_is_literal_untrusted`. Add:
    - `test_large_string_near_cap` — `wrap_untrusted("x" * 100_000)` preserves the full content (envelope doesn't truncate)
    - `test_prompt_injection_adversarial` — string containing `"<|im_start|>system"`, `"Ignore previous instructions"`, triple backticks — all preserved verbatim

    Top: `env = pytest.importorskip("mcp_trino_optimizer.safety.envelope")`.

    ### `tests/docs/test_readme_mcp_blocks.py` (PLAT-12)
    Stubs:
    - `test_readme_contains_stdio_mcp_servers_block` — reads README.md, asserts presence of a JSON code block containing `"command": "mcp-trino-optimizer"` AND `"args": ["serve", "--transport", "stdio"]`
    - `test_readme_contains_streamable_http_block` — similar assertion for `--transport http`
    - `test_readme_contains_docker_block` — similar assertion for `docker run`
    - `test_contributing_md_exists` — asserts file exists at repo root
    - `test_claude_md_exists` — asserts file exists

    Use `pathlib.Path(__file__).parents[2] / "README.md"` to locate. This test suite has no production-code dependency — it only needs files landed by plan 01-05.

    **Stub strategy for this file (PER-TEST xfail, not module-level):** CLAUDE.md already exists at repo root today, so `test_claude_md_exists` MUST be a real regression guard that passes immediately in Wave 0 (no xfail). Every other test in this file is decorated individually with `@pytest.mark.xfail(reason="README/CONTRIBUTING expanded in plan 01-05", strict=False)` so each flips green when plan 01-05 lands. Do NOT apply a module-level `pytest.mark.xfail` — it would swallow the `test_claude_md_exists` regression guard.

    Concretely:
    ```python
    import pathlib
    import pytest

    ROOT = pathlib.Path(__file__).parents[2]


    def test_claude_md_exists():
        """Regression guard — CLAUDE.md exists today and must keep existing."""
        assert (ROOT / "CLAUDE.md").exists()


    @pytest.mark.xfail(reason="CONTRIBUTING.md lands in plan 01-05", strict=False)
    def test_contributing_md_exists():
        assert (ROOT / "CONTRIBUTING.md").exists()


    @pytest.mark.xfail(reason="README expanded in plan 01-05", strict=False)
    def test_readme_contains_stdio_mcp_servers_block():
        ...


    @pytest.mark.xfail(reason="README expanded in plan 01-05", strict=False)
    def test_readme_contains_streamable_http_block():
        ...


    @pytest.mark.xfail(reason="README expanded in plan 01-05", strict=False)
    def test_readme_contains_docker_block():
        ...
    ```
  </action>
  <verify>
    <automated>cd /Users/allen/repo/mcp-trino-optimizer && uv run pytest --collect-only 2>&1 | tail -40 && uv run pytest -m "not integration" --co -q | grep -c "test_" </automated>
  </verify>
  <acceptance_criteria>
    - `uv run pytest --collect-only` exits 0 (no import errors, no collection errors)
    - `uv run pytest -m "not integration" --co -q | grep -c "test_"` returns at least 30 (collected stub tests)
    - Every file in the `<files>` list exists and is non-empty
    - `grep -l "importorskip" tests/smoke/ tests/logging/ tests/tools/ tests/safety/` returns at least 6 files (stubs skip on missing production modules)
    - `grep -c "INITIALIZE_FRAME" tests/smoke/test_stdio_initialize.py` returns `2` (constant + usage) — RESEARCH.md §15 verbatim
    - `grep -c "wrap_untrusted" tests/safety/test_envelope.py` returns at least `5`
    - `grep -c "credential" tests/logging/test_redaction.py` returns at least `1` (D-09 pattern)
    - `grep -c "test_http_without_bearer_token_raises\|test_load_settings_or_die" tests/test_settings.py` returns `2` (D-07 fail-fast coverage)
    - `uv run pytest -m "not integration" -q 2>&1 | grep -E "skipped|xfailed"` shows stubs skipped/xfailed (not errored)
    - `uv run pytest tests/docs/test_readme_mcp_blocks.py::test_claude_md_exists -v` PASSES in Wave 0 (NOT xfailed — CLAUDE.md is a real regression guard per checker fix W-05)
  </acceptance_criteria>
  <done>Every PLAT-ID listed in 01-VALIDATION.md has its stub test file; `pytest --collect-only` collects them all without import errors; tests skip cleanly via `importorskip` until downstream plans land production code; NO production module exists yet apart from empty package shells.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| pyproject.toml → PyPI | Dependency pins are the supply-chain boundary — wrong pins let unverified code in |
| tests/ → src/ | Test stubs must not silently skip forever; `importorskip` is the right tool, `pytest.skip` unconditional is wrong |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-01-05 | Tampering | pyproject.toml dependency pins | mitigate | Exact pins from CLAUDE.md copied verbatim; grep assertions in acceptance criteria block subtle substitutions |
| T-01-W0 | DoS (future) | Wave 0 stub tests silently passing | mitigate | Use `importorskip` (not unconditional `skip`); this auto-flips to real execution when modules land in later plans — no manual intervention required |
</threat_model>

<verification>
Run `uv sync --all-extras` and `uv run pytest --collect-only` — both must exit 0. Run `uv run pytest -m "not integration" -q` and confirm ALL tests either pass, skip (importorskip), or xfail (README docs tests). ZERO errors allowed.
</verification>

<success_criteria>
- pyproject.toml has every pinned dependency from CLAUDE.md verbatim
- Package `mcp_trino_optimizer` imports cleanly and exposes `__version__`
- Every Wave 0 stub test file from 01-VALIDATION.md exists
- `pytest --collect-only` collects every stub without import errors
- Tests that require production code use `importorskip` to flip green automatically when later plans land
</success_criteria>

<output>
After completion, create `.planning/phases/01-skeleton-safety-foundation/01-01-SUMMARY.md`
</output>
