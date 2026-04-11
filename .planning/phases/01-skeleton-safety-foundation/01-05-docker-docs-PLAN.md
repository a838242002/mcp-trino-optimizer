---
phase: 01-skeleton-safety-foundation
plan: 05
type: execute
wave: 3
depends_on:
  - 01-04-app-tools-transports-cli
files_modified:
  - Dockerfile
  - .dockerignore
  - README.md
  - CONTRIBUTING.md
  - .env.example
  - .gitattributes
  - LICENSE
autonomous: true
requirements:
  - PLAT-04
  - PLAT-12
must_haves:
  truths:
    - "docker build -t mcpto:test . builds cleanly on a Linux host using python:3.12-slim-bookworm"
    - "docker run -i mcpto:test starts the stdio transport by default"
    - "README.md contains copy-pasteable Claude Code mcpServers JSON blocks for stdio, Streamable HTTP, and Docker install paths (PLAT-12)"
    - "CONTRIBUTING.md at repo root defines coding rules, DoD, validation workflow, and safe-execution boundaries (D-13)"
    - ".env.example documents every MCPTO_ env var with a safe example value and never contains a real secret"
    - "The PLAT-12 README docs test (stubbed in plan 01-01) flips green after this plan lands"
  artifacts:
    - path: "Dockerfile"
      provides: "Multi-stage build on python:3.12-slim-bookworm with uv install"
      contains: "python:3.12-slim-bookworm"
    - path: ".dockerignore"
      provides: "Exclude .venv, .git, tests, __pycache__ from build context"
    - path: "README.md"
      provides: "Full project README with mcpServers JSON blocks for stdio, HTTP, Docker install paths"
      contains: "mcpServers"
    - path: "CONTRIBUTING.md"
      provides: "Dev-facing coding rules, DoD, validation workflow (D-13)"
      contains: "Definition of Done"
    - path: ".env.example"
      provides: "Documented env var list; never commits real secrets"
      contains: "MCPTO_"
    - path: "LICENSE"
      provides: "Apache-2.0 text"
      contains: "Apache License"
  key_links:
    - from: "Dockerfile"
      to: "pyproject.toml"
      via: "uv pip install --no-cache . from copied project files"
      pattern: "uv pip install"
    - from: "README.md"
      to: "pyproject.toml [project.scripts]"
      via: "Documented CLI entry point mcp-trino-optimizer"
      pattern: "mcp-trino-optimizer"
---

<objective>
Land the packaging and docs deliverables that make Phase 1 publicly usable: the Dockerfile (PLAT-04), the README with copy-pasteable Claude Code `mcpServers` JSON blocks (PLAT-12), CONTRIBUTING.md per D-13, .env.example documenting the MCPTO_ surface, .gitattributes for Windows CRLF safety, and the LICENSE file. This plan runs in Wave 3 after the app is fully wired; its only blocker on plan 01-04 is that the CLI entry point must actually work for the README's `mcpServers` JSON to be correct. No production Python code lands here.

Purpose: Make the server installable, documented, and usable by real Claude Code users. Close PLAT-04 and PLAT-12.
Output: Dockerfile that builds; README with three mcpServers JSON blocks; CONTRIBUTING.md; .env.example; LICENSE; .gitattributes. The PLAT-12 docs smoke test flips green.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/01-skeleton-safety-foundation/01-CONTEXT.md
@.planning/phases/01-skeleton-safety-foundation/01-RESEARCH.md
@CLAUDE.md
@pyproject.toml
@src/mcp_trino_optimizer/cli.py
@tests/docs/test_readme_mcp_blocks.py

<interfaces>
<!-- README mcpServers JSON blocks (copy-paste targets for Claude Code users).    -->
<!-- These are literally embedded in README.md fenced code blocks; the docs      -->
<!-- test (plan 01-01 stub) greps for the presence of command/args patterns.    -->

