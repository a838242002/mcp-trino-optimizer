# Phase 1: Skeleton & Safety Foundation - Context

**Gathered:** 2026-04-11
**Status:** Ready for planning

<domain>
## Phase Boundary

Deliver a pip/uvx/Docker-installable MCP server that:
1. Starts on **stdio** and **Streamable HTTP** transports,
2. Answers JSON-RPC `initialize`,
3. Exposes a single tool — `mcp_selftest` — returning server version, transport, capabilities, and a round-trip echo,
4. Enforces every day-one safety primitive (stdout discipline, redaction, untrusted-content envelope, strict JSON Schema posture) **before a single Trino-touching line of code lands**.

Covers PLAT-01 through PLAT-13. No Trino adapter code, no ports/adapters scaffolding beyond what ships, no rules, no rewrites, no live queries. This phase is pure infrastructure + safety primitives.

**Not in this phase (belongs elsewhere):** Trino HTTP REST client, hexagonal ports (`PlanSource`/`StatsSource`/`CatalogSource`), TLS fields in Settings, rule engine, SQL parser, plan parser, catalog support, docker-compose integration harness beyond what's needed for `testcontainers` in later phases.

</domain>

<decisions>
## Implementation Decisions

### Project Layout & Module Topology
- **D-01 (src-layout):** Package lives at `src/mcp_trino_optimizer/`. Hatchling build backend, `uv` manages virtualenv, `pyproject.toml` is authoritative. PyPI name `mcp-trino-optimizer`, module name `mcp_trino_optimizer`.
- **D-02 (flat top-level modules):** Inside the package, top-level modules are flat (no `core/` nesting):
  - `cli.py` — Typer entry point (`mcp-trino-optimizer serve --transport ...`)
  - `app.py` — `FastMCP` instance construction and tool auto-registration
  - `settings.py` — `pydantic-settings` `Settings` model
  - `logging_setup.py` — `structlog` configuration (stderr-only, denylist redaction, SecretStr rendering)
  - `transports.py` — stdio + Streamable HTTP entry glue, stdout guard install
  - `safety/` — subpackage: `envelope.py` (`wrap_untrusted()`), `schema_lint.py` (runtime + CI shared assertion), `stdout_guard.py`
  - `tools/` — subpackage: `__init__.py` auto-registers sibling modules, `selftest.py` exports `mcp_selftest`
- **D-03 (no ports in Phase 1):** `ports/` subpackage, `PlanSource`/`StatsSource`/`CatalogSource` Protocol stubs, and any Trino-adapter scaffolding are **deferred to Phase 2** when the first real adapter lands. Phase 1 must not ship empty Protocol stubs.
- **D-04 (tool auto-registration):** `tools/__init__.py` imports every sibling module in `tools/` and each module registers its handlers via `mcp.tool(...)`. Adding a new tool in a later phase is a new file in `tools/`; nothing else changes. Phase 1 ships exactly one tool file: `tools/selftest.py`.

### Config & Secrets Sourcing
- **D-05 (env + .env + defaults):** Config precedence is **OS env > `.env` file > defaults**. `pydantic-settings` `Settings` model with `env_file=".env"`. No TOML/YAML config file. `.env.example` is committed to the repo; `.env` is git-ignored.
- **D-06 (MCPTO_ env prefix):** All settings use the `MCPTO_` env prefix via `env_prefix="MCPTO_"`. Examples: `MCPTO_TRANSPORT`, `MCPTO_HTTP_HOST`, `MCPTO_HTTP_PORT`, `MCPTO_HTTP_BEARER_TOKEN`, `MCPTO_LOG_LEVEL`.
- **D-07 (bearer token, explicit-only):** `MCPTO_HTTP_BEARER_TOKEN` is typed `SecretStr`, has **no default**, and is **required only when `--transport http` is selected**. If the HTTP transport starts without a bearer token set, the server fails fast with a structured stderr error and exits non-zero. No autogen fallback. No config-file fallback. No default token.
- **D-08 (fail fast on invalid/missing required settings):** Any required-but-missing or invalid setting prints one structured JSON error line to stderr and exits non-zero **before** the transport starts. No partial startup, no warnings for required fields.
- **Phase 1 Settings surface (minimum):** `transport` (Literal[`stdio`,`http`]), `http_host` (default `127.0.0.1`), `http_port` (default `8080`), `http_bearer_token` (SecretStr, no default), `log_level` (Literal[`DEBUG`,`INFO`,`WARNING`,`ERROR`], default `INFO`). Trino-side settings (host, port, auth, TLS verify, CA bundle, etc.) **defer to Phase 2**.

