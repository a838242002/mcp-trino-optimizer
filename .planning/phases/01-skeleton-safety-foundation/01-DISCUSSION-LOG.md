# Phase 1: Skeleton & Safety Foundation - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in `01-CONTEXT.md` — this log preserves the alternatives considered.

**Date:** 2026-04-11
**Phase:** 01-skeleton-safety-foundation
**Areas discussed:** Project layout & module topology, Config & secrets sourcing, Safety primitives shape, CLAUDE.md DoD + CI matrix

---

## Project layout & module topology

### Q1 — Package layout style?

| Option | Description | Selected |
|--------|-------------|----------|
| src-layout (Recommended) | src/mcp_trino_optimizer/... — modern Python standard, prevents accidental imports from CWD, cleanly separates source from tests/tools. What hatchling + uv init lib defaults to. | ✓ |
| Flat layout | mcp_trino_optimizer/ at repo root. Simpler ls, but imports can resolve from CWD in dev and mask packaging bugs. | |

**User's choice:** src-layout

### Q2 — How should top-level modules be organized inside the package?

| Option | Description | Selected |
|--------|-------------|----------|
| Flat top-level (Recommended) | cli.py, app.py, settings.py, logging_setup.py, transports.py, safety/ (subpkg), tools/ (subpkg). ~9 files visible at the package root. Easy to navigate for a young codebase. | ✓ |
| Grouped under core/ | core/{app,settings,logging,transports}.py + safety/ + tools/. More structure but adds a level of indirection before any file exists. | |
| Hexagonal ports/adapters at top level | ports/, adapters/, app/, cli/, tools/. Mirrors research ARCHITECTURE.md terminology from day one. Heavier scaffolding for Phase 1 when Trino adapter doesn't exist yet. | |

**User's choice:** Flat top-level

### Q3 — Where should the hexagonal ports stubs live in Phase 1?

| Option | Description | Selected |
|--------|-------------|----------|
| Not in Phase 1 at all (Recommended) | Phase 1 is 'zero Trino-touching code.' Introduce ports in Phase 2 when the first adapter lands. Keeps Phase 1 small and avoids stubs that mask design drift. | ✓ |
| Empty Protocol stubs in ports/ | Create ports/plan_source.py etc. with typing.Protocol definitions only, no adapters. Signals architecture intent early; risks stale stubs. | |

**User's choice:** Not in Phase 1 at all

### Q4 — How should tool registration be wired?

| Option | Description | Selected |
|--------|-------------|----------|
| tools/ subpackage with auto-registration (Recommended) | tools/__init__.py imports and registers every sibling module on startup. Phase 1 ships tools/selftest.py. New tools later are just new files. | ✓ |
| Explicit registration in app.py | app.py imports and calls mcp.tool(...) on each handler by name. More explicit, but every new tool touches app.py. | |

**User's choice:** tools/ subpackage with auto-registration

---

## Config & secrets sourcing

### Q1 — How should config be sourced?

| Option | Description | Selected |
|--------|-------------|----------|
| Env + .env + defaults (Recommended) | Precedence: OS env > .env file > defaults. No separate config file format. Simplest surface. .env.example committed, .env gitignored. | ✓ |
| Env + TOML file + defaults | OS env > config.toml > defaults. More structured for multi-environment dev, but two formats to maintain. | |
| Env-only | No file loader at all. Simplest, but requires users to export every var or wrap in a shell script. | |

**User's choice:** Env + .env + defaults

### Q2 — Bearer token for Streamable HTTP transport — how is it sourced?

| Option | Description | Selected |
|--------|-------------|----------|
| Env var only: MCPTO_HTTP_BEARER_TOKEN as SecretStr (Recommended) | Required only when --transport http is used. Startup fails fast. No default, no file fallback, no autogen. | ✓ |
| Env var with autogen fallback | Generate a random token on first start if unset. Lower-friction dev but risks ephemeral-token deploys. | |
| Env var OR config file field | Allows operators to bake the token into deployment config. More flexible but expands secret surface. | |

**User's choice:** Env var only as SecretStr
**Notes:** User added: "1 is fine, but I also need to handle https protocol for trino API which must supports insecure verify ssl cert." This was captured as a follow-up: Phase 1 Settings model will NOT include Trino TLS fields (deferred to Phase 2), but the deferral is now explicit in CONTEXT.md `<deferred>` so Phase 2 must add `MCPTO_TRINO_VERIFY_SSL: bool = True` and `MCPTO_TRINO_CA_BUNDLE: Path | None = None` when the adapter lands.

### Q3 — Env var prefix / naming convention for all settings?

| Option | Description | Selected |
|--------|-------------|----------|
| MCPTO_ prefix (Recommended) | Short, unambiguous: MCPTO_TRANSPORT, MCPTO_HTTP_PORT, MCPTO_HTTP_BEARER_TOKEN. | ✓ |
| MCP_TRINO_OPTIMIZER_ prefix | Fully-qualified, no ambiguity, but verbose. | |
| No prefix | Use bare field names. Risk of collision. | |

**User's choice:** MCPTO_ prefix

### Q4 — Startup posture when required settings are missing or invalid?

| Option | Description | Selected |
|--------|-------------|----------|
| Fail fast with a structured error to stderr (Recommended) | Any required-but-missing or invalid setting prints a structured JSON error to stderr and exits non-zero BEFORE the transport starts. | ✓ |
| Warn and continue where possible | Missing optional settings warn; missing required ones still fail. | |

**User's choice:** Fail fast

---

## Safety primitives shape

### Q1 — Log redaction strategy?

