# Stack Research

**Domain:** Python MCP server for Trino + Iceberg query analysis and optimization
**Researched:** 2026-04-11
**Overall confidence:** HIGH (all core versions verified against PyPI/official repos on research date; one MEDIUM item noted inline)

---

## TL;DR — Prescriptive Stack

- **Runtime:** Python 3.11+ (3.12 recommended for perf; 3.11 is the floor because PROJECT.md specifies it and is the lowest that the official MCP SDK supports cleanly).
- **MCP SDK:** `mcp[cli]>=1.27.0,<2` using the `FastMCP` high-level API, with `stdio` + `streamable-http` transports (NOT legacy HTTP+SSE).
- **Trino client:** `trino>=0.337.0` (official `trinodb/trino-python-client`) for the low-level REST client + JWT/Basic auth. Wrap it in our own async-friendly adapter (run sync calls via `anyio.to_thread`) because the library is sync-only.
- **SQL parsing/rewriting:** `sqlglot>=30.4.2` with `dialect="trino"`. This is the only correct choice — `sqlparse` is a tokenizer, `sqlfluff` is a linter.
- **Plan parsing:** Hand-rolled over `EXPLAIN (FORMAT JSON)`. No library exists; the JSON schema is public but undocumented as a contract, so we pin a tested range of Trino versions and build typed `pydantic` models from fixtures.
- **Config:** `pydantic-settings>=2.13.1` — declarative, typed, `.env` + env var, fail-fast. No `dynaconf`.
- **Logging:** `structlog>=25.5.0` with JSON renderer to stderr (MCP stdio uses stdout for protocol frames — logging to stdout will corrupt the channel). Use `orjson` as the renderer backend.
- **HTTP (for offline/REST catalog calls):** `httpx>=0.28.1` (sync + async). Use async client in the HTTP transport path.
- **Packaging:** `uv` + `pyproject.toml` + `hatchling` build backend + `[project.scripts]` entry point.
- **Lint/format:** `ruff>=0.15.10` (replaces black + isort + flake8 + pyupgrade).
- **Type check:** `mypy>=1.11` in CI (strict mode). Optional: `ty` (Astral) in watch mode for dev speed — still beta, do not gate CI on it.
- **Testing:** `pytest>=8` + `pytest-asyncio>=1.3.0` + `syrupy>=5.1.0` (snapshot) + `testcontainers[trino,minio]>=4.14.2` with `DockerCompose` for the full Trino+Iceberg+MinIO stack.
- **Docker:** multi-stage build on `python:3.12-slim-bookworm`, `uv`-driven install, final image runs stdio by default with `--transport http` flag to flip to Streamable HTTP.
- **Local integration stack:** Trino 480 + **Lakekeeper** (Rust REST catalog) + MinIO + PostgreSQL. Lakekeeper over Nessie/Polaris because it has the simplest docker-compose story and is explicitly integration-tested with Trino.