### Safety Primitives
- **D-09 (redaction = denylist + SecretStr rendering):** A structlog processor drops any dict key matching the denylist `{authorization, x-trino-extra-credentials, cookie, token, password, api_key, apikey, bearer, secret, ssl_password}` (case-insensitive), plus any key matching the pattern `credential.*`, replacing the value with `[REDACTED]`. Additionally, any value of type `pydantic.SecretStr` renders as `[REDACTED]` regardless of key. Denylist is defined in `logging_setup.py` as a module-level constant and is unit-tested.
- **D-10 (`wrap_untrusted()` = pure JSON envelope):** `safety.envelope.wrap_untrusted(content: str) -> dict[str, str]` returns exactly `{"source": "untrusted", "content": content}`. No textual delimiters, no nested markers, no escaping. Callers serialize the dict as part of their tool response. The helper is unit-tested from day one, and the selftest tool exercises it (even though selftest itself returns only trusted content) via a dedicated test case.
- **D-11 (schema-lint = runtime guard + CI test):** A single `safety.schema_lint.assert_tools_compliant(mcp)` function asserts every registered tool's JSON Schema has:
  - `additionalProperties: false`
  - Every `string` field has a bounded `maxLength` (default SQL cap: 100_000 bytes)
  - Every identifier-shaped field has a `pattern` regex
  - Every `array` field has a bounded `maxItems`
  Called automatically by `app.py` at startup immediately after tool registration — raises `SchemaLintError` that crashes the server if any tool is non-compliant. **Also** called from a pytest test in CI that constructs the MCP app and runs the same assertion, so regressions are caught on PR before any container ever starts.
- **D-12 (stdout discipline, belt + suspenders):** Three independent layers enforce "stdout belongs to JSON-RPC":
  1. `logging_setup.py` configures `structlog` to write **only to `sys.stderr`** via a stream handler bound explicitly at module init. No `stdout` handlers ever.
  2. In stdio mode, `transports.py` installs `safety.stdout_guard.install_stdout_guard()` at entrypoint, which replaces `sys.stdout` with a sentinel sink. Any write that is not a valid JSON-RPC framed line is captured, logged to stderr as a `stdout_violation` error event with the offending bytes, and dropped. (The guard distinguishes the FastMCP framing writes from stray writes; exact mechanism is an implementation detail for the planner, but the behavior contract is: stray bytes never reach the wire.)
  3. A pytest test spawns the server in stdio mode, sends a valid `initialize` frame, and asserts that **every byte** on stdout parses as a JSON-RPC message. Run on all 9 matrix cells.

### CLAUDE.md, CLI, and CI Matrix
- **D-13 (CLAUDE.md + CONTRIBUTING.md split):** Keep `CLAUDE.md` at the repo root focused on tech stack, constraints, and project context (as it already is). Create a **new `CONTRIBUTING.md`** at the repo root for dev-facing content:
  - **Coding rules:** ruff enabled rule sets, mypy strict, no `print()`, no regex-based SQL rewrites, allowlist-based logging fields where applicable, read-only-by-construction guarantee
  - **Definition of Done:** unit tests pass, ruff + mypy pass, stdout-clean `initialize` smoke test passes on the current OS/Python, `mcp_selftest` tool round-trip passes
  - **Validation workflow:** pre-commit hooks (ruff format, ruff check, forbidden-SQL grep, secret lint), CI pipeline stages
  - **Safe-execution boundaries:** `SqlClassifier` invariants (Phase 2 will populate), untrusted envelope rule, schema-lint rule
  Both files are considered "project rules" for GSD — planners and executors must read both.
- **D-14 (CI matrix shape):** GitHub Actions, three jobs:
  1. **`lint-types`** — one cell: Linux, Python 3.12. Runs `ruff check`, `ruff format --check`, `mypy --strict`.
  2. **`unit-smoke`** — full matrix: 3 OS (`ubuntu-latest`, `macos-latest`, `windows-latest`) × 3 Python (`3.11`, `3.12`, `3.13`) = 9 cells. Runs `pytest -m "not integration"`, the stdout-clean `initialize` smoke test, and the `mcp_selftest` round-trip test.
  3. **`integration`** — reserved for Phase 2+ (Linux-only via `testcontainers`). **Not shipped in Phase 1** but the job stub with `if: false` is left in the workflow file so later phases can just flip the flag.
  PLAT-13 is satisfied by `unit-smoke` running on the 9-cell matrix.
