---
phase: 1
slug: skeleton-safety-foundation
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-11
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Source: `01-RESEARCH.md` §16 Validation Architecture.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | `pytest` 8.3+, `pytest-asyncio` 1.3.0+, `syrupy` 5.1.0+ |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` (`asyncio_mode = "auto"`) — installed by Wave 0 |
| **Quick run command** | `uv run pytest -m "not integration" -x` |
| **Full suite command** | `uv run pytest -v` |
| **Estimated runtime** | ~15 seconds for the full Phase 1 suite (no Trino, no containers) |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest -m "not integration" -x`
- **After every plan wave:** Run `uv run pytest -v`
- **Before `/gsd-verify-work`:** Full suite must be green on the local cell AND the CI 9-cell `unit-smoke` matrix must be green
- **Max feedback latency:** 30 seconds (quick run), 90 seconds (full suite on slowest cell)

---

## Per-Task Verification Map

> Plan/Task IDs are finalized when the planner writes `PLAN.md` files; this table is the requirement → test contract the planner MUST honor when assigning `<automated>` verification blocks.

| Requirement | Behavior | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|-------------|----------|------------|-----------------|-----------|-------------------|-------------|--------|
| PLAT-01 | `pip install .` / `uv tool install .` / `uvx mcp-trino-optimizer` succeed | — | Installs via standard PEP 517 path, entry point resolvable | smoke (CI) | CI job `unit-smoke` install step | ❌ W0 | ⬜ pending |
| PLAT-02 | stdio transport starts and answers `initialize` | T-01-01 (stdout corruption DoS) | Valid JSON-RPC frames only | smoke | `uv run pytest tests/smoke/test_stdio_initialize.py` | ❌ W0 | ⬜ pending |
| PLAT-03 | HTTP transport starts, enforces bearer token | T-01-02 (missing auth) | `hmac.compare_digest`, fail-fast if token unset | integration-lite | `uv run pytest tests/smoke/test_http_bearer.py` | ❌ W0 | ⬜ pending |
| PLAT-04 | Docker image runs stdio by default | — | Multi-stage `python:3.12-slim-bookworm`; stdio default | manual + CI | `docker build -t mcpto:test . && docker run -i mcpto:test` | ❌ W0 | ⬜ pending |
| PLAT-05 | stdout contains ONLY valid JSON-RPC bytes after `initialize` | T-01-01 (stdout corruption DoS) | Three-layer stdout discipline (D-12) + SentinelWriter | smoke | `uv run pytest tests/smoke/test_stdio_initialize.py::test_stdio_initialize_produces_only_json_rpc_on_stdout` | ❌ W0 | ⬜ pending |
| PLAT-06 | Log lines carry `request_id`, `tool_name`, `git_sha`, `package_version`, ISO8601 UTC `timestamp` | T-01-03 (missing audit fields) | structlog pipeline with contextvars + TimeStamper | unit | `uv run pytest tests/logging/test_structured_fields.py` | ❌ W0 | ⬜ pending |
| PLAT-07 | `Authorization`, `X-Trino-Extra-Credentials`, `credential.*` values redacted; `SecretStr` → `[REDACTED]` | T-01-04 (secret leak in logs) | Denylist processor + SecretStr rendering (D-09) | unit | `uv run pytest tests/logging/test_redaction.py` | ❌ W0 | ⬜ pending |
| PLAT-08 | `pydantic-settings` precedence OS env > `.env` > defaults; fail-fast on missing `http_bearer_token` when `transport=http` (D-07) | T-01-02 (missing auth) | Structured JSON error to stderr + exit non-zero before transport binds | unit | `uv run pytest tests/test_settings.py` | ❌ W0 | ⬜ pending |
| PLAT-09 | `mcp_selftest` tool round-trip returns `server_version`, `transport`, `echo`, plus discretionary fields | — | Returns trusted content; exercises `wrap_untrusted()` via companion test | unit | `uv run pytest tests/tools/test_selftest.py` | ❌ W0 | ⬜ pending |
| PLAT-10 | `assert_tools_compliant(mcp)` passes on every registered tool at startup AND in CI | T-01-05 (prompt-injection via loose schema) | `additionalProperties: false`, `maxLength`, `pattern`, `maxItems` on all tools | unit | `uv run pytest tests/safety/test_schema_lint.py` | ❌ W0 | ⬜ pending |
| PLAT-11 | `wrap_untrusted(s)` returns exactly `{"source": "untrusted", "content": s}` | T-01-06 (indirect prompt injection) | Pure JSON envelope, no delimiters (D-10) | unit | `uv run pytest tests/safety/test_envelope.py` | ❌ W0 | ⬜ pending |
| PLAT-12 | README contains copy-pasteable `mcpServers` JSON for stdio, Streamable HTTP, and Docker; CLAUDE.md + CONTRIBUTING.md present | — | Doc test asserts required code blocks exist | docs | `uv run pytest tests/docs/test_readme_mcp_blocks.py` | ❌ W0 | ⬜ pending |
| PLAT-13 | CI `unit-smoke` job green on all 9 cells (3 OS × 3 Python) | — | GitHub Actions matrix with hard-pinned setup-python | CI | GitHub Actions `unit-smoke` job status | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Wave 0 installs the framework and creates stub test files BEFORE any production code lands so the planner's Wave 1+ tasks have `<automated>` verification hooks from the very first commit.

