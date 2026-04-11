---
status: complete
phase: 01-skeleton-safety-foundation
source:
  - 01-01-SUMMARY.md
  - 01-02-SUMMARY.md
  - 01-03-SUMMARY.md
  - 01-04-SUMMARY.md
  - 01-05-SUMMARY.md
  - 01-06-SUMMARY.md
started: 2026-04-12T00:00:00Z
updated: 2026-04-12T00:00:01Z
---

## Current Test

number: 7
name: Schema lint runtime guard catches non-compliant tools
expected: |
  `uv run python -c "from mcp_trino_optimizer.app import build_app; build_app()"`
  succeeds and logs `tools_registered count=1`. If a developer later adds a tool
  with a missing `max_length` Field or `additionalProperties: false`, build_app
  crashes with `SchemaLintError` BEFORE the server binds any port. (Covered by
  `tests/safety/test_schema_lint.py` — 4 negative-case tests pass.)
awaiting: user response

## Tests

### 1. Cold Start Smoke Test
expected: |
  Kill any running mcp-trino-optimizer process. In a fresh shell (no prior env),
  run `uv sync --all-extras` in the repo root — completes cleanly without errors.
  Then run `uv run mcp-trino-optimizer --help` — prints the top-level Typer help
  showing the `serve` subcommand. No tracebacks, no stdout corruption warnings.
result: pass

### 2. CLI serve --help
expected: |
  `uv run mcp-trino-optimizer serve --help` exits 0 and lists five options:
  --transport, --host, --port, --log-level, --bearer-token. The help panel is
  rendered via Typer (clean boxed layout).
result: pass

### 3. stdio transport starts and answers initialize
expected: |
  `uv run mcp-trino-optimizer serve` (or `serve --transport stdio`) launches a
  stdio MCP server. Send a JSON-RPC initialize frame to stdin and receive a
  valid initialize response on stdout. Every byte on stdout parses as JSON-RPC —
  no stray banners, no print statements. Structured log lines appear on stderr.
  (The automated test `tests/smoke/test_stdio_initialize.py` covers this; you
  can drive it manually via `uv run pytest tests/smoke/test_stdio_initialize.py -v`.)
result: pass

### 4. HTTP transport fails fast without bearer token
expected: |
  `uv run mcp-trino-optimizer serve --transport http` WITHOUT setting
  MCPTO_HTTP_BEARER_TOKEN or passing --bearer-token exits within a second with
  a non-zero exit code AND emits a single structured JSON line on stderr with
  `"event":"settings_error"`. The server never binds a port.
result: pass

### 5. HTTP transport with bearer token binds and enforces auth
expected: |
  `MCPTO_HTTP_BEARER_TOKEN=$(openssl rand -hex 32) uv run mcp-trino-optimizer serve --transport http`
  starts uvicorn on 127.0.0.1:8080 and logs a `plaintext_http_warning`. Requests
  missing the Authorization header → 401. Requests with a wrong bearer → 401.
  Requests with the correct bearer + `Accept: application/json, text/event-stream`
  headers → 200. (The test file `tests/smoke/test_http_bearer.py` exercises all
  four cases; run it via `uv run pytest tests/smoke/test_http_bearer.py -v`.)
result: pass
note: |
  User's initial run appeared to show only the first log line (tools_registered)
  so reproduced locally and confirmed the full startup sequence —
  plaintext_http_warning + uvicorn bind all fire correctly. Test suite
  (tests/smoke/test_http_bearer.py) exercises all 4 auth cases green.

### 6. mcp_selftest tool round-trip
expected: |
  Call `mcp_selftest(echo="hello")` via any MCP client. Response contains all
  nine fields: server_version, transport, echo, python_version, package_version,
  git_sha, log_level, started_at, capabilities. The `echo` field equals "hello"
  verbatim. Structured log line `tool_invoked` is emitted on stderr with
  `request_id` and `tool_name=mcp_selftest` bound via contextvars.
result: pass

### 7. Schema lint runtime guard catches non-compliant tools
expected: |
  `uv run python -c "from mcp_trino_optimizer.app import build_app; build_app()"`
  succeeds and logs `tools_registered count=1`. If a developer later adds a tool
  with a missing `max_length` Field or `additionalProperties: false`, build_app
  crashes with `SchemaLintError` BEFORE the server binds any port. (Covered by
  `tests/safety/test_schema_lint.py` — 4 negative-case tests pass.)
