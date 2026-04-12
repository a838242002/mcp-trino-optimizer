# Contributing to mcp-trino-optimizer

This file is a project rule. Read it before making changes. See
[`CLAUDE.md`](./CLAUDE.md) for technology stack and project context — the
two files are both authoritative.

## Coding rules

1. **Every ruff rule in `pyproject.toml [tool.ruff.lint] select` is ON.**
   No per-line disables without justification in a code comment.
2. **`mypy --strict` must pass.** Use `Annotated[...]` and explicit types;
   no implicit `Any`.
3. **No `print()` anywhere in `src/`.** Use `structlog.get_logger()`. The
   `T20` ruff rule enforces this globally.
4. **No regex-based SQL manipulation.** Use `sqlglot` (lands in Phase 6+;
   forbidden by construction earlier).
5. **All logging goes to stderr via `mcp_trino_optimizer.logging_setup`.**
   Never write to `stdout` — it's the JSON-RPC channel in stdio mode.
6. **Tool responses that echo user-origin content must wrap it in
   `safety.envelope.wrap_untrusted()`.** No exceptions. Indirect prompt
   injection is a real attack surface for MCP servers.
7. **Tool input models use `pydantic.BaseModel` with
   `ConfigDict(extra="forbid")`.** Every string field has `max_length`;
   every identifier has a `pattern`; every array has a bounded `max_length`.
8. **Read-only-by-construction:** no code in `src/` may issue a Trino write
   statement — enforced by a `safety.classifier` AST gate (Phase 2+).

## Definition of Done

A PR is ready when:

- [ ] Unit tests pass: `uv run pytest -m "not integration"`
- [ ] `uv run ruff format --check .` clean
- [ ] `uv run ruff check .` clean
- [ ] `uv run mypy src` strict clean
- [ ] Stdio `initialize` smoke test passes on the current OS:
      `uv run pytest tests/smoke/test_stdio_initialize.py -v`
- [ ] `mcp_selftest` round-trip passes locally
- [ ] If the PR touches any tool signature, `schema_lint` still passes:
      `uv run pytest tests/safety/test_schema_lint.py -v`
- [ ] CHANGELOG entry added (once a CHANGELOG exists)

## Validation workflow

1. **Pre-commit hooks** run on every commit: `ruff format`, `ruff check`,
   `mypy src`. Install with `uv run pre-commit install`.
2. **CI** runs on push and PR:
   - `lint-types` — Linux × Python 3.12 — `ruff format --check`,
     `ruff check`, `mypy --strict`
   - `unit-smoke` — 3 OS × 3 Python matrix (9 cells) — `pytest -m "not
     integration"` plus the stdio cleanliness smoke test and the
     `mcp-trino-optimizer --help` entry-point check
   - `integration` — reserved for Phase 2+ when the docker-compose Trino
     stack lands
3. **Phase gates** require the full suite green on all 9 cells plus a
   `/gsd-verify-work` pass.

## Safe-execution boundaries

Five invariants the server makes with its callers:

1. **Read-only guarantee.** Every code path that reaches Trino routes
   through the `SqlClassifier` AST gate (Phase 2). The gate rejects
   `INSERT`, `UPDATE`, `DELETE`, `MERGE`, `DROP`, `CREATE`, `ALTER`,
   `TRUNCATE`, `CALL`, and multi-statement blocks — even when wrapped in
   comments or Unicode escapes.
2. **SqlClassifier invariant.** Every `TrinoClient` public method that
   accepts a `sql: str` parameter calls `assert_read_only(sql)` as its
   **first executable line** — before any network call, before any logging.
   This is enforced by `tests/adapters/test_trino_client_invariant.py`
   and must not be relaxed without explicit review.
3. **Untrusted envelope rule.** Every tool response that includes a
   user-origin string wraps it in
   `{"source": "untrusted", "content": "..."}` via
   `safety.envelope.wrap_untrusted()`.
4. **Schema-lint rule.** Every tool's input JSON Schema passes
   `safety.schema_lint.assert_tools_compliant` at startup (runtime guard)
   AND in CI (regression guard).
5. **Stdout discipline.** Stdio mode installs `stdout_guard` before the
   transport starts; a CI smoke test asserts every byte on stdout is a
   valid JSON-RPC frame.

### Integration test DDL boundary

No code in `src/` or in any integration test file other than
`tests/integration/fixtures.py` may issue Trino DDL statements.

- Raw `trino-python-client` DBAPI access (`trino.dbapi.connect`) is
  **only permitted** in `tests/integration/fixtures.py` (D-25). All other
  modules must go through `TrinoClient`.
- `tests/integration/fixtures.py` exists solely for test seeding
  (CREATE TABLE / INSERT). It must never be imported in `src/`.
- Enforced by pre-commit grep: `grep -r "trino.dbapi.connect" src/`
  must return no results.

## Local development

```bash
# Install dev deps
uv sync --all-extras

# Run stdio
uv run mcp-trino-optimizer serve

# Run HTTP with a test bearer token
MCPTO_HTTP_BEARER_TOKEN=$(openssl rand -hex 32) \
  uv run mcp-trino-optimizer serve --transport http

# Run the quick test suite
uv run pytest -m "not integration" -x

# Run the full suite
uv run pytest -v

# Update syrupy snapshots (when fixture output intentionally changes)
uv run pytest --snapshot-update
```

## Testing notes

- `pytest -m "not integration"` is the fast path — no Docker, no Trino.
- `pytest -m integration` is opt-in and currently empty (Phase 2+ adds the
  docker-compose stack).
- Snapshot tests use `syrupy`. When output legitimately changes, regenerate
  with `pytest --snapshot-update` and review the diff carefully before
  committing.

## Reporting security issues

Do NOT file a public GitHub issue for a security vulnerability. Email the
maintainers directly. We treat any tool-result-based prompt injection,
SQL classifier bypass, or stdio-channel corruption as a HIGH severity bug.