- **D-15 (CLI subcommand shape):** `mcp-trino-optimizer` entry point is a Typer app. Single subcommand in Phase 1: `serve`. Options: `--transport [stdio|http]` (default `stdio`), `--host` (default `127.0.0.1`), `--port` (default `8080`), `--log-level [DEBUG|INFO|WARNING|ERROR]` (default `INFO`). CLI flags take precedence over env vars (pydantic-settings init-kwargs > env > .env > defaults). Future subcommands (e.g., `doctor`, `config`) can be added as siblings without restructuring.

### Claude's Discretion
The planner may make concrete choices on the following without re-asking:
- Exact structure of the `safety/stdout_guard.py` implementation (e.g., replace `sys.stdout` vs `os.dup2` vs custom writer wrapper) — must honor D-12 behavior contract.
- Exact return shape of `mcp_selftest` beyond the mandatory fields in Success Criterion 1 (server version, transport name, round-trip echo). Suggested additions: `python_version`, `git_sha`, `package_version`, `capabilities` (list of enabled FastMCP capabilities), `log_level`, `started_at` ISO8601. Planner decides which are in v1.
- Pre-commit hook specifics (which ruff rules, whether to include `gitleaks`, whether to include a stdout-greppable forbidden-SQL check). Must include at minimum: ruff format, ruff check, mypy.
- `.env.example` exact contents (field list + comments).
- Logging output schema beyond the PLAT-06 mandatory keys (`request_id`, `tool_name`, `git_sha`, `package_version`, ISO8601 UTC `timestamp`). Planner may add `level`, `event`, `duration_ms`, `error_type`, etc.
- How `git_sha` is injected at build time (hatch version plugin, env var, runtime `git rev-parse`). Must not fail if run outside a git checkout (e.g., from a wheel install) — fallback to `"unknown"`.
- Whether the `integration` CI job stub is committed with `if: false` or simply omitted. Either is acceptable as long as Phase 2 does not need to redesign the workflow.
- Exact `pyproject.toml` tool config sections (`[tool.ruff]`, `[tool.mypy]`, `[tool.pytest.ini_options]`) — follow conventional defaults.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents (researcher, planner, executor, checker) MUST read these before acting.**

### Project Truth
- `CLAUDE.md` — project instructions, tech stack (load-bearing, contains prescriptive version pins)
- `.planning/PROJECT.md` — vision, core value, constraints, key decisions table
- `.planning/REQUIREMENTS.md` §PLAT-01..PLAT-13 — the 13 requirements this phase must deliver
- `.planning/ROADMAP.md` — Phase 1 section (Success Criteria 1–5 are the verification spine)
- `.planning/STATE.md` — Key Decisions 1–16 (non-negotiable project decisions locked at initialization)

### Research Corpus (load-bearing)
- `.planning/research/SUMMARY.md` §6.1 — Phase 1 safety pitfalls (this is THE spine of the safety criteria; every acceptance criterion traces back here)
- `.planning/research/STACK.md` — version pins, alternatives considered, what NOT to use
- `.planning/research/ARCHITECTURE.md` — hexagonal ports overview (for Phase 1, only the "safety-as-construction" principles apply; ports themselves are Phase 2)
- `.planning/research/PITFALLS.md` §7 (stdio stdout corruption), §ingredients on untrusted content envelope, §logging redaction — each pitfall cited here is a Phase 1 acceptance criterion
- `.planning/research/FEATURES.md` — for the `mcp_selftest` tool contract expectations (Phase 1 ships only this one feature-tool)

