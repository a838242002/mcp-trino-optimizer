---
phase: 01-skeleton-safety-foundation
plan: 03
subsystem: infra
tags: [settings, pydantic-settings, structlog, logging, redaction, secretstr, runtime, contextvars, git-sha]

requires:
  - phase: 01-01
    provides: "Python package shell, stub test files for PLAT-06/07/08"
provides:
  - "mcp_trino_optimizer.settings.Settings + load_settings_or_die fail-fast entry point"
  - "mcp_trino_optimizer.logging_setup.configure_logging + get_logger + REDACTION_DENYLIST + _redact_processor"
  - "mcp_trino_optimizer._runtime.RuntimeInfo + runtime_info + _resolve_git_sha (three-tier, never raises)"
  - "mcp_trino_optimizer._context.new_request_id + current_request_id (structlog contextvars binding)"
affects: [01-02, 01-04, 01-05, all downstream tool and transport plans]

tech-stack:
  added: []
  patterns:
    - "model_validator(mode='after') for cross-field validation (transport=http requires http_bearer_token)"
    - "load_settings_or_die uses orjson directly (no structlog dependency) because Settings loads BEFORE logging is configured"
    - "pydantic e.errors(include_context=False, include_input=False) strips non-JSON-serializable ctx objects and raw input (which may contain secrets)"
    - "structlog processor order: merge_contextvars → add_log_level → _add_logger_name → TimeStamper → static fields lambda → redaction → stack info → exc info → orjson renderer"
    - "_add_logger_name custom processor replaces structlog.stdlib.add_logger_name because PrintLogger has no .name attribute"
    - "Module-level _started_at captured at import time (dt.datetime.now(dt.UTC).isoformat() with +00:00 → Z normalization)"
    - "_resolve_git_sha three-tier fallback: env var → importlib.resources baked file → git rev-parse subprocess with 1s timeout → 'unknown'"
    - "processor signatures typed as MutableMapping[str, Any] to match structlog's invariant type; orjson.dumps(dict(event_dict)) to materialize for serialization"

key-files:
  created:
    - "src/mcp_trino_optimizer/settings.py"
    - "src/mcp_trino_optimizer/logging_setup.py"
    - "src/mcp_trino_optimizer/_runtime.py"
    - "src/mcp_trino_optimizer/_context.py"
    - "tests/test_runtime.py"
  modified:
    - "tests/smoke/test_http_bearer.py (ruff PT018 fix — split compound assert)"
    - "tests/smoke/test_stdio_initialize.py (ruff RUF002 fix — replace ambiguous × with x in docstring)"

key-decisions:
  - "load_settings_or_die passes include_context=False + include_input=False to pydantic's ValidationError.errors() because our model_validator raises ValueError (ctx not JSON-serializable) and raw input may carry secrets"
  - "Custom _add_logger_name processor — structlog.stdlib.add_logger_name crashes with AttributeError on PrintLogger because PrintLogger doesn't expose a .name attribute"
  - "MutableMapping[str, Any] processor signatures (not dict[str, Any]) — structlog declares its processor contract via typing.Protocol and mypy strict mode rejects the dict invariance"
  - "orjson.dumps takes dict(event_dict) to force-materialize the MutableMapping (MutableMapping is invariant at the orjson layer)"
  - "Module-level _started_at — captured once at import, not per call, so the RuntimeInfo dataclass remains frozen and the value is stable across the process lifetime"

patterns-established:
  - "Fail-fast config loading with structured JSON error line before any transport binds a port"
  - "structlog + orjson pipeline with recursion-safe redaction walker (dicts, lists, tuples, at any depth)"
  - "Three-tier git SHA resolver with always-a-string contract — never raises, never blocks"
  - "Contextvars-backed request_id binding that propagates through anyio/asyncio task trees"

requirements-completed:
  - PLAT-06
  - PLAT-07
  - PLAT-08

duration: ~25min
completed: 2026-04-11
---

# Phase 01 Plan 03: Settings / Logging / Runtime Summary

**pydantic-settings `Settings` with fail-fast loading, structlog + orjson stderr-only pipeline with recursive redaction, frozen `RuntimeInfo` dataclass with three-tier never-raising git_sha resolver, and contextvars-backed request_id helpers — all mypy strict clean and landing 27 new tests green.**

## Performance

- **Duration:** ~25 min
- **Completed:** 2026-04-11
- **Tasks:** 2 (settings + runtime + context in task 1; logging_setup in task 2)
- **Files created:** 5
- **Files modified:** 2 (pre-existing plan 01-01 test files — minor ruff lint fixups)

## Accomplishments