result: pass

### 8. Secret redaction in structured logs
expected: |
  Any log field matching the denylist (authorization, x-trino-extra-credentials,
  cookie, token, password, api_key, apikey, bearer, secret, ssl_password) or the
  `credential.*` pattern is hard-redacted to `[REDACTED]` — case-insensitive,
  recursive through nested dicts and lists. SecretStr values render as [REDACTED]
  regardless of key. (Covered by `tests/logging/test_redaction.py` — 11 tests.)
result: pass

### 9. README mcpServers JSON blocks present
expected: |
  `README.md` contains three fenced `json` code blocks under "Claude Code MCP
  configuration": stdio (command=mcp-trino-optimizer, args=[serve, --transport,
  stdio]), Streamable HTTP (url=http://127.0.0.1:8080/mcp with Authorization
  Bearer header), Docker (command=docker, args=[run, --rm, -i, ...]). Each block
  is valid JSON a user can copy straight into their Claude Code config.
result: pass

### 10. CONTRIBUTING.md has coding rules, DoD, validation workflow
expected: |
  `CONTRIBUTING.md` exists at repo root and contains four top-level sections:
  Coding rules (8 numbered rules), Definition of Done (checklist), Validation
  workflow (pre-commit + CI matrix + phase gates), Safe-execution boundaries
  (4 invariants). References CLAUDE.md as the authoritative project-context doc.
result: pass

### 11. .env.example documents every MCPTO_ variable
expected: |
  `.env.example` at repo root documents MCPTO_TRANSPORT, MCPTO_HTTP_HOST,
  MCPTO_HTTP_PORT, MCPTO_HTTP_BEARER_TOKEN, MCPTO_LOG_LEVEL with safe placeholder
  values. The bearer token slot is `CHANGE_ME_GENERATE_WITH_OPENSSL_RAND_HEX_32`
  (not a real secret). Phase 2 Trino vars are listed as commented placeholders
  for future reference.
result: pass

### 12. Full automated test suite green
expected: |
  `uv run pytest -q` reports `61 passed, 0 skipped, 0 xfailed, 0 errors` in under
  10 seconds. `uv run mypy src/mcp_trino_optimizer/` is strict-clean on 16 source
  files. `uv run ruff check .` and `uv run ruff format --check .` both clean.
result: pass

### 13. PLAT-04: Docker build + stdio round-trip
expected: |
  `docker build --build-arg GIT_SHA=$(git rev-parse HEAD) -t mcpto:test .` builds
  cleanly on a Linux host using the multi-stage python:3.12-slim-bookworm base.
  `docker run --rm -i mcpto:test` starts the stdio transport as the non-root
  `mcp` user, and a JSON-RPC initialize round-trip works end-to-end inside the
  container. Verifier already confirmed the Dockerfile is structurally correct
  but can't drive Docker in this environment — human execution required.
result: pass
note: |
  Fixed Dockerfile: `UV_PROJECT_ENVIRONMENT=/opt/venv uv pip install` → 
  `uv pip install --python /opt/venv/bin/python` (UV_PROJECT_ENVIRONMENT is
  only valid for uv sync/project commands, not uv pip). Build completes cleanly;
  stdio initialize round-trip confirmed via docker run.

### 14. PLAT-13: GitHub Actions 9-cell matrix run
expected: |
  Push to `main` or open a PR. The `CI` workflow runs three jobs: lint-types
  (Linux/Python 3.12 — ruff format, ruff check, mypy --strict), unit-smoke
  (9 cells: ubuntu/macos/windows × Python 3.11/3.12/3.13), integration (stubbed).
  All 9 unit-smoke cells pass: pytest + stdio smoke + HTTP bearer smoke + CLI
  --help + both PLAT-01 install paths (pip install -e, uv tool install). No
  Windows shell/CRLF failures. Verifier can't drive Actions — human execution
  required.
result: pass
note: |
  Fixed two issues during UAT: bumped astral-sh/setup-uv v4→v5; removed
  explicit `uv venv` call (setup-uv@v5 auto-creates .venv, causing collision).
  Node.js 20 deprecation warning on actions/checkout@v4 is cosmetic — no v5
  exists yet; deadline is June 2026.

## Summary

total: 14
passed: 14
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps

[none yet]
