---
phase: 01-skeleton-safety-foundation
plan: 05
subsystem: infra
tags: [docker, readme, contributing, apache-license, env-example, gitattributes, docs]

requires:
  - phase: 01-04
    provides: "Working CLI entry point (mcp-trino-optimizer serve) for accurate README mcpServers JSON blocks"
provides:
  - "Dockerfile (multi-stage, python:3.12-slim-bookworm, non-root, GIT_SHA build-arg)"
  - ".dockerignore, .gitattributes (Windows CRLF safety), LICENSE (Apache 2.0), .env.example"
  - "Full README.md with four install paths and three mcpServers JSON blocks (stdio, Streamable HTTP, Docker)"
  - "CONTRIBUTING.md (coding rules, DoD, validation workflow, safe-execution boundaries per D-13)"
affects: [01-06, all future phases, external contributors]

tech-stack:
  added: []
  patterns:
    - "Multi-stage Dockerfile builds the venv in a builder stage and COPY --from'es it into a slim runtime stage"
    - "GIT_SHA build-arg injection into a baked _git_sha.txt resource that _resolve_git_sha reads as tier 2"
    - "Non-root mcp user (uid 1000) with --shell /usr/sbin/nologin"
    - "Default entrypoint mcp-trino-optimizer serve --transport stdio so the container is safe out of the box (no port bound)"
    - "Test readiness polling via _wait_for_port — retry TCP connect every 100ms for 5s — replaces unreliable time.sleep() for uvicorn startup"

key-files:
  created:
    - "Dockerfile"
    - ".dockerignore"
    - ".gitattributes"
    - "LICENSE (Apache 2.0 canonical text)"
    - ".env.example"
    - "CONTRIBUTING.md"
  modified:
    - "README.md (minimal placeholder → full PLAT-12 README)"
    - "tests/smoke/test_http_bearer.py (MCP Streamable HTTP Accept headers + _wait_for_port polling)"
    - "tests/docs/test_readme_mcp_blocks.py (xfail markers removed, HTTP test updated for url+headers shape)"

key-decisions:
  - "README HTTP block uses url + headers rather than the args-based shape the plan-01-01 stub test assumed. Rationale: Claude Code's MCP client configuration for Streamable HTTP uses a url field (documented in the MCP spec 2025-03-26). Updated test to match."
  - "Remove xfail markers on test_readme_mcp_blocks.py now that plan 01-05 ships the full README — these become real regression guards"
  - "_wait_for_port TCP-polling helper replaces time.sleep(0.5) for HTTP bearer tests; uvicorn's multi-second startup on first run was causing flaky ConnectError skips"
  - "Test_http_bearer passes MCP-required Accept: application/json, text/event-stream + Content-Type: application/json headers — without them the server correctly returns 406 Not Acceptable per spec 2025-03-26"
  - "Apache 2.0 LICENSE text is the full canonical text (201 lines) with 'Copyright 2026 mcp-trino-optimizer contributors' in the appendix"
  - ".env.example placeholder for MCPTO_HTTP_BEARER_TOKEN reads 'CHANGE_ME_GENERATE_WITH_OPENSSL_RAND_HEX_32' to make the 'no real secret in git history' rule visually obvious"

patterns-established:
  - "Test infrastructure: TCP-level _wait_for_port polling for subprocess HTTP servers"
  - "README-as-contract: docs tests grep for specific JSON patterns (command, url, transport, docker run) to prevent silent regressions"
  - "Project rules split: CLAUDE.md (project context) + CONTRIBUTING.md (contributor workflow) both authoritative per D-13"

requirements-completed:
  - PLAT-04
  - PLAT-12

duration: ~25min
completed: 2026-04-11
---

# Phase 01 Plan 05: Docker / Docs Summary

**Fully documented, Docker-buildable Phase 1 — multi-stage Dockerfile on python:3.12-slim-bookworm with non-root runtime + GIT_SHA build-arg bake, full README with four install paths and three mcpServers JSON blocks (stdio/HTTP/Docker), CONTRIBUTING.md with coding rules + DoD + safe-execution boundaries per D-13, Apache 2.0 LICENSE, .env.example, .gitattributes, .dockerignore. PLAT-04 and PLAT-12 closed. 61 tests pass (up from 54), 0 skipped.**

## Performance

- **Duration:** ~25 min
- **Completed:** 2026-04-11
- **Tasks:** 2 (packaging files + docs)
- **Files created:** 6 (Dockerfile, .dockerignore, .gitattributes, LICENSE, .env.example, CONTRIBUTING.md)
- **Files modified:** 3 (README.md expanded, test_http_bearer + test_readme_mcp_blocks cleanup)

## Accomplishments

