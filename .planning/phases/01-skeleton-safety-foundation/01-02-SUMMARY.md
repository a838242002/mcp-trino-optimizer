---
phase: 01-skeleton-safety-foundation
plan: 02
subsystem: infra
tags: [safety, stdout-guard, envelope, schema-lint, prompt-injection, jsonschema, pydantic, mcp]

requires:
  - phase: 01-01
    provides: "Python package shells, stub test files, installed dev env"
provides:
  - "mcp_trino_optimizer.safety.envelope.wrap_untrusted() — pure-passthrough untrusted-content envelope"
  - "mcp_trino_optimizer.safety.stdout_guard — SentinelWriter + idempotent install/uninstall (layer 2 of 3)"
  - "mcp_trino_optimizer.safety.schema_lint — assert_tools_compliant() + SchemaLintError walker"
  - "MAX_STRING_LEN=100_000, MAX_PROSE_LEN=4_096, MAX_ARRAY_LEN=1_000 schema caps"
affects: [01-04, 01-05, all downstream tool-authoring plans]

tech-stack:
  added: []
  patterns:
    - "TypedDict envelope for mypy strict Literal type preservation"
    - "Lazy structlog import inside SentinelWriter.write to break circular dep with logging_setup"
    - "Fall-through JSON-on-stderr fallback when structlog isn't configured"
    - "Recursive schema walker that honors pydantic's \\$defs / definitions / anyOf / oneOf / allOf"
    - "Private SDK attribute access (mcp._tool_manager) by design — fail-loud if FastMCP renames"

key-files:
  created:
    - "src/mcp_trino_optimizer/safety/envelope.py"
    - "src/mcp_trino_optimizer/safety/stdout_guard.py"
    - "src/mcp_trino_optimizer/safety/schema_lint.py"
    - "tests/safety/test_stdout_guard.py"
  modified:
    - "tests/safety/test_schema_lint.py (per-test skipif refactor + module-level LooseInput for PEP 563 compat)"

key-decisions:
  - "SentinelWriter uses lazy import of logging_setup inside write() to avoid circular import with plan 01-03"
  - "fileno() raises OSError to make rich/colorama fall back to no-color mode cleanly"
  - "test_schema_lint.py pytestmark now only gates on schema_lint import — test_all_tools_are_schema_compliant has its own skipif for app_mod"
  - "Hoisted LooseInput BaseModel to module level so FastMCP's inspect.signature(eval_str=True) resolves type hints on Python 3.12+ (PEP 563 lazy annotations)"
  - "Ruff fixups: removed unused BLE001 noqa; tightened pytest.raises(OSError) with match= pattern"

patterns-established:
  - "Safety primitive as a pure, dependency-free module with one consumer (app.py in plan 01-04)"
  - "Lazy import of cross-cutting infrastructure to keep plan dependency order flexible"
  - "Test file structures hoist locally-scoped types to module level for Python 3.12+ eval_str compatibility"

requirements-completed:
  - PLAT-05
  - PLAT-10
  - PLAT-11

duration: ~20min
completed: 2026-04-11
---

# Phase 01 Plan 02: Safety Primitives Summary

**Three hardened safety primitives — `wrap_untrusted()` envelope (PLAT-11), `SentinelWriter` stdout guard (PLAT-05, D-12 layer 2), and `assert_tools_compliant()` JSON Schema walker (PLAT-10) — with 19 passing unit tests and mypy strict clean.**

## Performance

- **Duration:** ~20 min
- **Completed:** 2026-04-11
- **Tasks:** 3 (one per primitive)
- **Files created:** 4 (3 src modules + 1 test file)
- **Files modified:** 1 (test_schema_lint.py PEP 563 compat refactor)

## Accomplishments