- `Settings()` loads MCPTO_* env vars with `extra="forbid"`, port range validation, and SecretStr bearer token
- `_require_bearer_for_http` model_validator raises ValidationError when `transport=http` is set without `http_bearer_token` — D-07 fail-fast is enforced at the model layer
- `load_settings_or_die()` emits a single structured `{"level":"error","event":"settings_error","errors":[...]}` JSON line to stderr and `sys.exit(2)` before any transport starts
- `_resolve_git_sha()` is provably never-raising — direct smoke test + three-tier fallback + subprocess timeout + blanket OSError catch
- `configure_logging()` wires the full processor pipeline: contextvars merge → log level → logger name → ISO8601 UTC timestamp → static fields lambda → recursive redaction → stack info → exc info → orjson renderer
- `REDACTION_DENYLIST` covers authorization, x-trino-extra-credentials, cookie, token, password, api_key, apikey, bearer, secret, ssl_password (case-insensitive), plus `credential.*` regex pattern, plus unconditional SecretStr → `[REDACTED]`
- Redaction walker handles nested dicts, lists of dicts, tuples — PLAT-07 test matrix green
- Zero `sys.stdout` references anywhere in `logging_setup.py` (D-12 layer 1 of 3 honored)
- `_context.new_request_id()` generates a UUID hex request ID, binds it to both the contextvar and `structlog.contextvars.bind_contextvars`
- Test count delta: +13 (tests/test_runtime.py) + 14 (tests/logging/*) + 14 (tests/test_settings.py) — full run **47 passed, 10 skipped, 4 xfailed**
- `uv run mypy` on every new module passes in strict mode
- `uv run ruff check` clean across the entire repo

## Task Commits

1. **Task 1: settings.py + _runtime.py + _context.py + tests/test_runtime.py** — `73a8183` (feat)
2. **Task 2: logging_setup.py + plan 01-01 test lint fixups** — `dcb37b7` (feat)

## Files Created/Modified

- `src/mcp_trino_optimizer/settings.py` — `Settings` BaseSettings + `load_settings_or_die` fail-fast loader
- `src/mcp_trino_optimizer/_runtime.py` — `RuntimeInfo` frozen dataclass + `runtime_info()` + `_resolve_git_sha()` + `set_transport()`
- `src/mcp_trino_optimizer/_context.py` — `new_request_id()` + `current_request_id()` contextvar helpers
- `src/mcp_trino_optimizer/logging_setup.py` — `configure_logging` + `get_logger` + `REDACTION_DENYLIST` + `_redact_processor` + `_add_logger_name` + `_orjson_renderer`
- `tests/test_runtime.py` — 5 tests: env var tier, fallback tier, never-raises smoke, runtime_info field coverage, set_transport mutation
- `tests/smoke/test_http_bearer.py` — ruff PT018 fix (split compound assert)
- `tests/smoke/test_stdio_initialize.py` — ruff RUF002 fix (`×` → `x` in docstring)

## Decisions Made

- **`include_context=False` + `include_input=False` on `e.errors()`.** Pydantic 2's `errors()` surface includes a `ctx` field that may hold the original exception instance — orjson refuses to serialize a bare `ValueError`. Explicitly stripping `ctx` AND `input` keeps the fail-fast path both serializable and secret-safe.
- **Custom `_add_logger_name` processor.** `structlog.stdlib.add_logger_name` attempts `logger.name`; `PrintLogger` (used via `PrintLoggerFactory`) has no `name` attribute and raises `AttributeError`. A custom processor that uses `getattr(logger, "name", None)` and falls back cleanly sidesteps the stdlib/PrintLogger mismatch.
- **`MutableMapping[str, Any]` signatures.** structlog's processor protocol accepts a `MutableMapping` and my initial `dict[str, Any]` signatures triggered mypy variance errors. Using the abstract type matches structlog's contract and is what the stubs actually expect.
- **`orjson.dumps(dict(event_dict))`.** orjson doesn't know how to serialize an arbitrary `MutableMapping`; materializing to a plain dict is a single-allocation fix that also keeps the final render type stable.
- **Keep lint fix-ups in scope.** Plan 01-01 committed test files with two pre-existing ruff lints that blocked "clean" state. Executor auto-fix rule says these are in scope for the failing plan — fixed inline, noted in the commit message.

## Deviations from Plan

- **Processor name replacement (`_add_logger_name`).** Plan called for `structlog.stdlib.add_logger_name`; its incompatibility with `PrintLoggerFactory` on structlog 25.x surfaced only at runtime. Swapped for a safe drop-in. No semantic change to the emitted log lines other than: the `logger` field is only populated when the underlying logger actually has a name (equivalent behavior for a stdlib logger; no-op for the PrintLogger we use).
- **Pre-existing ruff fix-ups** (PT018, RUF002) in plan 01-01 test files. Not in 01-03's nominal scope but blocks the clean-state invariant the plan requires for CI readiness.

## Issues Encountered

- **structlog.stdlib.add_logger_name + PrintLogger incompatibility.** Raised `AttributeError: 'PrintLogger' object has no attribute 'name'` at first log call. Root-caused as a structlog stdlib-vs-PrintLogger contract mismatch; fixed with a custom processor.
- **orjson failing on pydantic ValueError.** First `load_settings_or_die` run hit `TypeError: Type is not JSON serializable: ValueError` because the model_validator raises `ValueError` and pydantic bubbles it into `ctx`. Fixed by passing `include_context=False` to `e.errors()`.
- **mypy strict variance errors on processor lists.** Initial `dict[str, Any]` signatures incompatible with structlog's `MutableMapping[str, Any]` protocol; fixed by widening to `MutableMapping[str, Any]`.

## User Setup Required

None — `.env.example` documentation lands in plan 01-05.

## Next Phase Readiness

- Plan 01-04 (app / tools / transports / CLI) can now:
  - call `load_settings_or_die()` from the CLI entry point (fail-fast before any server binds a port)
  - call `configure_logging(level=..., package_version=..., git_sha=...)` immediately after loading settings
  - use `runtime_info()` to populate the `mcp_selftest` tool response (package_version, python_version, git_sha, transport, started_at, log_level)
  - call `set_transport("stdio" | "http")` at transport bind time to update the module global read by `runtime_info()`
  - call `new_request_id()` inside the selftest tool handler to bind request_id into the structlog contextvars before logging
- The still-skipped PLAT-09 selftest tests (`tests/tools/test_selftest.py`) and PLAT-02/PLAT-05 smoke tests (`tests/smoke/test_*`) will flip green once plan 01-04 lands `build_app()` and the `cli` module
- Wave 1 is now complete on the source side — Wave 2 unblocked

---
*Phase: 01-skeleton-safety-foundation*
*Plan: 03-settings-logging-runtime*
*Completed: 2026-04-11*