### External Specs Touched by Phase 1
- [MCP Transports Spec 2025-03-26](https://modelcontextprotocol.io/specification/2025-03-26/basic/transports) — stdio + Streamable HTTP contracts (not legacy SSE)
- [MCP Python SDK FastMCP docs](https://github.com/modelcontextprotocol/python-sdk) — tool/resource decorator patterns
- [pydantic-settings docs](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) — env source precedence, SecretStr rendering

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **None.** This is the first-code phase of the project. No existing Python code, no tests, no Docker assets. The repo currently contains only `.planning/` and root-level `CLAUDE.md`.

### Established Patterns
- **Planning/research corpus is the source of truth.** Every implementation choice in Phase 1 must be traceable to `.planning/` content. The planner should cite CLAUDE.md, research docs, and this CONTEXT.md in PLAN.md task descriptions so executors read the right files before acting.
- **Commits follow GSD conventions** (see `git log`): `docs(NN): ...` for doc commits, `feat(NN): ...` for code commits, with `NN` being the padded phase number. Phase 1 commits use `01`.

### Integration Points
- `pyproject.toml` — created by this phase, consumed by every downstream phase. Every later phase adds dependencies, tool sections, and pins. Phase 1 establishes the structure.
- `.env.example` + Settings model — created by this phase, extended by Phase 2 (Trino settings) and later phases (rule engine config, comparison config, etc.). The env prefix and precedence rules are load-bearing.
- `src/mcp_trino_optimizer/tools/` — created by this phase, every later phase adds a new file under here.
- `src/mcp_trino_optimizer/safety/` — created by this phase, `wrap_untrusted()` is called by every tool that echoes user content (starting Phase 2). The helper contract is load-bearing.
- `src/mcp_trino_optimizer/logging_setup.py` — created by this phase, the redaction denylist is extended by Phase 9 (compose hardening).
- `.github/workflows/ci.yml` — created by this phase, Phase 2 adds the `integration` job and Phase 9 adds release artifacts.

</code_context>

<specifics>
## Specific Ideas

- **Bearer token loading is explicit-only** (D-07). No autogen, no file fallback. A user who runs `mcp-trino-optimizer serve --transport http` without `MCPTO_HTTP_BEARER_TOKEN` set must see a structured JSON error on stderr and exit non-zero before the HTTP server binds a port. This is non-negotiable.
- **The `integration` CI job is reserved but not populated.** Phase 1 ships the `lint-types` and `unit-smoke` jobs. Phase 2+ fills in `integration`. Do not write any `testcontainers` code in Phase 1.
- **`wrap_untrusted()` gets unit test coverage from day one** even though Phase 1's only tool (`mcp_selftest`) returns trusted content. This ensures the helper contract is locked before Phase 2 tools (which echo user SQL and Trino error messages) start calling it.
- **Phase 1 adds CONTRIBUTING.md** at the repo root. This is a new file, not an extension to CLAUDE.md. Both files must be listed in the GSD "project instructions" search path for future phases (both will be read by the planner/executor).
- **Stdout guard is a behavior contract, not an API contract.** The planner/executor may choose the implementation (replace `sys.stdout`, wrap with a custom writer, use `os.dup2`, etc.) but must deliver the behavior in D-12.
- **`git_sha` in log output must not fail for wheel installs.** If `git rev-parse` isn't available or the install directory isn't a git checkout, fall back to `"unknown"` (or the value baked in at build time by a hatch plugin). Never raise.

</specifics>

<deferred>
## Deferred Ideas

- **Hexagonal ports (`PlanSource`, `StatsSource`, `CatalogSource`):** Phase 2, when the first Trino adapter lands.
- **Trino HTTP REST client and adapter:** Phase 2.
- **TLS / SSL verify / CA bundle settings for Trino API** (raised during discussion): Phase 2, when the Trino adapter is wired. Phase 1 Settings intentionally does **not** include these fields. Phase 2 must add:
  - `MCPTO_TRINO_VERIFY_SSL: bool = True` (secure default; explicit opt-out only)
  - `MCPTO_TRINO_CA_BUNDLE: Path | None = None` (custom CA path for private PKIs)
  - Both plumbed through to the `httpx` client / trino-python-client session
- **Basic + JWT authentication for Trino:** Phase 2.
- **Rule engine, plan parser, rewrite engine, comparison engine, resources, prompts, catalog support:** later phases per ROADMAP.
- **`docker-compose.yml` for the Trino + Lakekeeper + MinIO + Postgres local stack:** Phase 9 (compose hardening). Phase 1's Docker work is limited to the single-image `Dockerfile` that runs the MCP server in stdio or HTTP mode.
- **Release tagging / wheel publishing / GitHub releases / PyPI trusted publishing:** later phase, not Phase 1. Phase 1 only needs the package to be `pip install`-able from source and buildable into a wheel.
- **`pre-commit` config specifics beyond "it exists and runs ruff + mypy":** planner's discretion within D-13.

</deferred>

---

*Phase: 01-skeleton-safety-foundation*
*Context gathered: 2026-04-11 via /gsd-discuss-phase*