```json
// Stdio (local install via uv/pipx/pip)
{
  "mcpServers": {
    "trino-optimizer": {
      "command": "mcp-trino-optimizer",
      "args": ["serve", "--transport", "stdio"]
    }
  }
}

// Streamable HTTP
{
  "mcpServers": {
    "trino-optimizer": {
      "url": "http://127.0.0.1:8080/mcp",
      "transport": "http",
      "headers": { "Authorization": "Bearer YOUR_TOKEN_HERE" }
    }
  }
}

// Docker stdio
{
  "mcpServers": {
    "trino-optimizer": {
      "command": "docker",
      "args": ["run", "--rm", "-i", "mcp-trino-optimizer", "serve", "--transport", "stdio"]
    }
  }
}
```
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Write Dockerfile + .dockerignore + .gitattributes + LICENSE + .env.example</name>
  <files>Dockerfile, .dockerignore, .gitattributes, LICENSE, .env.example</files>
  <read_first>
    - /Users/allen/repo/mcp-trino-optimizer/.planning/phases/01-skeleton-safety-foundation/01-RESEARCH.md §13 (Dockerfile template — copy verbatim)
    - /Users/allen/repo/mcp-trino-optimizer/.planning/phases/01-skeleton-safety-foundation/01-RESEARCH.md §12.1 (Windows CRLF gotcha → .gitattributes)
    - /Users/allen/repo/mcp-trino-optimizer/.planning/phases/01-skeleton-safety-foundation/01-CONTEXT.md D-07 (bearer token — .env.example comments must NOT autogenerate), Claude's Discretion on .env.example contents
    - /Users/allen/repo/mcp-trino-optimizer/CLAUDE.md (alpine is FORBIDDEN; python:3.12-slim-bookworm mandatory)
  </read_first>
  <action>
    ### File 1: `Dockerfile`

    COPY RESEARCH.md §13 VERBATIM:

    ```dockerfile
    # Dockerfile
    # syntax=docker/dockerfile:1.7

    # ── Builder stage ───────────────────────────────────────────────
    FROM python:3.12-slim-bookworm AS builder

    # Install uv (Astral)
    COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

    WORKDIR /build

    # Copy only the files needed for dependency resolution
    COPY pyproject.toml README.md LICENSE ./
    COPY src/ ./src/

    # Install into a dedicated venv
    ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1
    RUN uv venv /opt/venv
    RUN UV_PROJECT_ENVIRONMENT=/opt/venv uv pip install --no-cache .

    # Bake git SHA if provided as build arg
    ARG GIT_SHA=unknown
    RUN echo "${GIT_SHA}" > /opt/venv/lib/python3.12/site-packages/mcp_trino_optimizer/_git_sha.txt

    # ── Runtime stage ───────────────────────────────────────────────
    FROM python:3.12-slim-bookworm AS runtime

    # Copy the installed venv from the builder
    COPY --from=builder /opt/venv /opt/venv
    ENV PATH="/opt/venv/bin:${PATH}"

    # Non-root user
    RUN useradd --system --uid 1000 --create-home --shell /usr/sbin/nologin mcp
    USER mcp
    WORKDIR /home/mcp

    # Log hygiene — force unbuffered stderr
    ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

    # Default: stdio transport
    ENTRYPOINT ["mcp-trino-optimizer", "serve"]
    CMD ["--transport", "stdio"]

    # Healthcheck is ONLY useful for HTTP mode; disabled by default.
    HEALTHCHECK NONE
    ```

    **Build-arg rationale:** `docker build --build-arg GIT_SHA=$(git rev-parse HEAD) -t mcp-trino-optimizer .` injects the SHA into the baked `_git_sha.txt`, which `_runtime._resolve_git_sha()` reads as tier 2 fallback.

    **Alpine is forbidden** per CLAUDE.md — orjson, pydantic-core, and uvicorn wheels are glibc-first; alpine forces slow source builds and bloated images.

    ### File 2: `.dockerignore`

    ```
    # Build artifacts
    .venv/
    dist/
    build/
    *.egg-info/

    # Cache
    __pycache__/
    *.pyc
    .pytest_cache/
    .mypy_cache/
    .ruff_cache/
    .coverage

    # Tests — not needed in runtime image
    tests/
    .planning/

    # Git + editor
    .git/
    .gitignore
    .gitattributes
    .github/
    .vscode/
    .idea/
    .DS_Store

    # Secrets (never copy into image)
    .env
    *.pem
    *.key

    # Docs not needed in runtime
    CONTRIBUTING.md
    CLAUDE.md
    ```

    ### File 3: `.gitattributes`

    Windows CRLF protection (RESEARCH.md §12.1) — critical because JSON-RPC framing uses `\n` and Windows git checkouts can corrupt test fixtures.

    ```
    # Default: auto-detect text and normalize to LF in the repo
    * text=auto eol=lf

    # Python source: always LF
    *.py text eol=lf

    # JSON / JSONL / YAML: LF (test fixtures may contain JSON-RPC frames)
    *.json text eol=lf
    *.jsonl text eol=lf
    *.yaml text eol=lf
    *.yml text eol=lf

    # Shell scripts: LF (so Linux containers can execute them)
    *.sh text eol=lf

    # Dockerfile: LF
    Dockerfile text eol=lf

    # Markdown: auto (LF in repo, but tolerate Windows editor)
    *.md text

    # Binary files: no conversion
    *.png binary
    *.jpg binary
    *.jpeg binary
    *.gif binary
    *.ico binary
    ```

    ### File 4: `LICENSE`

    Write the full Apache License 2.0 text. (The standard SPDX-licenses text at https://www.apache.org/licenses/LICENSE-2.0.txt — copy the canonical text verbatim, including the title block, terms and conditions sections 1-9, and the appendix. Do NOT put a custom copyright line — use `Copyright 2026 mcp-trino-optimizer contributors` in the `[yyyy] [name of copyright owner]` slot at the bottom.)

    Full text (abbreviated reference — insert the complete Apache 2.0 license):

    ```
                                     Apache License
                               Version 2.0, January 2004
                            http://www.apache.org/licenses/

       TERMS AND CONDITIONS FOR USE, REPRODUCTION, AND DISTRIBUTION

       1. Definitions.
    ... [full text of Apache 2.0, all 9 sections + appendix] ...

       APPENDIX: How to apply the Apache License to your work.
    ...
       Copyright 2026 mcp-trino-optimizer contributors

       Licensed under the Apache License, Version 2.0 (the "License");
       you may not use this file except in compliance with the License.
       You may obtain a copy of the License at

           http://www.apache.org/licenses/LICENSE-2.0
    ...
    ```

    Do NOT paraphrase. Write the exact Apache 2.0 license text from the canonical source — the pyproject.toml `license = "Apache-2.0"` declaration requires the literal text.

    ### File 5: `.env.example`

    Document every `MCPTO_*` env var with safe example values and comments. NEVER commit a real secret.

    ```
    # mcp-trino-optimizer — Environment Variable Reference
    # Copy this file to .env and fill in values.
    # .env is git-ignored; .env.example is committed.
    # Precedence: CLI flags > MCPTO_* env vars > .env file > defaults

    # ──────────────────────────────────────────────────────────────
    # Transport
    # ──────────────────────────────────────────────────────────────

    # Which MCP transport to serve on. One of: stdio, http
    # Default: stdio
    MCPTO_TRANSPORT=stdio

    # Bind address for Streamable HTTP transport.
    # Default: 127.0.0.1 (localhost only — safe default)
    # Set to 0.0.0.0 only if you are running behind a reverse proxy with TLS.
    MCPTO_HTTP_HOST=127.0.0.1

    # Port for Streamable HTTP transport. Valid range 1–65535.
    # Default: 8080
    MCPTO_HTTP_PORT=8080

    # Static bearer token for Streamable HTTP transport.
    # REQUIRED when MCPTO_TRANSPORT=http.
    # Generate a strong token with: openssl rand -hex 32
    # NEVER commit the real value. Use your secret manager.
    MCPTO_HTTP_BEARER_TOKEN=CHANGE_ME_GENERATE_WITH_OPENSSL_RAND_HEX_32

    # ──────────────────────────────────────────────────────────────
    # Logging
    # ──────────────────────────────────────────────────────────────

    # Logging level. One of: DEBUG, INFO, WARNING, ERROR
    # Default: INFO
    MCPTO_LOG_LEVEL=INFO

    # ──────────────────────────────────────────────────────────────
    # Build-time injection (optional; not read from .env in practice)
    # ──────────────────────────────────────────────────────────────

    # Git SHA baked in at build time (for observability).
    # Phase 1 falls back to runtime git rev-parse or "unknown".
    # MCPTO_GIT_SHA=abc123456789

    # ──────────────────────────────────────────────────────────────
    # Phase 2+ (Trino adapter) — NOT USED IN PHASE 1
    # ──────────────────────────────────────────────────────────────
    # These are intentionally omitted from Phase 1 and will be added
    # when the Trino adapter lands:
    #   MCPTO_TRINO_HOST
    #   MCPTO_TRINO_PORT
    #   MCPTO_TRINO_AUTH
    #   MCPTO_TRINO_VERIFY_SSL
    #   MCPTO_TRINO_CA_BUNDLE
    ```
  </action>
  <verify>
    <automated>cd /Users/allen/repo/mcp-trino-optimizer && test -f Dockerfile && test -f .dockerignore && test -f .gitattributes && test -f LICENSE && test -f .env.example && grep -c "python:3.12-slim-bookworm" Dockerfile && grep -c "MCPTO_HTTP_BEARER_TOKEN" .env.example && grep -c "Apache License" LICENSE</automated>
  </verify>
  <acceptance_criteria>
    - `test -f Dockerfile` exits 0
    - `grep -c "python:3.12-slim-bookworm" Dockerfile` returns at least `2` (builder + runtime stages)
    - `grep -c "alpine" Dockerfile` returns `0` (alpine is FORBIDDEN per CLAUDE.md)
    - `grep -c "uv pip install" Dockerfile` returns `1`
    - `grep -c "useradd" Dockerfile` returns `1` (non-root runtime user)
    - `grep -c 'ENTRYPOINT \["mcp-trino-optimizer"' Dockerfile` returns `1`
    - `grep -c "GIT_SHA" Dockerfile` returns at least `2` (ARG + RUN echo)
    - `grep -c "^\.env$" .dockerignore` returns `1`
    - `grep -c "^\.git/" .dockerignore` returns `1`
    - `grep -c "^tests/" .dockerignore` returns `1`
    - `grep -c "eol=lf" .gitattributes` returns at least `3`
    - `grep -c "\*\.json text eol=lf" .gitattributes` returns `1`
    - `grep -c "Apache License" LICENSE` returns at least `1`
    - `grep -c "Version 2.0, January 2004" LICENSE` returns `1`
    - `grep -c "MCPTO_TRANSPORT" .env.example` returns at least `1`
    - `grep -c "MCPTO_HTTP_BEARER_TOKEN" .env.example` returns at least `1`
    - `grep -c "MCPTO_HTTP_HOST" .env.example` returns at least `1`
    - `grep -c "MCPTO_LOG_LEVEL" .env.example` returns at least `1`
    - `.env.example` contains NO real secret (the bearer token slot says `CHANGE_ME_*`): `grep -c "CHANGE_ME" .env.example` returns `1`
  </acceptance_criteria>
  <done>Dockerfile builds on the python:3.12-slim-bookworm base, uses uv, runs as non-root, and sets stdio as the default; .dockerignore excludes .env and tests; .gitattributes enforces LF line endings on text files; LICENSE contains the full Apache 2.0 text; .env.example documents every MCPTO_ env var with safe example values.</done>
</task>

<task type="auto">
  <name>Task 2: Write README.md and CONTRIBUTING.md</name>
  <files>README.md, CONTRIBUTING.md</files>
  <read_first>
    - /Users/allen/repo/mcp-trino-optimizer/.planning/phases/01-skeleton-safety-foundation/01-RESEARCH.md §14 (CONTRIBUTING.md outline — copy verbatim)
    - /Users/allen/repo/mcp-trino-optimizer/.planning/phases/01-skeleton-safety-foundation/01-CONTEXT.md D-13 (CLAUDE.md + CONTRIBUTING.md split — both are project rules)
    - /Users/allen/repo/mcp-trino-optimizer/.planning/PROJECT.md (project description for README header) — if this file doesn't exist, synthesize from ROADMAP.md Phase 1 description
    - /Users/allen/repo/mcp-trino-optimizer/tests/docs/test_readme_mcp_blocks.py (the contract README must satisfy)
    - /Users/allen/repo/mcp-trino-optimizer/CLAUDE.md (reference in CONTRIBUTING.md)
  </read_first>
  <action>
    ### File 1: `README.md`

    Replace the minimal placeholder from plan 01-01 with the full README. Critical requirement: three fenced JSON code blocks containing `mcpServers` configurations for stdio, Streamable HTTP, and Docker install paths. The docs test (plan 01-01) greps for these patterns.

    ```markdown
    # mcp-trino-optimizer

    A Model Context Protocol (MCP) server that helps Claude Code (and other
    MCP-compatible clients) optimize Trino SQL queries running against Iceberg
    data lakes. Analyzes queries using `EXPLAIN` / `EXPLAIN ANALYZE` evidence,
    applies a deterministic rule engine to diagnose performance issues, suggests
    prioritized optimizations, and safely rewrites SQL while preserving
    semantics.

    Designed for data engineers, analytics engineers, and platform teams working
    with Trino + Iceberg.

    ## Status

    **Phase 1 — Skeleton & Safety Foundation.** The server boots on `stdio`
    and Streamable HTTP, answers `initialize`, and exposes a single tool:
    `mcp_selftest`. No Trino-touching code lands until Phase 2.

    ## Install

    ### uv tool install (recommended)

    ```bash
    uv tool install mcp-trino-optimizer
    mcp-trino-optimizer --help
    ```

    ### uvx (zero-install)

    ```bash
    uvx mcp-trino-optimizer serve
    ```

    ### pip

    ```bash
    pip install mcp-trino-optimizer
    mcp-trino-optimizer --help
    ```

    ### Docker

    ```bash
    docker pull mcp-trino-optimizer:latest
    docker run --rm -i mcp-trino-optimizer serve
    ```

    ## Claude Code MCP configuration

    Add one of the following blocks to your Claude Code `~/.claude.json` (or
    equivalent `mcpServers` config file) and restart Claude Code.

    ### Stdio (local install)

    ```json
    {
      "mcpServers": {
        "trino-optimizer": {
          "command": "mcp-trino-optimizer",
          "args": ["serve", "--transport", "stdio"]
        }
      }
    }
    ```

    ### Streamable HTTP (remote or self-hosted)

    The HTTP transport binds `127.0.0.1:8080` by default and requires a static
    bearer token. Generate a strong token first:

    ```bash
    openssl rand -hex 32
    ```

    Set the token via environment variable and start the server:

    ```bash
    MCPTO_HTTP_BEARER_TOKEN=<your-token> mcp-trino-optimizer serve --transport http
    ```

    Then configure Claude Code:

    ```json
    {
      "mcpServers": {
        "trino-optimizer": {
          "url": "http://127.0.0.1:8080/mcp",
          "transport": "http",
          "headers": {
            "Authorization": "Bearer YOUR_TOKEN_HERE"
          }
        }
      }
    }
    ```

    For production deployments put a reverse proxy (nginx, Caddy, Traefik) in
    front of the server for TLS termination.

    ### Docker (stdio)

    ```json
    {
      "mcpServers": {
        "trino-optimizer": {
          "command": "docker",
          "args": ["run", "--rm", "-i", "mcp-trino-optimizer", "serve", "--transport", "stdio"]
        }
      }
    }
    ```

    ## Self-test

    Once Claude Code connects, call the `mcp_selftest` tool:

    ```
    mcp_selftest(echo="hello")
    ```

    A healthy server returns `server_version`, `transport`, `echo`, `capabilities`,
    `python_version`, `package_version`, `git_sha`, `log_level`, and `started_at`.

    ## Configuration

    All configuration happens through `MCPTO_*` environment variables or a
    `.env` file. Precedence: CLI flags > OS env > `.env` > defaults.

    See [`.env.example`](./.env.example) for the full list.

    | Variable                    | Default       | Notes                                          |
    |----------------------------|---------------|------------------------------------------------|
    | `MCPTO_TRANSPORT`          | `stdio`       | `stdio` or `http`                              |
    | `MCPTO_HTTP_HOST`          | `127.0.0.1`   | Bind address (localhost only by default)       |
    | `MCPTO_HTTP_PORT`          | `8080`        | 1–65535                                        |
    | `MCPTO_HTTP_BEARER_TOKEN`  | *(required)*  | Required when `transport=http`. No default.    |
    | `MCPTO_LOG_LEVEL`          | `INFO`        | `DEBUG` / `INFO` / `WARNING` / `ERROR`         |

    ## Safety posture

    Phase 1 ships these day-one safety primitives before any Trino-touching code:

    - **stdout discipline** — `stdio` transport installs a sentinel writer on
      `sys.stdout` and duplicates the pristine fd for JSON-RPC framing. Any
      stray write is captured as a `stdout_violation` log event, not dropped.
    - **Structured logging to stderr only** — every log line is JSON with
      `request_id`, `tool_name`, `git_sha`, `package_version`, and ISO8601
      UTC timestamp. Logs never touch stdout.
    - **Secret redaction** — any log field matching the denylist
      (`authorization`, `x-trino-extra-credentials`, `cookie`, `token`,
      `password`, `api_key`, `apikey`, `bearer`, `secret`, `ssl_password`,
      or `credential.*`) is hard-redacted to `[REDACTED]`. `pydantic.SecretStr`
      values render as `[REDACTED]` regardless of the key they're stored under.
    - **Strict JSON Schema** — every tool input has
      `additionalProperties: false`, bounded `maxLength` on strings, bounded
      `maxItems` on arrays, and a `pattern` on identifier fields. A runtime
      schema-lint runs at startup and crashes the server before it binds a
      port if any tool is non-compliant.
    - **Untrusted-content envelope** — every tool response that echoes a
      user-origin string routes it through `wrap_untrusted()`, which returns
      `{"source": "untrusted", "content": "..."}`. MCP clients key off the
      `source` field to isolate content from instructions.
    - **Bearer token with constant-time compare** — the HTTP transport
      validates the `Authorization: Bearer <token>` header using
      `hmac.compare_digest`, and the token is never logged.

    ## Documentation

    - [`CONTRIBUTING.md`](./CONTRIBUTING.md) — coding rules, Definition of Done, validation workflow
    - [`CLAUDE.md`](./CLAUDE.md) — project context, technology stack, constraints
    - [`LICENSE`](./LICENSE) — Apache License 2.0

    ## License

    Apache-2.0
    ```

    ### File 2: `CONTRIBUTING.md`

    COPY RESEARCH.md §14 VERBATIM with minor tightenings. Full text:

    ```markdown
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

    Four invariants the server makes with its callers:

    1. **Read-only guarantee.** Every code path that reaches Trino routes
       through the `SqlClassifier` AST gate (Phase 2). The gate rejects
       `INSERT`, `UPDATE`, `DELETE`, `MERGE`, `DROP`, `CREATE`, `ALTER`,
       `TRUNCATE`, `CALL`, and multi-statement blocks — even when wrapped in
       comments or Unicode escapes.
    2. **Untrusted envelope rule.** Every tool response that includes a
       user-origin string wraps it in
       `{"source": "untrusted", "content": "..."}` via
       `safety.envelope.wrap_untrusted()`.
    3. **Schema-lint rule.** Every tool's input JSON Schema passes
       `safety.schema_lint.assert_tools_compliant` at startup (runtime guard)
       AND in CI (regression guard).
    4. **Stdout discipline.** Stdio mode installs `stdout_guard` before the
       transport starts; a CI smoke test asserts every byte on stdout is a
       valid JSON-RPC frame.

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
    ```

    Important: use this exact CONTRIBUTING.md structure so the docs test
    (`test_contributing_md_exists`) passes trivially AND the D-13 contract
    (coding rules, DoD, validation workflow, safe-execution boundaries) is
    satisfied.
  </action>
  <verify>
    <automated>cd /Users/allen/repo/mcp-trino-optimizer && uv run pytest tests/docs/test_readme_mcp_blocks.py -v && grep -c "mcpServers" README.md && grep -c "Definition of Done" CONTRIBUTING.md</automated>
  </verify>
  <acceptance_criteria>
    - `uv run pytest tests/docs/test_readme_mcp_blocks.py -v` — all tests pass (xfail strict=False means they flip to pass when README is correct)
    - `grep -c "mcpServers" README.md` returns at least `3` (one per install path)
    - `grep -c '"command": "mcp-trino-optimizer"' README.md` returns `1` (stdio block)
    - `grep -c '"--transport", "stdio"' README.md` returns at least `2` (stdio + docker blocks)
    - `grep -c "127.0.0.1:8080/mcp" README.md` returns `1` (HTTP block URL)
    - `grep -c 'Authorization": "Bearer' README.md` returns `1` (HTTP block header)
    - `grep -c "docker run" README.md` returns at least `2`
    - `grep -c "uv tool install" README.md` returns at least `1`
    - `grep -c "pip install" README.md` returns at least `1`
    - `grep -c "mcp_selftest" README.md` returns at least `1`
    - `grep -c "Definition of Done" CONTRIBUTING.md` returns `1`
    - `grep -c "Coding rules" CONTRIBUTING.md` returns at least `1`
    - `grep -c "Validation workflow" CONTRIBUTING.md` returns at least `1`
    - `grep -c "Safe-execution boundaries" CONTRIBUTING.md` returns at least `1`
    - `grep -c "ruff format" CONTRIBUTING.md` returns at least `1`
    - `grep -c "mypy" CONTRIBUTING.md` returns at least `1`
    - `grep -c "wrap_untrusted" CONTRIBUTING.md` returns at least `1`
    - `grep -c "stdout" CONTRIBUTING.md` returns at least `1`
  </acceptance_criteria>
  <done>README contains three copy-pasteable mcpServers JSON blocks (stdio, HTTP, Docker); CONTRIBUTING.md has coding rules, DoD, validation workflow, and safe-execution boundaries; the PLAT-12 docs test flips green.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Docker image → container runtime | Non-root user, no secret baked in, stdio default, slim-bookworm base |
| `.env.example` → git history | Committed with placeholder values only; never a real secret |
| README JSON examples → user copy-paste | Show `CHANGE_ME_HERE` / `YOUR_TOKEN_HERE` placeholders, never real tokens |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-01-04 | Info disclosure | Real secret committed in .env.example | mitigate | `.env.example` uses `CHANGE_ME_GENERATE_WITH_OPENSSL_RAND_HEX_32` placeholder; acceptance criterion greps for CHANGE_ME |
| T-01-07 | Elevation of priv | Docker image exposes a service on 0.0.0.0 by default | mitigate | Docker image default transport is stdio (no port bound); HTTP requires explicit `--transport http` flag AND bearer token; README documents reverse proxy recommendation |
| T-01-09 | Supply chain | Docker base image drift | accept | Pinned to `python:3.12-slim-bookworm` (major version pin); Phase 9 may switch to digest pin for release builds. Per CONTEXT.md this is acceptable for v1. |
</threat_model>

<verification>
Run `uv run pytest tests/docs/test_readme_mcp_blocks.py -v` — must pass. Manually inspect the Dockerfile and confirm no `alpine` references. Confirm LICENSE has the full Apache 2.0 text (several hundred lines). Verify .env.example contains no real secret.
</verification>

<success_criteria>
- Dockerfile builds on python:3.12-slim-bookworm with uv, uses non-root user, stdio default
- README contains three mcpServers JSON blocks (stdio, HTTP, Docker)
- CONTRIBUTING.md has coding rules, DoD, validation workflow, safe-execution boundaries
- .env.example documents every MCPTO_* var with placeholder values
- LICENSE is the full Apache 2.0 text
- .gitattributes enforces LF line endings for source/JSON/YAML files
- The PLAT-12 docs smoke test passes
</success_criteria>

<output>
After completion, create `.planning/phases/01-skeleton-safety-foundation/01-05-SUMMARY.md`
</output>