---

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended | Confidence |
|------------|---------|---------|-----------------|------------|
| Python | 3.11+ (3.12 ideal) | Runtime | Floor set by PROJECT.md; MCP SDK + sqlglot + pydantic 2 all target 3.11+; 3.12 gives faster startup + per-interpreter GIL improvements that matter for stdio cold-start | HIGH |
| `mcp` (Python SDK) | `>=1.27.0,<2` (1.27.0 released 2026-04-02) | Official MCP implementation: `FastMCP`, tool/resource/prompt decorators, stdio + streamable-http transports | Only supported path; project explicitly requires the official SDK. Pin `<2` because v2 is planned for Q1 and is not backward compatible | HIGH |
| `trino` (trino-python-client) | `>=0.337.0` (2026-03-06) | Low-level Trino REST client, DBAPI, auth classes (`BasicAuthentication`, `JWTAuthentication`) | Official client from `trinodb`. HTTP REST only — no JVM. Covers all required auth modes. Alternative (raw `httpx`) reimplements retries, statement polling, cursor lifecycle for zero gain | HIGH |
| `sqlglot` | `>=30.4.2` (2026-04-08) | SQL parser, AST, optimizer, transpiler, dedicated **Trino dialect** | The ONLY viable choice for semantic-aware rewrites. Has a first-class Trino dialect that extends Presto with JSON_QUERY/VALUE/LISTAGG. Zero dependencies. Used in production by Datafold, Tobiko, AWS | HIGH |
| `pydantic` | `>=2.9,<3` | Typed models for plan tree, rule findings, tool input/output schemas | MCP SDK already requires it. Gives us JSON Schema for free on every tool signature | HIGH |
| `pydantic-settings` | `>=2.13.1` (2026-02-19) | Config from env vars + `.env` + file, validated against a `Settings` model | Declarative, fail-fast, plays nicely with pydantic 2. `dynaconf` is more flexible but wrong-scoped for a single-process server with ~20 settings | HIGH |
| `httpx` | `>=0.28.1` | Async/sync HTTP client for offline-mode REST catalog probes and for the ASGI side of Streamable HTTP | Modern, HTTP/2 capable, identical sync + async API. `requests` is sync-only and not async-friendly | HIGH |
| `structlog` | `>=25.5.0` | Structured logging with processor pipeline and JSON output | Non-negotiable for a tool LLMs will invoke — every finding needs traceable structured evidence. `loguru` is simpler but less composable and does not give us first-class context binding | HIGH |
| `orjson` | `>=3.10` | Fast JSON serializer used by structlog's `JSONRenderer` and by us for plan dumps | 3-5x faster than stdlib `json`; matters when snapshotting large EXPLAIN ANALYZE outputs | HIGH |
| `anyio` | `>=4.4` | Async primitives; bridge sync Trino client into the async MCP handler via `anyio.to_thread.run_sync` | MCP SDK is async under the hood; this lets us not block the event loop on Trino HTTP polling | HIGH |

### Supporting Libraries

| Library | Version | Purpose | When to Use | Confidence |
|---------|---------|---------|-------------|------------|
| `click` or `typer` | `typer>=0.12` | CLI for `mcp-trino-optimizer serve --transport stdio|http --port 8080` | Needed for the `[project.scripts]` entry point. Typer is pydantic-friendly; click is more battle-tested — either works. Prefer `typer` for consistency with the pydantic-based stack | HIGH |
| `uvicorn` | `>=0.30` | ASGI server for Streamable HTTP transport | Required by `FastMCP.run(transport="streamable-http")` to actually serve HTTP; the SDK mounts an ASGI app and needs a server | HIGH |
| `tenacity` | `>=9.0` | Retry with backoff for Trino HTTP polling edge cases | Trino's stateful query protocol occasionally returns transient 503s — tenacity is the cleanest way to wrap them without reinventing retry logic | MEDIUM |
| `rich` | `>=13` | Pretty tables / diffs in the CLI and for the `rewrite_sql` human-readable output | Optional but cheap; `sqlglot.diff` pairs well with rich syntax highlighting | MEDIUM |

### Development Tools

| Tool | Version | Purpose | Notes | Confidence |
|------|---------|---------|-------|------------|
| `uv` | `>=0.5` | Package manager, virtualenv, lockfile (`uv.lock`), `uv run`, `uvx` install | 10-100x faster than pip. Native pyproject support. Lockfile is reproducible across platforms | HIGH |
| `hatchling` | `>=1.25` | Build backend | Modern PEP 517 backend. Simpler than setuptools, more standard than pdm-backend. Default when you `uv init --lib` | HIGH |
| `ruff` | `>=0.15.10` (2026-04-09) | Linter + formatter (replaces black, isort, flake8, pyupgrade, pydocstyle) | Enable `E,F,I,N,B,UP,SIM,RUF,ASYNC,PT` rule sets. Use `ruff format` in place of black | HIGH |
| `mypy` | `>=1.11` | Static type checker in strict mode | Battle-tested. Use `--strict` with per-module relaxations only where pragmatic. Keep as the CI gate | HIGH |
| `ty` (Astral) | beta | Fast type checker for dev loop | Optional. 10-60x faster than mypy but still beta as of Dec 2025. Do not depend on it in CI yet | MEDIUM |
| `pytest` | `>=8.3` | Test runner | Standard | HIGH |
| `pytest-asyncio` | `>=1.3.0` (2025-11-10) | Async test support for MCP handlers and httpx clients | v1.x is stable and recent. Use `asyncio_mode = "auto"` | HIGH |
| `syrupy` | `>=5.1.0` (2026-01-25) | Snapshot tests for plan parser output, rule findings, rewrite diffs | Snapshot testing is the right hammer for "parser produces structurally identical output for fixture X" | HIGH |
| `testcontainers[trino,minio]` | `>=4.14.2` (2026-03-18) | Docker container lifecycle for integration tests, including `DockerCompose` wrapper | Has a first-class Trino module + MinIO module + `DockerCompose` class that manages `docker-compose up/down` from pytest fixtures. Replaces `pytest-docker-compose` which is stale | HIGH |
| `pytest-cov` | `>=5` | Coverage | Standard | HIGH |
| `pre-commit` | `>=3.8` | Git hooks for ruff + mypy + forbidden-SQL grep | Enforces the read-only-by-construction rule at commit time | HIGH |