- `wrap_untrusted()` is a pure passthrough into `{"source": "untrusted", "content": ...}` with no transformation — all 9 envelope tests pass including the 100KB near-cap preservation and adversarial prompt-injection payloads
- `SentinelWriter` replaces `sys.stdout` with a capture-and-log writer, dropping stray content while routing it to structlog (with a raw-stderr JSON fallback if logging isn't configured yet)
- `install_stdout_guard()` is idempotent; `uninstall_stdout_guard()` restores the original stream cleanly
- `SentinelWriter.fileno()` raises `OSError("no file descriptor")` so rich/colorama fall back to no-color probe behavior
- `assert_tools_compliant()` walks every `mcp._tool_manager.list_tools()` entry and detects missing `additionalProperties: false`, missing `maxLength`, missing `maxItems`, and prose-string overflow without `x-mcpto-sql`
- Walker recurses into `$defs`, `definitions`, `anyOf`, `oneOf`, `allOf` so pydantic-generated nested models are fully covered
- Full safety test suite: **19 passed, 1 skipped** (the skipped test waits on `app.build_app()` from plan 01-04)
- `uv run mypy src/mcp_trino_optimizer/safety/` — strict mode clean
- `uv run ruff check src/mcp_trino_optimizer/safety/ tests/safety/` — zero lints

## Task Commits

1. **Task 1: envelope.py** — `0abfcb8` (feat)
2. **Task 2: stdout_guard.py + test_stdout_guard.py** — `33023e4` (feat)
3. **Task 3: schema_lint.py + test_schema_lint.py PEP 563 fixups** — `79fa413` (feat)

## Files Created/Modified

- `src/mcp_trino_optimizer/safety/envelope.py` — `UntrustedEnvelope` TypedDict + `wrap_untrusted()`
- `src/mcp_trino_optimizer/safety/stdout_guard.py` — `SentinelWriter`, `install_stdout_guard`, `uninstall_stdout_guard`
- `src/mcp_trino_optimizer/safety/schema_lint.py` — `SchemaLintError`, `assert_tools_compliant`, `_check_schema` recursive walker, `MAX_*` constants
- `tests/safety/test_stdout_guard.py` — 6 tests: idempotency, stray-write capture, whitespace suppression, fileno OSError, attribute contract
- `tests/safety/test_schema_lint.py` — refactored to allow negative-case tests to run in this plan (pytestmark gates only on schema_lint import; test_all_tools_are_schema_compliant has its own per-test skipif); `LooseInput` hoisted to module level

## Decisions Made

- **Lazy logging_setup import.** `SentinelWriter.write` does the import inside the method body so this plan (01-02) and plan 01-03 (logging_setup) can execute in any order. A JSON-on-stderr fallback path guarantees violations are never silently dropped, even if logging_setup isn't yet on `sys.path`.
- **Per-test skipif refactor.** The stub test file from plan 01-01 had a module-level `pytestmark` that required both `schema_lint` AND `app_mod` — wrong for this plan since the negative-case tests don't need `app.build_app()`. Refactored so only `test_all_tools_are_schema_compliant` waits on plan 01-04.
- **Hoist LooseInput to module scope.** Python 3.12+ honors PEP 563 lazy annotations and FastMCP uses `inspect.signature(eval_str=True)`; a BaseModel defined inside a test function can't be resolved when used as a tool parameter annotation. Module-level definition fixes the InvalidSignature crash.
- **Ruff fixups.** Removed a BLE001 noqa that ruff's updated rule set no longer honors; tightened `pytest.raises(OSError)` with a `match=` pattern to satisfy PT011.

## Deviations from Plan

None material. Two small, defensible deviations captured above (test file refactor for Python 3.14 compat, ruff fixups) fall under execute-plan's auto-fix-blocking-issues rule. No scope creep.

## Issues Encountered

- **Python 3.14 + PEP 563 + FastMCP eval_str**: first run of `test_schema_lint_rejects_missing_additional_properties_false` raised `InvalidSignature: Unable to evaluate type annotations for callable 'loose_tool'`. Root cause: `LooseInput` was defined inside the test function, so FastMCP's inspect.signature couldn't resolve it under lazy annotations. Fix: move `LooseInput` to module scope. One-line fix, no bearing on the schema_lint module itself.
- **Stale `# type: ignore` markers.** On stricter mypy + Python 3.14, two ignore comments became "unused". Tagged them `[attr-defined,unused-ignore]` and `[assignment,unused-ignore]` so they survive on future interpreter bumps.

## User Setup Required

None.

## Next Phase Readiness

- `app.build_app()` (plan 01-04) can now:
  - call `assert_tools_compliant(mcp)` at startup as the runtime schema-lint guard
  - import `wrap_untrusted` to wrap every user-origin string in tool responses
  - call `install_stdout_guard()` in `transports.run_stdio()` after the pristine fd duplication
- Plan 01-03 (settings / logging / runtime) is unblocked and can run in parallel with this plan's outputs (no file overlap)
- The skipped schema-lint compliance test (`test_all_tools_are_schema_compliant`) will flip green automatically once plan 01-04 lands `app.build_app()`

---
*Phase: 01-skeleton-safety-foundation*
*Plan: 02-safety-primitives*
*Completed: 2026-04-11*