| Option | Description | Selected |
|--------|-------------|----------|
| Denylist + SecretStr (Recommended) | structlog processor drops any key matching a denylist AND any SecretStr renders as [REDACTED]. Simpler mental model, matches PLAT-07 wording. | ✓ |
| Strict allowlist | Only explicitly allowlisted keys pass through. Safest but painful to extend. | |
| Both: denylist by default, allowlist for headers | General log dicts go through denylist; HTTP headers specifically go through an allowlist. Matches research PITFALLS §7. | |

**User's choice:** Denylist + SecretStr

### Q2 — wrap_untrusted() helper — what does it return?

| Option | Description | Selected |
|--------|-------------|----------|
| Pure JSON envelope (Recommended) | Returns {'source': 'untrusted', 'content': '<original>'} as a dict. | ✓ |
| JSON envelope + string delimiters | Returns {'source': 'untrusted', 'content': '<<<UNTRUSTED>>>\\n<string>\\n<<<END UNTRUSTED>>>'}. | |

**User's choice:** Pure JSON envelope

### Q3 — Schema-lint enforcement — where does it run?

| Option | Description | Selected |
|--------|-------------|----------|
| Both: runtime guard + CI test (Recommended) | Runtime guard at FastMCP startup + pytest test in CI. Belt + suspenders. | ✓ |
| Runtime startup guard only | Only enforced at server start. | |
| CI test only | A pytest test iterates registered tools. Ships broken schemas if CI is bypassed. | |

**User's choice:** Both runtime + CI

### Q4 — Phase 1 Settings schema includes Trino TLS fields?

| Option | Description | Selected |
|--------|-------------|----------|
| Yes — MCPTO_TRINO_VERIFY_SSL=true default, MCPTO_TRINO_CA_BUNDLE optional path (Recommended) | Settings model defines TLS fields in Phase 1; Phase 2 plumbs them through. | |
| Defer to Phase 2 entirely | Keep Phase 1 settings model minimal. Add TLS fields when Phase 2 lands. | ✓ |

**User's choice:** Defer to Phase 2 entirely
**Notes:** Deferral is explicitly documented in CONTEXT.md `<deferred>` so Phase 2 planning picks it up.

---

## CLAUDE.md DoD + CI matrix

### Q1 — CLAUDE.md expansion for Phase 1 — what lands there?

| Option | Description | Selected |
|--------|-------------|----------|
| Expand existing CLAUDE.md in place (Recommended) | Keep single CLAUDE.md at repo root. Add sections for coding rules, DoD, validation workflow, safe-execution boundaries. | |
| Split: CLAUDE.md (tech stack) + CONTRIBUTING.md (DoD/rules) | Keep CLAUDE.md focused on tech stack; put dev rules + DoD in CONTRIBUTING.md. | ✓ |

**User's choice:** Split CLAUDE.md + CONTRIBUTING.md

### Q2 — CI install-matrix: which test suites run on which cells?

| Option | Description | Selected |
|--------|-------------|----------|
| Lint/types once, unit+selftest on 9 cells, integration Linux-only (Recommended) | Split jobs: lint/mypy once; unit+smoke on 3 OS × 3 Python = 9 cells; integration job stub reserved for Phase 2+. | ✓ |
| Full matrix — everything on all 9 cells | Lint/types/unit/smoke all run on every cell. ~3× CI time. | |
| Minimum viable: unit+smoke on Linux only, matrix only on release tags | Fast PR feedback, late discovery of cross-OS regressions. | |

**User's choice:** Lint/types once, unit+smoke on 9 cells, integration Linux-only

### Q3 — CLI subcommand shape for the entry point?

| Option | Description | Selected |
|--------|-------------|----------|
| mcp-trino-optimizer serve --transport stdio\|http (Recommended) | Single 'serve' subcommand with a --transport flag. Typer-idiomatic. | ✓ |
| mcp-trino-optimizer (no subcommand) — flags only | Bare invocation starts the server. | |
| serve-stdio / serve-http as separate subcommands | Explicit per-transport subcommands. | |

**User's choice:** serve --transport stdio|http

### Q4 — stdout discipline — how far do we go?

| Option | Description | Selected |
|--------|-------------|----------|
| Belt + suspenders: structlog→stderr AND redirect sys.stdout at entrypoint (Recommended) | Three layers: structlog stderr-only, sys.stdout guard at entrypoint, CI stdout-clean test. | ✓ |
| Two layers: structlog→stderr + CI stdout-clean test | No sys.stdout redirection. | |

**User's choice:** Belt + suspenders

---

## Claude's Discretion

Areas the planner may decide without re-asking:
- Exact `stdout_guard` implementation approach (must honor D-12 behavior contract)
- `mcp_selftest` optional fields beyond the mandatory server version / transport / echo
- Pre-commit hook specifics (must include ruff format, ruff check, mypy at minimum)
- `.env.example` exact contents
- Logging output schema beyond the PLAT-06 mandatory keys
- `git_sha` injection mechanism (with `"unknown"` fallback for non-git installs)
- `pyproject.toml` tool config section specifics

## Deferred Ideas

- Hexagonal ports (`ports/`) — Phase 2
- Trino HTTP REST client + adapter — Phase 2
- Trino TLS settings (`MCPTO_TRINO_VERIFY_SSL`, `MCPTO_TRINO_CA_BUNDLE`) — Phase 2
- Basic + JWT auth for Trino — Phase 2
- Rule engine, plan parser, rewrite engine, comparison engine — later phases
- `docker-compose.yml` for Trino + Lakekeeper + MinIO + Postgres — Phase 9
- Release tagging / wheel publishing / PyPI — later phase