### Local Integration Stack (docker-compose)

| Service | Image / Version | Role | Why This Choice | Confidence |
|---------|-----------------|------|-----------------|------------|
| Trino | `trinodb/trino:480` | Query engine under test | Pin to a specific major version for plan-JSON shape stability. 480 is current at research time; track Trino's LTS cadence | HIGH |
| Lakekeeper | `quay.io/lakekeeper/catalog:latest-main` pinned by digest | Iceberg REST catalog | Apache-licensed, Rust, fast, **explicitly integration-tested with Trino**, has a published docker-compose example with Trino + MinIO + Postgres. Simpler surface area than Polaris (which needs a Docker + Gradle build) and less opinionated than Nessie (git semantics we don't need). Aligns with PROJECT.md Out-of-Scope for Nessie versioning | HIGH |
| PostgreSQL | `postgres:16-alpine` | Lakekeeper metadata backend | Required by Lakekeeper | HIGH |
| MinIO | `minio/minio:latest` (digest-pinned) | S3-compatible object store for Iceberg data files | Standard; every Trino+Iceberg example uses it | HIGH |
| MinIO client (mc) | init job | Creates the bucket, applies policies | Standard bootstrap pattern | HIGH |

**Polaris / Nessie tradeoff:** Polaris is Apache-incubating and is the "official" answer but is harder to dockerize (requires a Gradle build step in most public examples). Nessie adds git-like branching semantics the project explicitly marks out of scope. Pick Lakekeeper for v1; leave a hook to swap catalogs for integration runs against Polaris if a user requests it. (Confidence: MEDIUM on Lakekeeper-over-Polaris — reversible decision.)

---

## Installation

```bash
# Bootstrap the project
uv init --lib mcp-trino-optimizer
cd mcp-trino-optimizer

# Core runtime deps
uv add "mcp[cli]>=1.27.0,<2"
uv add "trino>=0.337.0"
uv add "sqlglot>=30.4.2"
uv add "pydantic>=2.9,<3"
uv add "pydantic-settings>=2.13.1"
uv add "httpx>=0.28.1"
uv add "structlog>=25.5.0" "orjson>=3.10"
uv add "anyio>=4.4"
uv add "uvicorn>=0.30"
uv add "typer>=0.12"
uv add "tenacity>=9.0"
uv add "rich>=13"

# Dev deps
uv add --dev "pytest>=8.3" "pytest-asyncio>=1.3.0" "pytest-cov>=5"
uv add --dev "syrupy>=5.1.0"
uv add --dev "testcontainers[trino,minio]>=4.14.2"
uv add --dev "ruff>=0.15.10" "mypy>=1.11"
uv add --dev "pre-commit>=3.8"

# Install the project itself as an editable CLI
uv sync
# The entry point, declared in pyproject.toml [project.scripts]:
# mcp-trino-optimizer = "mcp_trino_optimizer.cli:app"
uv run mcp-trino-optimizer serve --transport stdio
```

End-users install with:

```bash
# One-shot via uvx (no venv management)
uvx mcp-trino-optimizer serve --transport stdio

# Or pip
pip install mcp-trino-optimizer
```

---

## pyproject.toml skeleton

```toml
[build-system]
requires = ["hatchling>=1.25"]
build-backend = "hatchling.build"

[project]
name = "mcp-trino-optimizer"
version = "0.1.0"
description = "MCP server that analyzes and safely rewrites Trino SQL against Iceberg"
requires-python = ">=3.11"
dependencies = [
    "mcp[cli]>=1.27.0,<2",
    "trino>=0.337.0",
    "sqlglot>=30.4.2",
    "pydantic>=2.9,<3",
    "pydantic-settings>=2.13.1",
    "httpx>=0.28.1",
    "structlog>=25.5.0",
    "orjson>=3.10",
    "anyio>=4.4",
    "uvicorn>=0.30",
    "typer>=0.12",
    "tenacity>=9.0",
    "rich>=13",
]

[project.scripts]
mcp-trino-optimizer = "mcp_trino_optimizer.cli:app"

[tool.ruff]
target-version = "py311"
line-length = 100
[tool.ruff.lint]
select = ["E","F","I","N","B","UP","SIM","RUF","ASYNC","PT"]

[tool.mypy]
python_version = "3.11"
strict = true

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

---

## Transport Architecture (load-bearing)

The project requires **stdio AND remote HTTP** from day one. The correct mapping to the current MCP spec is:

- **stdio transport** — `mcp.run()` with no arg. Used by Claude Code / Claude Desktop. Critical gotcha: anything written to stdout other than JSON-RPC frames corrupts the channel. All logging must go to stderr. `structlog` is configured to write to `sys.stderr`.
- **Streamable HTTP transport** — `mcp.run(transport="streamable-http", host="0.0.0.0", port=8080)`. Uses a single `/mcp` endpoint, bidirectional, resumable. This is the current spec as of 2025-03-26 and is what Anthropic's Connectors Directory requires.
- **Do NOT use legacy HTTP+SSE** — deprecated in the 2025-03-26 MCP spec revision. Even though the SDK still has SSE helpers for backwards compatibility, new servers should not ship it. The project requirement says "HTTP/SSE" because SSE was current when the requirement was written — the correct modern implementation of that requirement is Streamable HTTP.

Expose the transport choice as a CLI flag:

```bash
mcp-trino-optimizer serve --transport stdio           # default, for Claude Code
mcp-trino-optimizer serve --transport http --port 8080
```

Confidence: HIGH on stdio + streamable-http; HIGH on SSE deprecation.

---

## Docker Image Shape

Multi-stage, slim base, final image 80–120 MB:

```dockerfile
# --- builder ---
FROM python:3.12-slim-bookworm AS builder
RUN pip install --no-cache-dir uv
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src/ ./src/
RUN uv sync --frozen --no-dev

# --- runtime ---
FROM python:3.12-slim-bookworm
WORKDIR /app
COPY --from=builder /app /app
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
# stdio by default; override to run HTTP
ENTRYPOINT ["mcp-trino-optimizer", "serve"]
CMD ["--transport", "stdio"]
EXPOSE 8080
```

Why `python:3.12-slim-bookworm`: smallest official image with a modern glibc and security updates; `alpine` breaks wheels for several pydantic/orjson transitive deps. Do NOT use alpine. Confidence: HIGH.

---

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| `trino-python-client` | Raw `httpx` against Trino `/v1/statement` | Never for v1. Only if we need to bypass the DBAPI cursor semantics to interleave cancellation with statement polling in a way the client does not support — revisit in milestone 2 if statement cancellation turns out to be flaky |
| `sqlglot` | `sqlfluff` | If the goal were *linting* user SQL for style. `sqlfluff` can fix style issues and has a Trino dialect, but its AST is not designed for semantic-preserving rewrites. Wrong tool for EXISTS→JOIN conversion |
| `sqlglot` | `sqlparse` | Never. `sqlparse` is a tokenizer, not a parser — it cannot build the AST needed for safe rewrites |
| `pydantic-settings` | `dynaconf` | If we needed multi-environment merged YAML/TOML config layers with secret backends. Overkill here; our config surface is <25 settings |
| `pydantic-settings` | stdlib `os.environ` + `argparse` | Only for throwaway scripts. We need typed validation because bad config silently breaks Trino auth |
| `structlog` | `loguru` | If we valued simplicity over machine-readable structured output. Loguru is single-logger, harder to inject request/tool context, and its JSON output is less controllable. Unsuitable for an LLM-facing server where every log line is evidence |
| `structlog` | stdlib `logging` + custom JSON formatter | Viable for minimal footprint but requires writing context binding, processor pipeline, and filtering ourselves. Not worth the ~200 LOC |
| `Lakekeeper` | `Apache Polaris` | When a user deploys Polaris in production and needs us to match it bit-for-bit. Add a second compose profile rather than switching the default |
| `Lakekeeper` | `Nessie` | When branching/versioning is required (explicitly out of scope for v1) |
| `mypy` (strict) | `pyright` | If we standardized on VS Code + Pylance as the primary editor. Mypy has broader ecosystem support and better plugin story. Pick mypy for CI; devs can run pyright locally |
| `mypy` | `ty` (Astral) | When ty exits beta and stabilizes plugin/stubs story. Track but do not depend on |
| `hatchling` | `setuptools` / `pdm-backend` / `poetry-core` | Setuptools is fine but has more boilerplate. Poetry adds a non-standard dep graph (don't mix with uv). PDM-backend is fine but hatchling is the most widely adopted |
| `testcontainers` `DockerCompose` | `pytest-docker-compose` | pytest-docker-compose is stale and has sparse recent releases. testcontainers is actively maintained |
| `testcontainers` `DockerCompose` | Raw `subprocess` calls to `docker compose` | Only for CI debug. Testcontainers handles teardown, port discovery, and wait strategies for us |
| Streamable HTTP transport | HTTP+SSE transport | Only when interoperating with a pre-2025-03-26 MCP client that has not migrated. Backwards-compat bridge only |

---

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| **JDBC driver / PyHive / JayDeBeApi** | Pulls JVM into the container; violates PROJECT.md constraint | `trino` (HTTP REST client) |
| **`sqlparse`** | Tokenizer, not a parser. Cannot build an AST, so cannot do semantic rewrites | `sqlglot` |
| **`sqlfluff` for rewrites** | Linter with an auto-fix mode; its IR is style-oriented not semantic | `sqlglot` |
| **`presto-python-client`** | Legacy, Presto-era fork. Dead relative to `trino-python-client` which is the maintained successor | `trino` |
| **`requests` library** | Sync-only, not async-friendly. Every modern Python HTTP project standardizes on httpx | `httpx` |
| **`loguru` for this project** | Global singleton logger, hard to inject structured context per MCP request | `structlog` |
| **`poetry`** | Non-standard lockfile format, slow, and mixing it with `uv` is a foot-gun | `uv` + `hatchling` |
| **`black`** | Ruff format is a drop-in and is 10x faster; maintaining both is wasted config | `ruff format` |
| **`flake8` / `isort` / `pyupgrade` / `pydocstyle`** | All superseded by ruff rules | `ruff` |
| **`alpine`-based Docker images** | Wheels for orjson/pydantic/httpx dependencies are glibc-first; alpine forces musl rebuilds and bloated images | `python:3.12-slim-bookworm` |
| **`pytest-docker-compose`** | Last meaningful release years old; effectively abandoned | `testcontainers[compose]` |
| **HTTP+SSE transport (legacy)** | Deprecated in MCP spec 2025-03-26; will be removed | Streamable HTTP transport |
| **`mcp` v2 pre-releases** | Project doc says v2 is breaking and Q1-targeted. Pin `<2` until we have time to migrate | `mcp>=1.27.0,<2` |
| **Hand-rolled Trino HTTP polling** | Reimplements cursor lifecycle, next-uri chaining, error mapping. High bug surface | Use the official `trino` client's DBAPI cursor |
| **`anthropic`/OpenAI SDKs inside the server** | The server is an MCP provider, not an LLM client. Adding a model vendor dependency is wrong-scope | None; the MCP client brings its own model |
| **Writing EXPLAIN parser against string output** | Text EXPLAIN is unstable across versions and hard to parse | `EXPLAIN (FORMAT JSON)` + hand-rolled pydantic models |

---

## Stack Patterns by Variant

**If the MCP client is Claude Code or Claude Desktop (local):**
- Use stdio transport
- All logs to stderr, never stdout
- Config via env vars set in the client's MCP server config JSON

**If the MCP server runs remote / hosted:**
- Use Streamable HTTP transport on port 8080
- Bearer token auth on the Trino side (JWT)
- Run behind a reverse proxy (nginx/Caddy) for TLS — out of scope for the server itself

**If a user runs in "offline mode" with pasted EXPLAIN JSON:**
- No Trino client instantiated
- No network calls except reading input
- Same rule engine and rewrite engine path — the difference is purely that plan JSON comes from tool input rather than from a live `EXPLAIN` call

**If the test environment is CI without Docker:**
- Fall back to fixture-only tests (unit tests against stored `EXPLAIN (FORMAT JSON)` fixtures)
- Skip the `testcontainers`-marked integration tests via `pytest.mark.integration`

---

## Version Compatibility

| Package A | Compatible With | Notes |
|-----------|-----------------|-------|
| `mcp>=1.27.0,<2` | `pydantic>=2.9,<3` | MCP SDK depends on pydantic 2 |
| `mcp>=1.27.0,<2` | `anyio>=4` | The SDK is async-first on anyio |
| `trino>=0.337.0` | Trino server 400–480+ | Client is generally forward-compatible; pin a test matrix in CI |
| `sqlglot>=30.4.2` | Trino server 400–480+ | Dialect is maintained against current Trino; lags ~1–2 releases for new functions |
| `testcontainers>=4.14.2` | Docker Engine 20.10+ | DockerCompose class uses the Compose v2 plugin; ensure `docker compose` (space) is installed, not the legacy `docker-compose` binary |
| `ruff>=0.15.10` | Any Python 3.11+ | Ruff is independent of the target Python version |
| `pydantic-settings>=2.13` | `pydantic>=2.7` | Keep them bumped together |
| `python:3.12-slim-bookworm` | `orjson>=3.10`, `pydantic-core` wheels | All have `manylinux` wheels for glibc; alpine would force source builds |

---

## Reversible vs Load-Bearing Choices

**Load-bearing (changing these later means a rewrite):**
- Python 3.11+ (everything assumes modern typing)
- Official MCP SDK (there is no alternative)
- `sqlglot` (the rewrite engine is built on its AST)
- `pydantic` v2 models for plan tree and findings (touches every rule and every tool schema)
- `stdio + streamable-http` transports (shapes the CLI and the Docker entrypoint)
- HTTP REST Trino client (no JDBC) — constitutional constraint from PROJECT.md

**Reversible (can swap without major rewrite):**
- `structlog` → another structured logger (logging calls are centralized)
- `pydantic-settings` → stdlib or dynaconf (only the `Settings` class touches it)
- Lakekeeper → Polaris or Nessie in docker-compose (only changes integration tests, not production code)
- `typer` → `click` (only the CLI module)
- `testcontainers` → raw docker compose subprocess (only test fixtures)
- `mypy` → `pyright` → `ty` (type annotations themselves are portable)
- `ruff` config (rules tunable any time)

---

## Confidence Summary

| Area | Confidence | Reason |
|------|------------|--------|
| MCP SDK choice + version + transports | HIGH | Verified PyPI 1.27.0 (2026-04-02); SSE-deprecation verified in spec changelog |
| Trino client | HIGH | Verified PyPI 0.337.0 (2026-03-06); official maintainer; auth modes confirmed in docs |
| sqlglot | HIGH | Verified PyPI 30.4.2 (2026-04-08); dedicated Trino dialect confirmed |
| Plan parsing strategy (hand-rolled) | HIGH | Multiple searches confirm no library exists; correct answer is pydantic models over fixtures |
| Config (pydantic-settings) | HIGH | Verified 2.13.1 (2026-02-19); aligns with pydantic 2 ecosystem |
| Logging (structlog + orjson + stderr) | HIGH | Verified 25.5.0; stdio stdout-corruption gotcha is well-documented |
| Testing stack | HIGH | testcontainers 4.14.2 (2026-03-18) has Trino + MinIO modules and DockerCompose class |
| Lakekeeper vs Polaris/Nessie | MEDIUM | Lakekeeper has the cleanest docker-compose story, but Polaris is gaining Apache-official status. Reversible decision — revisit at milestone 2 |
| Docker base image | HIGH | slim-bookworm is the universal answer for Python+native-wheel stacks |
| Packaging (uv + hatchling) | HIGH | Current default and fastest |
| Lint/format (ruff) | HIGH | Verified 0.15.10 (2026-04-09); dominant choice |
| Type check (mypy as gate, ty for dev) | HIGH | ty is still beta; mypy strict is the safe CI gate |

---

## Sources

**Official documentation and registries (HIGH confidence):**
- [mcp · PyPI](https://pypi.org/project/mcp/) — v1.27.0 (2026-04-02); transports list
- [modelcontextprotocol/python-sdk on GitHub](https://github.com/modelcontextprotocol/python-sdk) — FastMCP patterns for tools/resources/prompts
- [trino · PyPI](https://pypi.org/project/trino/) — v0.337.0 (2026-03-06); auth methods
- [sqlglot · PyPI](https://pypi.org/project/sqlglot/) — v30.4.2 (2026-04-08); Trino dialect
- [sqlglot Trino dialect docs](https://sqlglot.com/sqlglot/dialects/trino.html)
- [pydantic-settings · PyPI](https://pypi.org/project/pydantic-settings/) — v2.13.1 (2026-02-19)
- [ruff · PyPI](https://pypi.org/project/ruff/) — v0.15.10 (2026-04-09)
- [testcontainers · PyPI](https://pypi.org/project/testcontainers/) — v4.14.2 (2026-03-18)
- [pytest-asyncio · PyPI](https://pypi.org/project/pytest-asyncio/) — v1.3.0 (2025-11-10)
- [syrupy · PyPI](https://pypi.org/project/syrupy/) — v5.1.0 (2026-01-25)
- [sqlfluff · PyPI](https://pypi.org/project/sqlfluff/) — v4.1.0 (2026-03-26), documented as linter-not-rewriter
- [Trino 480 docs — Iceberg connector](https://trino.io/docs/current/connector/iceberg.html)
- [Trino 480 docs — JWT auth](https://trino.io/docs/current/security/jwt.html)
- [Lakekeeper on GitHub](https://github.com/lakekeeper/lakekeeper) — Apache-licensed REST catalog, Trino-tested
- [Testcontainers Trino module](https://testcontainers.com/modules/trino/)
- [MCP Transports Spec 2025-03-26](https://modelcontextprotocol.io/specification/2025-03-26/basic/transports)

**Analysis and decision context (MEDIUM confidence):**
- [Why MCP deprecated SSE and went with Streamable HTTP — fka.dev](https://blog.fka.dev/blog/2025-06-06-why-mcp-deprecated-sse-and-go-with-streamable-http/)
- [SSE vs Streamable HTTP — Bright Data](https://brightdata.com/blog/ai/sse-vs-streamable-http)
- [Pydantic BaseSettings vs Dynaconf — Leapcell](https://leapcell.io/blog/pydantic-basesettings-vs-dynaconf-a-modern-guide-to-application-configuration)
- [How mypy, pyright, and ty compare — pydevtools](https://pydevtools.com/handbook/explanation/how-do-mypy-pyright-and-ty-compare/)
- [ty — astral.sh](https://astral.sh/blog/ty) — beta status confirmation
- [Iceberg Catalogs 2025 — e6data](https://www.e6data.com/blog/iceberg-catalogs-2025-emerging-catalogs-modern-metadata-management) — Lakekeeper / Polaris / Nessie comparison

---
*Stack research for: Python MCP server for Trino + Iceberg query optimization*
*Researched: 2026-04-11*