- [ ] `pyproject.toml` — `[project.optional-dependencies].dev` with `pytest>=8.3`, `pytest-asyncio>=1.3.0`, `syrupy>=5.1.0`, `mypy>=1.11`, `ruff>=0.15.10`
- [ ] `pyproject.toml` `[tool.pytest.ini_options]` — `asyncio_mode = "auto"`, `markers = ["integration: deferred to Phase 2"]`
- [ ] `tests/conftest.py` — shared fixtures: subprocess runner for stdio smoke, `monkeypatch` helpers for env vars, bearer-token fixture, structlog capture fixture
- [ ] `tests/smoke/test_stdio_initialize.py` — stubs for PLAT-02, PLAT-05 (subprocess-bytes-mode pattern per RESEARCH.md §15)
- [ ] `tests/smoke/test_http_bearer.py` — stubs for PLAT-03
- [ ] `tests/logging/test_structured_fields.py` — stubs for PLAT-06
- [ ] `tests/logging/test_redaction.py` — stubs for PLAT-07 (includes `SecretStr` + denylist + `credential.*` cases)
- [ ] `tests/test_settings.py` — stubs for PLAT-08, D-07 fail-fast, D-08 structured-error path
- [ ] `tests/tools/test_selftest.py` — stubs for PLAT-09
- [ ] `tests/safety/test_schema_lint.py` — stubs for PLAT-10 (including a deliberate "fake bad tool" case per RESEARCH.md §20 Q8)
- [ ] `tests/safety/test_envelope.py` — stubs for PLAT-11 (adversarial inputs: empty string, newline, already-JSON, huge string near `maxLength`)
- [ ] `tests/docs/test_readme_mcp_blocks.py` — stubs for PLAT-12
- [ ] Framework install: `uv add --dev pytest pytest-asyncio syrupy mypy ruff` (versions pinned via `pyproject.toml`)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Claude Code `mcpServers` block actually works end-to-end | PLAT-01, PLAT-12 | Requires a real Claude Code installation; can't be CI-mocked cleanly at phase gate | Install via `uv tool install .`; paste the README stdio block into `~/.claude.json`; restart Claude Code; call `mcp_selftest` tool; assert round-trip returns `server_version` and `transport: "stdio"` |
| Docker HTTP path with real bearer auth against a throwaway curl client | PLAT-03, PLAT-04 | Exercises the actual network path; CI covers unit-level bearer gate but not the full Docker + HTTP + bearer chain | `docker run -e MCPTO_HTTP_BEARER_TOKEN=$(openssl rand -hex 32) -p 8080:8080 mcpto:test serve --transport http`; curl with and without token; assert 200 vs 401 |

---

## Validation Sign-Off

- [ ] All 13 PLAT-IDs have `<automated>` verify OR explicit manual-only justification
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING test file references listed above
- [ ] No watch-mode flags (no `--watch`, no `pytest-watch`; CI and local both run one-shot)
- [ ] Feedback latency < 30s for quick run
- [ ] `nyquist_compliant: true` set in frontmatter when the planner has aligned PLAN.md `<automated>` blocks with this map

**Approval:** pending