- **Dockerfile** builds on python:3.12-slim-bookworm with uv in a multi-stage layout; non-root mcp user (uid 1000); stdio default entrypoint; `GIT_SHA` build-arg bakes into `_git_sha.txt` for `_resolve_git_sha` tier 2; HEALTHCHECK NONE (stdio has no useful healthcheck)
- **.dockerignore** excludes `.venv`, `.git`, `tests/`, `.planning/`, `.env`, `CLAUDE.md`, `CONTRIBUTING.md` from the build context
- **.gitattributes** forces LF on every text file type (py/json/yaml/sh/Dockerfile) and declares binary types — Windows CRLF can't corrupt JSON-RPC framing
- **LICENSE** is the full canonical Apache 2.0 text with the `Copyright 2026 mcp-trino-optimizer contributors` appendix line
- **.env.example** documents every MCPTO_* env var with safe placeholder values; bearer-token slot reads `CHANGE_ME_GENERATE_WITH_OPENSSL_RAND_HEX_32`
- **README.md** has four install paths (uv tool install, uvx, pip, docker pull) and three copy-pasteable `mcpServers` JSON blocks (stdio, Streamable HTTP with url+headers, Docker stdio) plus a configuration table and the Phase 1 safety-posture section
- **CONTRIBUTING.md** covers the D-13 surface: 8 coding rules, DoD checklist, CI validation workflow, 4 safe-execution boundaries, local development recipes, testing notes, and security reporting policy
- **test_http_bearer.py** fixes: Accept + Content-Type headers added for the MCP Streamable HTTP spec 2025-03-26 (was returning 406 Not Acceptable); `_wait_for_port` TCP-polling helper replaces `time.sleep(0.5)` so uvicorn multi-second startup no longer flakes the tests
- **test_readme_mcp_blocks.py** xfail markers removed — the tests are now real regression guards protecting the README from silent drift
- **Full test suite:** 61 passed, 0 skipped, 0 xfailed (up from 54/3/4)
- `uv run ruff check src/ tests/` clean; `uv run mypy src/mcp_trino_optimizer/` strict clean
- `uv run mcp-trino-optimizer serve --transport http --bearer-token ...` is now a fully documented, tested workflow end-to-end

## Task Commits

1. **Task 1: Dockerfile + .dockerignore + .gitattributes + LICENSE + .env.example** — `3e40286` (feat)
2. **Task 2: README + CONTRIBUTING + test fixups (HTTP spec headers, _wait_for_port, xfail removal)** — `e07d011` (feat)

## Files Created/Modified

- `Dockerfile` — multi-stage build with uv, non-root, stdio default entrypoint
- `.dockerignore` — excludes build-irrelevant + secret-sensitive paths
- `.gitattributes` — text=auto eol=lf with explicit overrides for py/json/yaml/sh/Dockerfile
- `LICENSE` — canonical Apache 2.0
- `.env.example` — every MCPTO_* var with placeholder values
- `README.md` — full PLAT-12 README with install paths, mcpServers JSON blocks, configuration table, safety posture
- `CONTRIBUTING.md` — D-13 contributor rules (coding + DoD + validation + safe-execution)
- `tests/smoke/test_http_bearer.py` — MCP spec headers + `_wait_for_port` polling
- `tests/docs/test_readme_mcp_blocks.py` — xfail removal + HTTP block test updated for url+headers

## Decisions Made

- **HTTP block uses url+headers shape, not args.** Matches Claude Code's Streamable HTTP client config and the MCP spec 2025-03-26. The plan-01-01 stub assumed args-based configuration; the test is now updated to detect either form.
- **MCP Streamable HTTP Accept header required.** Without `Accept: application/json, text/event-stream`, the server correctly returns 406 Not Acceptable (per spec). Test now sends both `Accept` and `Content-Type: application/json`.
- **TCP-level readiness polling over `time.sleep`.** Uvicorn's first-run startup can take 1–3 seconds on macOS/Python 3.14; `time.sleep(0.5)` was flakily skipping two tests. `_wait_for_port` retries every 100ms for 5s via `socket.create_connection`, which is both faster when the server is ready and robust against slow starts.
- **Xfail markers removed from README docs tests.** Plan 01-05 satisfies the contract; keeping `strict=False` xfail decorators would hide future regressions.
- **No test additions for Dockerfile.** PLAT-04 verification is currently by-inspection + the grep assertions in the acceptance criteria; actual `docker build` is deferred to plan 01-06's CI pipeline because running Docker in the execution environment is out of scope for this plan.

## Deviations from Plan

- **test_readme_mcp_blocks.py HTTP test logic update.** The plan-01-01 stub checked for `"http"` substring in `args` which doesn't match our real README's url+headers shape. Fixed by updating the detection logic — still a real regression guard, just matches the documented URL form.
- **Xfail markers removed.** Plan 01-05 shipping = time to make these real regression guards.

## Issues Encountered

- **`test_http_transport_accepts_correct_bearer_token` returned 406 Not Acceptable.** Root cause: MCP Streamable HTTP spec requires `Accept: application/json, text/event-stream`. Fix: add the headers (and matching `Content-Type`) in the test's httpx.post call.
- **Two HTTP tests flakily skipped with `ConnectError`.** Root cause: `time.sleep(0.5)` wasn't enough for uvicorn to bind. Fix: `_wait_for_port` TCP-polling helper.

## User Setup Required

None. All documentation is self-service via README + CONTRIBUTING + .env.example.

## Next Phase Readiness

- Plan 01-06 (CI/pre-commit) can reference the full test matrix with confidence: 61 passed, 0 skipped. The 9-cell install matrix workflow can run `pytest -m "not integration"` + `ruff check` + `mypy --strict` + `mcp-trino-optimizer --help` on every cell
- `docker build -t mcpto:test .` is ready to run in CI on Linux
- The three mcpServers JSON blocks are copy-pasteable; external contributors can drop them into `~/.claude.json` today

---
*Phase: 01-skeleton-safety-foundation*
*Plan: 05-docker-docs*
*Completed: 2026-04-11*
